"""Session-owned context compaction endpoint."""

from __future__ import annotations

import json
import queue
import threading
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .dependencies import get_core

if TYPE_CHECKING:
    from ..core import AngelusCore

router = APIRouter()

# Compaction lifecycle stages forwarded to the client.  Issue 7 removed the
# per-chunk ``context:compact_delta`` event from the durable trace, so the
# ledger keeps exactly these four stages.  This stream is a different consumer:
# it exists to show the summary while it is being written, so the route taps the
# compaction model call itself (``SessionService.compact(on_delta=...)``) and
# turns every chunk into a ``delta`` frame without touching the transcript.
_STAGE_FRAMES = {
    "context:compact_started": "started",
    "context:compact_success": "success",
    "context:compact_failed": "failed",
    "context:compact_skipped": "skipped",
}

# The compaction model answers inside this envelope; ``parse_compacted_abstract``
# strips it after the fact, so a live view must strip it while streaming.
_OPEN_TAG = "<context_abstract>"
_CLOSE_TAG = "</context_abstract>"
# A model that ignores the requested envelope still has to reach the browser:
# once this much text arrived without an opening tag, stream it verbatim.
_UNTAGGED_GRACE = 240


class CompactRequest(BaseModel):
    agent: str = Field(default="coordinator", min_length=1, max_length=80)


class _AbstractText:
    """Turn the streamed compaction response into clean, incremental text.

    ``feed`` returns only the newly displayable part of the summary: the
    ``<context_abstract>`` envelope is dropped, and a trailing fragment that
    could still become ``</context_abstract>`` is held back until the next chunk
    either completes it (then it is dropped) or contradicts it (then it is
    released).  Concatenating every delta therefore yields the abstract body
    with no tag debris, even though the body arrives in arbitrary chunks.
    """

    def __init__(self) -> None:
        """Start before the envelope has been seen."""
        self._raw = ""
        self._body_start: int | None = None
        self._sent = 0

    @property
    def characters(self) -> int:
        """Number of characters already returned by :meth:`feed`."""
        return self._sent

    def feed(self, chunk: str) -> str:
        """Return the text made displayable by ``chunk`` (empty when nothing yet)."""
        self._raw += chunk
        if self._body_start is None:
            opened = self._raw.find(_OPEN_TAG)
            if opened >= 0:
                self._body_start = opened + len(_OPEN_TAG)
            elif len(self._raw) > _UNTAGGED_GRACE:
                # No envelope at all: the model answered in prose, show it as is.
                self._body_start = 0
            else:
                return ""
        # The prompt puts the body on the line after the opening tag.  Skip
        # that whitespace by moving ``_body_start`` instead of trimming each
        # slice: ``_sent`` is an offset into this same body, so a per-call
        # lstrip would shift every later delta.
        while (
            self._body_start < len(self._raw)
            and self._raw[self._body_start].isspace()
        ):
            self._body_start += 1
        body = self._raw[self._body_start:]
        closed = body.find(_CLOSE_TAG)
        if closed >= 0:
            body = body[:closed]
        else:
            held = min(len(_CLOSE_TAG) - 1, len(body))
            while held > 0 and not body.endswith(_CLOSE_TAG[:held]):
                held -= 1
            if held:
                body = body[:-held]
        if len(body) <= self._sent:
            return ""
        delta = body[self._sent:]
        self._sent = len(body)
        return delta


def _core(request: Request) -> AngelusCore:
    return get_core(request)


def _frame(stage: str, detail: str, kind: str = "progress", **extra: Any) -> str:
    return json.dumps({"stage": stage, "detail": detail, "kind": kind, **extra}, ensure_ascii=False) + "\n"


@router.post("/api/sessions/{session_id}/compact")
def compact_session(session_id: str, payload: CompactRequest, request: Request) -> StreamingResponse:
    """Run compaction through the live Session Agent and stream delta frames."""
    core = _core(request)

    def generate():
        yield _frame("loading", "正在载入当前会话上下文…")
        frames: queue.Queue[dict[str, object]] = queue.Queue()
        summary: dict[str, object] = {}
        # A compaction that found nothing active still terminates with the
        # friendly ``done`` frame below; remember it so that frame explains
        # itself instead of claiming a real compaction happened.
        progress: dict[str, bool] = {"skipped": False}
        live = _AbstractText()

        def on_event(event_type: str, message: str, data: dict) -> None:
            stage = _STAGE_FRAMES.get(event_type)
            if stage is None:
                return
            # ``source_timeline`` is a large list; the terminal frame only needs
            # aggregate sizes, so keep the transport payload small.
            detail_data = {k: v for k, v in data.items() if k != "source_timeline"}
            if stage == "skipped":
                progress["skipped"] = True
            if stage == "success":
                summary["archived_messages"] = detail_data.get("archived_messages")
                summary["abstract_characters"] = detail_data.get("abstract_characters")
                summary["abstract"] = detail_data.get("abstract")
            frames.put({"stage": stage, "kind": "stage", "detail": str(message), "data": detail_data})

        def on_delta(chunk: str) -> None:
            text = live.feed(chunk)
            if text:
                frames.put({
                    "stage": "delta",
                    "kind": "delta",
                    "detail": f"正在生成摘要…（已 {live.characters} 字符）",
                    "delta": text,
                    "characters": live.characters,
                })

        def run() -> None:
            try:
                agent = core.session_service.compact(
                    session_id, payload.agent, on_event=on_event, on_delta=on_delta
                )
                linear = agent.context_handler.linear
                abstract = linear.abstract
                abstract_text = (abstract.abstract or "") if abstract else ""
                # The handler's parsed abstract is authoritative; the success
                # event carries the same body for older clients.
                full_text = str(summary.get("abstract") or abstract_text or "")
                skipped = progress["skipped"]
                frames.put({
                    "stage": "done",
                    "kind": "done",
                    "detail": (
                        "无需压缩：当前没有待压缩的活动消息，上下文已全部归档"
                        if skipped
                        else "上下文压缩完成"
                    ),
                    "skipped": skipped,
                    "archived_messages": (
                        None if skipped
                        else summary.get("archived_messages", len(linear.archive))
                    ),
                    "abstract_characters": summary.get("abstract_characters", len(abstract_text)),
                    # Full summary: the browser shows the whole body, never a
                    # truncated preview that hides what was actually kept.
                    "abstract": full_text,
                })
            except Exception as exc:
                frames.put({
                    "stage": "error",
                    "kind": "error",
                    "detail": "上下文压缩失败，原上下文保持不变",
                    "error": str(exc),
                })
            finally:
                frames.put({"stage": "__end__"})

        threading.Thread(target=run, name="angelus-compaction", daemon=True).start()
        while True:
            frame = frames.get()
            if frame.get("stage") == "__end__":
                break
            yield json.dumps(frame, ensure_ascii=False) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")


__all__ = ["router", "compact_session"]
