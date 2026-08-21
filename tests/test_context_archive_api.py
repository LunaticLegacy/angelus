"""Read-only visibility of raw context archived during compaction."""

import json
import tempfile
import unittest
from pathlib import Path

from angelus import storage, webapp


class ContextArchiveApiTests(unittest.TestCase):
    def test_agent_context_graph_is_bounded_and_exposes_only_visible_relations(self) -> None:
        """The graph inspector receives a safe per-Agent persisted snapshot."""
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(directory)
            try:
                graph_path = webapp._context_path("work", "session", "worker")
                graph_path.with_name(f"{graph_path.name}.graph.json").write_text(json.dumps({
                    "nodes": {
                        "file:a.py": {"id": "file:a.py", "name": "a.py", "entity_type": "file", "last_seen": 5, "freq": 2},
                        "tool:rg": {"id": "tool:rg", "name": "rg", "entity_type": "tool", "last_seen": 4, "freq": 1},
                        "concept:hidden": {"id": "concept:hidden", "name": "hidden", "last_seen": 1},
                    },
                    "edges": [
                        {"source_id": "file:a.py", "target_id": "tool:rg", "relation": "uses", "weight": 2, "last_seen": 5, "evidence": [3]},
                        {"source_id": "file:a.py", "target_id": "concept:hidden", "relation": "mentions"},
                    ],
                    "communities": {"0": [{"level": 0, "community_id": "one", "summary": "source tools"}]},
                }), encoding="utf-8")

                payload = webapp._agent_context_graph("work", "worker", limit=2)

                self.assertTrue(payload["available"])
                self.assertTrue(payload["truncated"])
                self.assertEqual(payload["node_count"], 3)
                self.assertEqual([node["id"] for node in payload["nodes"]], ["file:a.py", "tool:rg"])
                self.assertEqual(payload["edges"], [{
                    "source_id": "file:a.py", "target_id": "tool:rg", "relation": "uses", "weight": 2.0,
                    "first_seen": 0, "last_seen": 5, "valid": True, "evidence": [3],
                }])
                self.assertEqual(payload["community_count"], 1)
            finally:
                storage.WORKSPACE_ROOT = original_root

    def test_agent_context_graph_is_empty_when_companion_file_is_missing(self) -> None:
        """Old linear-only contexts remain inspectable without an API error."""
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(directory)
            try:
                payload = webapp._agent_context_graph("work", "coordinator")
                self.assertFalse(payload["available"])
                self.assertEqual(payload["nodes"], [])
                self.assertEqual(payload["edges"], [])
            finally:
                storage.WORKSPACE_ROOT = original_root

    def test_archive_page_exposes_raw_evidence_and_timeline_with_pagination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(directory)
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
                storage.WORKSPACE_ROOT = original_root

    def test_active_context_page_is_paginated_and_keeps_typed_tool_results(self) -> None:
        """The context viewer reads the active prompt without loading it all."""
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(directory)
            try:
                context = webapp._context_path("work", "session", "coordinator")
                context.write_text(json.dumps({"messages": [
                    {"timeline": 1, "role": "user", "content": "first"},
                    {"timeline": 2, "role": "assistant", "content": "second", "tool_calls": [{
                        "call": {"name": "plan", "arguments": {"id": 2}},
                        "result": {"ok": True},
                    }]},
                    {"timeline": 3, "role": "user", "content": "third"},
                ]}), encoding="utf-8")

                newest = webapp._agent_context_page("work", "coordinator", limit=2)
                self.assertEqual([item["timeline"] for item in newest["messages"]], [3, 2])
                self.assertEqual(newest["messages"][1]["tools"][0]["result"], {"ok": True})
                self.assertEqual(newest["next_before"], 1)

                older = webapp._agent_context_page("work", "coordinator", before=newest["next_before"], limit=2)
                self.assertEqual([item["timeline"] for item in older["messages"]], [1])
                self.assertIsNone(older["next_before"])
            finally:
                storage.WORKSPACE_ROOT = original_root

    def test_archive_page_is_empty_for_legacy_or_malformed_contexts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(directory)
            try:
                context = webapp._context_path("work", "legacy", "coordinator")
                context.write_text(json.dumps({"messages": [{"role": "user", "content": "old"}]}), encoding="utf-8")
                self.assertEqual(webapp._archived_context_page("work", "legacy"), {
                    "evidence": [], "total": 0, "next_before": None,
                })

                context.write_text(json.dumps({"archive": [{"timeline": "bad", "role": "user"}, None]}), encoding="utf-8")
                self.assertEqual(webapp._archived_context_page("work", "legacy")["evidence"], [])
            finally:
                storage.WORKSPACE_ROOT = original_root


if __name__ == "__main__":
    unittest.main()
