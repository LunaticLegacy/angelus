"""Append-only durable execution events."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Iterator


class ExecutionJournal:
    """The sole append-only durable fact log for one execution attempt.

    It deliberately has no in-memory event cache: durable replay reopens this
    file, making a later host observe the same facts as the writing process.
    """

    def __init__(self, path: Path, execution_id: str) -> None:
        """Create a journal writer for one immutable execution identity.

        Args:
            path: NDJSON event file, created on first append.
            execution_id: Identity copied into every event for validation.
        """
        # Durable NDJSON path; all events for this attempt share this file.
        self.path = path
        # Immutable identity injected into every event record.
        self.execution_id = execution_id
        # Serializes append/write/fsync and the offset observed after commit.
        self._lock = threading.Lock()

    def append(self, event_type: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        """Commit one event before any caller publishes it to observers.

        Args:
            event_type: Stable lifecycle/checkpoint event discriminator.
            data: JSON-compatible event payload; ``None`` means empty object.

        Returns:
            The committed event plus byte offset immediately after its newline.
        """
        event = {
            "event_id": uuid.uuid4().hex,
            "execution_id": self.execution_id,
            "type": event_type,
            "timestamp": time.time(),
            "data": data or {},
        }
        encoded = json.dumps(event, ensure_ascii=False, separators=(",", ":"), default=str) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
                event["offset"] = handle.tell()
        return event

    def events(self) -> Iterator[dict[str, Any]]:
        """Yield complete valid JSON lines in commit order.

        A trailing partial line after a crash is skipped rather than invented;
        absence of the journal also means no durable event has been committed.
        """
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        value = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(value, dict):
                        yield value
        except FileNotFoundError:
            return
