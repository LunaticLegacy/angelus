"""Immutable context revisions over llmfetcher's SQLite checkpoint format."""
from __future__ import annotations

from dataclasses import dataclass, replace
from contextlib import closing
import hashlib
import json
import sqlite3
import threading
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from llmfetcher.context_handlers.archive_retrieval import (
    ArchiveEvidence,
    ArchiveRetrievalConfig,
    retrieve_archive,
)
from llmfetcher.context_handlers.linear.codec import (
    context_item_from_dict,
    context_item_to_dict,
    tool_result_to_dict,
)
from llmfetcher.llm_types import (
    ContextItem,
    JsonObject,
    JsonValue,
    LLMContext,
    ToolResultRecord,
)

from ..settings_module.json_schema import decode_record, encode_record
from ..settings_module.json_store import JsonSchemaError, read_json, write_json
from .messages import ContextCompactedMessage, ContextEntry, ContextMessage


class ContextVersionError(ValueError):
    """Safe context revision or edit rejection."""


@dataclass(frozen=True)
class ContextEditOperation:
    kind: str
    target_record_id: str = ""
    content: str = ""
    role: str = "user"


@dataclass(frozen=True)
class ContextRevision:
    """Immutable metadata describing one context snapshot."""

    revision_id: str
    parent_revision_id: str | None
    agent: str
    created_at: float
    actor: str
    reason: str
    operations: tuple[ContextEditOperation, ...]
    restored_from: str | None
    snapshot_sha256: str


@dataclass(frozen=True)
class ContextRevisionDocument:
    """The complete ``context-revisions/<revision_id>.json`` document.

    ``messages`` stays the projection llmfetcher's
    ``context_item_to_dict``/``context_item_from_dict`` pair produces: the
    message schema belongs to the linear context handler, and duplicating it
    here would create a third representation that could drift from the one the
    handler restores.
    """

    revision: ContextRevision
    messages: tuple[ContextEntry, ...]


@dataclass(frozen=True)
class ArchiveSearchResult:
    """Ranked lexical evidence from one Agent's compacted-out archive."""

    agent: str
    query: str
    archive_records: int
    scanned_records: int
    evidence: tuple[ArchiveEvidence, ...]


@dataclass(frozen=True)
class ArchiveRecordResult:
    """One full archived context record resolved by timeline identity."""

    agent: str
    record: LLMContext


def _normalize_revision(value: JsonValue) -> JsonValue:
    """Migrate legacy revision fields before the strict decoder runs.

    Older revision files omitted ``ImageReference.detail`` and used
    ``reasoning`` / ``reasoning_content`` instead of ``content_reasoning``.
    Filling those is a schema migration, not a runtime fallback: any other
    unknown or missing field still fails the strict decoder.
    """
    if not isinstance(value, dict):
        return value
    messages = value.get("messages")
    if not isinstance(messages, list):
        return value
    for message in messages:
        if not isinstance(message, dict):
            continue
        _normalize_images(message.get("images"))
        tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, list):
            for tool in tool_calls:
                if isinstance(tool, dict):
                    _normalize_images(tool.get("images"))
        if "content_reasoning" not in message:
            for alias in ("reasoning_content", "reasoning"):
                candidate = message.get(alias)
                if isinstance(candidate, str):
                    message["content_reasoning"] = candidate
                    break
            else:
                message["content_reasoning"] = ""
        message.pop("reasoning_content", None)
        message.pop("reasoning", None)
    return value


def _normalize_images(value: JsonValue) -> None:
    """Fill the optional image detail default omitted by older revisions."""
    if not isinstance(value, list):
        return
    for image in value:
        if isinstance(image, dict):
            image.setdefault("detail", "auto")


