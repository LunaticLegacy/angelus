"""Managed MCP lifecycle plus dynamic ToolRegistry provider."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from uuid import uuid4
from collections.abc import Callable, Mapping, Sequence
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
from .runtime import MCPRegistrySnapshot, MCPRuntimeKey, MCPRuntimeManager, MCPServerSnapshot


@dataclass
class MCPOperation:
    id: str
    kind: str
    state: str = "queued"
    result: object | None = None
    error: str | None = None


def _probe_error(exc: BaseException) -> str:
    """Flatten AnyIO/TaskGroup wrappers into an actionable probe error."""
    if isinstance(exc, BaseExceptionGroup):
        return "; ".join(_probe_error(item) for item in exc.exceptions)
    code = getattr(exc, "code", None)
    data = getattr(exc, "data", None)
    detail = str(exc)
    if code is not None:
        detail = f"{detail} (code {code})"
    if data not in (None, ""):
        detail = f"{detail}: {data}"
    return f"{type(exc).__name__}: {detail}"

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
        self._runtimes = MCPRuntimeManager()
        self._revision = 0
        self._operations: dict[str, MCPOperation] = {}
        self._operation_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="angelus-mcp-op")

    def revision(self) -> int:
        """Return the in-process catalog revision used by new attempts."""
        with self._lock:
            return self._revision

    def operation(self, operation_id: str) -> MCPOperation:
        with self._lock:
            operation = self._operations.get(operation_id)
            if operation is None:
                raise KeyError(operation_id)
            return replace(operation)

    def register_async(self, payload: Mapping[str, JsonValue]) -> MCPOperation:
        operation = self._new_operation("register")
        self._operation_pool.submit(self._run_operation, operation.id, lambda: self.create_server(payload))
        return operation

    def remove_async(self, server_id: str) -> MCPOperation:
        operation = self._new_operation("delete")
        self._operation_pool.submit(self._run_operation, operation.id, lambda: self.remove_server(server_id))
        return operation

    def _new_operation(self, kind: str) -> MCPOperation:
        operation = MCPOperation(uuid4().hex, kind)
        with self._lock:
            self._operations[operation.id] = operation
        return operation

    def _run_operation(self, operation_id: str, action: Callable[[], object]) -> None:
        with self._lock:
            operation = self._operations[operation_id]
            operation.state = "running"
        try:
            result = action()
        except Exception as exc:
            with self._lock:
                operation.state = "failed"
                operation.error = f"{type(exc).__name__}: {exc}"
        else:
            with self._lock:
                operation.state = "completed"
                operation.result = result

    def snapshot(self, session_id: str, role: str) -> MCPRegistrySnapshot:
        """Return a secret-free, revisioned MCP view for an attempt."""
        workspace = self._core.workspaces.get(session_id)
        servers = self.store.resolve(session_id, workspace.project_path or workspace.state_path, role)
        return MCPRegistrySnapshot(
            revision=self.revision(),
            servers=tuple(MCPServerSnapshot(
                server_id=item.record.id, server_revision=item.record.updated_at,
                name=item.record.name, transport=item.record.transport,
                tool_allowlist=item.tool_allowlist,
            ) for item in servers),
        )

    def list_servers(self) -> tuple[MCPPublicServer, ...]:
        """Return every configured server without credentials."""
        return self.store.list()

    def create_server(self, payload: Mapping[str, JsonValue]) -> MCPPublicServer:
        """Create one server and invalidate cached bridges."""
        self.invalidate()
        result = self.store.create(payload)
        with self._lock:
            self._revision += 1
        return result

    def replace_server(
        self, server_id: str, payload: Mapping[str, JsonValue]
    ) -> MCPPublicServer:
        """Replace one server and invalidate cached bridges."""
        self.invalidate()
        result = self.store.replace(server_id, payload)
        with self._lock:
            self._revision += 1
        return result

    def remove_server(self, server_id: str) -> None:
        """Delete one server and invalidate cached bridges."""
        self.invalidate()
        self.store.remove(server_id)
        with self._lock:
            self._revision += 1

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
        result = self.store.write_bindings(session_id, bindings)
        with self._lock:
            self._revision += 1
        return result

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
                error=_probe_error(exc)[:1000],
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
                try:
                    runtime = self._runtimes.ensure_ready(
                        MCPRuntimeKey(session_id, fingerprint), servers
                    )
                    bridge = runtime.bridge
                except Exception as exc:
                    details = "; ".join(
                        f"server={item.record.name} transport={item.record.transport}"
                        for item in servers
                    )
                    raise MCPToolError(
                        f"MCP connecting_mcp failed ({details}): {type(exc).__name__}: {exc}"
                    ) from exc
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

    def invalidate(self, session_id: str | None = None, *, timeout: float = 5.0) -> None:
        """Close cached bridges for one Session, or for every Session."""
        with self._lock:
            keys = [
                key
                for key in self._bridges
                if session_id is None or key[0] == session_id
            ]
            runtimes = [self._bridges.pop(key)[1] for key in keys]
        # Slow transport cleanup must never run under the service lock.
        for bridge in runtimes:
            bridge.close(timeout=timeout)
        if session_id is None:
            self._runtimes.close(timeout=timeout)
        else:
            self._runtimes.drain(server_id=session_id, timeout=timeout)

    def close(self, *, timeout: float = 5.0) -> None:
        """Close every cached bridge."""
        self.invalidate(timeout=timeout)
        self._operation_pool.shutdown(wait=False, cancel_futures=True)


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
