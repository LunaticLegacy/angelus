"""MCP metadata, private credentials, and Session-local bindings.

Four documents, each with exactly one dataclass schema:

- ``settings/mcp-servers.json`` — :class:`MCPCatalog`
- ``secrets/mcp/<id>.json`` — :class:`MCPSecrets`
- ``sessions/<id>/mcp-bindings.json`` — :class:`MCPBindingsDocument`
- ``secrets/mcp-oauth-pending.json`` — :class:`MCPOAuthPendingDocument`

Writes and reads share the dataclass through ``encode_record``/``decode_record``.
Legacy documents are migrated field-by-field *before* the strict decode; an
unrecognised shape raises instead of loading as an empty catalog.
"""

from __future__ import annotations

import os
import time
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from llmfetcher.llm_types import JsonObject, JsonValue

from ..settings_module.json_schema import decode_record, encode_record
from ..settings_module.json_store import JsonSchemaError, read_json, write_json
from ..session_module import validate_session_id
from .bridge import MCPServer, MCPToolError
from .records import (
    MCPBinding,
    MCPBindingsDocument,
    MCPCapabilities,
    MCPCatalog,
    MCPOAuthPendingDocument,
    MCPOAuthTransaction,
    MCPProbe,
    MCPPublicServer,
    MCPResolvedServer,
    MCPSecrets,
    MCPServerRecord,
    MCPServerWithSecrets,
)

_TEMPLATE = "${project_root}"


