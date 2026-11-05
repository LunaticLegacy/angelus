"""ToolRegistry provider for versioned edits of the calling Agent."""
from __future__ import annotations

from dataclasses import asdict
import json
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
        def search_archive(query: str, limit: int = 5) -> str:
            return json.dumps(asdict(store().search_archive(query, limit)), ensure_ascii=False)
        def read_archive(timeline: int) -> str:
            return json.dumps(asdict(store().read_archive(timeline)), ensure_ascii=False)
        def edit(expected_revision_id: str | None, operations: list[dict[str, Any]], reason: str = "") -> dict[str, Any]:
            parsed = [ContextEditOperation(str(x.get("kind", "")), str(x.get("target_record_id", "")), str(x.get("content", "")), str(x.get("role", "user"))) for x in operations]
            return store().apply(expected_revision_id, parsed, reason)
        def restore(expected_revision_id: str | None, revision_id: str, reason: str = "") -> dict[str, Any]: return store().restore(expected_revision_id, revision_id, reason)
        candidates = [
            ("inspect_agent_context", inspect, ToolSchema()),
            ("search_agent_archive", search_archive, ToolSchema(properties=[ToolParameter("query"), ToolParameter("limit", type="integer", required=False, default=5)])),
            ("read_agent_archive", read_archive, ToolSchema(properties=[ToolParameter("timeline", type="integer")])),
            ("edit_agent_context", edit, ToolSchema(properties=[ToolParameter("expected_revision_id", required=False), ToolParameter("operations", type="array"), ToolParameter("reason", required=False, default="")])),
            ("restore_agent_context", restore, ToolSchema(properties=[ToolParameter("expected_revision_id", required=False), ToolParameter("revision_id"), ToolParameter("reason", required=False, default="")]))]
        descriptions = {
            "inspect_agent_context": "检视当前 Agent 的上下文记录、当前修订和历史版本；只读。",
            "search_agent_archive": "在当前 Agent 已被压缩掉的原始上下文中做词法检索，返回带时间线与角色的证据；只读。",
            "read_agent_archive": "按 timeline 读取一条已被压缩掉的完整原始记录；只读。",
            "edit_agent_context": "按记录替换、删除或插入上下文内容，并创建新的修订版本。",
            "restore_agent_context": "从指定历史修订创建新的恢复版本；不会覆盖历史修订。",
        }
        return [Tool(name, descriptions[name], schema, handler) for name, handler, schema in candidates if policy.allows("context_version", name)]


def context_version_tool_registration(core: "AngelusCore") -> ToolProviderRegistration:
    names = ("inspect_agent_context", "search_agent_archive", "read_agent_archive", "edit_agent_context", "restore_agent_context")
    return ToolProviderRegistration("context_version", ContextVersionToolProvider(core),
        (ToolCategory("context_version", "上下文版本", "检查、搜索、编辑并向前恢复当前 Agent 上下文。"),),
        tuple(ToolDefinition(name, "context_version", {
            "inspect_agent_context": "检视当前上下文",
            "search_agent_archive": "搜索已压缩上下文",
            "read_agent_archive": "读取归档记录",
            "edit_agent_context": "编辑上下文",
            "restore_agent_context": "恢复上下文版本",
        }[name], {
            "inspect_agent_context": "检视当前 Agent 的上下文记录、当前修订和历史版本；只读。",
            "search_agent_archive": "在当前 Agent 已被压缩掉的原始上下文中做词法检索，返回带时间线与角色的证据；只读。",
            "read_agent_archive": "按 timeline 读取一条已被压缩掉的完整原始记录；只读。",
            "edit_agent_context": "按记录替换、删除或插入上下文内容，并创建新的修订版本。",
            "restore_agent_context": "从指定历史修订创建新的恢复版本；不会覆盖历史修订。",
        }[name], "context_version", frozenset({"coordinator", "worker"})) for name in names))
