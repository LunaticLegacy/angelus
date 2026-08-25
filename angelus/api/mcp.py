"""Managed MCP server registry, probe, and session authorization routes."""

from __future__ import annotations

import time
import base64
import hashlib
import json
import secrets
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request as URLRequest, urlopen

from fastapi import APIRouter, Body, HTTPException

from .. import mcp_registry
from ..mcp_tools import MCPToolError, create_mcp_tools
from ..storage import _safe_id, _sessions_lock

router = APIRouter()
_OAUTH_PENDING = mcp_registry.storage.STATE_ROOT / "mcp-oauth-pending.json"


def _oauth_pending() -> dict[str, Any]:
    """Read short-lived OAuth state/PKCE transactions from private app state."""
    try:
        payload = json.loads(_OAUTH_PENDING.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_oauth_pending(payload: dict[str, Any]) -> None:
    """Atomically persist private OAuth state and verifier values."""
    _OAUTH_PENDING.parent.mkdir(parents=True, exist_ok=True)
    temporary = _OAUTH_PENDING.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    try:
        temporary.chmod(0o600)
    except OSError:
        pass
    temporary.replace(_OAUTH_PENDING)


def _record(server_id: str) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
    """Locate one MCP registry record under its stable identifier.

    Args:
        server_id: Browser-supplied registry identifier.

    Returns:
        Mutable record collection, matching index, and matching record.
    """
    safe_id = _safe_id(server_id, "MCP server")
    records = mcp_registry.read_servers()
    for index, record in enumerate(records):
        if record.get("id") == safe_id:
            return records, index, record
    raise HTTPException(status_code=404, detail="MCP server not found")


@router.get("/api/mcp/servers")
def list_mcp_servers() -> dict[str, Any]:
    """List global MCP servers without returning credential values."""
    return {"servers": [mcp_registry.public_server(item) for item in mcp_registry.read_servers()]}


@router.post("/api/mcp/servers", status_code=201)
def create_mcp_server(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Validate, encrypt, and create one global MCP server.

    Args:
        payload: Structured transport, authentication, and launch fields.
    """
    try:
        record = mcp_registry._normalize_server(payload)
    except MCPToolError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    with _sessions_lock:
        records = mcp_registry.read_servers()
        if any(item.get("name") == record["name"] for item in records):
            raise HTTPException(status_code=409, detail="MCP server name already exists")
        records.append(record)
        mcp_registry.write_servers(records)
    return mcp_registry.public_server(record)


@router.put("/api/mcp/servers/{server_id}")
def update_mcp_server(server_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Replace one global MCP server while preserving blank credentials.

    Args:
        server_id: Stable registry identifier.
        payload: Complete structured replacement form.
    """
    with _sessions_lock:
        records, index, existing = _record(server_id)
        merged = dict(payload)
        for field in ("bearer_token", "oauth_client_secret", "oauth_token", "oauth_refresh_token"):
            if not merged.get(field):
                merged[field] = existing.get(field, "")
        for field in ("headers", "env"):
            submitted = merged.get(field)
            if not submitted and existing.get(field):
                merged[field] = existing[field]
            elif isinstance(submitted, dict):
                merged[field] = {
                    key: (existing.get(field, {}).get(key, "") if value == "" else value)
                    for key, value in submitted.items()
                }
        try:
            replacement = mcp_registry._normalize_server(merged, existing_id=existing["id"])
        except MCPToolError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        records[index] = replacement
        mcp_registry.write_servers(records)
    return mcp_registry.public_server(replacement)


@router.delete("/api/mcp/servers/{server_id}", status_code=204)
def delete_mcp_server(server_id: str) -> None:
    """Delete one global MCP server record.

    Args:
        server_id: Stable registry identifier.
    """
    with _sessions_lock:
        records, index, deleted = _record(server_id)
        records.pop(index)
        mcp_registry.write_servers(records)
        # Remove dangling grants from every registered session so later policy
        # edits cannot fail validation on a server that no longer exists.
        for session in mcp_registry.storage._read_workspaces():
            session_id = str(session.get("id", ""))
            if not session_id:
                continue
            bindings = [
                item for item in mcp_registry.read_bindings(session_id)
                if item.get("server_id") != deleted["id"]
            ]
            mcp_registry.write_bindings(session_id, bindings)


@router.post("/api/mcp/servers/{server_id}/probe")
def probe_mcp_server(server_id: str) -> dict[str, Any]:
    """Temporarily connect and cache one server's discovered tools.

    Args:
        server_id: Stable registry identifier.

    Returns:
        Browser-safe updated record including probe and capability metadata.
    """
    with _sessions_lock:
        records, index, record = _record(server_id)
    bridge = None
    try:
        bridge, tools = create_mcp_tools([record])
        capabilities = bridge.capability_snapshot()
        record["capabilities"] = capabilities
        record["probe"] = {"ok": True, "checked_at": time.time(), "error": ""}
    except Exception as exc:
        record["probe"] = {
            "ok": False, "checked_at": time.time(),
            "error": f"{type(exc).__name__}: {exc}"[:1000],
        }
    finally:
        if bridge is not None:
            bridge.close()
    with _sessions_lock:
        records[index] = record
        mcp_registry.write_servers(records)
    return mcp_registry.public_server(record)


@router.get("/api/mcp/servers/{server_id}/capabilities")
def get_mcp_capabilities(server_id: str) -> dict[str, Any]:
    """Return the most recently probed capability cache."""
    _, _, record = _record(server_id)
    return {"capabilities": record.get("capabilities", {}), "probe": record.get("probe", {})}


@router.post("/api/mcp/servers/{server_id}/oauth/connect")
def connect_mcp_oauth(
    server_id: str, payload: dict[str, Any] = Body(...),
) -> dict[str, str]:
    """Start standard OAuth authorization with state and PKCE protection.

    Args:
        server_id: Stable global server identifier.
        payload: Browser callback ``redirect_uri`` for this local console.
    """
    _, _, record = _record(server_id)
    authorize_url = str(record.get("oauth_authorize_url", ""))
    client_id = str(record.get("oauth_client_id", ""))
    redirect_uri = str(payload.get("redirect_uri", "")).strip()
    if not authorize_url.startswith(("https://", "http://localhost", "http://127.0.0.1")) or not client_id or not redirect_uri:
        raise HTTPException(status_code=422, detail="OAuth authorize URL, client ID, and redirect URI are required")
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    pending = _oauth_pending()
    pending[state] = {
        "server_id": record["id"], "verifier": verifier,
        "redirect_uri": redirect_uri, "created_at": time.time(),
    }
    _write_oauth_pending(pending)
    query = urlencode({
        "response_type": "code", "client_id": client_id,
        "redirect_uri": redirect_uri, "scope": record.get("oauth_scopes", ""),
        "state": state, "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    return {"authorization_url": f"{authorize_url}{'&' if '?' in authorize_url else '?'}{query}", "state": state}


@router.get("/api/mcp/oauth/callback")
def callback_mcp_oauth(state: str, code: str) -> dict[str, Any]:
    """Validate OAuth state/PKCE and exchange the one-time code for tokens."""
    pending = _oauth_pending()
    transaction = pending.pop(state, None)
    _write_oauth_pending(pending)
    if not transaction or time.time() - float(transaction.get("created_at", 0)) > 300:
        raise HTTPException(status_code=400, detail="OAuth state is invalid or expired")
    with _sessions_lock:
        records, index, record = _record(str(transaction["server_id"]))
        token_url = str(record.get("oauth_token_url", ""))
        if not token_url.startswith(("https://", "http://localhost", "http://127.0.0.1")):
            raise HTTPException(status_code=422, detail="OAuth token URL is invalid")
        form = {
            "grant_type": "authorization_code", "code": code,
            "redirect_uri": transaction["redirect_uri"],
            "client_id": record.get("oauth_client_id", ""),
            "code_verifier": transaction["verifier"],
        }
        if record.get("oauth_client_secret"):
            form["client_secret"] = record["oauth_client_secret"]
        try:
            request = URLRequest(token_url, data=urlencode(form).encode(), headers={"Content-Type": "application/x-www-form-urlencoded"})
            with urlopen(request, timeout=30) as response:
                token = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"OAuth token exchange failed: {exc}") from exc
        record["oauth_token"] = str(token.get("access_token", ""))
        record["oauth_refresh_token"] = str(token.get("refresh_token", ""))
        record["oauth_expires_at"] = time.time() + float(token.get("expires_in", 0) or 0)
        if not record["oauth_token"]:
            raise HTTPException(status_code=502, detail="OAuth response did not contain an access token")
        records[index] = record
        mcp_registry.write_servers(records)
    return mcp_registry.public_server(record)


@router.post("/api/mcp/servers/{server_id}/oauth/disconnect")
def disconnect_mcp_oauth(server_id: str) -> dict[str, Any]:
    """Delete stored OAuth access and refresh tokens for one server."""
    with _sessions_lock:
        records, index, record = _record(server_id)
        record["oauth_token"] = ""
        record["oauth_refresh_token"] = ""
        record["oauth_expires_at"] = 0
        records[index] = record
        mcp_registry.write_servers(records)
    return mcp_registry.public_server(record)


@router.post("/api/mcp/servers/{server_id}/oauth/refresh")
def refresh_mcp_oauth(server_id: str) -> dict[str, Any]:
    """Refresh one server's OAuth access token without exposing it."""
    with _sessions_lock:
        records, index, record = _record(server_id)
        refresh_token = str(record.get("oauth_refresh_token", ""))
        if not refresh_token:
            raise HTTPException(status_code=409, detail="No OAuth refresh token is configured")
        form = {
            "grant_type": "refresh_token", "refresh_token": refresh_token,
            "client_id": record.get("oauth_client_id", ""),
        }
        if record.get("oauth_client_secret"):
            form["client_secret"] = record["oauth_client_secret"]
        try:
            request = URLRequest(str(record.get("oauth_token_url", "")), data=urlencode(form).encode(), headers={"Content-Type": "application/x-www-form-urlencoded"})
            with urlopen(request, timeout=30) as response:
                token = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"OAuth refresh failed: {exc}") from exc
        record["oauth_token"] = str(token.get("access_token", ""))
        record["oauth_refresh_token"] = str(token.get("refresh_token", refresh_token))
        record["oauth_expires_at"] = time.time() + float(token.get("expires_in", 0) or 0)
        if not record["oauth_token"]:
            raise HTTPException(status_code=502, detail="OAuth refresh did not return an access token")
        records[index] = record
        mcp_registry.write_servers(records)
    return mcp_registry.public_server(record)


@router.get("/api/sessions/{session_id}/mcp-bindings")
def get_mcp_bindings(session_id: str) -> dict[str, Any]:
    """Return server/role/tool grants for one browser session."""
    safe_session = _safe_id(session_id, "session")
    return {"bindings": mcp_registry.read_bindings(safe_session)}


@router.put("/api/sessions/{session_id}/mcp-bindings")
def put_mcp_bindings(
    session_id: str, payload: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Replace MCP grants for one browser session.

    Args:
        session_id: Browser-stable session identity.
        payload: Object containing the complete ``bindings`` array.
    """
    safe_session = _safe_id(session_id, "session")
    bindings = payload.get("bindings", [])
    if not isinstance(bindings, list):
        raise HTTPException(status_code=422, detail="bindings must be an array")
    try:
        mcp_registry.write_bindings(safe_session, bindings)
    except MCPToolError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"bindings": mcp_registry.read_bindings(safe_session)}


__all__ = ["router"]
