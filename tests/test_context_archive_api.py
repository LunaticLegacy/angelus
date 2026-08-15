"""Read-only visibility of raw context archived during compaction."""

import json
import tempfile
import unittest
from pathlib import Path

from angelus import webapp


class ContextArchiveApiTests(unittest.TestCase):
    def test_archive_page_exposes_raw_evidence_and_timeline_with_pagination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            original_root = webapp.WORKSPACE_ROOT
            webapp.WORKSPACE_ROOT = Path(directory)
            try:
                context = webapp._context_path("work", "session", "coordinator")
                context.write_text(json.dumps({"archive": [
                    {"timeline": 1, "role": "user", "content": "first", "tags": ["request"]},
                    {"timeline": 2, "role": "assistant", "content": "second", "content_reasoning": "why",
                     "tool_calls": [{"call": {"name": "search", "arguments": {"q": "x"}}, "result": "found"}]},
                    {"timeline": 3, "role": "user", "content": "third"},
                ], "messages": []}), encoding="utf-8")

                newest = webapp._archived_context_page("work", "session", limit=2)
                self.assertEqual(newest["total"], 3)
                self.assertEqual(newest["next_before"], 1)
                self.assertEqual([item["timeline"] for item in newest["evidence"]], [3, 2])
                self.assertEqual(newest["evidence"][1]["reasoning"], "why")
                self.assertEqual(newest["evidence"][1]["tool_calls"][0]["result"], "found")

                older = webapp._archived_context_page("work", "session", before=newest["next_before"], limit=2)
                self.assertIsNone(older["next_before"])
                self.assertEqual([item["timeline"] for item in older["evidence"]], [1])
            finally:
                webapp.WORKSPACE_ROOT = original_root

    def test_archive_page_is_empty_for_legacy_or_malformed_contexts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            original_root = webapp.WORKSPACE_ROOT
            webapp.WORKSPACE_ROOT = Path(directory)
            try:
                context = webapp._context_path("work", "legacy", "coordinator")
                context.write_text(json.dumps({"messages": [{"role": "user", "content": "old"}]}), encoding="utf-8")
                self.assertEqual(webapp._archived_context_page("work", "legacy"), {
                    "evidence": [], "total": 0, "next_before": None,
                })

                context.write_text(json.dumps({"archive": [{"timeline": "bad", "role": "user"}, None]}), encoding="utf-8")
                self.assertEqual(webapp._archived_context_page("work", "legacy")["evidence"], [])
            finally:
                webapp.WORKSPACE_ROOT = original_root


if __name__ == "__main__":
    unittest.main()
