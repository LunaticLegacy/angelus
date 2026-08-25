"""Official MCP Python SDK bridge for Agent tool calls.

One bridge owns a server configuration for a single Angelus run.  It discovers
remote tools through ``list_tools`` and exposes them as native
``llmfetcher.Tool`` instances, so an Agent calls MCP tools through its normal
tool loop instead of reconstructing JSON-RPC through Shell.
"""

from __future__ import annotations

import asyncio
import contextvars
import os
import re
import threading
from concurrent.futures import Future as ConcurrentFuture
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from llmfetcher.llm_types import Tool, ToolSchema


class MCPToolError(RuntimeError):
    """Raised when MCP configuration, discovery, or invocation fails."""


_NAME_PART = re.compile(r"[^A-Za-z0-9_-]+")


def _safe_name_part(value: str) -> str:
    value = _NAME_PART.sub("_", value.strip()).strip("_-")
    return value or "tool"


def _model_dump(value: Any) -> Any:
    """Return SDK Pydantic models as JSON-compatible values."""
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        return dump(mode="json")
    return value


@dataclass(frozen=True)
class MCPServer:
    """One validated user-selected MCP server definition."""

    name: str
    transport: str
    command: str = ""
    args: tuple[str, ...] = ()
    url: str = ""
    env: tuple[tuple[str, str], ...] = ()
    cwd: str = ""
    headers: tuple[tuple[str, str], ...] = ()

    @classmethod
    def from_config(cls, item: dict[str, Any]) -> "MCPServer":
        """Validate one decrypted registry or compatibility server mapping.

        Args:
            item: Structured server fields. ``env`` may be a legacy list of
                host variable names or a decrypted name/value mapping.

        Returns:
            Immutable normalized server definition.

        Raises:
            MCPToolError: If identity, transport, endpoint, args, environment,
                headers, or credentials are malformed.
        """
        name = str(item.get("name") or "").strip()
        transport = str(item.get("transport") or "stdio").strip().lower()
        if not name or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", name):
            raise MCPToolError("MCP server name must match [A-Za-z][A-Za-z0-9_-]{0,63}")
        if transport not in {"stdio", "streamable-http"}:
            raise MCPToolError(f"MCP server {name!r} has unsupported transport {transport!r}")
        command = str(item.get("command") or "").strip()
        url = str(item.get("url") or "").strip()
        if transport == "stdio" and not command:
            raise MCPToolError(f"MCP stdio server {name!r} needs a command")
        if transport != "stdio" and not re.fullmatch(r"https?://[^\s]+", url):
            raise MCPToolError(f"MCP {transport} server {name!r} needs an http(s) URL")
        args = item.get("args") or []
        env = item.get("env") or []
        headers = item.get("headers") or {}
        if not isinstance(args, list) or not all(isinstance(value, str) for value in args):
            raise MCPToolError(f"MCP server {name!r} args must be a string array")
        if isinstance(env, list):
            if not all(isinstance(value, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value) for value in env):
                raise MCPToolError(f"MCP server {name!r} env must contain environment-variable names")
            env_values = tuple((value, os.environ.get(value, "")) for value in env if value in os.environ)
        elif isinstance(env, dict) and all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(key)) and isinstance(value, str) for key, value in env.items()):
            env_values = tuple((str(key), value) for key, value in env.items())
        else:
            raise MCPToolError(f"MCP server {name!r} env must be a string array or mapping")
        if not isinstance(headers, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in headers.items()):
            raise MCPToolError(f"MCP server {name!r} headers must be a string mapping")
        bearer = str(item.get("bearer_token") or item.get("oauth_token") or "")
        if bearer and not any(key.lower() == "authorization" for key in headers):
            headers = {**headers, "Authorization": f"Bearer {bearer}"}
        return cls(name=name, transport=transport, command=command, args=tuple(args), url=url,
                   env=env_values, cwd=str(item.get("cwd") or "").strip(),
                   headers=tuple((key, value) for key, value in headers.items()))


