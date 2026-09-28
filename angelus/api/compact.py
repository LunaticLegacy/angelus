"""Unified automatic/manual context compaction endpoints."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..core import AngelusCore

router = APIRouter()


class CompactRequest(BaseModel):
    agent: str = Field(default="coordinator", min_length=1, max_length=80)


class CompactStopRequest(BaseModel):
    reason: str = Field(default="user_requested", min_length=1, max_length=512)


def _core(request: Request) -> AngelusCore:
    core = getattr(request.app.state, "angelus_core", None)
    if not isinstance(core, AngelusCore):
        raise RuntimeError("AngelusCore is not installed on this application")
    return core


def _stage(stage: str, detail: str, kind: str = "progress", **extra: Any) -> str:
    payload = {"stage": stage, "detail": detail, "kind": kind, **extra}
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"


@router.post("/api/sessions/{session_id}/compact")
def compact_session(session_id: str, payload: CompactRequest, request: Request) -> StreamingResponse:
    """Run explicit compaction through the session's existing Agent handler."""
    core = _core(request)

    def generate():
        yield _stage("loading", "正在载入当前 session 上下文…")
        try:
            yield _stage("compacting", "正在生成摘要…")
            _control, agent = core.session_service.compact(session_id, payload.agent)
            linear = getattr(agent.context_handler, "linear", agent.context_handler)
            abstract = getattr(linear, "abstract", None)
            yield _stage(
                "done",
                "上下文压缩完成",
                "done",
                archived_messages=len(getattr(linear, "archive", [])),
                abstract_characters=len(getattr(abstract, "abstract_msg", "") or ""),
            )
        except Exception as exc:
            yield _stage("error", "上下文压缩未完成，原上下文保持不变", "error", error=str(exc))

    return StreamingResponse(generate(), media_type="application/x-ndjson")


@router.post("/api/sessions/{session_id}/compact/stop")
def stop_compaction(session_id: str, payload: CompactStopRequest, request: Request) -> dict[str, Any]:
    stopped = _core(request).session_service.stop_compaction(session_id, reason=payload.reason)
    if not stopped:
        raise HTTPException(status_code=409, detail="No compaction is running")
    return {"accepted": True, "session_id": session_id}


@router.post("/api/sessions/{session_id}/compact/force-stop")
def force_stop_compaction(session_id: str, payload: CompactStopRequest, request: Request) -> dict[str, Any]:
    stopped = _core(request).session_service.stop_compaction(session_id, force=True, reason=payload.reason)
    if not stopped:
        raise HTTPException(status_code=409, detail="No compaction is running")
    return {"accepted": True, "session_id": session_id}


__all__ = ["router", "compact_session"]
