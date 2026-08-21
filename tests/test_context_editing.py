"""Regression coverage for versioned active-context edits and recovery."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from angelus.context_editing import (
    ContextEditError,
    ContextEditOperation,
    ContextEditStore,
    create_context_editing_tools,
)
from angelus import storage, webapp


class ContextEditingTests(unittest.TestCase):
    """Exercise append-only revisions without changing archived evidence."""

    def _store(self, directory: str) -> ContextEditStore:
        """Create an editable checkpoint with two timeline-stable messages.

        Args:
            directory: Temporary test directory receiving the context file.

        Returns:
            Agent-scoped context editing store backed by that file.
        """
        path = Path(directory) / "contexts" / "coordinator.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({
            "messages": [
                {"timeline": 1, "role": "user", "content": "original request"},
                {"timeline": 2, "role": "assistant", "content": "original answer"},
            ],
            "archive": [{"timeline": 0, "role": "system", "content": "archive stays immutable"}],
        }), encoding="utf-8")
        return ContextEditStore(path, "coordinator")

    def test_first_edit_saves_baseline_and_restore_is_forward_only(self) -> None:
        """A first edit can always recover its pristine legacy checkpoint."""
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(directory)
            before = store.inspect()
            first = before["records"][0]

            changed = store.apply(
                None,
                [ContextEditOperation("replace_content", first["record_id"], "edited request")],
                actor="test",
                reason="correct an accidental prompt",
            )
            revision_id = changed["revision"]["revision_id"]
            revisions = store.list_revisions()
            baseline = next(item for item in revisions if item["revision_id"].startswith("baseline-"))
            self.assertEqual(changed["context"]["revision_id"], revision_id)
            self.assertTrue(changed["context"]["graph_stale"])

            restored = store.restore(
                revision_id,
                baseline["revision_id"],
                actor="test",
                reason="recover pristine context",
            )
            raw = json.loads(store.path.read_text(encoding="utf-8"))
            self.assertEqual(raw["messages"][0]["content"], "original request")
            self.assertEqual(raw["archive"][0]["content"], "archive stays immutable")
            self.assertEqual(restored["revision"]["restored_from"], baseline["revision_id"])
            self.assertNotEqual(restored["revision"]["revision_id"], revision_id)
            self.assertEqual(len(store.audit_path.read_text(encoding="utf-8").splitlines()), 3)

    def test_stale_revision_and_unknown_record_are_rejected(self) -> None:
        """Optimistic revision checks prevent silent concurrent overwrites."""
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(directory)
            record = store.inspect()["records"][0]
            applied = store.apply(
                None,
                [ContextEditOperation("replace_content", record["record_id"], "new")],
                actor="test",
                reason="update",
            )
            with self.assertRaisesRegex(ContextEditError, "stale"):
                store.apply(
                    None,
                    [ContextEditOperation("delete", record["record_id"])],
                    actor="test",
                    reason="stale delete",
                )
            with self.assertRaisesRegex(ContextEditError, "target"):
                store.apply(
                    applied["revision"]["revision_id"],
                    [ContextEditOperation("delete", "unknown-record")],
                    actor="test",
                    reason="bad target",
                )

    def test_context_edit_marks_existing_entity_graph_stale(self) -> None:
        """The graph API never presents entities derived from pre-edit text."""
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(directory)
            try:
                path = webapp._context_path("session", "session", "coordinator")
                path.write_text(json.dumps({"messages": [
                    {"timeline": 1, "role": "user", "content": "original"},
                ]}), encoding="utf-8")
                path.with_name(f"{path.name}.graph.json").write_text(json.dumps({
                    "nodes": {"concept:old": {"id": "concept:old", "name": "old"}},
                    "edges": [], "communities": {},
                }), encoding="utf-8")
                record = ContextEditStore(path, "coordinator").inspect()["records"][0]
                ContextEditStore(path, "coordinator").apply(
                    None,
                    [ContextEditOperation("replace_content", record["record_id"], "new")],
                    actor="test",
                    reason="invalidate graph",
                )

                graph = webapp._agent_context_graph("session", "coordinator")
                self.assertFalse(graph.available)
                self.assertTrue(graph.stale)
                self.assertEqual(graph.nodes, [])
            finally:
                storage.WORKSPACE_ROOT = original_root

    def test_browser_api_and_live_tool_share_the_same_revision_protocol(self) -> None:
        """HTTP and Agent handlers both enforce the public dataclass schema."""
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(directory)
            try:
                path = webapp._context_path("session", "session", "coordinator")
                path.write_text(json.dumps({"messages": [
                    {"timeline": 1, "role": "user", "content": "original"},
                ]}), encoding="utf-8")
                inspected = webapp.inspect_editable_agent_context("session", "coordinator")
                record_id = inspected["records"][0]["record_id"]
                changed = webapp.edit_agent_context("session", "coordinator", {
                    "expected_revision_id": None,
                    "operations": [{
                        "kind": "replace_content",
                        "target_record_id": record_id,
                        "content": "via api",
                    }],
                    "reason": "browser correction",
                })
                self.assertEqual(changed["context"]["records"][0]["content"], "via api")

                callbacks: list[str] = []
                tools = {tool.name: tool for tool in create_context_editing_tools(
                    ContextEditStore(path, "coordinator"),
                    persist_context=lambda: callbacks.append("persist"),
                    reload_context=lambda: callbacks.append("reload"),
                )}
                tool_view = tools["inspect_agent_context"].handler()
                tool_record_id = tool_view["records"][0]["record_id"]
                tools["edit_agent_context"].handler(
                    expected_revision_id=tool_view["revision_id"],
                    operations=[{
                        "kind": "replace_content",
                        "target_record_id": tool_record_id,
                        "content": "via tool",
                    }],
                    reason="agent correction",
                )
                self.assertEqual(callbacks, ["persist", "reload"])
            finally:
                storage.WORKSPACE_ROOT = original_root


if __name__ == "__main__":
    unittest.main()
