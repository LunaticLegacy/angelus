"""ToolRegistry provider for session-isolated knowledge retrieval."""
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

    def __init__(self, _core: "AngelusCore") -> None:
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

        def upsert(**kwargs: object) -> str:
            try:
                return self._result(store.upsert(kwargs.get("id"), kwargs.get("content"), kwargs.get("title", ""), kwargs.get("tags", [])))
            except ValueError as exc:
                return f"Error: {exc}"

        def search(**kwargs: object) -> str:
            try:
                return self._result({"query": kwargs.get("query"), "results": store.search(kwargs.get("query"), kwargs.get("limit", 5))})
            except ValueError as exc:
                return f"Error: {exc}"

        def read(**kwargs: object) -> str:
            try:
                return self._result(store.read(kwargs.get("id"), kwargs.get("max_chars", 6000)))
            except KeyError:
                return "Error: knowledge document was not found"
            except ValueError as exc:
                return f"Error: {exc}"

        def delete(**kwargs: object) -> str:
            try:
                return self._result({"id": kwargs.get("id"), "deleted": store.delete(kwargs.get("id"))})
            except ValueError as exc:
                return f"Error: {exc}"

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
    """Return the built-in local knowledge-base provider registration."""
    return ToolProviderRegistration(
        id="knowledge",
        provider=KnowledgeToolProvider(core),
        categories=(ToolCategory("knowledge", "知识库", "按会话保存资料，并只在 Agent 显式检索时提供受限片段。"),),
        definitions=(
            ToolDefinition("knowledge_upsert", "knowledge", "写入知识", "新增或替换当前会话的一份知识文档。", "knowledge", frozenset({"coordinator", "worker"})),
            ToolDefinition("knowledge_search", "knowledge", "检索知识", "从当前会话知识库返回排序后的受限片段。", "knowledge", frozenset({"coordinator", "worker"})),
            ToolDefinition("knowledge_read", "knowledge", "读取知识", "按文档 ID 读取受限长度的原文。", "knowledge", frozenset({"coordinator", "worker"})),
            ToolDefinition("knowledge_delete", "knowledge", "删除知识", "按文档 ID 删除当前会话的一份知识。", "knowledge", frozenset({"coordinator", "worker"})),
        ),
    )
