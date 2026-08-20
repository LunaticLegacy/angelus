"""Connector and provider routes for the Angelus browser console."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from llmfetcher.llm_fetcher import LLMFetcher

from ..classes import ConnectorRequest
from ..connectors import _public_connector, _read_connectors, _write_connectors
from ..storage import _safe_id, _sessions_lock

router = APIRouter()



@router.get("/api/providers")
def providers(request: Request) -> dict[str, list[str]]:
    """Expose built-in providers plus plugin-registered connector kinds.

    Plugin connector kinds come from the PluginManager attached to
    ``app.state.plugin_manager`` (wired by ``angelus.webapp``); when no
    plugin system is present the response degrades to the built-in set.
    """
    manager = getattr(getattr(request.app, "state", None), "plugin_manager", None)
    if manager is not None:
        from ..plugins.bridge_connectors import aggregate_providers

        return {"providers": list(aggregate_providers(manager))}
    return {"providers": list(LLMFetcher.list_available_backend_providers())}

@router.get("/api/connectors")
def list_connectors() -> dict[str, list[dict[str, Any]]]:
    """List connector metadata without returning any saved API key."""
    return {"connectors": [_public_connector(item) for item in _read_connectors()]}

@router.post("/api/connectors", status_code=201)
def create_connector(request: ConnectorRequest) -> dict[str, Any]:
    """Persist a named connection and return its complete local record.

    Args:
        request: Provider, model, credential and runtime defaults to store.

    Returns:
        New connector record with its generated stable ID.
    """
    record = {"id": uuid.uuid4().hex, **request.model_dump()}
    with _sessions_lock:
        connectors = _read_connectors()
        connectors.append(record)
        _write_connectors(connectors)
    return _public_connector(record)

@router.put("/api/connectors/{connector_id}")
def update_connector(connector_id: str, request: ConnectorRequest) -> dict[str, Any]:
    """Replace one connector's persisted settings while retaining its ID.

    Args:
        connector_id: Stable connector identifier returned by creation.
        request: Entire replacement connector configuration.

    Returns:
        Updated connector record.

    Raises:
        HTTPException: If the connector identifier does not exist.
    """
    connector_id = _safe_id(connector_id, "connector")
    with _sessions_lock:
        connectors = _read_connectors()
        for index, connector in enumerate(connectors):
            if connector.get("id") == connector_id:
                replacement = {"id": connector_id, **request.model_dump()}
                # Selecting a connector intentionally leaves the input blank;
                # a blank update therefore keeps its existing encrypted key.
                if not replacement.get("api_key"):
                    replacement["api_key"] = connector.get("api_key", "")
                connectors[index] = replacement
                _write_connectors(connectors)
                return _public_connector(replacement)
    raise HTTPException(status_code=404, detail="Connector not found")

@router.delete("/api/connectors/{connector_id}", status_code=204)
def delete_connector(connector_id: str) -> None:
    """Delete one persisted connector and its locally stored credential.

    Args:
        connector_id: Stable connector identifier returned by creation.

    Raises:
        HTTPException: If no connector uses ``connector_id``.
    """
    connector_id = _safe_id(connector_id, "connector")
    with _sessions_lock:
        connectors = _read_connectors()
        remaining = [item for item in connectors if item.get("id") != connector_id]
        if len(remaining) == len(connectors):
            raise HTTPException(status_code=404, detail="Connector not found")
        _write_connectors(remaining)

__all__ = ["providers", "list_connectors", "create_connector", "update_connector", "delete_connector", "router"]
