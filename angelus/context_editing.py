"""Versioned, auditable edits for one Agent's active persisted context."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import uuid
from typing import Any, Callable, Literal

from llmfetcher.llm_types import Tool, ToolParameter, ToolSchema


EditKind = Literal["replace_content", "delete", "insert_after"]
_LOCKS: dict[Path, threading.RLock] = {}
_LOCK_GUARD = threading.Lock()


@dataclass(frozen=True)
class ContextRecordRef:
    """Stable identity for one editable active-context message.

    Attributes:
        record_id: Opaque identifier used as an edit target.
        timeline: Original conversation timeline associated with the record.
        role: Model-message role stored in the active checkpoint.
        content_hash: SHA-256 digest of the current content for diagnostics.
    """

    record_id: str
    timeline: int
    role: str
    content_hash: str


@dataclass(frozen=True)
class ContextEditOperation:
    """One validated mutation against a stable active-context record.

    Attributes:
        kind: ``replace_content``, ``delete``, or ``insert_after``.
        target_record_id: Existing record selected by an inspection response.
        content: Replacement or inserted textual content.
        role: Role for an inserted record; ignored by other operations.
    """

    kind: EditKind
    target_record_id: str | None = None
    content: str = ""
    role: str = "user"


@dataclass(frozen=True)
class ContextRevision:
    """Immutable audit entry and complete snapshot identity for one edit.

    The revision metadata is written both in its snapshot and the append-only
    audit log. ``restored_from`` makes a recovery operation traceable without
    mutating the source revision.
    """

    revision_id: str
    parent_revision_id: str | None
    agent_name: str
    created_at: float
    actor: str
    reason: str
    operations: tuple[ContextEditOperation, ...]
    snapshot_sha256: str
    restored_from: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible revision payload."""
        return asdict(self)


class ContextEditError(ValueError):
    """Safe rejection for invalid edits, stale revisions, or unknown records."""


