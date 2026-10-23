"""Typed records for the four durable MCP documents.

The catalog (``settings/mcp-servers.json``), per-server secrets
(``secrets/mcp/<id>.json``), Session bindings (``mcp-bindings.json``) and the
OAuth pending transaction map (``secrets/mcp-oauth-pending.json``) each have
exactly one dataclass here.  ``json_schema.encode_record``/``decode_record``
drive both directions, so a field the writer emits is a field the reader
restores.

``capabilities`` and the resource/prompt entries keep the MCP SDK payload as
``JsonObject``: the SDK defines those fields, not this repository, so the
honest type is a concrete recursive JSON value rather than a fabricated
schema that would silently drop unknown members.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from llmfetcher.llm_types import JsonObject, JsonValue


@dataclass(frozen=True)
class MCPProbe:
    """Outcome of the last connection probe for one server."""

    ok: bool
    checked_at: float
    error: str = ""

    @classmethod
    def from_snapshot(cls, value: JsonObject) -> "MCPProbe":
        """Decode a probe payload written by an older store version."""
        ok = value.get("ok")
        checked_at = value.get("checked_at")
        error = value.get("error", "")
        if not isinstance(ok, bool):
            raise ValueError("MCP probe.ok must be a boolean")
        if isinstance(checked_at, bool) or not isinstance(checked_at, (int, float)):
            raise ValueError("MCP probe.checked_at must be a number")
        if not isinstance(error, str):
            raise ValueError("MCP probe.error must be a string")
        return cls(ok=ok, checked_at=float(checked_at), error=error)


@dataclass(frozen=True)
class MCPCapabilities:
    """Last discovered capability snapshot for one server."""

    tools: tuple[str, ...] = ()
    resources: tuple[JsonObject, ...] = ()
    resource_templates: tuple[JsonObject, ...] = ()
    prompts: tuple[JsonObject, ...] = ()

    @classmethod
    def from_snapshot(cls, value: JsonObject) -> "MCPCapabilities":
        """Decode the SDK discovery snapshot produced by the bridge."""
        tools = value.get("tools", [])
        if not isinstance(tools, list):
            raise ValueError("MCP capabilities.tools must be an array")
        return cls(
            tools=tuple(str(item) for item in tools),
            resources=_json_objects(value.get("resources", []), "resources"),
            resource_templates=_json_objects(
                value.get("resource_templates", []), "resource_templates"
            ),
            prompts=_json_objects(value.get("prompts", []), "prompts"),
        )


def _json_objects(value: object, field: str) -> tuple[JsonObject, ...]:
    """Return an array of JSON objects, rejecting non-object entries."""
    if not isinstance(value, list):
        raise ValueError(f"MCP capabilities.{field} must be an array")
    entries: list[JsonObject] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError(f"MCP capabilities.{field} entries must be objects")
        entries.append(item)  # type: ignore[arg-type]
    return tuple(entries)


@dataclass(frozen=True)
class MCPServerRecord:
    """One catalog entry in ``settings/mcp-servers.json``."""

    id: str
    name: str
    transport: str
    command: str
    args: tuple[str, ...]
    cwd: str
    url: str
    auth_type: str
    oauth_authorize_url: str
    oauth_token_url: str
    oauth_client_id: str
    oauth_scopes: str
    oauth_expires_at: float
    capabilities: MCPCapabilities
    probe: MCPProbe
    updated_at: float


@dataclass(frozen=True)
class MCPCatalog:
    """The complete ``settings/mcp-servers.json`` document."""

    servers: tuple[MCPServerRecord, ...]
    schema_version: int = 1


@dataclass(frozen=True)
class MCPSecrets:
    """The private ``secrets/mcp/<id>.json`` document."""

    bearer_token: str = ""
    oauth_client_secret: str = ""
    oauth_token: str = ""
    oauth_refresh_token: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)
    schema_version: int = 1


@dataclass(frozen=True)
class MCPBinding:
    """One Session's authorization for a server and role set."""

    server_id: str
    roles: tuple[str, ...]
    tools: tuple[str, ...]

    @classmethod
    def from_mapping(cls, value: object) -> "MCPBinding":
        """Decode one HTTP-supplied binding, rejecting malformed members."""
        if not isinstance(value, dict):
            raise ValueError("MCP binding must be an object")
        server_id = value.get("server_id")
        roles = value.get("roles", [])
        tools = value.get("tools", [])
        if not isinstance(server_id, str) or not server_id:
            raise ValueError("MCP binding.server_id must be a non-empty string")
        if not isinstance(roles, list) or not all(
            isinstance(role, str) for role in roles
        ):
            raise ValueError("MCP binding.roles must be a string array")
        if not isinstance(tools, list) or not all(
            isinstance(tool, str) for tool in tools
        ):
            raise ValueError("MCP binding.tools must be a string array")
        return cls(
            server_id=server_id,
            roles=tuple(roles),  # type: ignore[arg-type]
            tools=tuple(tools),  # type: ignore[arg-type]
        )


@dataclass(frozen=True)
class MCPBindingsDocument:
    """The complete ``sessions/<id>/mcp-bindings.json`` document."""

    bindings: tuple[MCPBinding, ...]
    schema_version: int = 1


@dataclass(frozen=True)
class MCPOAuthTransaction:
    """One in-flight OAuth authorization keyed by its state value."""

    server_id: str
    verifier: str
    redirect_uri: str
    created_at: float


@dataclass(frozen=True)
class MCPOAuthPendingDocument:
    """The complete ``secrets/mcp-oauth-pending.json`` document."""

    pending: dict[str, MCPOAuthTransaction]
    schema_version: int = 1


@dataclass(frozen=True)
class MCPPublicServer:
    """Secret-free projection returned to the settings surface."""

    id: str
    name: str
    transport: str
    command: str
    args: tuple[str, ...]
    cwd: str
    url: str
    auth_type: str
    oauth_authorize_url: str
    oauth_token_url: str
    oauth_client_id: str
    oauth_scopes: str
    oauth_expires_at: float
    capabilities: MCPCapabilities
    probe: MCPProbe
    updated_at: float
    headers: tuple[str, ...]
    env: tuple[str, ...]
    has_bearer_token: bool
    oauth_connected: bool
    credentials_configured: bool


@dataclass(frozen=True)
class MCPServerWithSecrets:
    """One catalog entry merged with its private credential document."""

    record: MCPServerRecord
    secrets: MCPSecrets


@dataclass(frozen=True)
class MCPResolvedServer:
    """One server merged with its decrypted secrets for a live Agent."""

    record: MCPServerRecord
    secrets: MCPSecrets
    tool_allowlist: tuple[str, ...]
    project_root: str
