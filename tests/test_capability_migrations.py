"""Focused regression coverage for restored Angelus capability families."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import unittest

from llmfetcher.context_handlers.linear import ContextHandlerLinear

from angelus.core import AngelusCore
from angelus.modules.console_module.console_state import ConsoleDomainError, ConsoleState
from angelus.modules.context_version_module.store import ContextEditOperation, ContextVersionError, ContextVersionStore
from angelus.modules.mcp_module.store import MCPStore
from angelus.modules.session_memory_module.store import SessionMemoryStore
from angelus.modules.tool_module import ToolPolicy


class CapabilityMigrationTests(unittest.TestCase):
    def test_nested_plan_is_atomic_and_derives_parent_status(self) -> None:
        with TemporaryDirectory() as directory:
            state = ConsoleState(Path(directory))
            plan = state.set_plan("coordinator", "Ship", "full tree", [{
                "id": "root", "title": "Root", "status": "completed", "subtasks": [
                    {"id": "a", "title": "A", "status": "completed"},
                    {"id": "b", "title": "B", "status": "not_started"},
                ],
            }])
            self.assertEqual(plan.tasks[0].status, "in_progress")
            updated = state.update_task_status("coordinator", "b", "completed")
            self.assertEqual(updated.tasks[0].status, "completed")
            with self.assertRaises(ConsoleDomainError):
                state.update_task_status("coordinator", "root", "blocked")
            state.bind_execution("b", "assignment-1")
            bound = state.plan("coordinator").tasks[0].subtasks[1]
            self.assertEqual(bound.execution.active_assignment_id, "assignment-1")
            self.assertEqual(bound.status, "in_progress")
            state.update_assignment_status("assignment-1", "completed")
            self.assertEqual(state.plan("coordinator").tasks[0].status, "completed")

    def test_flat_schema_one_plan_is_migrated_to_coordinator(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory); (root / "console").mkdir()
            (root / "console" / "state.json").write_text('{"plan":[{"id":"old","status":"completed","title":"Old"}]}')
            self.assertEqual(ConsoleState(root).plan("coordinator").tasks[0].id, "old")

    def test_context_edit_requires_revision_and_restore_is_forward_only(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "agent" / "context.json"; path.parent.mkdir()
            linear = ContextHandlerLinear(None); linear.add_user_message("before"); self.assertTrue(linear.save(path))
            store = ContextVersionStore(SimpleNamespace(context_path=path, context_handler=linear), "coordinator")
            first = store.inspect(); record = first["records"][0]
            edited = store.apply(None, [ContextEditOperation("replace_content", record["record_id"], "after")], "fix")
            self.assertEqual(edited["records"][0]["content"], "after")
            with self.assertRaises(ContextVersionError): store.apply(None, [ContextEditOperation("delete", edited["records"][0]["record_id"])], "stale")
            active_revision = next(item for item in edited["revisions"] if item["revision_id"] == edited["revision_id"])
            baseline = active_revision["parent_revision_id"]
            restored = store.restore(edited["revision_id"], baseline, "undo")
            self.assertEqual(restored["records"][0]["content"], "before")
            self.assertNotEqual(restored["revision_id"], baseline)

    def test_mcp_secrets_are_not_in_catalog_and_bindings_resolve_by_role(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory); store = MCPStore(root)
            public = store.create({"name":"local","transport":"stdio","command":"/bin/echo","args":[],"env":{"TOKEN":"secret"},"headers":{},"bearer_token":"bearer"})
            catalog = (root / "settings" / "mcp-servers.json").read_text()
            self.assertNotIn("secret", catalog); self.assertNotIn("bearer", catalog)
            store.set_probe(public["id"], {"ok":True}, {"tools":["mcp.local.echo"]})
            store.write_bindings("demo", [{"server_id":public["id"],"roles":["worker"],"tools":["echo"]}])
            self.assertEqual(store.resolve("demo", root, "coordinator"), [])
            self.assertEqual(store.resolve("demo", root, "worker")[0]["tool_allowlist"], ["echo"])

    def test_restored_tools_are_registered_and_enabled_by_default(self) -> None:
        with TemporaryDirectory() as directory:
            root=Path(directory); (root/"project").mkdir(); core=AngelusCore(state_root=root/"state")
            core.session_service.create("demo","Demo",root/"project")
            catalog={category.id:{tool.id for tool in category.tools} for category in core.tool_registry.catalog().categories}
            self.assertEqual(catalog["context_version"], {"inspect_agent_context","edit_agent_context","restore_agent_context"})
            self.assertEqual(len(catalog["session_memory"]), 6)
            permissions=ToolPolicy.from_profile(core.run_profiles.global_profile()["tool_permissions"])
            names={tool.name for tool in core.tool_registry.materialize(core.sessions.get("demo"),permissions,"coordinator","coordinator")}
            self.assertTrue({"inspect_agent_context","search_session_memory","create_session_handoff"} <= names)

    def test_session_snapshot_reads_current_sqlite_context(self) -> None:
        with TemporaryDirectory() as directory:
            root=Path(directory); path=root/"sessions"/"source"/"agents"/"coordinator"/"context.json"; path.parent.mkdir(parents=True)
            linear=ContextHandlerLinear(None); linear.add_user_message("portable evidence"); self.assertTrue(linear.save(path))
            manifest=SessionMemoryStore(root).snapshot("source")
            self.assertEqual(manifest["evidence"][0]["body"], "portable evidence")


if __name__ == "__main__": unittest.main()
