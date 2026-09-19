"""ToolRegistry provider for explicit cross-Session retrieval."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from llmfetcher import Tool, ToolParameter, ToolSchema

from ..tool_module import ToolCategory, ToolDefinition, ToolPolicy
from ..tool_module.tool_registry import ToolProviderRegistration
from .store import SessionMemoryError, SessionMemoryStore

if TYPE_CHECKING:
    from ...core import AngelusCore


class SessionMemoryToolProvider:
    def __init__(self, core: "AngelusCore") -> None:
        self._core = core
        self._store = SessionMemoryStore(core.state_root)

    def materialize(self, session: object, policy: ToolPolicy, role: str, agent_name: str | None = None) -> list[Tool]:
        session_id = session.execution.session_id if session.execution is not None else ""
        profile = self._core.run_profiles.effective(session_id)
        grants = {
            "search": set(profile["session_memory_search_sessions"]), "read": set(profile["session_memory_read_sessions"]),
            "artifact_search": set(profile["session_artifact_search_sessions"]), "artifact_open": set(profile["session_artifact_open_sessions"]),
        }
        schema = lambda *p: ToolSchema(properties=list(p))
        tools: list[Tool] = []
        def allowed(kind: str, source: str) -> None:
            if source not in grants[kind]: raise SessionMemoryError("session is not authorized for this operation")
        def search(query: str, session_ids: list[str] | None = None, include_attachments: bool = False, include_handoffs: bool = True) -> str:
            results: list[dict[str, Any]] = []; needle = query.casefold()
            for source in session_ids or sorted(grants["search"]):
                allowed("search", source); manifest = self._store.snapshot(source)
                results.extend({**{k: item.get(k) for k in ("evidence_id", "kind", "agent", "timeline", "summary")}, "session_id": source, "generation": manifest["generation"]} for item in manifest["evidence"] if needle in (item["summary"] + "\n" + item["body"]).casefold() and (include_handoffs or item["kind"] != "handoff"))
                if include_attachments: results.extend({**{k: v for k, v in item.items() if k != "relative_path"}, "session_id": source, "generation": manifest["generation"]} for item in manifest["artifacts"] if needle in item["logical_name"].casefold())
            return json.dumps({"results": results[:100]}, ensure_ascii=False)
        def read(session_id: str, evidence_ids: list[str]) -> str:
            allowed("read", session_id); manifest = self._store.snapshot(session_id); wanted = set(evidence_ids)
            return json.dumps({"session_id": session_id, "generation": manifest["generation"], "evidence": [x for x in manifest["evidence"] if x["evidence_id"] in wanted]}, ensure_ascii=False)
        def search_artifacts(session_id: str, query: str) -> str:
            allowed("artifact_search", session_id); manifest = self._store.snapshot(session_id); needle = query.casefold()
            return json.dumps({"session_id": session_id, "generation": manifest["generation"], "results": [{k:v for k,v in x.items() if k != "relative_path"} for x in manifest["artifacts"] if needle in x["logical_name"].casefold()]}, ensure_ascii=False)
        def open_artifact(session_id: str, artifact_id: str) -> str:
            allowed("artifact_open", session_id); return json.dumps(self._store.copy_artifact(session_id, artifact_id, session.execution.session_id), ensure_ascii=False)
        def create_handoff(handoff: dict[str, Any]) -> str: return json.dumps(self._store.create_handoff(session_id, handoff), ensure_ascii=False)
        def read_handoff(session_id: str, handoff_id: str) -> str:
            allowed("read", session_id); return json.dumps(self._store.read_handoff(session_id, handoff_id), ensure_ascii=False)
        definitions = [
            ("search_session_memory", search, schema(ToolParameter("query"), ToolParameter("session_ids", type="array", required=False), ToolParameter("include_attachments", type="boolean", required=False, default=False), ToolParameter("include_handoffs", type="boolean", required=False, default=True))),
            ("read_session_memory", read, schema(ToolParameter("session_id"), ToolParameter("evidence_ids", type="array"))),
            ("search_session_artifacts", search_artifacts, schema(ToolParameter("session_id"), ToolParameter("query"))),
            ("open_session_artifact", open_artifact, schema(ToolParameter("session_id"), ToolParameter("artifact_id"))),
            ("create_session_handoff", create_handoff, schema(ToolParameter("handoff", type="object"))),
            ("read_session_handoff", read_handoff, schema(ToolParameter("session_id"), ToolParameter("handoff_id"))),
        ]
        for name, handler, tool_schema in definitions:
            if policy.allows("session_memory", name): tools.append(Tool(name, "Explicitly authorized cross-Session memory operation.", tool_schema, handler))
        return tools


def session_memory_tool_registration(core: "AngelusCore") -> ToolProviderRegistration:
    names = ("search_session_memory", "read_session_memory", "search_session_artifacts", "open_session_artifact", "create_session_handoff", "read_session_handoff")
    return ToolProviderRegistration("session_memory", SessionMemoryToolProvider(core),
        (ToolCategory("session_memory", "跨对话记忆", "显式授权的会话快照、交接与只读附件访问。"),),
        tuple(ToolDefinition(name, "session_memory", name, "显式授权的跨对话操作。", "session_memory", frozenset({"coordinator", "worker"})) for name in names))
