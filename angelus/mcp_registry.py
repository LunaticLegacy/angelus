"""Global MCP server registry and session-local authorization policies."""

from __future__ import annotations

import json
import base64
import re
import time
import uuid
from pathlib import Path
from typing import Any

from . import storage
from .connectors import _decrypt_connector_key, _encrypt_connector_key
from .mcp_tools import MCPServer, MCPToolError

MCP_SERVER_INDEX = storage.STATE_ROOT / "mcp-servers.json"
_SECRET_FIELDS = {"bearer_token", "oauth_client_secret", "oauth_token", "oauth_refresh_token"}
_PROJECT_TEMPLATE = "${project_root}"


def _encrypt_secret(value: str) -> dict[str, Any]:
    """Envelope long UTF-8 secrets into RSA-safe encrypted chunks."""
    encoded = value.encode("utf-8")
    chunks = [
        _encrypt_connector_key(base64.b64encode(encoded[index:index + 150]).decode("ascii"))
        for index in range(0, len(encoded), 150)
    ]
    return {"encoding": "base64-utf8-chunks", "chunks": chunks}


def _decrypt_secret(payload: Any) -> str:
    """Decrypt a chunked secret while retaining old single-RSA compatibility."""
    if isinstance(payload, dict) and payload.get("encoding") == "base64-utf8-chunks":
        try:
            raw = b"".join(
                base64.b64decode(_decrypt_connector_key(chunk), validate=True)
                for chunk in payload.get("chunks", [])
            )
            return raw.decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError("cannot decrypt MCP secret") from exc
    return _decrypt_connector_key(payload)


def _read_json(path: Path, default: Any) -> Any:
    """Read JSON from ``path`` and return ``default`` on invalid input.

    Args:
        path: Application-state file, never a user project file.
        default: Fallback value returned for missing or malformed content.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, payload: Any) -> None:
    """Atomically persist one private registry payload with mode 0600.

    Args:
        path: Destination inside the Angelus application-state directory.
        payload: JSON-compatible value replacing the previous file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        temporary.chmod(0o600)
    except OSError:
        pass
    temporary.replace(path)


def _validate_template_boundaries(payload: dict[str, Any]) -> None:
    """Reject project-root expansion outside controlled stdio args/cwd.

    Args:
        payload: Untrusted server form submitted by the browser.

    Raises:
        MCPToolError: If a forbidden field contains ``${project_root}``.
    """
    forbidden = [
        payload.get("command", ""), payload.get("url", ""),
        payload.get("oauth_authorize_url", ""), payload.get("oauth_token_url", ""),
        payload.get("oauth_client_id", ""),
    ]
    forbidden.extend(str(value) for value in (payload.get("headers") or {}).values())
    forbidden.extend(str(payload.get(field, "")) for field in _SECRET_FIELDS)
    forbidden.extend(str(value) for value in (payload.get("env") or {}).values())
    if any(_PROJECT_TEMPLATE in str(value) for value in forbidden):
        raise MCPToolError("${project_root} is allowed only in stdio args and cwd")
    if str(payload.get("transport", "stdio")).lower() != "stdio" and (
        _PROJECT_TEMPLATE in str(payload.get("cwd", ""))
        or any(_PROJECT_TEMPLATE in str(value) for value in payload.get("args", []))
    ):
        raise MCPToolError("${project_root} is allowed only in stdio args and cwd")


def _normalize_server(payload: dict[str, Any], *, existing_id: str = "") -> dict[str, Any]:
    """Validate and normalize a global MCP server record.

    Args:
        payload: Structured browser server form.
        existing_id: Stable identifier retained during updates.

    Returns:
        Plain internal record whose secret values are not yet encrypted.
    """
    _validate_template_boundaries(payload)
    transport = str(payload.get("transport", "stdio")).strip().lower()
    if transport == "sse":
        raise MCPToolError("Legacy SSE transport is not supported")
    if transport not in {"stdio", "streamable-http"}:
        raise MCPToolError(f"Unsupported MCP transport: {transport}")
    name = str(payload.get("name", "")).strip()
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", name):
        raise MCPToolError("MCP server name must match [A-Za-z][A-Za-z0-9_-]{0,63}")
    args = payload.get("args") or []
    headers = payload.get("headers") or {}
    env = payload.get("env") or {}
    if not isinstance(args, list) or not all(isinstance(value, str) for value in args):
        raise MCPToolError("MCP args must be a string array")
    if not isinstance(headers, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in headers.items()):
        raise MCPToolError("MCP headers must be a string mapping")
    if not isinstance(env, dict) or not all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(key)) and isinstance(value, str) for key, value in env.items()):
        raise MCPToolError("MCP env must be an environment-variable mapping")
    candidate = {
        "name": name,
        "transport": transport,
        "command": str(payload.get("command", "")).strip(),
        "args": args,
        "cwd": str(payload.get("cwd", "")).strip(),
        "url": str(payload.get("url", "")).strip(),
        "headers": headers,
        "env": env,
    }
    MCPServer.from_config(candidate)
    return {
        "id": existing_id or uuid.uuid4().hex,
        **candidate,
        "auth_type": str(payload.get("auth_type", "none")),
        "bearer_token": str(payload.get("bearer_token", "")),
        "oauth_authorize_url": str(payload.get("oauth_authorize_url", "")).strip(),
        "oauth_token_url": str(payload.get("oauth_token_url", "")).strip(),
        "oauth_client_id": str(payload.get("oauth_client_id", "")).strip(),
        "oauth_client_secret": str(payload.get("oauth_client_secret", "")),
        "oauth_scopes": str(payload.get("oauth_scopes", "")).strip(),
        "oauth_token": str(payload.get("oauth_token", "")),
        "oauth_refresh_token": str(payload.get("oauth_refresh_token", "")),
        "oauth_expires_at": float(payload.get("oauth_expires_at", 0) or 0),
        "capabilities": payload.get("capabilities", {}) if isinstance(payload.get("capabilities", {}), dict) else {},
        "probe": payload.get("probe", {}) if isinstance(payload.get("probe", {}), dict) else {},
        "updated_at": time.time(),
    }


