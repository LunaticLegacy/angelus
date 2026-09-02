"""HTTP adapters for the rebuilt connector and future-run configuration APIs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..core import AngelusCore
from ..modules.application_module import UnknownSession
from ..modules.tool_module import ToolCatalog
from ..version import RuntimeVersions, runtime_versions


router = APIRouter()


class ConnectorPayload(BaseModel):
    """Public connector metadata plus an optional write-only API key.

    Attributes:
        name: Human-readable global connector label, unique ID is server-made.
        provider: LLMFetcher provider kind; capability discovery is separate.
        model: Provider model identifier to prefill future run profiles.
        api_url: Optional provider base URL; no connection is attempted here.
        api_key: Write-only credential.  Blank on update means retain existing.
    """

    name: str = Field(min_length=1, max_length=80)
    provider: str = Field(min_length=1, max_length=80)
    model: str = Field(default="", max_length=300)
    api_url: str = Field(default="", max_length=4_000)
    api_key: str = Field(default="", max_length=20_000)


class ProfilePayload(BaseModel):
    """A complete profile document for global defaults or one Session override.

    Attributes:
        settings: JSON object containing only supported future-run fields.
            It replaces one complete profile document, never live execution.
    """

    settings: dict[str, Any]


def _core(request: Request) -> AngelusCore:
    """Resolve host-owned core without creating a second settings store.

    Raises:
        RuntimeError: If this router was installed without AngelusCore state.
    """
    core = getattr(request.app.state, "angelus_core", None)
    if not isinstance(core, AngelusCore):
        raise RuntimeError("AngelusCore is not installed on this application")
    return core


@router.get("/api/tool-registry")
def tool_registry(request: Request) -> ToolCatalog:
    """Return categories and tools actually registered by backend providers.

    Args:
        request: Incoming request carrying the application composition root.

    Returns:
        Typed non-secret catalog used to render tool authorization controls.
    """
    return _core(request).tool_registry.catalog()


@router.get("/api/version")
def version() -> RuntimeVersions:
    """Return independent Angelus and llmfetcher runtime versions.

    Returns:
        Immutable version metadata suitable for diagnostics and UI display.
    """
    return runtime_versions()


@router.get("/api/connectors")
def list_connectors(request: Request) -> dict[str, list[dict[str, Any]]]:
    """List global connectors without serializing credentials in HTTP output."""
    return {"connectors": list(_core(request).settings_service.list_connectors())}


@router.post("/api/connectors", status_code=201)
def create_connector(payload: ConnectorPayload, request: Request) -> dict[str, Any]:
    """Create one globally reusable connector and return its public projection."""
    try:
        return _core(request).settings_service.create_connector(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.put("/api/connectors/{connector_id}")
def replace_connector(connector_id: str, payload: ConnectorPayload, request: Request) -> dict[str, Any]:
    """Replace metadata, retaining a secret when the supplied API key is blank."""
    try:
        return _core(request).settings_service.replace_connector(connector_id, payload.model_dump())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown connector") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/api/connectors/{connector_id}", status_code=204)
def delete_connector(connector_id: str, request: Request) -> None:
    """Delete connector only when no effective run profile references it.

    A 409 response is intentional: callers must first change every retaining
    global/session profile, rather than leaving a broken future-run reference.
    """
    try:
        _core(request).settings_service.delete_connector(connector_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown connector") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/settings/run-profile")
def get_global_profile(request: Request) -> dict[str, Any]:
    """Return global defaults for future Session attempts, not a live config."""
    return _core(request).settings_service.global_profile()


@router.put("/api/settings/run-profile")
def put_global_profile(payload: ProfilePayload, request: Request) -> dict[str, Any]:
    """Validate then atomically replace global defaults for later attempts."""
    try:
        return _core(request).settings_service.replace_global_profile(payload.settings)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/sessions/{session_id}/run-profile")
def get_session_profile(session_id: str, request: Request) -> dict[str, Any]:
    """Return one Session's effective future-attempt profile and inheritance."""
    try:
        return _core(request).settings_service.session_profile(session_id)
    except UnknownSession as exc:
        raise HTTPException(status_code=404, detail="Unknown session") from exc


@router.put("/api/sessions/{session_id}/run-profile")
def put_session_profile(session_id: str, payload: ProfilePayload, request: Request) -> dict[str, Any]:
    """Validate then atomically replace one Session's future-run override."""
    try:
        return _core(request).settings_service.replace_session_profile(session_id, payload.settings)
    except UnknownSession as exc:
        raise HTTPException(status_code=404, detail="Unknown session") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/api/sessions/{session_id}/run-profile")
def delete_session_profile(session_id: str, request: Request) -> dict[str, Any]:
    """Discard a Session override and return its now-inherited effective profile."""
    try:
        return _core(request).settings_service.clear_session_profile(session_id)
    except UnknownSession as exc:
        raise HTTPException(status_code=404, detail="Unknown session") from exc


__all__ = ["router"]
