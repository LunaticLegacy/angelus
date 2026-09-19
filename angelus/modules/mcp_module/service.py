"""Managed MCP lifecycle plus dynamic ToolRegistry provider."""
from __future__ import annotations

import hashlib
import json
import threading
import time
from typing import TYPE_CHECKING, Any

from llmfetcher import Tool
from ..tool_module import ToolCategory, ToolPolicy
from ..tool_module.tool_registry import ToolProviderRegistration
from .bridge import MCPToolBridge
from .store import MCPStore

if TYPE_CHECKING:
    from ...core import AngelusCore


class MCPService:
    def __init__(self, core: "AngelusCore") -> None:
        self._core = core; self.store = MCPStore(core.state_root); self._lock = threading.RLock(); self._bridges: dict[tuple[str,str], tuple[str,MCPToolBridge]] = {}
    def list_servers(self): return self.store.list()
    def create_server(self, payload): self.invalidate(); return self.store.create(payload)
    def replace_server(self, server_id, payload): self.invalidate(); return self.store.replace(server_id,payload)
    def remove_server(self, server_id): self.invalidate(); return self.store.remove(server_id)
    def bindings(self, session_id): return self.store.read_bindings(session_id)
    def fingerprint(self, session_id: str, role: str) -> str:
        """Return a secret-free identity that forces future Agent rebuilding."""
        workspace=self._core.workspaces.get(session_id)
        servers=self.store.resolve(session_id,workspace.project_path or workspace.state_path,role)
        safe=[{k:v for k,v in item.items() if k not in {"headers","env","bearer_token","oauth_client_secret","oauth_token","oauth_refresh_token"}} for item in servers]
        return hashlib.sha256(json.dumps(safe,sort_keys=True,default=str).encode()).hexdigest()
    def replace_bindings(self, session_id, bindings): self.invalidate(session_id); return self.store.write_bindings(session_id,bindings)
    def probe(self, server_id: str) -> dict[str, Any]:
        bridge = MCPToolBridge([self.store.get_internal(server_id)])
        try:
            bridge.start(); capabilities = bridge.capability_snapshot(); probe={"ok":True,"checked_at":time.time(),"error":""}
        except Exception as exc:
            capabilities={}; probe={"ok":False,"checked_at":time.time(),"error":f"{type(exc).__name__}: {exc}"[:1000]}
        finally: bridge.close()
        self.invalidate(); return self.store.set_probe(server_id,probe,capabilities)
    def tools(self, session: Any, role: str, agent_name: str) -> list[Tool]:
        session_id=session.execution.session_id; workspace=self._core.workspaces.get(session_id); servers=self.store.resolve(session_id, workspace.project_path or workspace.state_path, role)
        if not servers: return []
        fingerprint=hashlib.sha256(json.dumps(servers,sort_keys=True,default=str).encode()).hexdigest(); key=(session_id,role)
        with self._lock:
            cached=self._bridges.get(key)
            if cached is None or cached[0] != fingerprint:
                if cached: cached[1].close()
                bridge=MCPToolBridge(servers); bridge.start(); self._bridges[key]=(fingerprint,bridge)
            else: bridge=cached[1]
        result=[]
        for tool in bridge.tools_for(agent_name):
            server=next((x for x in servers if tool.name.startswith(f"mcp.{x['name']}.")),None)
            if server is None: continue
            allowed=server["tool_allowlist"]
            remote=tool.name.rsplit(".",1)[-1]
            if not allowed or tool.name in allowed or remote in allowed:
                remote_handler=tool.handler
                def controlled_handler(_handler=remote_handler, **arguments: Any):
                    unregister=lambda: None
                    if session.run_control is not None:
                        unregister=session.run_control.for_agent(agent_name).register_force_canceller(lambda _request: bridge.cancel_agent(agent_name))
                    try: return _handler(**arguments)
                    finally: unregister()
                result.append(Tool(tool.name,tool.description,tool.schemas,controlled_handler))
        return result
    def invalidate(self, session_id: str | None = None) -> None:
        with self._lock:
            keys=[k for k in self._bridges if session_id is None or k[0]==session_id]
            for key in keys: self._bridges.pop(key)[1].close()
    def close(self) -> None: self.invalidate()


class MCPToolProvider:
    def __init__(self, service: MCPService) -> None: self._service=service
    def materialize(self, session: Any, policy: ToolPolicy, role: str, agent_name: str | None = None) -> list[Tool]:
        return self._service.tools(session,role,agent_name or ("coordinator" if role=="coordinator" else "worker"))


def mcp_tool_registration(service: MCPService) -> ToolProviderRegistration:
    return ToolProviderRegistration("mcp", MCPToolProvider(service), (ToolCategory("mcp","MCP","Session 绑定的外部 MCP 工具。"),), ())
