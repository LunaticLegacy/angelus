"""Immutable context revisions over llmfetcher's SQLite checkpoint format."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..settings_module.json_store import read_json, write_json


class ContextVersionError(ValueError):
    """Safe context revision or edit rejection."""


@dataclass(frozen=True)
class ContextEditOperation:
    kind: str
    target_record_id: str = ""
    content: str = ""
    role: str = "user"


class ContextVersionStore:
    """Version and rewrite only one live Agent's active linear context."""

    def __init__(self, agent: Any, agent_name: str) -> None:
        if agent.context_path is None:
            raise ContextVersionError("Agent context persistence is unavailable")
        self.agent, self.agent_name = agent, agent_name
        self.path = Path(agent.context_path)
        self.revisions = self.path.parent / "context-revisions"
        self._lock = _CONTEXT_LOCK

    def inspect(self) -> dict[str, Any]:
        with self._lock:
            self._persist()
            messages = self._messages()
            metadata = self._metadata()
            history = []
            for path in sorted(self.revisions.glob("*.json")) if self.revisions.is_dir() else ():
                value = read_json(path, {})
                if isinstance(value, dict) and isinstance(value.get("revision"), dict): history.append(value["revision"])
            return {"agent": self.agent_name, "revision_id": metadata.get("revision_id"),
                    "records": [self._record(item, index) for index, item in enumerate(messages, 1)],
                    "revisions": history}

    def apply(self, expected_revision_id: str | None, operations: list[ContextEditOperation], reason: str) -> dict[str, Any]:
        if not operations: raise ContextVersionError("at least one operation is required")
        with self._lock:
            self._persist(); messages = self._messages(); current = self._metadata().get("revision_id")
            if expected_revision_id != current: raise ContextVersionError("context revision is stale; inspect again")
            parent = current or self._snapshot(messages, None, "system", "Automatic baseline", [])
            for operation in operations:
                refs = {self._record(item, i)["record_id"]: i - 1 for i, item in enumerate(messages, 1)}
                if operation.target_record_id not in refs: raise ContextVersionError("edit target is not active")
                index = refs[operation.target_record_id]
                if operation.kind == "replace_content": messages[index]["content"] = operation.content
                elif operation.kind == "delete": messages.pop(index)
                elif operation.kind == "insert_after":
                    if operation.role not in {"user", "assistant", "tool"}: raise ContextVersionError("invalid inserted role")
                    messages.insert(index + 1, {"role": operation.role, "content": operation.content})
                else: raise ContextVersionError("unsupported context edit")
            revision = self._snapshot(messages, parent, "tool", reason, [asdict(x) for x in operations])
            self._activate(messages, revision)
            return self.inspect()

    def restore(self, expected_revision_id: str | None, revision_id: str, reason: str) -> dict[str, Any]:
        with self._lock:
            self._persist(); current = self._metadata().get("revision_id")
            if expected_revision_id != current: raise ContextVersionError("context revision is stale; inspect again")
            source = read_json(self.revisions / f"{revision_id}.json", None)
            if not isinstance(source, dict) or not isinstance(source.get("messages"), list): raise ContextVersionError("revision is unavailable")
            new_revision = self._snapshot(source["messages"], current, "tool", reason, [], restored_from=revision_id)
            self._activate([dict(item) for item in source["messages"]], new_revision)
            return self.inspect()

    def _persist(self) -> None:
        if not self.agent.context_handler.save(self.path):
            raise ContextVersionError("could not persist the live Agent context")

    def _linear(self) -> Any:
        return getattr(self.agent.context_handler, "linear", self.agent.context_handler)

    def _pointer(self) -> dict[str, Any]:
        value = read_json(self.path, {})
        return value if isinstance(value, dict) else {}

    def _metadata(self) -> dict[str, Any]:
        value = self._pointer().get("context_editing", {})
        return value if isinstance(value, dict) else {}

    def _messages(self) -> list[dict[str, Any]]:
        linear = self._linear()
        return [linear._context_to_dict(item) for item in linear.messages]

    def _record(self, item: dict[str, Any], ordinal: int) -> dict[str, Any]:
        stable = f"{ordinal}:{item.get('timeline', 0)}:{item.get('role', '')}:{item.get('content', '')}"
        stable += json.dumps(item.get("images", []), sort_keys=True)
        return {"record_id": hashlib.sha256(stable.encode()).hexdigest()[:24], "ordinal": ordinal,
                "timeline": item.get("timeline", 0), "role": item.get("role", ""),
                "content": item.get("content", ""), "images": item.get("images", []),
                "has_tool_calls": bool(item.get("tool_calls"))}

    def _snapshot(self, messages: list[dict[str, Any]], parent: str | None, actor: str, reason: str,
                  operations: list[dict[str, Any]], restored_from: str | None = None) -> str:
        revision_id = uuid4().hex
        revision = {"revision_id": revision_id, "parent_revision_id": parent, "agent": self.agent_name,
                    "created_at": time.time(), "actor": actor, "reason": reason[:1000],
                    "operations": operations, "restored_from": restored_from,
                    "snapshot_sha256": hashlib.sha256(json.dumps(messages, ensure_ascii=False, sort_keys=True).encode()).hexdigest()}
        write_json(self.revisions / f"{revision_id}.json", {"revision": revision, "messages": messages})
        return revision_id

    def _activate(self, messages: list[dict[str, Any]], revision_id: str) -> None:
        linear = self._linear()
        pointer = self._pointer(); database_name = pointer.get("database")
        if not isinstance(database_name, str): raise ContextVersionError("unsupported context checkpoint")
        database = self.path.parent / database_name
        with sqlite3.connect(database) as connection:
            archive_max = connection.execute("SELECT COALESCE(MAX(timeline), 0) FROM archive").fetchone()[0]
            message_max = connection.execute("SELECT COALESCE(MAX(timeline), 0) FROM messages").fetchone()[0]
            start = max(int(archive_max), int(message_max), int(getattr(linear, "_round", 0))) + 1
            normalized = []
            for offset, item in enumerate(messages):
                value = dict(item); value["timeline"] = start + offset; normalized.append(value)
            connection.execute("DELETE FROM messages")
            connection.executemany("INSERT INTO messages(timeline, payload) VALUES (?, ?)", [(x["timeline"], json.dumps(x, ensure_ascii=False)) for x in normalized])
            connection.commit()
        linear.messages = [linear._context_from_dict(item) for item in normalized]
        linear._round = normalized[-1]["timeline"] if normalized else start
        linear._storage_message_high_water = linear._round
        linear.context_editing = {"revision_id": revision_id, "graph_stale": True}
        reset = getattr(self.agent.context_handler, "_init_session_state", None)
        if callable(reset): reset()
        if not linear.save(self.path): raise ContextVersionError("edited context could not be activated")


_CONTEXT_LOCK = threading.RLock()
