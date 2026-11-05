"""Session-scoped image transport; storage belongs to the Session aggregate."""

import base64
import binascii
import hashlib
import json
import re
import threading
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .runs import _core

router = APIRouter()

_MAX_FILE_BYTES = 20 * 1024 * 1024
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._ -]+")
_IMAGE_MIME_TYPES = ("image/png", "image/jpeg", "image/webp", "image/gif")
_MANIFEST_LOCKS: dict[Path, threading.RLock] = {}
_MANIFEST_LOCKS_GUARD = threading.Lock()
_WINDOWS_RESERVED = frozenset(
    {"con", "prn", "aux", "nul", *(f"com{index}" for index in range(1, 10)),
     *(f"lpt{index}" for index in range(1, 10))}
)


def _manifest_lock(root: Path) -> threading.RLock:
    """Return the per-artifact-root lock protecting manifest read-modify-write."""
    key = root.resolve()
    with _MANIFEST_LOCKS_GUARD:
        return _MANIFEST_LOCKS.setdefault(key, threading.RLock())


class ArtifactUpload(BaseModel):
    """JSON upload contract for non-image Session artifacts."""

    data_base64: str = Field(min_length=1, max_length=_MAX_FILE_BYTES * 2)
    logical_name: str = Field(default="attachment", min_length=1, max_length=255)
    mime_type: str = Field(default="application/octet-stream", max_length=255)


@router.get("/api/capabilities/attachments")
def attachment_capabilities() -> dict[str, object]:
    """Publish the attachment limits used by both UI validation and storage."""
    from ..modules.attachment_module.store import (
        MAX_IMAGES_PER_RUN,
        MAX_IMAGES_TOTAL_BYTES,
        ImageAttachmentStore,
    )

    return {
        "artifact_max_bytes": _MAX_FILE_BYTES,
        "image_max_bytes": ImageAttachmentStore.MAX_BYTES,
        "max_images_per_run": MAX_IMAGES_PER_RUN,
        "max_images_total_bytes": MAX_IMAGES_TOTAL_BYTES,
        "image_mime_types": list(_IMAGE_MIME_TYPES),
        "max_image_pixels": ImageAttachmentStore.MAX_PIXELS,
        "max_image_side": 8000,
        "max_image_attachments": ImageAttachmentStore.MAX_ATTACHMENTS,
    }


def _store(request: Request, session_id: str):
    try:
        store = _core(request).sessions.get(session_id).attachments
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown session") from exc
    if store is None:
        raise HTTPException(status_code=409, detail="Session image storage is unavailable")
    return store


@router.post("/api/sessions/{session_id}/attachments/images")
async def upload_image(session_id: str, request: Request, filename: str = "image") -> dict:
    """Accept bounded raw image bytes without requiring a multipart parser."""
    store = _store(request, session_id)
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > store.MAX_BYTES:
            raise HTTPException(status_code=413, detail="Image upload exceeds byte limit")
        data.extend(chunk)
    try:
        metadata = store.put(bytes(data), filename)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {**metadata, "url": f"/api/sessions/{quote(session_id, safe='')}/attachments/images/{metadata['attachment_id']}"}


@router.get("/api/sessions/{session_id}/attachments/images/{attachment_id}")
def download_image(session_id: str, attachment_id: str, request: Request) -> FileResponse:
    """Serve an existing validated image only within its owning Session."""
    store = _store(request, session_id)
    try:
        metadata = store.get(attachment_id)
        path = store.path(attachment_id)
    except (KeyError, ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail="Unknown image attachment") from exc
    return FileResponse(path, media_type=metadata["media_type"], headers={
        "X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=31536000, immutable",
    })


def _artifact_root(request: Request, session_id: str, *, create: bool) -> Path:
    try:
        workspace = _core(request).workspaces.get(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown session") from exc
    if workspace.project_path is None:
        raise HTTPException(status_code=409, detail="Session has no project directory")
    root = workspace.project_path / "attachments"
    if root.is_symlink():
        raise HTTPException(status_code=422, detail="Attachments directory must not be a symlink")
    if create:
        root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_filename(value: str) -> str:
    name = Path(value).name.strip() or "attachment"
    name = _SAFE_NAME.sub("_", name).strip(". ")
    if not name:
        return "attachment"
    if name.split(".", 1)[0].casefold() in _WINDOWS_RESERVED:
        name = f"_{name}"
    return name[:160].strip(". ") or "attachment"


def _read_manifest(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


@router.post("/api/sessions/{session_id}/artifacts", status_code=201)
def upload_artifact(session_id: str, payload: ArtifactUpload, request: Request) -> dict:
    """Register a bounded user file for the Session memory/artifact tools."""
    root = _artifact_root(request, session_id, create=True)
    try:
        data = base64.b64decode(payload.data_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail="data_base64 is not valid base64") from exc
    if not data or len(data) > _MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="Artifact exceeds the 20 MiB upload limit")
    digest = hashlib.sha256(data).hexdigest()
    artifact_id = digest
    logical_name = _safe_filename(payload.logical_name)
    manifest = root / "manifest.json"
    with _manifest_lock(root):
        existing = _read_manifest(manifest)
        recorded = existing.get(artifact_id)
        if isinstance(recorded, dict) and (root / artifact_id / recorded.get("logical_name", "")).is_file():
            return {**recorded, "url": f"/api/sessions/{quote(session_id, safe='')}/artifacts/{artifact_id}"}
        directory = root / artifact_id
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / logical_name
        if not path.exists():
            path.write_bytes(data)
        metadata = {
            "artifact_id": artifact_id,
            "sha256": digest,
            "logical_name": logical_name,
            "mime_type": payload.mime_type or "application/octet-stream",
            "size": len(data),
            "relative_path": f"attachments/{artifact_id}/{logical_name}",
        }
        existing[artifact_id] = metadata
        manifest.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {**metadata, "url": f"/api/sessions/{quote(session_id, safe='')}/artifacts/{artifact_id}"}


@router.get("/api/sessions/{session_id}/artifacts/{artifact_id}")
def download_artifact(session_id: str, artifact_id: str, request: Request) -> FileResponse:
    """Download one user artifact by its content hash."""
    root = _artifact_root(request, session_id, create=False)
    if not re.fullmatch(r"[a-f0-9]{64}", artifact_id):
        raise HTTPException(status_code=404, detail="Unknown artifact")
    manifest = root / "manifest.json"
    with _manifest_lock(root):
        metadata = _read_manifest(manifest).get(artifact_id)
    path = root / artifact_id / metadata.get("logical_name", "") if isinstance(metadata, dict) else root / artifact_id
    if not isinstance(metadata, dict) or not path.is_file():
        raise HTTPException(status_code=404, detail="Unknown artifact")
    return FileResponse(path, media_type=metadata.get("mime_type", "application/octet-stream"),
                        filename=metadata.get("logical_name", artifact_id),
                        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=31536000, immutable"})
