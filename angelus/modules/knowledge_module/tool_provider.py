"""ToolRegistry provider for session knowledge documents and Agent pins."""
from __future__ import annotations

import json
from pathlib import Path
import threading
from typing import TYPE_CHECKING

from llmfetcher import Tool
from llmfetcher.llm_types import ToolParameter, ToolSchema

from ..tool_module import ToolCategory, ToolDefinition, ToolPolicy
from ..tool_module.tool_registry import ToolProviderRegistration
from .knowledge_store import KnowledgeStore

if TYPE_CHECKING:
    from ...core import AngelusCore
    from ..session_module.session_handler import Session


def _schema(*parameters: ToolParameter) -> ToolSchema:
    return ToolSchema(properties=list(parameters))


class KnowledgeToolProvider:
    """Materialize only authorized knowledge Tools for their owning Session."""

    def __init__(self, core: "AngelusCore") -> None:
        self._core = core
        self._stores: dict[Path, KnowledgeStore] = {}
        self._lock = threading.RLock()

    def _store(self, session: "Session") -> KnowledgeStore:
        if session.execution is None:
            raise RuntimeError("Session knowledge storage is not configured")
        root = session.execution.root.resolve()
        with self._lock:
            return self._stores.setdefault(root, KnowledgeStore(root))

    @staticmethod
    def _result(value: object) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    def materialize(self, session: "Session", policy: ToolPolicy, role: str, agent_name: str | None = None) -> list[Tool]:
        if role not in {"coordinator", "worker"}:
            return []
        store = self._store(session)
        tools: list[Tool] = []
        injection = self._core.knowledge_injection
        session_id = session.execution.session_id if session.execution is not None else ""
        agent = agent_name or ""

        def upsert(id: str, content: str, title: str = "", tags: list[str] | None = None) -> str:
            try:
                return self._result(store.upsert(id, content, title, tags or []))
            except ValueError as exc:
                return f"Error: {exc}"

        def search(query: str, limit: int = 5) -> str:
            try:
                return self._result({"query": query, "results": store.search(query, limit)})
            except ValueError as exc:
                return f"Error: {exc}"

        def read(id: str, max_chars: int = 6000) -> str:
            try:
                return self._result(store.read(id, max_chars))
            except KeyError:
                return "Error: knowledge document was not found"
            except ValueError as exc:
                return f"Error: {exc}"

        def delete(id: str) -> str:
            try:
                return self._result({"id": id, "deleted": store.delete(id)})
            except ValueError as exc:
                return f"Error: {exc}"

        def pin(path: str) -> str:
            try:
                return self._result({"agent": agent, "pins": list(injection.add(session_id, agent, path))})
            except ValueError as exc:
                return f"Error: {exc}"

        def unpin(path: str) -> str:
            try:
                return self._result({"agent": agent, "pins": list(injection.remove(session_id, agent, path))})
            except ValueError as exc:
                return f"Error: {exc}"

        if injection.available and policy.allows("knowledge", "knowledge_pin"):
            tools.append(Tool("knowledge_pin", "Keep one knowledge document in this Agent's context for every request.", _schema(ToolParameter("path", description="Corpus-relative document path")), pin))
        if injection.available and policy.allows("knowledge", "knowledge_unpin"):
            tools.append(Tool("knowledge_unpin", "Stop injecting one pinned knowledge document for this Agent.", _schema(ToolParameter("path", description="Corpus-relative document path")), unpin))

        if policy.allows("knowledge", "knowledge_upsert"):
            tools.append(Tool("knowledge_upsert", "Create or replace one explicit document in this Session's knowledge base. The content is not added to context until searched or read.", _schema(ToolParameter("id", description="Stable document ID"), ToolParameter("content", description="Document text to retain"), ToolParameter("title", description="Optional concise title", required=False, default=""), ToolParameter("tags", type="array", description="Optional labels", required=False, default=[])), upsert))
        if policy.allows("knowledge", "knowledge_search"):
            tools.append(Tool("knowledge_search", "Search this Session's knowledge base and return small ranked excerpts. Use knowledge_read only for a selected document.", _schema(ToolParameter("query", description="Question or search terms"), ToolParameter("limit", type="integer", description="Maximum results (1-20)", required=False, default=5)), search))
        if policy.allows("knowledge", "knowledge_read"):
            tools.append(Tool("knowledge_read", "Read one known knowledge document with an explicit size limit.", _schema(ToolParameter("id", description="Document ID returned by knowledge_search"), ToolParameter("max_chars", type="integer", description="Maximum characters (1-6000)", required=False, default=6000)), read))
        if policy.allows("knowledge", "knowledge_delete"):
            tools.append(Tool("knowledge_delete", "Delete one explicit document from this Session's knowledge base.", _schema(ToolParameter("id", description="Document ID to delete")), delete))
        return tools


def knowledge_tool_registration(core: "AngelusCore") -> ToolProviderRegistration:
    """Return the knowledge provider registration: session documents and pins."""
    definitions = [
        ToolDefinition("knowledge_upsert", "knowledge", "写入知识", "新增或替换当前会话的一份知识文档。", "knowledge", frozenset({"coordinator", "worker"})),
        ToolDefinition("knowledge_search", "knowledge", "检索知识", "从当前会话知识库返回排序后的受限片段。", "knowledge", frozenset({"coordinator", "worker"})),
        ToolDefinition("knowledge_read", "knowledge", "读取知识", "按文档 ID 读取受限长度的原文。", "knowledge", frozenset({"coordinator", "worker"})),
        ToolDefinition("knowledge_delete", "knowledge", "删除知识", "按文档 ID 删除当前会话的一份知识。", "knowledge", frozenset({"coordinator", "worker"})),
    ]
    if core.knowledge_injection.available:
        definitions.extend([
            ToolDefinition("knowledge_pin", "knowledge", "固定知识到上下文", "把一篇知识文档加入本 Agent 的持续注入清单。", "knowledge", frozenset({"coordinator", "worker"})),
            ToolDefinition("knowledge_unpin", "knowledge", "取消固定知识", "把一篇知识文档移出本 Agent 的持续注入清单。", "knowledge", frozenset({"coordinator", "worker"})),
        ])
    return ToolProviderRegistration(
        id="knowledge",
        provider=KnowledgeToolProvider(core),
        categories=(ToolCategory("knowledge", "知识库", "按会话保存资料，并提供可选的持续注入清单。"),),
        definitions=tuple(definitions),
    )
