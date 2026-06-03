"""Persistent session storage for llmfetcher agents.

The store persists conversation context, compacted summaries, and agent
memories as JSON. Model clients and tool registries are intentionally not
serialized; they are process resources rebuilt at startup.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .agent import Agent
from .llm_context import LLMContextHandler
from .llm_types import LLMContext, LLMContextCompacted


SESSION_ID_RE = re.compile(r"[^a-zA-Z0-9_.-]+")


def normalize_session_id(session_id: str) -> str:
    """Return a filesystem-safe session id."""
    cleaned = SESSION_ID_RE.sub("_", str(session_id).strip())
    cleaned = cleaned.strip("._-")
    return cleaned or "default"


class JsonSessionStore:
    """File-backed JSON session store."""

    def __init__(self, root: str | Path = ".llmfetcher_sessions") -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def session_path(self, session_id: str) -> Path:
        """Return the JSON path for a session id."""
        return self.root / f"{normalize_session_id(session_id)}.json"

    def list_sessions(self) -> List[Dict[str, Any]]:
        """List stored sessions with lightweight metadata."""
        sessions: List[Dict[str, Any]] = []
        for path in sorted(self.root.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            sessions.append(
                {
                    "session_id": data.get("session_id", path.stem),
                    "path": str(path),
                    "created_at": data.get("created_at"),
                    "updated_at": data.get("updated_at"),
                    "context_count": len(data.get("contexts", [])),
                    "compacted_count": len(data.get("compacted_contexts", [])),
                    "memory_count": len(data.get("memories", [])),
                }
            )
        return sessions

    def read_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Read raw session JSON, returning None when absent."""
        path = self.session_path(session_id)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def delete_session(self, session_id: str) -> bool:
        """Delete a stored session if it exists."""
        path = self.session_path(session_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def save_agent(self, session_id: str, agent: Agent) -> Dict[str, Any]:
        """Persist an agent's context state to a session file."""
        normalized = normalize_session_id(session_id)
        path = self.session_path(normalized)
        previous = self.read_session(normalized) or {}
        now = time.time()

        handler = agent.llm_context_handler
        contexts = [
            {
                "context_id": context_id,
                "role": context.role,
                "content": context.content,
                "tool_call_info": context.tool_call_info or [],
                "tool_call_result": context.tool_call_result or [],
                "tags": context.tags or [],
                "uncompacted": context_id in handler.context_dict_uncompacted,
            }
            for context_id, context in sorted(handler.context_dict.items())
            if isinstance(context, LLMContext)
        ]
        compacted = [
            {
                "context_id": context_id,
                "abstract_msg": context.abstract_msg,
                "source_ids": context.source_ids,
                "tags": context.tags or [],
            }
            for context_id, context in sorted(handler.context_dict_compacted.items())
        ]

        data = {
            "version": 1,
            "session_id": normalized,
            "created_at": previous.get("created_at", now),
            "updated_at": now,
            "system_prompt": agent._base_system_prompt,
            "provider": agent.provider,
            "memories": list(agent.memory_list),
            "contexts": contexts,
            "compacted_contexts": compacted,
            "next_context_id": handler.now_context_id,
        }
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return data

    def load_agent(self, session_id: str, agent: Agent) -> bool:
        """Load stored context into an agent. Returns False when absent."""
        data = self.read_session(session_id)
        if data is None:
            return False

        handler = agent.llm_context_handler
        self._clear_handler(handler)
        agent.memory_list = list(data.get("memories", []))
        agent.tool_call_history = []
        agent.tool_call_result_history = []

        for item in data.get("contexts", []):
            context = LLMContext(
                role=str(item.get("role", "")),
                content=str(item.get("content", "")),
                tool_call_info=list(item.get("tool_call_info") or []),
                tool_call_result=list(item.get("tool_call_result") or []),
                tags=list(item.get("tags") or []),
            )
            context_id = int(item.get("context_id", handler.now_context_id))
            self._insert_context(
                handler,
                context_id,
                context,
                uncompacted=bool(item.get("uncompacted", True)),
            )

        for item in data.get("compacted_contexts", []):
            compacted = LLMContextCompacted(
                abstract_msg=str(item.get("abstract_msg", "")),
                source=[],
                source_ids=[int(source_id) for source_id in item.get("source_ids", [])],
                tags=list(item.get("tags") or []),
            )
            context_id = int(item.get("context_id", handler.now_context_id))
            self._insert_compacted_context(handler, context_id, compacted)

        explicit_next = data.get("next_context_id")
        if explicit_next is not None:
            handler.now_context_id = max(handler.now_context_id, int(explicit_next))
        return True

    def clear_agent(self, agent: Agent) -> None:
        """Clear in-memory context and memories for a reusable agent instance."""
        self._clear_handler(agent.llm_context_handler)
        agent.memory_list = []
        agent.tool_call_history = []
        agent.tool_call_result_history = []

    def _clear_handler(self, handler: LLMContextHandler) -> None:
        handler.context_raw_dict.clear()
        handler.context_raw_dict_reversed.clear()
        handler.context_dict.clear()
        handler.context_dict_uncompacted.clear()
        handler.context_dict_compacted.clear()
        handler.reverse_tag_dict.clear()
        handler.now_context_id = 0

    def _insert_context(
        self,
        handler: LLMContextHandler,
        context_id: int,
        context: LLMContext,
        uncompacted: bool = True,
    ) -> None:
        handler.context_raw_dict[context_id] = context
        handler.context_raw_dict_reversed[id(context)] = context_id
        handler.context_dict[context_id] = context
        if uncompacted:
            handler.context_dict_uncompacted[context_id] = context
        for tag in context.tags or []:
            handler.reverse_tag_dict.setdefault(tag, set()).add(context_id)
        handler.now_context_id = max(handler.now_context_id, context_id + 1)

    def _insert_compacted_context(
        self,
        handler: LLMContextHandler,
        context_id: int,
        context: LLMContextCompacted,
    ) -> None:
        handler.context_raw_dict[context_id] = context
        handler.context_raw_dict_reversed[id(context)] = context_id
        handler.context_dict_compacted[context_id] = context
        for tag in context.tags or []:
            handler.reverse_tag_dict.setdefault(tag, set()).add(context_id)
        handler.now_context_id = max(handler.now_context_id, context_id + 1)