class MCPToolBridge:
    """Keep one official SDK connection per server for the lifetime of a run.

    A dedicated asyncio thread owns every transport and its cleanup stack.
    Synchronous Agent tool handlers submit calls to that loop, which avoids
    moving SDK task-bound contexts between Worker threads. Failed calls are
    never replayed; a disconnected client is re-opened only for a later call.
    """

    def __init__(
        self,
        servers: list[dict[str, Any]],
        *,
        approval_handler: Any | None = None,
        sampling_handler: Any | None = None,
        event_handler: Any | None = None,
    ) -> None:
        """Validate servers and prepare a run-scoped connection manager.

        Args:
            servers: Decrypted, session-authorized server records.
            approval_handler: Blocking browser approval callback.
            sampling_handler: Blocking no-tools model completion callback.
            event_handler: Optional trace callback for connection/notification metadata.
        """
        if not all(isinstance(item, dict) for item in servers):
            raise MCPToolError("Every MCP server entry must be an object")
        parsed = [MCPServer.from_config(item) for item in servers]
        names = [server.name for server in parsed]
        if len(names) != len(set(names)):
            raise MCPToolError("MCP server names must be unique")
        self._servers = parsed
        self._servers_by_name = {server.name: server for server in parsed}
        self._tools: list[tuple[str, str, str, dict[str, Any], str]] = []
        self._closed = False
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, name="angelus-mcp", daemon=True)
        self._stack: AsyncExitStack | None = None
        self._owner_future: ConcurrentFuture[Any] | None = None
        self._close_requested: asyncio.Event | None = None
        self._reconnect_queue: asyncio.Queue[tuple[MCPServer, asyncio.Future[Any]]] | None = None
        self._owner_task: asyncio.Task[Any] | None = None
        self._ready = threading.Event()
        self._startup_error: BaseException | None = None
        self._clients: dict[str, Any] = {}
        self._calls: dict[str, set[ConcurrentFuture[Any]]] = {}
        self._calls_lock = threading.Lock()
        self._project_root = str(next((item.get("_project_root", "") for item in servers if item.get("_project_root")), ""))
        self._approval_handler = approval_handler
        self._sampling_handler = sampling_handler
        self._event_handler = event_handler
        self._current_agent: contextvars.ContextVar[str] = contextvars.ContextVar("mcp_agent", default="coordinator")
        self._active_server_agents: dict[str, set[str]] = {}

    def _approval_agent(self, server: str) -> str:
        """Return the sole active caller for a server, or coordinator fallback."""
        with self._calls_lock:
            agents = self._active_server_agents.get(server, set())
            return next(iter(agents)) if len(agents) == 1 else self._current_agent.get()

    def _emit(self, kind: str, server: str, data: Any = None) -> None:
        """Forward credential-free MCP runtime metadata to the host Trace."""
        if self._event_handler is not None:
            try:
                self._event_handler({"event": "mcp_trace", "kind": kind, "server": server, "data": _model_dump(data)})
            except Exception:
                pass

    def _run_loop(self) -> None:
        """Own the asyncio loop used by all run-scoped MCP transports."""
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def start(self) -> list[Tool]:
        """Discover remote MCP tools and return native synchronous wrappers."""
        if self._closed:
            raise MCPToolError("MCP bridge is closed")
        if not self._thread.is_alive():
            self._thread.start()
        self._owner_future = asyncio.run_coroutine_threadsafe(self._own_connections(), self._loop)
        if not self._ready.wait(timeout=120):
            raise MCPToolError("MCP connection startup timed out")
        if self._startup_error is not None:
            raise self._startup_error
        return self.tools_for("coordinator")

    def tools_for(self, agent: str, allowed: set[str] | None = None) -> list[Tool]:
        """Create wrappers attributed to one Agent and optional allowlist.

        Args:
            agent: Concrete owner used for targeted cancellation.
            allowed: Public or remote tool names permitted for this Agent.
                ``None`` permits every discovered tool.
        """
        return [
            Tool(
                name=public_name,
                description=f"MCP {server_name}/{tool_name}: {description}".strip(),
                schemas=ToolSchema(raw_schema=schema),
                handler=self._handler(server_name, tool_name, agent),
            )
            for public_name, server_name, tool_name, schema, description in self._tools
            if allowed is None or public_name in allowed or tool_name in allowed
        ]

    def close(self) -> None:
        """Close every persistent transport and stop the owning event loop."""
        if self._closed:
            return
        self._closed = True
        if self._thread.is_alive():
            try:
                if self._close_requested is not None:
                    self._loop.call_soon_threadsafe(self._close_requested.set)
                if self._owner_future is not None:
                    try:
                        self._owner_future.result(timeout=15)
                    except Exception:
                        pass
            finally:
                self._loop.call_soon_threadsafe(self._loop.stop)
                self._thread.join(timeout=5)

    def cancel_agent(self, agent: str) -> int:
        """Cancel in-flight MCP calls attributed to one Agent.

        Args:
            agent: Concrete Agent identity, or ``all`` for every call.

        Returns:
            Number of futures asked to cancel.
        """
        with self._calls_lock:
            futures = [future for owner, owned in self._calls.items() if agent == "all" or owner == agent for future in owned]
        for future in futures:
            future.cancel()
        return len(futures)

    def _handler(self, server_name: str, tool_name: str, agent: str):
        """Build a synchronous tool handler attributed to ``agent``."""
        def call(**arguments: Any) -> dict[str, Any]:
            """Submit one remote call and track its Agent-owned future."""
            if self._closed:
                raise MCPToolError("MCP bridge is closed")
            future = asyncio.run_coroutine_threadsafe(
                self._call(server_name, tool_name, arguments, agent), self._loop
            )
            with self._calls_lock:
                self._calls.setdefault(agent, set()).add(future)
            try:
                return future.result()
            finally:
                with self._calls_lock:
                    self._calls.get(agent, set()).discard(future)
        return call

    async def _open_client(self, server: MCPServer) -> Any:
        """Open and retain one SDK client inside the run cleanup stack."""
        try:
            from mcp import Client
            from mcp.client.session import ClientSession
            from mcp.client.stdio import StdioServerParameters, stdio_client
        except ImportError as exc:
            raise MCPToolError("MCP SDK is unavailable; install dependency 'mcp>=2,<3'") from exc
        if self._stack is None:
            raise MCPToolError("MCP connection manager is not started")

        async def approve_sampling(context: Any, params: Any) -> Any:
            """Approve and execute stateless no-tools session sampling."""
            from mcp_types import ErrorData
            if self._approval_handler is None or self._sampling_handler is None:
                return ErrorData(code=-32603, message="Sampling requires browser approval")
            details = {"max_tokens": int(getattr(params, "max_tokens", 0) or 0)}
            decision = await asyncio.to_thread(
                self._approval_handler, server.name, self._approval_agent(server.name), "sampling", details,
            )
            if decision.get("decision") != "allow":
                return ErrorData(code=-32603, message="Sampling was rejected")
            return await asyncio.to_thread(self._sampling_handler, params)

        async def approve_elicitation(context: Any, params: Any) -> Any:
            """Return only browser-submitted elicitation fields to the server."""
            from mcp_types import ElicitResult, ErrorData
            if self._approval_handler is None:
                return ErrorData(code=-32603, message="Elicitation requires browser approval")
            dumped = _model_dump(params)
            schema = dumped.get("requestedSchema", dumped.get("requested_schema", {})) if isinstance(dumped, dict) else {}
            details = {"fields": sorted((schema.get("properties") or {}).keys()) if isinstance(schema, dict) else []}
            decision = await asyncio.to_thread(
                self._approval_handler, server.name, self._approval_agent(server.name), "elicitation", details,
            )
            if decision.get("decision") != "allow":
                return ElicitResult(action="decline")
            return ElicitResult(action="accept", content=decision.get("content") or {})

        async def list_roots(context: Any) -> Any:
            """Expose only the current session's bound project directory."""
            from mcp_types import ErrorData, ListRootsResult, Root
            if not self._project_root:
                return ErrorData(code=-32603, message="No project root is bound")
            return ListRootsResult(roots=[Root(uri=Path(self._project_root).resolve().as_uri(), name="project_root")])

        async def log_message(params: Any) -> None:
            """Relay server logging notifications into the run Trace."""
            self._emit("logging", server.name, params)

        async def message_handler(message: Any) -> None:
            """Relay resource/progress/connection notifications into Trace."""
            self._emit("notification", server.name, message)

        client_options = {
            "sampling_callback": approve_sampling,
            "elicitation_callback": approve_elicitation,
            "list_roots_callback": list_roots,
            "logging_callback": log_message,
            "message_handler": message_handler,
        }
        if server.transport == "stdio":
            parameters = StdioServerParameters(
                command=server.command, args=list(server.args),
                env=dict(server.env) or None, cwd=server.cwd or None,
            )
            # Stdio is the initialized stream protocol. Use the SDK session
            # directly so no HTTP-style discovery probe can stall startup.
            read_stream, write_stream = await self._stack.enter_async_context(
                stdio_client(parameters)
            )
            client = await self._stack.enter_async_context(
                ClientSession(read_stream, write_stream, **client_options)
            )
            await client.initialize()
        else:
            if server.headers:
                from mcp.client.streamable_http import streamable_http_client
                transport = streamable_http_client(server.url, headers=dict(server.headers))
                client = await self._stack.enter_async_context(Client(transport, **client_options))
            else:
                client = await self._stack.enter_async_context(Client(server.url, **client_options))
        self._clients[server.name] = client
        self._emit("connected", server.name)
        return client

    async def _ensure_client(self, server: MCPServer) -> Any:
        """Return a live client, asking the stack-owning task to reconnect."""
        client = self._clients.get(server.name)
        if client is not None:
            return client
        if asyncio.current_task() is self._owner_task:
            return await self._open_client(server)
        if self._reconnect_queue is None:
            raise MCPToolError("MCP connection owner is unavailable")
        future = self._loop.create_future()
        self._reconnect_queue.put_nowait((server, future))
        return await future

    async def _own_connections(self) -> None:
        """Open and close task-bound SDK transports in the same asyncio task."""
        self._stack = AsyncExitStack()
        await self._stack.__aenter__()
        self._owner_task = asyncio.current_task()
        self._close_requested = asyncio.Event()
        self._reconnect_queue = asyncio.Queue()
        try:
            await self._discover_all()
        except BaseException as exc:
            self._startup_error = exc
            self._ready.set()
        else:
            self._ready.set()
            while not self._close_requested.is_set():
                close_task = asyncio.create_task(self._close_requested.wait())
                reconnect_task = asyncio.create_task(self._reconnect_queue.get())
                done, pending = await asyncio.wait(
                    {close_task, reconnect_task}, return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                if close_task in done:
                    break
                requested_server, response = reconnect_task.result()
                try:
                    # Another request for the same server may already have
                    # restored it while this queue item was waiting.
                    response.set_result(await self._ensure_client(requested_server))
                except Exception as exc:
                    response.set_exception(exc)
        finally:
            self.cancel_agent("all")
            self._clients.clear()
            if self._stack is not None:
                await self._stack.aclose()
                self._stack = None
            self._owner_task = None
            self._reconnect_queue = None
            self._emit("closed", "all")

    async def _discover_all(self) -> None:
        """Open each configured server once and replace the tool cache."""
        self._tools.clear()
        for server in self._servers:
            client = await self._ensure_client(server)
            await self._discover_tools(server, client)

    async def _discover_tools(self, server: MCPServer, client: Any) -> None:
        """Page through one live client's tools into the public-name cache.

        Args:
            server: Server owning the discovered tools.
            client: Connected official SDK client or session.
        """
        cursor: str | None = None
        while True:
            try:
                listing = await client.list_tools(cursor=cursor)
            except TypeError:
                from mcp_types import PaginatedRequestParams
                listing = await client.list_tools(
                    params=PaginatedRequestParams(cursor=cursor)
                )
            for tool in getattr(listing, "tools", []):
                tool_name = str(getattr(tool, "name", "")).strip()
                if not tool_name:
                    continue
                schema = _model_dump(getattr(tool, "input_schema", {}))
                if not isinstance(schema, dict):
                    schema = {"type": "object", "properties": {}}
                schema.setdefault("type", "object")
                schema.setdefault("properties", {})
                public_name = f"mcp.{_safe_name_part(server.name)}.{_safe_name_part(tool_name)}"
                if any(existing[0] == public_name for existing in self._tools):
                    raise MCPToolError(f"MCP tool name collision: {public_name}")
                description = str(getattr(tool, "description", "") or getattr(tool, "title", "") or tool_name)
                self._tools.append((public_name, server.name, tool_name, schema, description))
            cursor = getattr(listing, "next_cursor", None)
            if not cursor:
                return

    def capability_snapshot(self) -> dict[str, Any]:
        """Discover tools, resources, templates, and prompts on live clients."""
        if self._closed:
            raise MCPToolError("MCP bridge is closed")
        return asyncio.run_coroutine_threadsafe(
            self._capability_snapshot_async(), self._loop
        ).result(timeout=120)

    def read_resource(self, server_name: str, uri: str) -> Any:
        """Read one MCP resource through the persistent server connection."""
        return self._submit_client_method(server_name, "read_resource", uri)

    def subscribe_resource(self, server_name: str, uri: str) -> Any:
        """Subscribe to one resource; later notifications enter Trace."""
        return self._submit_client_method(server_name, "subscribe_resource", uri)

    def get_prompt(self, server_name: str, name: str, arguments: dict[str, str] | None = None) -> Any:
        """Get one MCP prompt using the persistent server connection."""
        return self._submit_client_method(server_name, "get_prompt", name, arguments)

    def complete(
        self, server_name: str, reference: Any, argument: dict[str, str],
        context_arguments: dict[str, str] | None = None,
    ) -> Any:
        """Request MCP completion for a prompt or resource template reference."""
        return self._submit_client_method(server_name, "complete", reference, argument, context_arguments)

    def _submit_client_method(self, server_name: str, method: str, *args: Any) -> Any:
        """Run one non-tool MCP capability call on the owning event loop."""
        future = asyncio.run_coroutine_threadsafe(
            self._client_method(server_name, method, *args), self._loop
        )
        return future.result(timeout=120)

    async def _client_method(self, server_name: str, method: str, *args: Any) -> Any:
        """Invoke a named SDK client method without automatic replay."""
        server = self._servers_by_name.get(server_name)
        if server is None:
            raise MCPToolError(f"MCP server {server_name!r} is not configured")
        client = await self._ensure_client(server)
        result = await getattr(client, method)(*args)
        return _model_dump(result)

    async def _capability_snapshot_async(self) -> dict[str, Any]:
        """Collect JSON-safe full discovery data from every live server."""
        snapshot: dict[str, Any] = {"tools": [], "resources": [], "resource_templates": [], "prompts": []}
        for server in self._servers:
            client = await self._ensure_client(server)
            snapshot["tools"].extend(public for public, owner, *_ in self._tools if owner == server.name)
            for method, key, attribute in (
                (client.list_resources, "resources", "resources"),
                (client.list_resource_templates, "resource_templates", "resource_templates"),
                (client.list_prompts, "prompts", "prompts"),
            ):
                try:
                    result = await method()
                except Exception:
                    continue
                values = getattr(result, attribute, [])
                snapshot[key].extend(
                    {"server": server.name, **(_model_dump(value) if isinstance(_model_dump(value), dict) else {"value": str(value)})}
                    for value in values
                )
        return snapshot

    async def _call(
        self, server_name: str, tool_name: str, arguments: dict[str, Any], agent: str,
    ) -> dict[str, Any]:
        """Invoke one tool once, discarding a stale client after failure.

        Args:
            server_name: Configured server identity.
            tool_name: Remote tool name without Angelus prefix.
            arguments: JSON-compatible tool arguments from the Agent.
            agent: Concrete Agent used for server-initiated approvals.

        Returns:
            JSON-compatible SDK result mapping.

        Raises:
            MCPToolError: If the server is not configured.
            Exception: The original SDK/transport failure; it is never replayed.
        """
        server = self._servers_by_name.get(server_name)
        if server is None:
            raise MCPToolError(f"MCP server {server_name!r} is not configured")
        client = await self._ensure_client(server)
        agent_token = self._current_agent.set(agent)
        with self._calls_lock:
            self._active_server_agents.setdefault(server_name, set()).add(agent)
        try:
            result = await client.call_tool(tool_name, arguments)
            payload = _model_dump(result)
            return payload if isinstance(payload, dict) else {"result": payload}
        except Exception:
            # Do not replay this possibly side-effecting call. The next
            # invocation may reconnect after the stale client is discarded.
            self._clients.pop(server.name, None)
            self._emit("disconnected", server.name)
            raise
        finally:
            with self._calls_lock:
                owners = self._active_server_agents.get(server_name, set())
                owners.discard(agent)
                if not owners:
                    self._active_server_agents.pop(server_name, None)
            self._current_agent.reset(agent_token)


def create_mcp_tools(
    servers: list[dict[str, Any]],
    *,
    approval_handler: Any | None = None,
    sampling_handler: Any | None = None,
    event_handler: Any | None = None,
) -> tuple[MCPToolBridge, list[Tool]]:
    """Connect configured servers and expose remote tools natively.

    Args:
        servers: Decrypted server definitions.
        approval_handler: Optional browser approval callback.
        sampling_handler: Optional no-tools model callback.
        event_handler: Optional runtime Trace callback.
    """
    bridge = MCPToolBridge(
        servers, approval_handler=approval_handler,
        sampling_handler=sampling_handler, event_handler=event_handler,
    )
    try:
        return bridge, bridge.start()
    except Exception:
        bridge.close()
        raise


__all__ = ["MCPServer", "MCPToolBridge", "MCPToolError", "create_mcp_tools"]
