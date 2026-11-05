"""HTTP projections for Session memory, user artifacts, and handoffs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

from ..core import AngelusCore
from .dependencies import get_core
from ..modules.session_memory_module.store import SessionMemoryError, SessionMemoryStore

router = APIRouter()


def _store(request: Request) -> SessionMemoryStore:
    core = get_core(request)
    return SessionMemoryStore(core.state_root,
                              lambda session_id: core.workspaces.get(session_id).project_path)


def _known(request: Request, session_id: str) -> None:
    core = request.app.state.angelus_core
    if not core.sessions.exists(session_id):
        raise HTTPException(status_code=404, detail="Unknown session")


@router.get("/api/sessions/{session_id}/memory/capabilities")
def memory_capabilities(session_id: str, request: Request) -> dict[str, object]:
    _known(request, session_id)
    return {
        "capabilities": {"search": True, "read": True, "artifacts": True, "handoffs": True},
        "current_session_implicit": True,
        "note": "Memory access is subject to the Session run profile and Agent tool permissions.",
    }


@router.get("/api/sessions/{session_id}/artifacts")
def list_artifacts(session_id: str, request: Request) -> dict[str, object]:
    _known(request, session_id)
    manifest = _store(request).snapshot(session_id)
    return {"session_id": session_id, "generation": manifest["generation"], "artifacts": manifest["artifacts"]}


@router.get("/api/sessions/{session_id}/handoffs")
def list_handoffs(session_id: str, request: Request) -> dict[str, object]:
    _known(request, session_id)
    manifest = _store(request).snapshot(session_id)
    return {"handoffs": [item for item in manifest["evidence"] if item.get("kind") == "handoff"]}


@router.get("/api/sessions/{session_id}/handoffs/{handoff_id}")
def get_handoff(session_id: str, handoff_id: str, request: Request) -> dict[str, object]:
    _known(request, session_id)
    try:
        return _store(request).read_handoff(session_id, handoff_id)
    except SessionMemoryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/sessions/{session_id}/handoffs", status_code=201)
def create_handoff(session_id: str, request: Request, payload: dict[str, Any] = Body(...)) -> dict[str, object]:
    _known(request, session_id)
    try:
        return _store(request).create_handoff(session_id, payload)
    except SessionMemoryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


__all__ = ["router"]