def _stored_server(record: dict[str, Any]) -> dict[str, Any]:
    """Encrypt every configured credential in one registry record."""
    stored = dict(record)
    for field in _SECRET_FIELDS:
        stored[f"{field}_encrypted"] = _encrypt_secret(str(stored.pop(field, "")))
    stored["headers_encrypted"] = {
        name: _encrypt_secret(value) for name, value in stored.pop("headers", {}).items()
    }
    stored["env_encrypted"] = {
        name: _encrypt_secret(value) for name, value in stored.pop("env", {}).items()
    }
    return stored


def _loaded_server(stored: dict[str, Any]) -> dict[str, Any]:
    """Decrypt one record for server-side connection use."""
    record = dict(stored)
    for field in _SECRET_FIELDS:
        record[field] = _decrypt_secret(record.pop(f"{field}_encrypted", {}))
    record["headers"] = {
        name: _decrypt_secret(value)
        for name, value in record.pop("headers_encrypted", {}).items()
    }
    record["env"] = {
        name: _decrypt_secret(value)
        for name, value in record.pop("env_encrypted", {}).items()
    }
    return record


def read_servers() -> list[dict[str, Any]]:
    """Return all decrypted MCP records for internal server use."""
    records = _read_json(MCP_SERVER_INDEX, [])
    return [_loaded_server(item) for item in records if isinstance(item, dict)]


def write_servers(records: list[dict[str, Any]]) -> None:
    """Replace the global MCP registry with encrypted records.

    Args:
        records: Complete decrypted internal record collection.
    """
    _write_json(MCP_SERVER_INDEX, [_stored_server(item) for item in records])


def public_server(record: dict[str, Any]) -> dict[str, Any]:
    """Return browser-safe metadata and credential-presence flags."""
    return {
        key: value for key, value in record.items()
        if key not in _SECRET_FIELDS | {"headers", "env"}
    } | {
        "headers": sorted(record.get("headers", {})),
        "env": sorted(record.get("env", {})),
        "has_bearer_token": bool(record.get("bearer_token")),
        "oauth_connected": bool(record.get("oauth_token")),
        "credentials_configured": bool(record.get("headers") or record.get("env") or record.get("bearer_token") or record.get("oauth_token")),
    }


def binding_path(session_id: str) -> Path:
    """Return the app-state path for one session's MCP grants."""
    return storage._session_path(session_id, session_id) / "mcp-bindings.json"


def read_bindings(session_id: str) -> list[dict[str, Any]]:
    """Return normalized MCP grants for ``session_id``."""
    payload = _read_json(binding_path(session_id), {"bindings": []})
    bindings = payload.get("bindings", []) if isinstance(payload, dict) else []
    return [item for item in bindings if isinstance(item, dict)]


def write_bindings(session_id: str, bindings: list[dict[str, Any]]) -> None:
    """Validate and persist server/role/tool grants for one session.

    Args:
        session_id: Browser-stable session identifier.
        bindings: Complete replacement binding list.
    """
    server_ids = {record["id"] for record in read_servers()}
    normalized: list[dict[str, Any]] = []
    for item in bindings:
        server_id = str(item.get("server_id", ""))
        roles = sorted(set(str(role) for role in item.get("roles", []) if role in {"coordinator", "worker"}))
        tools = sorted(set(str(tool) for tool in item.get("tools", []) if str(tool)))
        if server_id not in server_ids or not roles:
            raise MCPToolError("Each MCP binding needs an existing server and at least one role")
        normalized.append({"server_id": server_id, "roles": roles, "tools": tools})
    _write_json(binding_path(session_id), {"bindings": normalized})


def resolve_session_servers(session_id: str, project_root: Path) -> list[dict[str, Any]]:
    """Resolve authorized registry records for one run and project root.

    Args:
        session_id: Session whose role/tool policies apply.
        project_root: Bound user project expanded only in stdio args/cwd.
    """
    servers = {record["id"]: record for record in read_servers()}
    resolved: list[dict[str, Any]] = []
    for binding in read_bindings(session_id):
        record = dict(servers.get(binding.get("server_id"), {}))
        if not record or not record.get("probe", {}).get("ok"):
            continue
        record["args"] = [value.replace(_PROJECT_TEMPLATE, str(project_root)) for value in record.get("args", [])]
        record["cwd"] = str(record.get("cwd", "")).replace(_PROJECT_TEMPLATE, str(project_root))
        record["roles"] = list(binding.get("roles", []))
        record["tool_allowlist"] = list(binding.get("tools", []))
        record["_project_root"] = str(project_root)
        resolved.append(record)
    return resolved


__all__ = [
    "MCP_SERVER_INDEX", "_normalize_server", "binding_path", "public_server",
    "read_bindings", "read_servers", "resolve_session_servers", "write_bindings", "write_servers",
]
