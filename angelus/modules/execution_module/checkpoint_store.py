"""Generation-based checkpoint commit protocol."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from .journal import ExecutionJournal


def _write_json_atomically(path: Path, payload: dict[str, Any]) -> str:
    """Durably replace one JSON document and return its SHA-256 digest.

    The digest is calculated from the exact committed bytes and recorded by a
    checkpoint manifest, allowing a recovery reader to reject torn/corrupt
    generations without consulting process memory.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return hashlib.sha256(encoded).hexdigest()
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


class CheckpointStore:
    """Commit graph/context generations through one journal event.

    It owns no execution state.  ``ExecutionAttempt`` supplies a complete
    generation at safe boundaries, then this store writes payload files before
    publishing the one ``checkpoint_committed`` fact that makes them valid.
    """

    def __init__(self, attempt_root: Path, journal: ExecutionJournal) -> None:
        """Bind checkpoint output to exactly one attempt root and journal.

        Args:
            attempt_root: Exclusive durable directory of the owning attempt.
            journal: Its append-only journal used to commit generations.
        """
        # Exclusive directory for graph/context generation payloads.
        self.attempt_root = attempt_root
        # The only authority that can make a written generation recoverable.
        self.journal = journal
        # Compact restart/status projection updated after each committed epoch.
        self.manifest_path = attempt_root / "execution-manifest.json"

    def commit(
        self,
        generation: str,
        graph: dict[str, Any],
        contexts: dict[str, dict[str, Any]],
        *,
        reason: str,
    ) -> dict[str, Any]:
        """Write a complete generation and make it recoverable exactly once.

        Args:
            generation: Caller-defined, unique generation label for this attempt.
            graph: Complete execution-graph snapshot at one safe boundary.
            contexts: Complete per-Agent context snapshots at that boundary.
            reason: Boundary cause, retained for recovery and observability.

        Returns:
            Updated manifest containing the journal-committed checkpoint ref.
        """
        graph_path = self.attempt_root / "graph" / f"{generation}.json"
        graph_hash = _write_json_atomically(graph_path, graph)
        context_refs: dict[str, dict[str, Any]] = {}
        for agent_id, context in contexts.items():
            path = self.attempt_root / "contexts" / agent_id / f"{generation}.json"
            context_refs[agent_id] = {
                "path": str(path.relative_to(self.attempt_root)),
                "sha256": _write_json_atomically(path, context),
                "last_completed_boundary": context.get("boundary", {}).get("round"),
            }
        checkpoint = {
            "generation": generation,
            "reason": reason,
            "graph": {
                "path": str(graph_path.relative_to(self.attempt_root)),
                "sha256": graph_hash,
            },
            "contexts": context_refs,
            "committed_at": time.time(),
        }
        committed = self.journal.append("checkpoint_committed", checkpoint)
        try:
            existing = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            manifest = dict(existing) if isinstance(existing, dict) else {}
        except (OSError, json.JSONDecodeError):
            manifest = {}
        manifest.update({
            "schema_version": 1,
            "execution_id": self.journal.execution_id,
            "checkpoint": {**checkpoint, "committed_event_id": committed["event_id"], "event_offset": committed["offset"]},
        })
        _write_json_atomically(self.manifest_path, manifest)
        return manifest
