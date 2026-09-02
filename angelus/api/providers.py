"""HTTP adapter for read-only provider capability discovery."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..core import AngelusCore


router = APIRouter()


def _core(request: Request) -> AngelusCore:
    """Resolve the application-owned core and its provider catalog."""
    core = getattr(request.app.state, "angelus_core", None)
    if not isinstance(core, AngelusCore):
        raise RuntimeError("AngelusCore is not installed on this application")
    return core


@router.get("/api/providers")
def list_providers(request: Request) -> dict[str, list[str]]:
    """Return providers available from the installed LLMFetcher handlers."""
    return {"providers": list(_core(request).providers.list())}


__all__ = ["router"]
