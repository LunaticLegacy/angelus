"""Thin HTTP adapter for durable session/workspace registration."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any
import uuid

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..modules.console_module import ConsoleDomainError
from .dependencies import get_core


if TYPE_CHECKING:
    from ..core import AngelusCore


router = APIRouter()


def _session_status(snapshot: Any) -> str:
    state = snapshot.state.value if hasattr(snapshot.state, "value") else str(snapshot.state)
    return {"completed": "done", "failed": "error", "interrupted": "error"}.get(state, state)


class CreateSessionRequest(BaseModel):
    """HTTP input for an empty logical Session and its workspace."""

    session_id: str | None = Field(default=None, min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    project_path: str | None = Field(default=None, max_length=16_384)


class DeleteSessionRequest(BaseModel):
    """Explicit confirmation for an irreversible session-data deletion."""

    confirmation: str = Field(min_length=1, max_length=80)


class RenameSessionRequest(BaseModel):
    """HTTP input for changing one Session's display name only."""

    name: str = Field(min_length=1, max_length=200)


def _core(request: Request) -> AngelusCore:
    """Resolve the app-owned core without manufacturing application state."""
    return get_core(request)


def _open_directory(path: Path) -> None:
    """Ask the host desktop to open an existing directory.

    The desktop release serves the UI from a local webview, while this API is
    owned by the packaged backend process.  Returning a path is not enough to
    open a native file manager, so perform the platform operation here without
    invoking a shell or interpolating user-controlled text into a command.
    """
    if not path.is_dir():
        raise OSError(f"Directory does not exist: {path}")
    if sys.platform == "win32":
        os.startfile(str(path))  # type: ignore[attr-defined]
        return
    command = "open" if sys.platform == "darwin" else "xdg-open"
    executable = shutil.which(command)
    if executable is None:
        raise OSError(f"Desktop opener is unavailable: {command}")
    subprocess.Popen(
        [executable, str(path)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


@router.get("/api/sessions")
def list_sessions(request: Request) -> dict[str, list[dict[str, Any]]]:
    """List durable workspace identities, not process-local execution state."""
    core = _core(request)
    return {
        "sessions": [
            {
                "id": item.session_id,
                "name": item.name,
                "project_path": str(item.project_path) if item.project_path is not None else None,
                "status": _session_status(core.execution_service.status(item.session_id)) if core.sessions.exists(item.session_id) else "idle",
            }
            for item in core.session_service.list()
        ]
    }


@router.get("/api/workspaces")
def list_workspaces(request: Request) -> dict[str, list[dict[str, Any]]]:
    """Compatibility alias during the session/workspace naming migration."""
    return {
        "workspaces": [
            {"id": item.session_id, "name": item.name, "project_path": str(item.project_path)}
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
            Path(payload.project_path) if payload.project_path else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "id": workspace.session_id,
        "name": workspace.name,
        "project_path": str(workspace.project_path) if workspace.project_path else None,
        "status": "idle",
    }


@router.post("/api/workspaces", status_code=201)
def create_workspace(payload: CreateSessionRequest, request: Request) -> dict[str, Any]:
    """Compatibility alias for clients that still call a workspace a workspace."""
    return create_session(payload, request)


@router.post("/api/sessions/{session_id}/open-folder")
def open_session_folder(session_id: str, request: Request) -> dict[str, str]:
    """Open the session project directory in the host file manager."""
    try:
        workspace = _core(request).workspaces.get(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown session") from exc
    path = Path(workspace.project_path)
    try:
        _open_directory(path)
    except OSError as exc:
        raise HTTPException(status_code=503, detail=f"无法打开会话目录：{exc}") from exc
    return {"path": str(path)}


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


@router.patch("/api/sessions/{session_id}")
def rename_session(session_id: str, payload: RenameSessionRequest, request: Request) -> dict[str, str]:
    """Rename one Session without changing its state or execution history."""
    try:
        workspace = _core(request).workspaces.rename(session_id, payload.name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown session") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"id": workspace.session_id, "name": workspace.name}


@router.get("/api/sessions/{session_id}/messages")
def get_session_messages(
    session_id: str,
    request: Request,
    before: int | None = Query(default=None, ge=0),
    limit: int = Query(default=200, ge=1, le=200),
    agent: str | None = Query(default=None, max_length=64),
) -> dict[str, Any]:
    """Return one Agent's durable context as a chronological chat page.

    Args:
        session_id: Stable Session identity whose transcript is requested.
        request: Incoming request carrying the application composition root.
        before: Exclusive older-than context timeline cursor.
        limit: Maximum number of context entries to return.
        agent: Optional Agent identity; ``all`` resolves to coordinator.

    Returns:
        Persisted context entries formatted for the chat view and a cursor for
        the next older page.

    Raises:
        HTTPException: If the Session or Agent does not exist, or its durable
            context cannot be read.
    """
    core = _core(request)
    if not core.sessions.exists(session_id):
        raise HTTPException(status_code=404, detail="Unknown session")
    try:
        return core.console_service.messages(session_id, agent, before, limit)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown session") from exc
    except ConsoleDomainError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


__all__ = ["router"]
