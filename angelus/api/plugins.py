"""HTTP adapters for controlled Angelus plugin lifecycle and settings."""

from __future__ import annotations

from collections.abc import Mapping

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..core import AngelusCore


router = APIRouter()


class PluginConfirmation(BaseModel):
    """Explicit browser confirmation required for executable plugin actions.

    Attributes:
        confirm: Must be true; prevents accidental lifecycle clicks from
            executing package code.
        grant_permissions: Explicit approval for newly requested permissions.
    """

    confirm: bool = False
    grant_permissions: bool = False


def _core(request: Request) -> AngelusCore:
    """Resolve the host's only plugin manager ownership graph.

    Args:
        request: Incoming FastAPI request with application state.

    Returns:
        Installed Angelus composition root.

    Raises:
        RuntimeError: If the host omitted the Angelus composition root.
    """
    core = getattr(request.app.state, "angelus_core", None)
    if not isinstance(core, AngelusCore):
        raise RuntimeError("AngelusCore is not installed on this application")
    return core


@router.get("/api/plugins")
def active_plugins(request: Request) -> dict[str, object]:
    """Return only currently active browser-loadable plugin packages.

    Args:
        request: Incoming request carrying the composition root.

    Returns:
        Public active plugin status objects.
    """
    return {"plugins": list(_core(request).plugin_manager.active())}


@router.get("/api/plugins/status")
def plugin_status(request: Request) -> dict[str, object]:
    """Return discovered, registered, inactive, and active plugin status.

    Args:
        request: Incoming request carrying the composition root.

    Returns:
        Public non-secret plugin lifecycle projections.
    """
    return {"plugins": list(_core(request).plugin_manager.statuses())}


@router.post("/api/plugins/rescan")
def rescan_plugins(request: Request) -> dict[str, object]:
    """Refresh declarative package discovery without executing plugin code.

    Args:
        request: Incoming request carrying the composition root.

    Returns:
        Count of package directories inspected by the safe discovery pass.
    """
    discovered = _core(request).plugin_manager.rescan()
    return {"discovered": len(discovered)}


@router.post("/api/plugins/discovered/{name}/register")
def register_plugin(name: str, payload: PluginConfirmation, request: Request) -> dict[str, object]:
    """Register one validated discovered package without importing it.

    Args:
        name: Manifest name selected from current discovery results.
        payload: Required explicit confirmation body.
        request: Incoming request carrying the composition root.

    Returns:
        Public registered plugin status.
    """
    if not payload.confirm:
        raise HTTPException(status_code=422, detail="plugin registration requires confirm=true")
    try:
        return {"plugin": _core(request).plugin_manager.register(name)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="unknown valid discovered plugin") from exc


@router.post("/api/plugins/{plugin_id}/load")
def load_plugin(plugin_id: str, payload: PluginConfirmation, request: Request) -> dict[str, object]:
    """Load one registered plugin after confirmation and permission approval.

    Args:
        plugin_id: Durable registered plugin identity.
        payload: Explicit code-execution and permission confirmation.
        request: Incoming request carrying the composition root.

    Returns:
        Active public plugin status.
    """
    if not payload.confirm:
        raise HTTPException(status_code=422, detail="plugin load requires confirm=true")
    try:
        return {"plugin": _core(request).plugin_manager.load(plugin_id, grant_permissions=payload.grant_permissions)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="unknown plugin") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/plugins/{plugin_id}/unload")
def unload_plugin(plugin_id: str, payload: PluginConfirmation, request: Request) -> dict[str, object]:
    """Unload one plugin while retaining its package, grants, and settings.

    Args:
        plugin_id: Durable registered plugin identity.
        payload: Explicit unload confirmation.
        request: Incoming request carrying the composition root.

    Returns:
        Inactive public plugin status.
    """
    if not payload.confirm:
        raise HTTPException(status_code=422, detail="plugin unload requires confirm=true")
    try:
        return {"plugin": _core(request).plugin_manager.unload(plugin_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="unknown plugin") from exc


@router.get("/api/plugins/{plugin_id}/settings")
def get_plugin_settings(plugin_id: str, request: Request) -> dict[str, object]:
    """Read typed non-secret settings and schema for one plugin.

    Args:
        plugin_id: Durable registered plugin identity.
        request: Incoming request carrying the composition root.

    Returns:
        Persisted settings and UI schema.
    """
    try:
        return _core(request).plugin_manager.settings(plugin_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="plugin settings are unavailable") from exc


@router.put("/api/plugins/{plugin_id}/settings")
def put_plugin_settings(plugin_id: str, request: Request, values: object = Body(...)) -> dict[str, object]:
    """Validate and persist one plugin's non-secret scalar settings.

    Args:
        plugin_id: Durable registered plugin identity.
        values: JSON object constrained by the plugin manifest's schema.
        request: Incoming request carrying the composition root.

    Returns:
        Stored settings projection.
    """
    if not isinstance(values, Mapping):
        raise HTTPException(status_code=422, detail="plugin settings must be an object")
    try:
        return _core(request).plugin_manager.replace_settings(plugin_id, values)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="plugin settings are unavailable") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/plugins/{name}/static/{asset:path}", include_in_schema=False)
def plugin_static(name: str, asset: str, request: Request) -> FileResponse:
    """Serve one active plugin's manifest-whitelisted static asset.

    Args:
        name: Active manifest name.
        asset: Requested package-relative static asset.
        request: Incoming request carrying the composition root.

    Returns:
        Whitelisted static file response.

    Raises:
        HTTPException: If the plugin is inactive or the asset is unauthorized.
    """
    path = _core(request).plugin_manager.static_asset(name, asset)
    if path is None:
        raise HTTPException(status_code=404, detail="plugin asset not found")
    return FileResponse(path)


__all__ = ["router"]