class MCPStore:
    """Own the MCP catalog, secrets, bindings and pending OAuth transactions."""

    def __init__(self, state_root: Path) -> None:
        """Create a store rooted in the Angelus state directory."""
        self._catalog = state_root / "settings" / "mcp-servers.json"
        self._secrets = state_root / "secrets" / "mcp"
        self._sessions = state_root / "sessions"
        self._pending = state_root / "secrets" / "mcp-oauth-pending.json"

    # ------------------------------------------------------------------
    # Catalog
    # ------------------------------------------------------------------

    def list(self) -> tuple[MCPPublicServer, ...]:
        """Return every server without credentials or header/env values."""
        return tuple(
            self.public(item) for item in self._records()
        )

    def internal(self) -> tuple[MCPServerWithSecrets, ...]:
        """Return every server merged with its decrypted secrets."""
        return tuple(self._with_secrets(item) for item in self._records())

    def create(self, payload: Mapping[str, JsonValue]) -> MCPPublicServer:
        """Create one server and persist its secrets separately.

        Raises:
            MCPToolError: If the name exists or a field is malformed.
        """
        record, secrets = self._normalize(payload)
        records = list(self._records())
        if any(item.name == record.name for item in records):
            raise MCPToolError("MCP server name already exists")
        records.append(record)
        self._write(records)
        self._write_secret(record.id, secrets)
        return self.public(MCPServerWithSecrets(record, secrets))

    def replace(
        self, server_id: str, payload: Mapping[str, JsonValue]
    ) -> MCPPublicServer:
        """Replace one server, retaining omitted credentials and header values."""
        records = list(self._records())
        index = self._index(records, server_id)
        existing = self._with_secrets(records[index])
        merged = dict(payload)
        current, current_secrets = existing.record, existing.secrets
        for name, retained in (
            ("bearer_token", current_secrets.bearer_token),
            ("oauth_client_secret", current_secrets.oauth_client_secret),
            ("oauth_token", current_secrets.oauth_token),
            ("oauth_refresh_token", current_secrets.oauth_refresh_token),
        ):
            if not merged.get(name):
                merged[name] = retained
        submitted_headers = merged.get("headers")
        if not submitted_headers:
            merged["headers"] = dict(current_secrets.headers)
        elif isinstance(submitted_headers, dict):
            merged["headers"] = {
                key: current_secrets.headers.get(key, "") if value == "" else value
                for key, value in submitted_headers.items()
            }
        submitted_env = merged.get("env")
        if not submitted_env:
            merged["env"] = dict(current_secrets.env)
        elif isinstance(submitted_env, dict):
            merged["env"] = {
                key: current_secrets.env.get(key, "") if value == "" else value
                for key, value in submitted_env.items()
            }
        record, secrets = self._normalize(merged, server_id)
        records[index] = record
        self._write(records)
        self._write_secret(server_id, secrets)
        return self.public(MCPServerWithSecrets(record, secrets))

    def remove(self, server_id: str) -> None:
        """Delete one server, its secrets, and every Session binding to it."""
        records = list(self._records())
        records.pop(self._index(records, server_id))
        self._write(records)
        secret_path = self._secrets / f"{server_id}.json"
        if secret_path.exists():
            secret_path.unlink()
        for root in self._sessions.iterdir() if self._sessions.is_dir() else ():
            if not root.is_dir():
                continue
            bindings = [
                item
                for item in self.read_bindings(root.name)
                if item.server_id != server_id
            ]
            self.write_bindings(root.name, bindings)

    def set_probe(
        self,
        server_id: str,
        probe: MCPProbe,
        capabilities: MCPCapabilities,
    ) -> MCPPublicServer:
        """Persist the latest connection probe and discovery snapshot."""
        records = list(self._records())
        index = self._index(records, server_id)
        updated = replace(
            records[index],
            probe=probe,
            capabilities=capabilities,
            updated_at=time.time(),
        )
        records[index] = updated
        self._write(records)
        return self.public(self._with_secrets(updated))

    def get_internal(self, server_id: str) -> MCPServerWithSecrets:
        """Return one server with its decrypted secrets."""
        records = list(self._records())
        return self._with_secrets(records[self._index(records, server_id)])

    def update_credentials(
        self,
        server_id: str,
        *,
        bearer_token: str | None = None,
        oauth_client_secret: str | None = None,
        oauth_token: str | None = None,
        oauth_refresh_token: str | None = None,
        oauth_expires_at: float | None = None,
    ) -> MCPPublicServer:
        """Replace selected private credential fields without exposing them."""
        records = list(self._records())
        index = self._index(records, server_id)
        current = self._with_secrets(records[index])
        secrets = MCPSecrets(
            bearer_token=(
                current.secrets.bearer_token
                if bearer_token is None
                else bearer_token
            ),
            oauth_client_secret=(
                current.secrets.oauth_client_secret
                if oauth_client_secret is None
                else oauth_client_secret
            ),
            oauth_token=(
                current.secrets.oauth_token if oauth_token is None else oauth_token
            ),
            oauth_refresh_token=(
                current.secrets.oauth_refresh_token
                if oauth_refresh_token is None
                else oauth_refresh_token
            ),
            headers=dict(current.secrets.headers),
            env=dict(current.secrets.env),
        )
        record = replace(
            records[index],
            oauth_expires_at=(
                current.record.oauth_expires_at
                if oauth_expires_at is None
                else float(oauth_expires_at)
            ),
            updated_at=time.time(),
        )
        records[index] = record
        self._write(records)
        self._write_secret(server_id, secrets)
        return self.public(MCPServerWithSecrets(record, secrets))

    def public(self, item: MCPServerWithSecrets) -> MCPPublicServer:
        """Project one stored server for API consumers without secret values."""
        record, secrets = item.record, item.secrets
        return MCPPublicServer(
            id=record.id,
            name=record.name,
            transport=record.transport,
            command=record.command,
            args=record.args,
            cwd=record.cwd,
            url=record.url,
            auth_type=record.auth_type,
            oauth_authorize_url=record.oauth_authorize_url,
            oauth_token_url=record.oauth_token_url,
            oauth_client_id=record.oauth_client_id,
            oauth_scopes=record.oauth_scopes,
            oauth_expires_at=record.oauth_expires_at,
            capabilities=record.capabilities,
            probe=record.probe,
            updated_at=record.updated_at,
            headers=tuple(sorted(secrets.headers)),
            env=tuple(sorted(secrets.env)),
            has_bearer_token=bool(secrets.bearer_token),
            oauth_connected=bool(secrets.oauth_token),
            credentials_configured=bool(
                secrets.headers
                or secrets.env
                or secrets.bearer_token
                or secrets.oauth_token
            ),
        )

    # ------------------------------------------------------------------
    # Session bindings
    # ------------------------------------------------------------------

    def read_bindings(self, session_id: str) -> tuple[MCPBinding, ...]:
        """Return one Session's authorized servers, or none yet."""
        document = read_json(
            self._binding_path(session_id),
            encode_record(MCPBindingsDocument(bindings=())),
        )
        try:
            decoded = decode_record(
                MCPBindingsDocument, document, "mcp bindings"
            )
        except JsonSchemaError as exc:
            raise MCPToolError("invalid MCP bindings document") from exc
        return decoded.bindings

    def write_bindings(
        self, session_id: str, bindings: Sequence[MCPBinding]
    ) -> tuple[MCPBinding, ...]:
        """Validate and persist one Session's complete binding set."""
        server_ids = {item.id for item in self._records()}
        normalized: list[MCPBinding] = []
        for item in bindings:
            roles = tuple(
                sorted({role for role in item.roles if role in {"coordinator", "worker"}})
            )
            if item.server_id not in server_ids or not roles:
                raise MCPToolError(
                    "Each MCP binding needs an existing server and at least one role"
                )
            normalized.append(
                MCPBinding(
                    server_id=item.server_id,
                    roles=roles,
                    tools=tuple(sorted({tool for tool in item.tools if tool})),
                )
            )
        document = MCPBindingsDocument(bindings=tuple(normalized))
        write_json(self._binding_path(session_id), encode_record(document))
        return tuple(normalized)

    def resolve(
        self, session_id: str, project_root: Path, role: str
    ) -> tuple[MCPResolvedServer, ...]:
        """Return the servers a Session may use for one Agent role."""
        servers = {item.record.id: item for item in self.internal()}
        resolved: list[MCPResolvedServer] = []
        for binding in self.read_bindings(session_id):
            item = servers.get(binding.server_id)
            if item is None or role not in binding.roles or not item.record.probe.ok:
                continue
            resolved.append(
                MCPResolvedServer(
                    record=item.record,
                    secrets=item.secrets,
                    tool_allowlist=binding.tools,
                    project_root=str(project_root),
                )
            )
        return tuple(resolved)

    # ------------------------------------------------------------------
    # OAuth pending transactions
    # ------------------------------------------------------------------

    def read_pending(self) -> MCPOAuthPendingDocument:
        """Return in-flight OAuth transactions, or an empty document."""
        document = read_json(
            self._pending,
            encode_record(MCPOAuthPendingDocument(pending={})),
        )
        try:
            return decode_record(
                MCPOAuthPendingDocument, document, "mcp oauth pending"
            )
        except JsonSchemaError as exc:
            raise MCPToolError("invalid MCP OAuth pending document") from exc

    def write_pending(self, document: MCPOAuthPendingDocument) -> None:
        """Persist the complete in-flight OAuth transaction map."""
        path = self._pending
        write_json(path, encode_record(document))
        try:
            path.chmod(0o600)
        except OSError as exc:
            raise MCPToolError(
                f"cannot restrict MCP OAuth pending permissions: {path}"
            ) from exc

    # ------------------------------------------------------------------
    # Decoding and encoding
    # ------------------------------------------------------------------

    def _records(self) -> tuple[MCPServerRecord, ...]:
        """Decode the catalog, migrating legacy entries before validation."""
        document = read_json(
            self._catalog, encode_record(MCPCatalog(servers=()))
        )
        raw = _require_object(document, "MCP catalog")
        servers = raw.get("servers", [])
        if not isinstance(servers, list):
            raise MCPToolError("invalid MCP catalog")
        migrated: dict[str, JsonValue] = {
            "schema_version": raw.get("schema_version", 1),
            "servers": [
                _migrate_record(_require_object(entry, "MCP catalog entry"))
                for entry in servers
            ],
        }
        try:
            decoded = decode_record(MCPCatalog, migrated, "MCP catalog")
        except JsonSchemaError as exc:
            raise MCPToolError("invalid MCP catalog") from exc
        if decoded.schema_version != 1:
            raise MCPToolError("unsupported MCP catalog version")
        names = [item.name for item in decoded.servers]
        if len(names) != len(set(names)):
            raise MCPToolError("MCP server names must be unique")
        return decoded.servers

    def _write(self, records: Sequence[MCPServerRecord]) -> None:
        """Publish the complete catalog generation."""
        write_json(
            self._catalog, encode_record(MCPCatalog(servers=tuple(records)))
        )

    def _secret(self, server_id: str) -> MCPSecrets:
        """Decode one server's secrets, defaulting a never-written document."""
        document = read_json(
            self._secrets / f"{server_id}.json",
            encode_record(MCPSecrets()),
        )
        raw = _require_object(document, f"MCP secret {server_id}")
        raw.setdefault("schema_version", 1)
        raw["env"] = _migrate_env(raw.get("env", {}))
        try:
            return decode_record(MCPSecrets, raw, f"MCP secret {server_id}")
        except JsonSchemaError as exc:
            raise MCPToolError("invalid MCP secret document") from exc

    def _write_secret(self, server_id: str, value: MCPSecrets) -> None:
        """Persist one server's private credential document."""
        path = self._secrets / f"{server_id}.json"
        write_json(path, encode_record(value))
        try:
            path.chmod(0o600)
        except OSError as exc:
            raise MCPToolError(
                f"cannot restrict MCP secret permissions: {path}"
            ) from exc

    def _with_secrets(self, record: MCPServerRecord) -> MCPServerWithSecrets:
        """Merge one catalog entry with its private document."""
        return MCPServerWithSecrets(record=record, secrets=self._secret(record.id))

    def _binding_path(self, session_id: str) -> Path:
        """Return the binding document path for an already validated Session."""
        return self._sessions / validate_session_id(session_id) / "mcp-bindings.json"

    @staticmethod
    def _index(records: Sequence[MCPServerRecord], server_id: str) -> int:
        """Return the position of one server, raising ``KeyError`` if absent."""
        for index, item in enumerate(records):
            if item.id == server_id:
                return index
        raise KeyError(server_id)

    def _normalize(
        self, payload: Mapping[str, JsonValue], server_id: str = ""
    ) -> tuple[MCPServerRecord, MCPSecrets]:
        """Validate one submitted server definition into record plus secrets."""
        transport = str(payload.get("transport", "stdio")).lower()
        name = str(payload.get("name", "")).strip()
        args = payload.get("args") or []
        headers = payload.get("headers") or {}
        env = payload.get("env") or {}
        if not isinstance(args, list) or not all(
            isinstance(value, str) for value in args
        ):
            raise MCPToolError("MCP args must be a string array")
        if not isinstance(headers, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in headers.items()
        ):
            raise MCPToolError("MCP headers must be a string mapping")
        if not isinstance(env, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in env.items()
        ):
            raise MCPToolError("MCP env must be a string mapping")
        record = MCPServerRecord(
            id=server_id or uuid4().hex,
            name=name,
            transport=transport,
            command=str(payload.get("command", "")).strip(),
            args=tuple(str(value) for value in args),
            cwd=str(payload.get("cwd", "")).strip(),
            url=str(payload.get("url", "")).strip(),
            auth_type=str(payload.get("auth_type", "none")),
            oauth_authorize_url=str(payload.get("oauth_authorize_url", "")),
            oauth_token_url=str(payload.get("oauth_token_url", "")),
            oauth_client_id=str(payload.get("oauth_client_id", "")),
            oauth_scopes=str(payload.get("oauth_scopes", "")),
            oauth_expires_at=float(payload.get("oauth_expires_at", 0) or 0),
            capabilities=_capabilities(payload.get("capabilities", {})),
            probe=_probe(payload.get("probe", {})),
            updated_at=time.time(),
        )
        secrets = MCPSecrets(
            bearer_token=str(payload.get("bearer_token", "")),
            oauth_client_secret=str(payload.get("oauth_client_secret", "")),
            oauth_token=str(payload.get("oauth_token", "")),
            oauth_refresh_token=str(payload.get("oauth_refresh_token", "")),
            headers={str(key): value for key, value in headers.items()},
            env={str(key): value for key, value in env.items()},
        )
        # Reuse the bridge's transport/identity validation as the single rule.
        MCPServer.from_record(record, secrets)
        forbidden = [
            record.command,
            record.url,
            record.oauth_authorize_url,
            record.oauth_token_url,
            record.oauth_client_id,
            *secrets.headers.values(),
            *secrets.env.values(),
            secrets.bearer_token,
            secrets.oauth_client_secret,
            secrets.oauth_token,
            secrets.oauth_refresh_token,
        ]
        if any(_TEMPLATE in str(value) for value in forbidden):
            raise MCPToolError(
                "${project_root} is allowed only in stdio args and cwd"
            )
        return record, secrets