class ContextVersionStore:
    """Version and rewrite only one live Agent's active linear context."""

    def __init__(self, agent: Any, agent_name: str) -> None:
        if agent.context_path is None:
            raise ContextVersionError("Agent context persistence is unavailable")
        self.agent, self.agent_name = agent, agent_name
        self.path = Path(agent.context_path)
        self.revisions = self.path.parent / "context-revisions"
        self._lock = _CONTEXT_LOCK

    def inspect(self) -> dict[str, object]:
        with self._lock:
            self._persist()
            entries = self._messages()
            active = [item for item in entries if isinstance(item, ContextMessage)]
            metadata = self._metadata()
            archive = self._linear().archive
            history: list[dict[str, object]] = []
            for path in sorted(self.revisions.glob("*.json")) if self.revisions.is_dir() else ():
                try:
                    document = decode_record(
                        ContextRevisionDocument,
                        _normalize_revision(cast("JsonValue", read_json(path, None))),
                        f"context revision {path.name}",
                    )
                except (JsonSchemaError, ValueError) as exc:
                    raise ContextVersionError(
                        f"invalid context revision: {path.name}"
                    ) from exc
                history.append(encode_record(document.revision))
            return {
                "agent": self.agent_name,
                "revision_id": metadata.get("revision_id"),
                "archive_records": len(cast("list[object]", archive)) if archive else 0,
                "records": [
                    self._record(item, index)
                    for index, item in enumerate(active, 1)
                ],
                "revisions": history,
            }

    def search_archive(self, query: str, limit: int = 5) -> ArchiveSearchResult:
        """Search this Agent's compacted-out raw records without mutation.

        Args:
            query: Lexical query over archived content, reasoning and tools.
            limit: Maximum evidence records, clamped to one through 20.

        Returns:
            Ranked evidence with provenance plus archive and scan counts.

        Raises:
            ContextVersionError: If the query is empty.
        """
        normalized = query.strip()
        if not normalized:
            raise ContextVersionError("archive query is required")
        try:
            bounded = max(1, min(int(limit), 20))
        except (TypeError, ValueError):
            bounded = 5
        linear = self._linear()
        records = list(linear.archive)
        result = retrieve_archive(
            normalized,
            records,
            store=linear,
            config=ArchiveRetrievalConfig(
                max_results=bounded,
                max_chars_per_record=2_000,
            ),
        )
        return ArchiveSearchResult(
            agent=self.agent_name,
            query=normalized,
            archive_records=len(records),
            scanned_records=result.scanned_records,
            evidence=result.evidence,
        )

    def read_archive(self, timeline: int) -> ArchiveRecordResult:
        """Return one compacted-out raw record by its timeline identity.

        Args:
            timeline: Stable timeline number of the archived record.

        Returns:
            The full archived record, including reasoning and tool evidence.

        Raises:
            ContextVersionError: If the timeline is invalid or absent.
        """
        try:
            wanted = int(timeline)
        except (TypeError, ValueError):
            raise ContextVersionError("timeline must be an integer") from None
        linear = self._linear()
        for record in linear.archive:
            if int(record.timeline) == wanted:
                entry = ContextMessage.from_item(record, linear.tool_results)
                if not isinstance(entry, ContextMessage):
                    break
                return ArchiveRecordResult(agent=self.agent_name, record=entry.to_context())
        raise ContextVersionError("archive record is unavailable")

    def apply(self, expected_revision_id: str | None, operations: list[ContextEditOperation], reason: str) -> dict[str, object]:
        if not operations: raise ContextVersionError("at least one operation is required")
        with self._lock:
            self._persist(); entries = self._messages(); current = self._current_revision_id()
            active = [item for item in entries if isinstance(item, ContextMessage)]
            compacted = [item for item in entries if isinstance(item, ContextCompactedMessage)]
            if expected_revision_id != current: raise ContextVersionError("context revision is stale; inspect again")
            baseline = [*compacted, *active]
            parent = current or self._snapshot(baseline, None, "system", "Automatic baseline", [])
            for operation in operations:
                refs = {cast("str", self._record(item, i)["record_id"]): i - 1 for i, item in enumerate(active, 1)}
                if operation.target_record_id not in refs: raise ContextVersionError("edit target is not active")
                index = refs[operation.target_record_id]
                if operation.kind == "replace_content": active[index] = replace(active[index], content=operation.content)
                elif operation.kind == "delete": active.pop(index)
                elif operation.kind == "insert_after":
                    if operation.role not in {"user", "assistant", "tool"}: raise ContextVersionError("invalid inserted role")
                    active.insert(index + 1, ContextMessage(role=operation.role, timeline=0, content=operation.content))
                else: raise ContextVersionError("unsupported context edit")
            snapshot = [*compacted, *active]
            revision = self._snapshot(snapshot, parent, "tool", reason, operations)
            self._activate(snapshot, revision)
            return self.inspect()

    def restore(self, expected_revision_id: str | None, revision_id: str, reason: str) -> dict[str, object]:
        with self._lock:
            self._persist(); current = self._current_revision_id()
            if expected_revision_id != current: raise ContextVersionError("context revision is stale; inspect again")
            try:
                document = decode_record(
                    ContextRevisionDocument,
                    _normalize_revision(cast("JsonValue", read_json(self.revisions / f"{revision_id}.json", None))),
                    f"context revision {revision_id}",
                )
            except JsonSchemaError as exc:
                raise ContextVersionError("revision is unavailable") from exc
            messages = list(document.messages)
            new_revision = self._snapshot(messages, current, "tool", reason, [], restored_from=revision_id)
            self._activate(messages, new_revision)
            return self.inspect()

    def _persist(self) -> None:
        if not self.agent.context_handler.save(self.path):
            raise ContextVersionError("could not persist the live Agent context")

    def _linear(self) -> Any:
        return self.agent.context_handler.linear

    def _pointer(self) -> dict[str, object]:
        value = read_json(self.path, {})
        if not isinstance(value, dict):
            raise ContextVersionError("context checkpoint pointer must be an object")
        return cast("dict[str, object]", value)

    def _metadata(self) -> dict[str, object]:
        value = self._pointer().get("context_editing", {})
        if not isinstance(value, dict):
            raise ContextVersionError("context_editing metadata must be an object")
        return cast("dict[str, object]", value)

    def _current_revision_id(self) -> str | None:
        value = self._metadata().get("revision_id")
        return value if isinstance(value, str) else None

    def _messages(self) -> list[ContextEntry]:
        linear = self._linear()
        entries: list[ContextEntry] = []
        if linear.abstract is not None:
            entries.append(ContextCompactedMessage.from_summary(linear.abstract))
        entries.extend(
            ContextMessage.from_item(item, linear.tool_results)
            for item in linear.messages
        )
        return entries

    def _record(self, item: ContextMessage, ordinal: int) -> JsonObject:
        images = [cast("JsonObject", encode_record(image)) for image in item.images]
        stable = f"{ordinal}:{item.timeline}:{item.role}:{item.content}"
        stable += json.dumps(images, sort_keys=True)
        return cast("JsonObject", {
            "record_id": hashlib.sha256(stable.encode()).hexdigest()[:24],
            "ordinal": ordinal,
            "timeline": item.timeline,
            "role": item.role,
            "content": item.content,
            "images": images,
            "has_tool_calls": bool(item.tool_calls),
        })

    def _snapshot(self, messages: list[ContextEntry], parent: str | None, actor: str, reason: str,
                  operations: Sequence[ContextEditOperation], restored_from: str | None = None) -> str:
        revision_id = uuid4().hex
        encoded_messages = [encode_record(message) for message in messages]
        revision = ContextRevision(
            revision_id=revision_id,
            parent_revision_id=parent,
            agent=self.agent_name,
            created_at=time.time(),
            actor=actor,
            reason=reason[:1000],
            operations=tuple(operations),
            restored_from=restored_from,
            snapshot_sha256=hashlib.sha256(
                json.dumps(encoded_messages, ensure_ascii=False, sort_keys=True).encode()
            ).hexdigest(),
        )
        document = ContextRevisionDocument(
            revision=revision,
            messages=tuple(messages),
        )
        write_json(self.revisions / f"{revision_id}.json", encode_record(document))
        return revision_id

    def _activate(self, messages: list[ContextEntry], revision_id: str) -> None:
        linear = self._linear()
        compacted = next(
            (item for item in messages if isinstance(item, ContextCompactedMessage)),
            None,
        )
        active = [item for item in messages if isinstance(item, ContextMessage)]
        pointer = self._pointer(); database_name = pointer.get("database")
        if not isinstance(database_name, str): raise ContextVersionError("unsupported context checkpoint")
        database = self.path.parent / database_name
        items: list[ContextItem] = []
        records: list[ToolResultRecord] = []
        for entry in active:
            item, entry_results = entry.to_item_with_results()
            items.append(item)
            records.extend(entry_results)
        with closing(sqlite3.connect(database, timeout=30)) as connection:
            connection.execute("PRAGMA busy_timeout = 30000")
            archive_max = connection.execute("SELECT COALESCE(MAX(timeline), 0) FROM archive").fetchone()[0]
            message_max = connection.execute("SELECT COALESCE(MAX(timeline), 0) FROM messages").fetchone()[0]
            start = max(int(archive_max), int(message_max), int(linear._round)) + 1
            normalized = [replace(item, timeline=start + offset) for offset, item in enumerate(items)]
            payloads = [context_item_to_dict(item) for item in normalized]
            connection.execute("DELETE FROM messages")
            connection.executemany(
                "INSERT INTO messages(timeline, payload) VALUES (?, ?)",
                [(int(payload["timeline"]), json.dumps(payload, ensure_ascii=False)) for payload in payloads],
            )
            for record in records:
                connection.execute(
                    "INSERT OR REPLACE INTO tool_results(result_id, payload) VALUES (?, ?)",
                    (record.result_id.value, json.dumps(tool_result_to_dict(record), ensure_ascii=False)),
                )
            connection.commit()
        linear.abstract = compacted.to_summary() if compacted is not None else None
        linear.messages = list(normalized)
        linear.tool_results.update({record.result_id.value: record for record in records})
        linear._persisted_result_ids.update(record.result_id.value for record in records)
        linear._round = normalized[-1].timeline if normalized else start
        linear._storage_message_high_water = linear._round
        linear.context_editing = {"revision_id": revision_id, "graph_stale": True}
        self.agent.context_handler._init_session_state()
        if not linear.save(self.path): raise ContextVersionError("edited context could not be activated")


_CONTEXT_LOCK = threading.RLock()
