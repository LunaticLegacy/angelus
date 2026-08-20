"""Manual context compaction with staged progress events.

Compaction normally happens automatically when a session's retained context
grows past its threshold.  ``/compact`` exposes the same ``ContextHandlerLinear``
compactor on demand, guarded against running sessions, and streams each real
stage back to the browser so a multi-second model call never looks frozen.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from llmfetcher.context_handlers.linear import ContextHandlerLinear
from llmfetcher.llm_fetcher import LLMBackendConfig, LLMFetcher

from ..classes import CompactRequest
from ..connectors import _resolve_connector_key
from ..history import _agent_context_stats
from ..provider_adapters import resolve_provider
from ..storage import _get_session, _safe_id, _session_path

router = APIRouter()


def _stage(
    stage: str,
    detail: str,
    kind: str = "progress",
    *,
    error: str | None = None,
    raw_content: str | None = None,
) -> str:
    """Serialize one compaction progress record as an NDJSON line.

    Args:
        stage: Stable progress stage identifier consumed by the browser.
        detail: Human-readable status text safe to render directly.
        kind: Event category: ``progress``, ``done``, or ``error``.
        error: Optional diagnostic reason for a failed compaction attempt.
        raw_content: Optional unparseable model ``content`` returned by the
            compactor. It is streamed to the current browser request only and
            is never persisted with the session context.

    Returns:
        One newline-delimited JSON event for the streaming response.
    """
    payload: dict[str, str] = {"stage": stage, "detail": detail, "kind": kind}
    if error:
        payload["error"] = error
    if raw_content:
        payload["raw_content"] = raw_content
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ) + "\n"


def _build_compactor_fetcher(config: Any) -> LLMFetcher:
    """Create a throwaway LLM fetcher for the manual compaction call.

    The compactor is a separate, bounded model request with its own backend;
    credentials are resolved server-side from the browser's run config and
    never written to the session directory.
    """
    provider, api_url = resolve_provider(config.provider, config.api_url)
    backend = LLMBackendConfig(
        name="browser",
        provider=provider,
        model=config.model.strip(),
        api_key=config.api_key,
        api_url=api_url or None,
        timeout=120,
        max_retries=config.max_retries,
    )
    return LLMFetcher([backend])


@router.post("/api/sessions/{session_id}/compact")
def compact_session(session_id: str, request: CompactRequest) -> StreamingResponse:
    """Compress one Agent's linear context into a single summary abstract.

    Args:
        session_id: Browser-visible session identity (single-workspace mode
            uses the session id as its own workspace).
        request: Target agent name and the browser's current run config used
            to build the compactor.

    Returns:
        An NDJSON stream of progress stages; the final record carries
        ``kind: "done"`` (success) or ``kind: "error"`` (failure with the
        context left untouched). A failed model parse also carries a
        transient ``error`` reason and ``raw_content`` field for the browser
        to inspect; neither is persisted in session state.

    Raises:
        HTTPException: 409 when the session has an active run (compaction
            would race the run's own context writes), or 422 when no model
            is configured.
    """
    session_id = _safe_id(session_id, "session")
    agent_name = _safe_id(request.agent or "coordinator", "agent")
    config = _resolve_connector_key(request.config)
    if not config.model.strip():
        raise HTTPException(status_code=422, detail="Model is required")
    session = _get_session(session_id, session_id)
    with session.lock:
        if session.active and not session.active.done.is_set():
            raise HTTPException(
                status_code=409,
                detail="Cannot compact while a run is active in this session",
            )

    context_path = _session_path(session_id, session_id) / "contexts" / f"{agent_name}.json"

    def generate() -> Any:
        fetcher = _build_compactor_fetcher(config)
        handler = ContextHandlerLinear(
            compacting_llmfetcher_handler=fetcher,
            max_context_threshold=config.max_context_threshold,
        )
        if not context_path.exists() or not handler.load(context_path):
            yield _stage("error", "无可压缩的上下文（未找到或无法读取会话上下文）", "error")
            return
        if not handler.messages:
            if handler.abstract is not None:
                yield _stage("done", "无需压缩：上下文已是压缩后的摘要", "done")
            else:
                yield _stage("done", "无需压缩：当前没有待压缩的消息", "done")
            return
        before = _agent_context_stats(session_id, agent_name)
        yield _stage(
            "loading",
            f"已载入 {before.get('messages', 0)} 条消息，正在调用模型生成摘要…",
            "progress",
        )
        try:
            compacted = handler.compact()
        except Exception as exc:  # pragma: no cover - defensive
            yield _stage(
                "error",
                "压缩模型请求失败，上下文保持原样",
                "error",
                error=handler.last_compaction_error or str(exc),
            )
            return
        if not compacted:
            yield _stage(
                "error",
                "压缩失败，上下文保持原样",
                "error",
                error=handler.last_compaction_error,
                raw_content=handler.last_compaction_raw,
            )
            return
        yield _stage("saving", "摘要已生成，正在保存…", "progress")
        if not handler.save(context_path):
            yield _stage("error", "摘要已生成但保存失败，上下文保持原样", "error")
            return
        after = _agent_context_stats(session_id, agent_name)
        detail = (
            f"完成：{before.get('messages', 0)} 条消息 → 1 条摘要"
            f"（保留 {after.get('abstract_characters', 0)} 字符）"
        )
        yield _stage("done", detail, "done")

    return StreamingResponse(generate(), media_type="application/x-ndjson")


__all__ = ["compact_session", "router"]
