"""HTTP adapters for phase-one External Agent Hub configuration and inspection."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from fastapi import APIRouter, Body, HTTPException, Request

from ..core import AngelusCore
from ..modules.external_agent_hub_module import ExternalAgentAdapterFailure, ExternalAgentCapability, ExternalAgentDefinition, ExternalAgentHealth, ExternalAgentSession


router = APIRouter()


@dataclass(frozen=True)
class ExternalAgentInput:
    """Validated HTTP body fields for a complete external Agent definition.

    Attributes:
        id: Stable local external Agent identifier.
        title: User-facing Agent title.
        adapter_kind: Selected protocol adapter kind.
        endpoint: Non-secret endpoint or local runtime address.
        connector_id: Optional ConnectorStore reference; never a secret itself.
        enabled: Whether future execution may select this definition.
        description: Optional public description of the external Agent role.
    """

    id: str
    title: str
    adapter_kind: str
    endpoint: str = ""
    connector_id: str = ""
    enabled: bool = True
    description: str = ""


def _core(request: Request) -> AngelusCore:
    """Resolve the application composition root from FastAPI state.

    Args:
        request: Incoming request carrying application state.

    Returns:
        Installed Angelus composition root.

    Raises:
        RuntimeError: If no Angelus composition root is installed.
    """
    core = getattr(request.app.state, "angelus_core", None)
    if not isinstance(core, AngelusCore):
        raise RuntimeError("AngelusCore is not installed on this application")
    return core


@router.get("/api/external-agents")
def list_external_agents(request: Request) -> dict[str, object]:
    """List all durable external Agent definitions.

    Args:
        request: Incoming request carrying the composition root.

    Returns:
        Public, credential-free external Agent definitions.
    """
    return {"agents": [_definition(item) for item in _core(request).external_agent_hub.list()]}


@router.get("/api/external-agents/{agent_id}")
def get_external_agent(agent_id: str, request: Request) -> dict[str, object]:
    """Read one durable external Agent definition.

    Args:
        agent_id: Stable external Agent identifier.
        request: Incoming request carrying the composition root.

    Returns:
        Public, credential-free external Agent definition.

    Raises:
        HTTPException: If the requested Agent is absent.
    """
    try:
        return {"agent": _definition(_core(request).external_agent_hub.get(agent_id))}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="external Agent not found") from exc
    except ExternalAgentAdapterFailure as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/api/external-agents", status_code=201)
def create_external_agent(request: Request, payload: object = Body(...)) -> dict[str, object]:
    """Create one external Agent definition without contacting it.

    Args:
        request: Incoming request carrying the composition root.
        payload: Complete JSON definition with no credential values.

    Returns:
        Newly persisted public definition.

    Raises:
        HTTPException: If the body is invalid or the identifier exists.
    """
    try:
        created = _core(request).external_agent_hub.create(_parse_input(payload))
        return {"agent": _definition(created)}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.put("/api/external-agents/{agent_id}")
def replace_external_agent(agent_id: str, request: Request, payload: object = Body(...)) -> dict[str, object]:
    """Replace one external Agent definition without contacting it.

    Args:
        agent_id: Existing external Agent identifier.
        request: Incoming request carrying the composition root.
        payload: Complete JSON replacement with no credential values.

    Returns:
        Persisted public definition.

    Raises:
        HTTPException: If the Agent is absent or input is invalid.
    """
    try:
        updated = _core(request).external_agent_hub.replace(agent_id, _parse_input(payload))
        return {"agent": _definition(updated)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="external Agent not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/api/external-agents/{agent_id}", status_code=204)
def delete_external_agent(agent_id: str, request: Request) -> None:
    """Remove one configuration definition without deleting its connector.

    Args:
        agent_id: External Agent identifier to remove.
        request: Incoming request carrying the composition root.

    Returns:
        None.

    Raises:
        HTTPException: If the requested definition is absent.
    """
    try:
        _core(request).external_agent_hub.remove(agent_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="external Agent not found") from exc


@router.post("/api/external-agents/{agent_id}/health")
def external_agent_health(agent_id: str, request: Request) -> dict[str, object]:
    """Perform a non-executing adapter health check.

    Args:
        agent_id: External Agent identifier to probe.
        request: Incoming request carrying the composition root.

    Returns:
        User-safe normalized health state.

    Raises:
        HTTPException: If the requested definition is absent.
    """
    try:
        return {"health": _health(_core(request).external_agent_hub.health(agent_id))}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="external Agent not found") from exc


@router.get("/api/external-agents/{agent_id}/capabilities")
def external_agent_capabilities(agent_id: str, request: Request) -> dict[str, object]:
    """Read capabilities advertised by an installed adapter without running it.

    Args:
        agent_id: External Agent identifier to inspect.
        request: Incoming request carrying the composition root.

    Returns:
        Credential-free capability declarations.

    Raises:
        HTTPException: If the requested definition is absent.
    """
    try:
        capabilities = _core(request).external_agent_hub.capabilities(agent_id)
        return {"capabilities": [_capability(item) for item in capabilities]}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="external Agent not found") from exc
    except ExternalAgentAdapterFailure as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/api/external-agents/{agent_id}/sessions")
def external_agent_sessions(agent_id: str, request: Request, limit: int = 50) -> dict[str, object]:
    """List bounded remote session summaries without importing or running them.

    Args:
        agent_id: External Agent identifier whose runtime is inspected.
        request: Incoming request carrying the composition root.
        limit: Maximum newest-first session summaries, from 1 through 200.

    Returns:
        Credential-free remote session summaries.

    Raises:
        HTTPException: If the Agent is absent or the page size is invalid.
    """
    try:
        sessions = _core(request).external_agent_hub.sessions(agent_id, limit)
        return {"sessions": [_session(item) for item in sessions]}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="external Agent not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ExternalAgentAdapterFailure as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _parse_input(payload: object) -> ExternalAgentDefinition:
    """Decode a strict JSON request object into a typed definition.

    Args:
        payload: JSON body supplied by an API caller.

    Returns:
        Typed credential-free external Agent definition.

    Raises:
        ValueError: If fields are missing, unknown, or incorrectly typed.
    """
    if not isinstance(payload, Mapping):
        raise ValueError("external Agent body must be an object")
    allowed = {"id", "title", "adapter_kind", "endpoint", "connector_id", "enabled", "description"}
    unknown = sorted(str(key) for key in payload if key not in allowed)
    if unknown:
        raise ValueError(f"unknown external Agent fields: {', '.join(unknown)}")
    required = ("id", "title", "adapter_kind")
    if any(not isinstance(payload.get(key), str) for key in required):
        raise ValueError("external Agent id, title, and adapter_kind must be strings")
    optional_text = ("endpoint", "connector_id", "description")
    if any(key in payload and not isinstance(payload[key], str) for key in optional_text):
        raise ValueError("external Agent text fields must be strings")
    enabled = payload.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError("external Agent enabled must be boolean")
    parsed = ExternalAgentInput(
        id=str(payload["id"]),
        title=str(payload["title"]),
        adapter_kind=str(payload["adapter_kind"]),
        endpoint=str(payload.get("endpoint", "")),
        connector_id=str(payload.get("connector_id", "")),
        enabled=enabled,
        description=str(payload.get("description", "")),
    )
    return ExternalAgentDefinition(
        parsed.id,
        parsed.title,
        parsed.adapter_kind,
        parsed.endpoint,
        parsed.connector_id,
        parsed.enabled,
        parsed.description,
    )


def _definition(value: ExternalAgentDefinition) -> dict[str, object]:
    """Serialize a definition without resolving connector credentials.

    Args:
        value: Typed external Agent definition.

    Returns:
        JSON-safe public definition object.
    """
    return {
        "id": value.id,
        "title": value.title,
        "adapter_kind": value.adapter_kind,
        "endpoint": value.endpoint,
        "connector_id": value.connector_id,
        "enabled": value.enabled,
        "description": value.description,
    }


def _health(value: ExternalAgentHealth) -> dict[str, object]:
    """Serialize a typed health observation for the HTTP response.

    Args:
        value: Typed health object returned by the Hub service.

    Returns:
        JSON-safe health response object.
    """
    return {
        "agent_id": value.agent_id,
        "adapter_kind": value.adapter_kind,
        "status": value.status,
        "message": value.message,
    }


def _capability(value: ExternalAgentCapability) -> dict[str, object]:
    """Serialize one typed capability declaration for the HTTP response.

    Args:
        value: Typed capability returned by the Hub service.

    Returns:
        JSON-safe capability response object.
    """
    return {
        "id": value.id,
        "title": value.title,
        "description": value.description,
        "invocation_mode": value.invocation_mode,
    }


def _session(value: ExternalAgentSession) -> dict[str, object]:
    """Serialize one remote session without treating references as local paths.

    Args:
        value: Typed external session summary returned by an adapter.

    Returns:
        JSON-safe remote session summary.
    """
    return {
        "agent_id": value.agent_id,
        "external_id": value.external_id,
        "title": value.title,
        "status": value.status,
        "updated_at": value.updated_at,
        "project_path": value.project_path,
    }


__all__ = ["router"]
