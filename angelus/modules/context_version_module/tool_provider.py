"""ToolRegistry provider for versioned edits of the calling Agent."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any
from llmfetcher import Tool, ToolParameter, ToolSchema

from ..tool_module import ToolCategory, ToolDefinition, ToolPolicy
from ..tool_module.tool_registry import ToolProviderRegistration
from .store import ContextEditOperation, ContextVersionError, ContextVersionStore

if TYPE_CHECKING:
    from ...core import AngelusCore


class ContextVersionToolProvider:
    def __init__(self, core: "AngelusCore") -> None: self._core = core

    def materialize(self, session: Any, policy: ToolPolicy, role: str, agent_name: str | None = None) -> list[Tool]:
        owner = agent_name or ("coordinator" if role == "coordinator" else "worker")
        def store() -> ContextVersionStore:
            agent = session.coordinator if owner == session.coordinator_name else session.swarm.get_agent(owner)
            if agent is None: raise ContextVersionError("calling Agent is unavailable")
            return ContextVersionStore(agent, owner)
        def inspect() -> dict[str, Any]: return store().inspect()
        def edit(expected_revision_id: str | None, operations: list[dict[str, Any]], reason: str = "") -> dict[str, Any]:
            parsed = [ContextEditOperation(str(x.get("kind", "")), str(x.get("target_record_id", "")), str(x.get("content", "")), str(x.get("role", "user"))) for x in operations if isinstance(x, dict)]
            return store().apply(expected_revision_id, parsed, reason)
        def restore(expected_revision_id: str | None, revision_id: str, reason: str = "") -> dict[str, Any]: return store().restore(expected_revision_id, revision_id, reason)
        candidates = [
            ("inspect_agent_context", inspect, ToolSchema()),
            ("edit_agent_context", edit, ToolSchema(properties=[ToolParameter("expected_revision_id", required=False), ToolParameter("operations", type="array"), ToolParameter("reason", required=False, default="")])),
            ("restore_agent_context", restore, ToolSchema(properties=[ToolParameter("expected_revision_id", required=False), ToolParameter("revision_id"), ToolParameter("reason", required=False, default="")]))]
        return [Tool(name, "Versioned operation on this Agent's own active context.", schema, handler) for name, handler, schema in candidates if policy.allows("context_version", name)]


def context_version_tool_registration(core: "AngelusCore") -> ToolProviderRegistration:
    names = ("inspect_agent_context", "edit_agent_context", "restore_agent_context")
    return ToolProviderRegistration("context_version", ContextVersionToolProvider(core),
        (ToolCategory("context_version", "上下文版本", "检查、编辑并向前恢复当前 Agent 上下文。"),),
        tuple(ToolDefinition(name, "context_version", name, "当前 Agent 的版本化上下文操作。", "context_version", frozenset({"coordinator", "worker"})) for name in names))
