"""Thin HTTP adapter for durable session/workspace registration."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import uuid

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..core import AngelusCore


router = APIRouter()


class CreateSessionRequest(BaseModel):
    """HTTP input for an empty logical Session and its workspace."""

    session_id: str | None = Field(default=None, min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    project_path: str = Field(min_length=1, max_length=16_384)


class DeleteSessionRequest(BaseModel):
    """Explicit confirmation for an irreversible session-data deletion."""

    confirmation: str = Field(min_length=1, max_length=80)


def _core(request: Request) -> AngelusCore:
    """Resolve the app-owned core without manufacturing application state."""
    core = getattr(request.app.state, "angelus_core", None)
    if not isinstance(core, AngelusCore):
        raise RuntimeError("AngelusCore is not installed on this application")
    return core


@router.get("/api/sessions")
def list_sessions(request: Request) -> dict[str, list[dict[str, Any]]]:
    """List durable workspace identities, not process-local execution state."""
    return {
        "sessions": [
            {
                "id": item.session_id,
                "name": item.name,
                "project_path": str(item.project_path) if item.project_path is not None else None,
                "state": _core(request).execution_service.status(item.session_id).state,
            }
            for item in _core(request).session_service.list()
        ]
    }


@router.post("/api/sessions", status_code=201)
def create_session(payload: CreateSessionRequest, request: Request) -> dict[str, Any]:
    """Create an empty session; Agent and graph configuration come afterwards."""
    try:
        workspace = _core(request).session_service.create(
            payload.session_id or f"session_{uuid.uuid4().hex[:12]}",
            payload.name,
            Path(payload.project_path),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "id": workspace.session_id,
        "name": workspace.name,
        "project_path": str(workspace.project_path),
        "state": "idle",
    }


@router.delete("/api/sessions/{session_id}")
def delete_session(session_id: str, payload: DeleteSessionRequest, request: Request) -> dict[str, str]:
    """Delete one confirmed Session after its active execution has stopped."""
    try:
        _core(request).session_service.delete(session_id, confirmation=payload.confirmation)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown session") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "deleted", "session_id": session_id}


@router.get("/api/sessions/{session_id}/messages")
def get_session_messages(
    session_id: str,
    request: Request,
    before: int | None = Query(default=None, ge=0),
    limit: int = Query(default=200, ge=1, le=200),
) -> dict[str, Any]:
    """Return the selected Session's persisted transcript page.

    ``agent`` remains an accepted client query parameter for compatibility;
    legacy transcripts predate per-Agent attribution and are returned as the
    aggregate conversation until the new conversation writer is introduced.
    """
    core = _core(request)
    if not core.sessions.exists(session_id):
        raise HTTPException(status_code=404, detail="Unknown session")
    return core.conversations.page(session_id, before=before, limit=limit)


__all__ = ["router"]
