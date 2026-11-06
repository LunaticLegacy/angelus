"""Agent tools for editable Session and Project notes."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from llmfetcher import Tool, ToolParameter, ToolSchema

from ..tool_module import ToolCategory, ToolDefinition, ToolPolicy
from ..tool_module.tool_registry import ToolProviderRegistration
from .store import NoteError, NoteStore

if TYPE_CHECKING:
    from ...core import AngelusCore


class NoteToolProvider:
    def __init__(self, core: "AngelusCore") -> None:
        self.core = core

    def _store(self, session: object) -> NoteStore:
        session_id = session.execution.session_id if session.execution is not None else ""
        workspace = self.core.workspaces.get(session_id)
        return NoteStore(workspace.state_path, NoteStore.project_root(self.core.state_root, workspace.project_path))

    def materialize(self, session: object, policy: ToolPolicy, role: str, agent_name: str | None = None) -> list[Tool]:
        if not policy.allows("notes", "note_list"):
            return []
        store = self._store(session)
        agent = agent_name or role
        schema = lambda *properties: ToolSchema(properties=list(properties))
        scope = ToolParameter("scope", description="session or project")
        note_id = ToolParameter("note_id", required=False)
        revision = ToolParameter("revision", type="integer", required=False)

        def encode(notes: Any) -> str:
            return json.dumps([note.as_dict() for note in notes] if isinstance(notes, list) else notes.as_dict(), ensure_ascii=False)
        def create(scope: str, title: str, content: str, tags: list[str] | None = None) -> str:
            return encode(store.create(scope, title, content, tags or []))
        def update(scope: str, note_id: str, title: str | None = None, content: str | None = None, tags: list[str] | None = None, revision: int | None = None) -> str:
            return encode(store.update(scope, note_id, title=title, content=content, tags=tags, revision=revision))
        def delete(scope: str, note_id: str, revision: int | None = None) -> str:
            return encode(store.delete(scope, note_id, revision))
        def pin(scope: str, note_id: str) -> str:
            return encode(store.pin(agent, scope, note_id))
        def unpin(scope: str, note_id: str) -> str:
            return encode(store.unpin(agent, scope, note_id))
        definitions = [
            ("note_list", lambda scope="session": encode(store.list(scope)), schema(scope)),
            ("note_search", lambda scope, query: encode(store.search(scope, query)), schema(scope, ToolParameter("query"))),
            ("note_read", lambda scope, note_id: encode(store.read(scope, note_id)), schema(scope, note_id)),
            ("note_create", create, schema(scope, ToolParameter("title"), ToolParameter("content"), ToolParameter("tags", type="array", required=False))),
            ("note_update", update, schema(scope, ToolParameter("note_id"), ToolParameter("title", required=False), ToolParameter("content", required=False), ToolParameter("tags", type="array", required=False), revision)),
            ("note_delete", delete, schema(scope, note_id, revision)),
            ("note_pin", pin, schema(scope, note_id)),
            ("note_unpin", unpin, schema(scope, note_id)),
        ]
        return [Tool(name, "Manage durable Agent notes.", tool_schema, handler) for name, handler, tool_schema in definitions if policy.allows("notes", name)]


def note_tool_registration(core: "AngelusCore") -> ToolProviderRegistration:
    names = ("note_list", "note_search", "note_read", "note_create", "note_update", "note_delete", "note_pin", "note_unpin")
    titles = {
        "note_list": "列出笔记", "note_search": "搜索笔记", "note_read": "读取笔记",
        "note_create": "创建笔记", "note_update": "更新笔记", "note_delete": "删除笔记",
        "note_pin": "固定笔记", "note_unpin": "取消固定笔记",
    }
    return ToolProviderRegistration(
        "notes",
        NoteToolProvider(core),
        (ToolCategory("notes", "笔记", "Agent 可维护的 Session 与 Project 笔记。"),),
        tuple(ToolDefinition(name, "notes", titles[name], "读取、修改或固定 Agent 笔记。", "notes", frozenset({"coordinator", "worker"})) for name in names),
    )