def _require_object(value: JsonValue, where: str) -> JsonObject:
    """Return one decoded JSON object or fail with the document name."""
    if not isinstance(value, dict):
        raise MCPToolError(f"{where} must be a JSON object")
    return value


def _probe(value: JsonValue) -> MCPProbe:
    """Decode an optional stored probe payload.

    A missing probe means "never checked"; a probe that exists but is
    malformed raises rather than silently reading as unchecked.
    """
    if not isinstance(value, dict) or not value:
        return MCPProbe(ok=False, checked_at=0.0)
    raw = dict(value)
    raw.setdefault("checked_at", 0.0)
    raw.setdefault("error", "")
    try:
        return MCPProbe.from_snapshot(raw)
    except ValueError as exc:
        raise MCPToolError(f"invalid MCP probe: {exc}") from exc


def _capabilities(value: JsonValue) -> MCPCapabilities:
    """Decode an optional discovery snapshot."""
    if not isinstance(value, dict) or not value:
        return MCPCapabilities()
    try:
        return MCPCapabilities.from_snapshot(value)
    except ValueError as exc:
        raise MCPToolError(f"invalid MCP capabilities: {exc}") from exc


def _migrate_record(raw: JsonObject) -> JsonObject:
    """Fill fields added after the first catalog generation wrote its entries."""
    migrated = dict(raw)
    migrated.setdefault("args", [])
    migrated.setdefault("cwd", "")
    migrated.setdefault("command", "")
    migrated.setdefault("url", "")
    migrated.setdefault("transport", "stdio")
    migrated.setdefault("auth_type", "none")
    migrated.setdefault("oauth_authorize_url", "")
    migrated.setdefault("oauth_token_url", "")
    migrated.setdefault("oauth_client_id", "")
    migrated.setdefault("oauth_scopes", "")
    migrated.setdefault("oauth_expires_at", 0.0)
    migrated.setdefault("capabilities", {})
    migrated.setdefault("probe", {})
    migrated.setdefault("updated_at", 0.0)
    return migrated


def _migrate_env(value: JsonValue) -> dict[str, str]:
    """Accept the legacy ``env`` list of host variable names."""
    if isinstance(value, list):
        return {
            str(name): os.environ.get(str(name), "")
            for name in value
            if isinstance(name, str)
        }
    if isinstance(value, dict):
        return {str(key): str(item) for key, item in value.items()}
    raise MCPToolError("MCP secret env must be a list or string mapping")


def new_oauth_transaction(
    server_id: str, verifier: str, redirect_uri: str
) -> MCPOAuthTransaction:
    """Build one pending OAuth transaction stamped with the current time."""
    return MCPOAuthTransaction(
        server_id=server_id,
        verifier=verifier,
        redirect_uri=redirect_uri,
        created_at=time.time(),
    )
