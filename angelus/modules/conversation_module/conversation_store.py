"""Read the legacy conversation archive through the new Session boundary."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
from typing import Any


class ConversationStore:
    """Project one Session's persisted messages into a bounded chronological page.

    During the storage transition the old ``workspace/<session>/conversation.json``
    archive remains authoritative for historical messages.  The store isolates
    that compatibility read from HTTP and from Agent execution, so a later
    append-only conversation writer has one replacement point.
    """

    def __init__(self, legacy_root: Path) -> None:
        """Use ``legacy_root`` only to recover existing conversation archives."""
        self._legacy_root = legacy_root

    def page(self, session_id: str, *, before: int | None, limit: int) -> dict[str, Any]:
        """Return at most ``limit`` messages ending immediately before ``before``.

        The first page returns the newest bounded suffix in chronological order.
        Its opaque cursor is the number of older records still available.
        """
        messages = self._read_legacy(session_id)
        end = len(messages) if before is None else max(0, min(before, len(messages)))
        start = max(0, end - limit)
        return {
            "messages": messages[start:end],
            "next_cursor": str(start) if start else None,
            "has_more": start > 0,
        }

    def _read_legacy(self, session_id: str) -> list[dict[str, Any]]:
        """Read valid old records; malformed or absent archives mean no history."""
        path = self._legacy_root / session_id / "conversation.json"
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        raw_messages = document.get("messages") if isinstance(document, dict) else None
        if not isinstance(raw_messages, list):
            return []
        messages: list[dict[str, Any]] = []
        for sequence, item in enumerate(raw_messages):
            if not isinstance(item, dict):
                continue
            messages.append({
                "id": f"legacy-{sequence}",
                "role": str(item.get("role") or "assistant"),
                "content": str(item.get("content") or ""),
                "reasoning": str(item.get("reasoning") or ""),
                "tools": item.get("tools") if isinstance(item.get("tools"), list) else [],
                "content_html": str(item.get("content_html") or ""),
                "reasoning_html": str(item.get("reasoning_html") or ""),
            })
        return messages

    def remove(self, session_id: str) -> None:
        """Remove the Angelus-owned legacy archive for a deleted Session only."""
        path = (self._legacy_root / session_id).resolve()
        root = self._legacy_root.resolve()
        if path.parent != root:
            raise ValueError("invalid session archive path")
        if path.exists():
            shutil.rmtree(path)
