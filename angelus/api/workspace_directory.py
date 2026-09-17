"""HTTP adapter for host operating-system directory selection."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..modules.platform_module import (
    SystemResourceManager,
    SystemResourceManagerError,
    SystemResourceManagerUnavailable,
)


router = APIRouter()
_resource_manager = SystemResourceManager()


@router.post("/api/workspace-directory/pick")
def pick_workspace_directory() -> dict[str, bool | str | None]:
    """Ask the system resource manager to select one absolute directory.

    The workbench is a loopback application, so the dialog belongs to the
    same desktop user that started Angelus. The browser and Tauri shell do not
    own or implement directory selection.
    """
    try:
        selected = _resource_manager.select_directory()
    except SystemResourceManagerUnavailable as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except SystemResourceManagerError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not selected:
        return {"cancelled": True, "path": None}
    return {"cancelled": False, "path": str(selected)}


__all__ = ["router"]
