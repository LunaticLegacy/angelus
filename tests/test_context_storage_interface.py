"""Regression coverage for the context storage port boundary."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from llmfetcher.context_handlers import (
    SQLiteContextStorage,
    is_sqlite_context_pointer,
)
from llmfetcher.context_handlers.linear import ContextHandlerLinear


class _NoopCompactor:
    """Minimal compactor placeholder because these tests do not compact."""


def _payload(timeline: int, content: str) -> str:
    """Serialize one active row the way the linear handler does."""
    return json.dumps(
        {"role": "user", "timeline": timeline, "content": content, "images": []},
        ensure_ascii=False,
    )


class ContextStorageInterfaceTests(unittest.TestCase):
    """Verify the port owns every SQL read and write callers need."""

    def test_replace_active_rewrites_active_rows_and_keeps_archive(self) -> None:
        """Replacing the active window must not touch archived rows."""
        with tempfile.TemporaryDirectory() as directory:
            storage = SQLiteContextStorage()
            database = Path(directory) / "context.json.sqlite3"
            storage.append_rows(
                database,
                [(1, _payload(1, "active-one"))],
                [(2, _payload(2, "archived")), (3, _payload(3, "archived"))],
            )

            storage.replace_active(database, [(9, _payload(9, "edited"))])

            active = storage.read_rows(database)
            self.assertEqual([9], [timeline for timeline, _ in active])
            self.assertEqual("edited", json.loads(active[0][1])["content"])
            self.assertEqual(1, storage.count(database, "messages"))
            self.assertEqual(2, storage.count(database, "archive"))
            combined = storage.read_rows(database, include_archive=True)
            self.assertEqual([2, 3, 9], [timeline for timeline, _ in combined])

    def test_read_rows_returns_ascending_raw_pairs(self) -> None:
        """Raw rows expose timeline plus payload in ascending order."""
        with tempfile.TemporaryDirectory() as directory:
            storage = SQLiteContextStorage()
            database = Path(directory) / "context.json.sqlite3"
            storage.append_rows(
                database,
                [(4, _payload(4, "four")), (2, _payload(2, "two"))],
                [],
            )

            rows = storage.read_rows(database)

            self.assertEqual([2, 4], [timeline for timeline, _ in rows])
            self.assertEqual(["two", "four"], [json.loads(payload)["content"] for _, payload in rows])

    def test_append_rows_moves_archived_timelines_out_of_active(self) -> None:
        """The archive invariant stays enforced inside the port."""
        with tempfile.TemporaryDirectory() as directory:
            storage = SQLiteContextStorage()
            database = Path(directory) / "context.json.sqlite3"
            storage.append_rows(
                database,
                [(1, _payload(1, "one")), (2, _payload(2, "two"))],
                [],
            )

            storage.append_rows(database, [], [(1, _payload(1, "one"))])

            self.assertEqual([2], [timeline for timeline, _ in storage.read_rows(database)])
            self.assertEqual(1, storage.count(database, "archive"))
            self.assertEqual(1, storage.count(database, "messages"))

    def test_pointer_predicate_recognizes_only_schema_three_sqlite(self) -> None:
        """Format recognition lives in one place."""
        self.assertTrue(
            is_sqlite_context_pointer({"schema_version": 3, "storage": "sqlite"})
        )
        self.assertFalse(
            is_sqlite_context_pointer({"schema_version": 2, "storage": "sqlite"})
        )
        self.assertFalse(is_sqlite_context_pointer({"messages": []}))
        self.assertFalse(is_sqlite_context_pointer(None))

    def test_linear_replace_active_context_renumbers_above_high_water(self) -> None:
        """The handler keeps in-memory state and durable rows consistent."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.json"
            linear = ContextHandlerLinear(_NoopCompactor())
            for number in range(3):
                linear.add_user_message(f"message-{number}")
            self.assertTrue(linear.save(path))
            database = path.with_suffix(path.suffix + ".sqlite3")

            high_water = linear.replace_active_context(
                [{"role": "user", "content": "edited"}],
                database=database,
                context_editing={"revision_id": "rev-1", "graph_stale": True},
            )

            self.assertEqual(4, high_water)
            self.assertEqual(["edited"], [message.content for message in linear.messages])
            self.assertEqual([4], [message.timeline for message in linear.messages])
            self.assertEqual(
                {"revision_id": "rev-1", "graph_stale": True},
                linear.context_editing,
            )
            self.assertEqual([4], [timeline for timeline, _ in SQLiteContextStorage().read_rows(database)])


if __name__ == "__main__": unittest.main()
