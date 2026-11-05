"""HTTP CRUD projection for Session and Project notes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

from ..core import AngelusCore
from ..modules.note_module import NoteError, NoteStore

router = APIRouter()


def _store(request: Request, session_id: str) -> NoteStore:
    core = request.app.state.angelus_core
    if not isinstance(core, AngelusCore) or not core.sessions.exists(session_id):
        raise HTTPException(status_code=404, detail="Unknown session")
    workspace = core.workspaces.get(session_id)
    return NoteStore(workspace.state_path, NoteStore.project_root(core.state_root, workspace.project_path))


def _payload(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="note payload must be an object")
    return payload


@router.get("/api/sessions/{session_id}/notes")
def list_notes(session_id: str, request: Request, scope: str = "session", query: str = "", include_inactive: bool = False) -> dict[str, object]:
    try:
        store = _store(request, session_id)
        notes = store.search(scope, query) if query.strip() else store.list(scope, include_inactive=include_inactive)
        return {"session_id": session_id, "scope": scope, "notes": [note.as_dict() for note in notes]}
    except NoteError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/sessions/{session_id}/notes", status_code=201)
def create_note(session_id: str, request: Request, payload: object = Body(...)) -> dict[str, object]:
    value = _payload(payload)
    try:
        note = _store(request, session_id).create(value.get("scope", "session"), value.get("title"), value.get("content"), value.get("tags", []))
        return note.as_dict()
    except NoteError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/api/sessions/{session_id}/notes/{scope}/{note_id}")
def update_note(session_id: str, scope: str, note_id: str, request: Request, payload: object = Body(...)) -> dict[str, object]:
    value = _payload(payload)
    try:
        note = _store(request, session_id).update(scope, note_id, title=value.get("title"), content=value.get("content"), tags=value.get("tags"), status=value.get("status"), revision=value.get("revision"))
        return note.as_dict()
    except NoteError as exc:
        status = 409 if "conflict" in str(exc) else 422
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.delete("/api/sessions/{session_id}/notes/{scope}/{note_id}")
def delete_note(session_id: str, scope: str, note_id: str, request: Request, revision: int | None = None) -> dict[str, object]:
    try:
        return _store(request, session_id).delete(scope, note_id, revision).as_dict()
    except NoteError as exc:
        status = 409 if "conflict" in str(exc) else 422
        raise HTTPException(status_code=status, detail=str(exc)) from exc

