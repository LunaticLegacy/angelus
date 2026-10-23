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


class CompactRequest(BaseModel):
    agent: str = Field(default="coordinator", min_length=1, max_length=80)


def _core(request: Request) -> AngelusCore:
    return get_core(request)


def _frame(stage: str, detail: str, kind: str = "progress", **extra: Any) -> str:
    return json.dumps({"stage": stage, "detail": detail, "kind": kind, **extra}, ensure_ascii=False) + "\n"


@router.post("/api/sessions/{session_id}/compact")
def compact_session(session_id: str, payload: CompactRequest, request: Request) -> StreamingResponse:
    """Run compaction through the live Session Agent and stream lifecycle frames."""
    core = _core(request)

    def generate():
        yield _frame("loading", "正在载入当前会话上下文…")
        yield _frame("compacting", "正在流式生成摘要…")
        frames: queue.Queue[dict[str, Any]] = queue.Queue()

        def on_event(event_type: str, _message: str, data: dict) -> None:
            if event_type == "context:compact_delta":
                delta = str(data.get("delta", ""))
                frames.put({"stage": "output", "kind": "delta", "delta": delta, "detail": delta})

        def run() -> None:
            try:
                agent = core.session_service.compact(session_id, payload.agent, on_event=on_event)
                linear = agent.context_handler.linear
                abstract = linear.abstract
                frames.put({"stage": "done", "detail": "上下文压缩完成", "kind": "done",
                            "archived_messages": len(linear.archive),
                            "abstract_characters": len(abstract.abstract_msg or "") if abstract is not None else 0})
            except Exception as exc:
                frames.put({"stage": "error", "detail": "上下文压缩失败，原上下文保持不变", "kind": "error", "error": str(exc)})
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
