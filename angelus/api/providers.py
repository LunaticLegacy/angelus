"""HTTP adapter for read-only provider capability discovery."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Request

from .dependencies import get_core

if TYPE_CHECKING:
    from ..core import AngelusCore


router = APIRouter()


def _core(request: Request) -> AngelusCore:
    """Resolve the application-owned core and its provider catalog."""
    return get_core(request)


@router.get("/api/providers")
def list_providers(request: Request) -> dict[str, list[str]]:
    """Return providers available from the installed LLMFetcher handlers."""
    return {"providers": list(_core(request).providers.list())}


__all__ = ["router"]
