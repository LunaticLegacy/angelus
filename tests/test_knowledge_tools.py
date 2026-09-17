"""Regression tests for the explicit session-local knowledge base."""
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from angelus.core import AngelusCore
from angelus.modules.knowledge_module.knowledge_store import KnowledgeStore
from angelus.modules.tool_module import ToolPolicy


class KnowledgeStoreTests(unittest.TestCase):
    """Verify durable retrieval stays outside Agent context and task state."""

    def test_upsert_search_read_delete_are_session_local(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = KnowledgeStore(root)
            store.upsert("architecture", "Angelus execution attempts use durable checkpoints and journals.", "Execution", ["backend"])
            store.upsert("frontend", "The browser renders a RunGraph projection.", "UI", ["frontend"])
            results = store.search("durable execution checkpoint")
            self.assertEqual("architecture", results[0]["id"])
            document = store.read("architecture", 20)
            self.assertTrue(document["truncated"])
            self.assertTrue(store.delete("architecture"))
            self.assertFalse(store.delete("architecture"))
            self.assertEqual([], store.search("checkpoint"))
            self.assertTrue((root / "knowledge" / "documents.json").is_file())

    def test_registry_requires_explicit_knowledge_grants(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory); project = root / "project"; project.mkdir()
            core = AngelusCore(state_root=root / "state")
            core.session_service.create("demo", "Demo", project)
            session = core.sessions.get("demo")
            self.assertIn("knowledge", [item.id for item in core.tool_registry.categories()])
            disabled = core.tool_registry.materialize(session, ToolPolicy(frozenset(), frozenset()), "coordinator")
            self.assertNotIn("knowledge_search", [item.name for item in disabled])
            granted = ToolPolicy(frozenset({"knowledge"}), frozenset({"knowledge_upsert", "knowledge_search", "knowledge_read", "knowledge_delete"}))
            enabled = core.tool_registry.materialize(session, granted, "worker")
            self.assertEqual(
                ["artifact_info", "artifact_read", "artifact_search", "knowledge_upsert", "knowledge_search", "knowledge_read", "knowledge_delete"],
                [item.name for item in enabled],
            )
            schemas = {item.name: item.schemas.to_dict() for item in enabled if item.name.startswith("knowledge_")}
            self.assertEqual({"id", "content", "title", "tags"}, set(schemas["knowledge_upsert"]["properties"]))
            self.assertEqual(["id", "content"], schemas["knowledge_upsert"]["required"])
            self.assertEqual("integer", schemas["knowledge_search"]["properties"]["limit"]["type"])
