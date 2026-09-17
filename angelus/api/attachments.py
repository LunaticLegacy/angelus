"""Session-scoped image transport; storage belongs to the Session aggregate."""

from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from .runs import _core

router = APIRouter()


def _store(request: Request, session_id: str):
    try:
        return _core(request).sessions.get(session_id).attachments
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown session") from exc


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
