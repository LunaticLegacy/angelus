"""Managed MCP lifecycle plus dynamic ToolRegistry provider."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from llmfetcher import Tool
from llmfetcher.llm_types import JsonValue, ToolCallable

from ..tool_module import ToolCategory, ToolPolicy
from ..tool_module.tool_registry import ToolProviderRegistration
from .bridge import MCPToolBridge
from .records import (
    MCPBinding,
    MCPCapabilities,
    MCPProbe,
    MCPPublicServer,
    MCPResolvedServer,
)
from .store import MCPStore

if TYPE_CHECKING:
    from ...core import AngelusCore
    from ..session_module import Session


def _resolved_fingerprint(servers: Sequence[MCPResolvedServer]) -> str:
    """Hash the non-secret identity of the resolved servers.

    Credentials are excluded, but ``updated_at`` changes whenever a secret is
    replaced, so a rotated token still forces a new bridge.
    """
    projection = [
        {
            "id": item.record.id,
            "name": item.record.name,
            "transport": item.record.transport,
            "command": item.record.command,
            "args": item.record.args,
            "cwd": item.record.cwd,
            "url": item.record.url,
            "auth_type": item.record.auth_type,
            "oauth_expires_at": item.record.oauth_expires_at,
            "updated_at": item.record.updated_at,
            "tools": item.tool_allowlist,
        }
        for item in servers
    ]
    return hashlib.sha256(
        json.dumps(projection, sort_keys=True).encode()
    ).hexdigest()


class MCPService:
    """Own MCP bridges per Session role and expose their tools to Agents."""

    def __init__(self, core: "AngelusCore") -> None:
        """Create the service over one Angelus state root."""
        self._core = core
        self.store = MCPStore(core.state_root)
        self._lock = threading.RLock()
        self._bridges: dict[tuple[str, str], tuple[str, MCPToolBridge]] = {}

    def list_servers(self) -> tuple[MCPPublicServer, ...]:
        """Return every configured server without credentials."""
        return self.store.list()

    def create_server(self, payload: Mapping[str, JsonValue]) -> MCPPublicServer:
        """Create one server and invalidate cached bridges."""
        self.invalidate()
        return self.store.create(payload)

    def replace_server(
        self, server_id: str, payload: Mapping[str, JsonValue]
    ) -> MCPPublicServer:
        """Replace one server and invalidate cached bridges."""
        self.invalidate()
        return self.store.replace(server_id, payload)

    def remove_server(self, server_id: str) -> None:
        """Delete one server and invalidate cached bridges."""
        self.invalidate()
        self.store.remove(server_id)

    def bindings(self, session_id: str) -> tuple[MCPBinding, ...]:
        """Return one Session's server bindings."""
        return self.store.read_bindings(session_id)

    def fingerprint(self, session_id: str, role: str) -> str:
        """Return a secret-free identity that forces future Agent rebuilding."""
        workspace = self._core.workspaces.get(session_id)
        servers = self.store.resolve(
            session_id, workspace.project_path or workspace.state_path, role
        )
        return _resolved_fingerprint(servers)

    def replace_bindings(
        self, session_id: str, bindings: Sequence[MCPBinding]
    ) -> tuple[MCPBinding, ...]:
        """Replace one Session's binding set and invalidate its bridge."""
        self.invalidate(session_id)
        return self.store.write_bindings(session_id, bindings)

    def probe(self, server_id: str) -> MCPPublicServer:
        """Connect once, persist the discovery snapshot, and disconnect."""
        stored = self.store.get_internal(server_id)
        server = MCPResolvedServer(
            record=stored.record,
            secrets=stored.secrets,
            tool_allowlist=(),
            project_root="",
        )
        bridge = MCPToolBridge([server])
        try:
            bridge.start()
            capabilities = bridge.capability_snapshot()
            probe = MCPProbe(ok=True, checked_at=time.time())
        except Exception as exc:
            capabilities = MCPCapabilities()
            probe = MCPProbe(
                ok=False,
                checked_at=time.time(),
                error=f"{type(exc).__name__}: {exc}"[:1000],
            )
        finally:
            bridge.close()
        self.invalidate()
        return self.store.set_probe(server_id, probe, capabilities)

    def tools(
        self, session: "Session", role: str, agent_name: str
    ) -> list[Tool]:
        """Return the Session's MCP tools allowed for one Agent."""
        session_id = session.execution.session_id
        workspace = self._core.workspaces.get(session_id)
        servers = self.store.resolve(
            session_id,
            workspace.project_path or workspace.state_path,
            role,
        )
        if not servers:
            return []
        fingerprint = _resolved_fingerprint(servers)
        key = (session_id, role)
        with self._lock:
            cached = self._bridges.get(key)
            if cached is None or cached[0] != fingerprint:
                if cached:
                    cached[1].close()
                bridge = MCPToolBridge(servers)
                bridge.start()
                self._bridges[key] = (fingerprint, bridge)
            else:
                bridge = cached[1]
        result: list[Tool] = []
        for tool in bridge.tools_for(agent_name):
            server = next(
                (
                    item
                    for item in servers
                    if tool.name.startswith(f"mcp.{item.record.name}.")
                ),
                None,
            )
            if server is None:
                continue
            allowed = server.tool_allowlist
            remote = tool.name.rsplit(".", 1)[-1]
            if not allowed or tool.name in allowed or remote in allowed:
                remote_handler = tool.handler

                def controlled_handler(
                    _handler: ToolCallable = remote_handler,
                    **arguments: object,
                ) -> object:
                    unregister = lambda: None
                    if session.run_control is not None:
                        unregister = session.run_control.for_agent(
                            agent_name
                        ).register_force_canceller(
                            lambda _request: bridge.cancel_agent(agent_name)
                        )
                    try:
                        return _handler(**arguments)
                    finally:
                        unregister()

                result.append(
                    Tool(
                        tool.name,
                        tool.description,
                        tool.schemas,
                        controlled_handler,
                    )
                )
        return result

    def invalidate(self, session_id: str | None = None) -> None:
        """Close cached bridges for one Session, or for every Session."""
        with self._lock:
            keys = [
                key
                for key in self._bridges
                if session_id is None or key[0] == session_id
            ]
            for key in keys:
                self._bridges.pop(key)[1].close()

    def close(self) -> None:
        """Close every cached bridge."""
        self.invalidate()


class MCPToolProvider:
    """Materialize MCP tools for one Agent within an Agent role."""

    def __init__(self, service: MCPService) -> None:
        self._service = service

    def materialize(
        self,
        session: "Session",
        policy: ToolPolicy,
        role: str,
        agent_name: str | None = None,
    ) -> list[Tool]:
        """Return the MCP tools bound to this Session and Agent."""
        return self._service.tools(
            session,
            role,
            agent_name or ("coordinator" if role == "coordinator" else "worker"),
        )


def mcp_tool_registration(service: MCPService) -> ToolProviderRegistration:
    """Register the Session-scoped MCP tool provider."""
    return ToolProviderRegistration(
        "mcp",
        MCPToolProvider(service),
        (ToolCategory("mcp", "MCP", "Session 绑定的外部 MCP 工具。"),),
        (),
    )
