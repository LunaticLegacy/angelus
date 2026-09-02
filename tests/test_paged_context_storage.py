"""Regression tests for bounded context checkpoint persistence."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from llmfetcher.context_handlers.linear import ContextHandlerLinear, read_persisted_context_page


class _NoopCompactor:
    """Minimal compactor placeholder because this test does not compact."""


class PagedContextStorageTests(unittest.TestCase):
    """Verify the durable reader returns bounded newest-first windows."""

    def test_save_load_and_page_without_full_context(self) -> None:
        """Store 205 entries then restore and page the newest 200 entries.

        Returns:
            ``None`` after asserting chronological pages and a SQLite pointer.
        """
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.json"
            writer = ContextHandlerLinear(_NoopCompactor())
            for number in range(205):
                writer.add_user_message(f"message-{number}")
            self.assertTrue(writer.save(path))
            pointer = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(3, pointer["schema_version"])
            reader = ContextHandlerLinear(_NoopCompactor())
            self.assertTrue(reader.load(path))
            self.assertEqual(200, len(reader.messages))
            newest, cursor, total = read_persisted_context_page(path)
            self.assertEqual(205, total)
            self.assertEqual(200, len(newest))
            self.assertEqual(6, newest[0].timeline)
            self.assertEqual(205, newest[-1].timeline)
            self.assertEqual(6, cursor)
            oldest, cursor, total = read_persisted_context_page(path, before_timeline=cursor)
            self.assertEqual(205, total)
            self.assertEqual([1, 2, 3, 4, 5], [entry.timeline for entry in oldest])
            self.assertIsNone(cursor)

