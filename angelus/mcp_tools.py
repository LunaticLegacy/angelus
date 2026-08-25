"""Official MCP Python SDK bridge for Agent tool calls.

One bridge owns a server configuration for a single Angelus run.  It discovers
remote tools through ``list_tools`` and exposes them as native
``llmfetcher.Tool`` instances, so an Agent calls MCP tools through its normal
tool loop instead of reconstructing JSON-RPC through Shell.
"""

from __future__ import annotations

import asyncio
import os
import re
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
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
    env: tuple[str, ...] = ()
    cwd: str = ""

    @classmethod
    def from_config(cls, item: dict[str, Any]) -> "MCPServer":
        name = str(item.get("name") or "").strip()
        transport = str(item.get("transport") or "stdio").strip().lower()
        if not name or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", name):
            raise MCPToolError("MCP server name must match [A-Za-z][A-Za-z0-9_-]{0,63}")
        if transport not in {"stdio", "streamable-http", "sse"}:
            raise MCPToolError(f"MCP server {name!r} has unsupported transport {transport!r}")
        command = str(item.get("command") or "").strip()
        url = str(item.get("url") or "").strip()
        if transport == "stdio" and not command:
            raise MCPToolError(f"MCP stdio server {name!r} needs a command")
        if transport != "stdio" and not re.fullmatch(r"https?://[^\s]+", url):
            raise MCPToolError(f"MCP {transport} server {name!r} needs an http(s) URL")
        args = item.get("args") or []
        env = item.get("env") or []
        if not isinstance(args, list) or not all(isinstance(value, str) for value in args):
            raise MCPToolError(f"MCP server {name!r} args must be a string array")
        if not isinstance(env, list) or not all(
            isinstance(value, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value)
            for value in env
        ):
            raise MCPToolError(f"MCP server {name!r} env must contain environment-variable names")
        return cls(name=name, transport=transport, command=command, args=tuple(args), url=url,
                   env=tuple(env), cwd=str(item.get("cwd") or "").strip())


class MCPToolBridge:
    """Use a fresh official SDK client context for each discovery or call.

    MCP SDK v2 binds transport cleanup to the async task that opened it.  The
    synchronous Agent loop can invoke tools on different worker threads, so
    opening and closing a Client inside each operation is the safe, portable
    boundary.  It still uses the SDK for the complete MCP lifecycle rather
    than sending JSON-RPC from Angelus itself.
    """

    def __init__(self, servers: list[dict[str, Any]]) -> None:
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

    def start(self) -> list[Tool]:
        """Discover remote MCP tools and return native synchronous wrappers."""
        if self._closed:
            raise MCPToolError("MCP bridge is closed")
        asyncio.run(self._discover_all())
        return [
            Tool(
                name=public_name,
                description=f"MCP {server_name}/{tool_name}: {description}".strip(),
                schemas=ToolSchema(raw_schema=schema),
                handler=self._handler(server_name, tool_name),
            )
            for public_name, server_name, tool_name, schema, description in self._tools
        ]

    def close(self) -> None:
        """Mark wrappers closed; SDK transports already close per operation."""
        self._closed = True

    def _handler(self, server_name: str, tool_name: str):
        def call(**arguments: Any) -> dict[str, Any]:
            if self._closed:
                raise MCPToolError("MCP bridge is closed")
            return asyncio.run(self._call(server_name, tool_name, arguments))
        return call

    @asynccontextmanager
    async def _client(self, server: MCPServer):
        try:
            from mcp import Client
            from mcp.client.stdio import StdioServerParameters, stdio_client
        except ImportError as exc:
            raise MCPToolError("MCP SDK is unavailable; install dependency 'mcp>=2,<3'") from exc
        async with AsyncExitStack() as stack:
            if server.transport == "stdio":
                passed_env = {name: os.environ[name] for name in server.env if name in os.environ}
                parameters = StdioServerParameters(
                    command=server.command,
                    args=list(server.args),
                    env=passed_env or None,
                    cwd=server.cwd or None,
                )
                client = await stack.enter_async_context(Client(stdio_client(parameters)))
            elif server.transport == "streamable-http":
                client = await stack.enter_async_context(Client(server.url))
            else:
                from mcp.client.sse import sse_client
                client = await stack.enter_async_context(Client(sse_client(server.url)))
            yield client

    async def _discover_all(self) -> None:
        self._tools.clear()
        for server in self._servers:
            async with self._client(server) as client:
                await self._discover_tools(server, client)

    async def _discover_tools(self, server: MCPServer, client: Any) -> None:
        cursor: str | None = None
        while True:
            listing = await client.list_tools(cursor=cursor)
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

    async def _call(self, server_name: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        server = self._servers_by_name.get(server_name)
        if server is None:
            raise MCPToolError(f"MCP server {server_name!r} is not configured")
        async with self._client(server) as client:
            result = await client.call_tool(tool_name, arguments)
            payload = _model_dump(result)
            return payload if isinstance(payload, dict) else {"result": payload}


def create_mcp_tools(servers: list[dict[str, Any]]) -> tuple[MCPToolBridge, list[Tool]]:
    """Connect configured MCP servers and expose their remote tools natively."""
    bridge = MCPToolBridge(servers)
    try:
        return bridge, bridge.start()
    except Exception:
        bridge.close()
        raise


__all__ = ["MCPServer", "MCPToolBridge", "MCPToolError", "create_mcp_tools"]