def _lock_for(path: Path) -> threading.RLock:
    """Return the process-local lock that serializes one context file."""
    resolved = path.resolve()
    with _LOCK_GUARD:
        return _LOCKS.setdefault(resolved, threading.RLock())


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        value = {}
    return value if isinstance(value, dict) else {}


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    """Atomically write one JSON record and flush its file contents."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


class ContextEditStore:
    """Own immutable revisions and the active JSON checkpoint for one Agent."""

    def __init__(self, path: str | Path, agent_name: str) -> None:
        """Bind the store to one Agent-owned context file.

        Args:
            path: Active ``contexts/<agent>.json`` destination.
            agent_name: Stable graph-local Agent identity for audit entries.
        """
        self.path = Path(path)
        self.agent_name = agent_name
        self.revision_dir = self.path.parent / "revisions" / self.path.stem
        self.audit_path = self.path.parent / "context-edits.ndjson"
        self._lock = _lock_for(self.path)

    @staticmethod
    def _record_ref(message: dict[str, Any], ordinal: int) -> ContextRecordRef:
        """Derive a stable reference from immutable message provenance fields."""
        content = str(message.get("content", ""))
        timeline = int(message.get("timeline", 0) or 0)
        role = str(message.get("role", "unknown"))
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        record_id = str(message.get("record_id") or hashlib.sha256(
            f"{timeline}:{role}:{ordinal}:{content_hash}".encode("utf-8")
        ).hexdigest()[:24])
        return ContextRecordRef(record_id, timeline, role, content_hash)

    def inspect(self) -> dict[str, Any]:
        """Return editable records and revision metadata without mutation.

        Returns:
            The active revision, graph-staleness state, stable record refs, and
            all restorable revision summaries for this Agent.
        """
        with self._lock:
            raw = _read_json(self.path)
            records = []
            for ordinal, message in enumerate(raw.get("messages", []), start=1):
                if isinstance(message, dict):
                    ref = self._record_ref(message, ordinal)
                    records.append({"index": ordinal, **asdict(ref), "content": str(message.get("content", ""))})
            metadata = raw.get("context_editing", {})
            return {
                "agent_name": self.agent_name,
                "revision_id": metadata.get("revision_id") if isinstance(metadata, dict) else None,
                "graph_stale": bool(metadata.get("graph_stale")) if isinstance(metadata, dict) else False,
                "records": records,
                "revisions": self.list_revisions(),
            }

    def list_revisions(self) -> list[dict[str, Any]]:
        """List immutable revision metadata newest first.

        Returns:
            JSON-ready revision records. A partial/corrupt snapshot is ignored
            so inspection remains usable after an interrupted old write.
        """
        if not self.revision_dir.is_dir():
            return []
        revisions = [
            _read_json(path).get("revision", {})
            for path in self.revision_dir.glob("*.json")
        ]
        return sorted(
            (item for item in revisions if isinstance(item, dict)),
            key=lambda item: float(item.get("created_at", 0)),
            reverse=True,
        )

    def _append_audit(self, revision: ContextRevision) -> None:
        """Append and flush one revision audit event.

        Args:
            revision: Immutable revision record already saved as a snapshot.

        Side Effects:
            Appends one line to ``context-edits.ndjson`` and fsyncs it so the
            human-readable audit cannot lag an activated context revision.
        """
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(revision.to_dict(), ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _write_baseline(self, raw: dict[str, Any]) -> str:
        """Snapshot an unedited legacy context before its first mutation.

        Args:
            raw: Current legacy checkpoint before its first versioned edit.

        Returns:
            Revision ID that can restore the pristine pre-edit state.
        """
        snapshot_sha256 = hashlib.sha256(
            json.dumps(raw.get("messages", []), ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        revision = ContextRevision(
            revision_id=f"baseline-{uuid.uuid4().hex}",
            parent_revision_id=None,
            agent_name=self.agent_name,
            created_at=time.time(),
            actor="system",
            reason="Automatic baseline before the first context edit.",
            operations=(),
            snapshot_sha256=snapshot_sha256,
        )
        _atomic_json(
            self.revision_dir / f"{revision.revision_id}.json",
            {"revision": revision.to_dict(), "context": raw},
        )
        self._append_audit(revision)
        return revision.revision_id

    def apply(self, expected_revision_id: str | None, operations: list[ContextEditOperation], *, actor: str, reason: str) -> dict[str, Any]:
        """Validate operations, snapshot the result, and atomically activate it.

        Args:
            expected_revision_id: Revision observed by the caller, or ``None``
                for an unedited legacy context.
            operations: Replace, delete, or insert-after changes to active messages.
            actor: Audit identity such as ``tool`` or ``api``.
            reason: Human-readable change rationale.

        Returns:
            New revision metadata and fresh editable-record projection.

        Raises:
            ContextEditError: If the revision is stale or an operation is invalid.
        """
        if not operations:
            raise ContextEditError("at least one edit operation is required")
        with self._lock:
            raw = _read_json(self.path)
            metadata = raw.get("context_editing") if isinstance(raw.get("context_editing"), dict) else {}
            current_revision = metadata.get("revision_id")
            if expected_revision_id != current_revision:
                raise ContextEditError("context revision is stale; inspect again before editing")
            # Preserve the original legacy checkpoint before a first edit so
            # recovery never depends on an already-mutated active file.
            parent_revision = current_revision or self._write_baseline(raw)
            messages = [dict(item) for item in raw.get("messages", []) if isinstance(item, dict)]
            refs = {self._record_ref(message, ordinal).record_id: (ordinal - 1, message) for ordinal, message in enumerate(messages, start=1)}
            for operation in operations:
                if operation.kind not in {"replace_content", "delete", "insert_after"}:
                    raise ContextEditError(f"unsupported context edit: {operation.kind}")
                if operation.kind == "insert_after":
                    if operation.target_record_id not in refs or operation.role not in {"user", "assistant", "tool"}:
                        raise ContextEditError("insert_after needs an existing target and a valid role")
                    index, parent = refs[operation.target_record_id]
                    messages.insert(index + 1, {"timeline": int(parent.get("timeline", 0) or 0), "role": operation.role, "content": operation.content})
                else:
                    if operation.target_record_id not in refs:
                        raise ContextEditError("edit target is not in the active context")
                    index, _ = refs[operation.target_record_id]
                    if operation.kind == "replace_content":
                        messages[index]["content"] = operation.content
                    else:
                        messages.pop(index)
                refs = {self._record_ref(message, ordinal).record_id: (ordinal - 1, message) for ordinal, message in enumerate(messages, start=1)}
            revision = ContextRevision(
                revision_id=uuid.uuid4().hex,
                parent_revision_id=parent_revision,
                agent_name=self.agent_name,
                created_at=time.time(), actor=actor, reason=reason.strip()[:1_000],
                operations=tuple(operations),
                snapshot_sha256=hashlib.sha256(json.dumps(messages, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
            )
            raw["messages"] = messages
            raw["context_editing"] = {"revision_id": revision.revision_id, "graph_stale": True}
            raw["schema_version"] = max(2, int(raw.get("schema_version", 1) or 1))
            raw["checkpoint_generation"] = uuid.uuid4().hex
            raw.pop("graph_checkpoint", None)
            snapshot = {"revision": revision.to_dict(), "context": raw}
            _atomic_json(self.revision_dir / f"{revision.revision_id}.json", snapshot)
            _atomic_json(self.path, raw)
            self._append_audit(revision)
            return {"ok": True, "revision": revision.to_dict(), "context": self.inspect()}

    def restore(self, expected_revision_id: str | None, revision_id: str, *, actor: str, reason: str) -> dict[str, Any]:
        """Restore a saved revision as a new forward revision without deleting history."""
        source = _read_json(self.revision_dir / f"{revision_id}.json")
        source_context = source.get("context") if isinstance(source, dict) else None
        if not isinstance(source_context, dict):
            raise ContextEditError("revision is unavailable")
        with self._lock:
            current = _read_json(self.path)
            metadata = current.get("context_editing") if isinstance(current.get("context_editing"), dict) else {}
            if expected_revision_id != metadata.get("revision_id"):
                raise ContextEditError("context revision is stale; inspect again before restoring")
            new_revision = ContextRevision(
                revision_id=uuid.uuid4().hex,
                parent_revision_id=metadata.get("revision_id"),
                agent_name=self.agent_name,
                created_at=time.time(),
                actor=actor,
                reason=reason.strip()[:1_000],
                operations=(),
                snapshot_sha256=hashlib.sha256(
                    json.dumps(source_context.get("messages", []), ensure_ascii=False, sort_keys=True).encode("utf-8")
                ).hexdigest(),
                restored_from=revision_id,
            )
            restored = dict(source_context)
            restored["context_editing"] = {"revision_id": new_revision.revision_id, "graph_stale": True}
            restored["schema_version"] = max(2, int(restored.get("schema_version", 1) or 1))
            restored["checkpoint_generation"] = uuid.uuid4().hex
            restored.pop("graph_checkpoint", None)
            _atomic_json(self.revision_dir / f"{new_revision.revision_id}.json", {"revision": new_revision.to_dict(), "context": restored})
            _atomic_json(self.path, restored)
            self._append_audit(new_revision)
            return {"ok": True, "revision": new_revision.to_dict(), "context": self.inspect()}


def create_context_editing_tools(
    store: ContextEditStore,
    *,
    persist_context: Callable[[], None] | None = None,
    reload_context: Callable[[], None] | None = None,
) -> list[Tool]:
    """Create tools for inspecting, editing, and restoring one Agent context.

    Args:
        store: Versioned store scoped to the owning Agent's context path.
        persist_context: Optional callback that flushes live in-memory context
            before a mutation.
        reload_context: Optional callback that reloads the edited checkpoint
            into the live Agent immediately after a successful mutation.

    Returns:
        Three LLM-callable tools: inspection, version-checked edit, and
        forward-only revision restore.
    """
    def inspect_agent_context() -> dict[str, Any]:
        """Return stable record references and immutable revision history."""
        return store.inspect()

    def edit_agent_context(expected_revision_id: str | None, operations: list[dict[str, Any]], reason: str = "") -> dict[str, Any]:
        """Apply safe active-context edits and reload the owning Agent checkpoint."""
        if persist_context is not None:
            persist_context()
        parsed = [
            ContextEditOperation(
                str(item.get("kind", "")), item.get("target_record_id"),
                str(item.get("content", "")), str(item.get("role", "user")),
            )
            for item in operations
            if isinstance(item, dict)
        ]
        result = store.apply(expected_revision_id, parsed, actor="tool", reason=reason)
        if reload_context is not None:
            reload_context()
        return result

    def restore_agent_context(expected_revision_id: str | None, revision_id: str, reason: str = "") -> dict[str, Any]:
        """Activate an earlier saved context as a new auditable revision."""
        if persist_context is not None:
            persist_context()
        result = store.restore(expected_revision_id, revision_id, actor="tool", reason=reason)
        if reload_context is not None:
            reload_context()
        return result

    return [
        Tool(
            "inspect_agent_context",
            "Inspect this Agent's editable active context and revision history.",
            ToolSchema(),
            inspect_agent_context,
        ),
        Tool(
            "edit_agent_context",
            "Versioned edit of this Agent's active context. Inspect first and use stable record IDs with the current revision.",
            ToolSchema(properties=[
                ToolParameter("expected_revision_id", type="string", description="Revision ID from inspect_agent_context; omit only for an unedited legacy context."),
                ToolParameter("operations", type="array", description="replace_content, delete, or insert_after operations.", required=True),
                ToolParameter("reason", description="Why this context change is needed."),
            ]),
            edit_agent_context,
        ),
        Tool(
            "restore_agent_context",
            "Restore a saved context revision as a new auditable revision.",
            ToolSchema(properties=[
                ToolParameter("expected_revision_id", type="string", description="Current revision ID; omit only for an unedited legacy context."),
                ToolParameter("revision_id", description="Earlier revision to restore.", required=True),
                ToolParameter("reason", description="Why this revision is restored."),
            ]),
            restore_agent_context,
        ),
    ]
