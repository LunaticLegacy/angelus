"""Regression tests for workspace/session registration ownership."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
import json

from angelus.core import AngelusCore


class WorkspaceServiceTests(unittest.TestCase):
    """Ensure durable workspace records do not create a second session owner."""

    def test_create_is_durable_and_core_rehydrates_empty_session(self) -> None:
        """A subsequent host sees the workspace and can address its session."""
        with tempfile.TemporaryDirectory() as temporary:
            state_root = Path(temporary) / "state"
            project = Path(temporary) / "project"
            project.mkdir()
            core = AngelusCore(state_root=state_root)
            created = core.session_service.create("alpha", "Alpha", project)

            restored = AngelusCore(state_root=state_root)

            self.assertEqual(created.project_path, project.resolve())
            self.assertTrue(restored.sessions.exists("alpha"))
            self.assertEqual([item.session_id for item in restored.session_service.list()], ["alpha"])

    def test_legacy_session_index_is_imported_without_inventing_project_paths(self) -> None:
        """Old session identities remain selectable after the storage redesign."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            legacy = root / "workspace" / "sessions.json"
            legacy.parent.mkdir()
            project = root / "project"
            project.mkdir()
            legacy.write_text(
                json.dumps([
                    {"id": "bound", "name": "Bound", "project_path": str(project)},
                    {"id": "unbound", "name": "Unbound"},
                ]),
                encoding="utf-8",
            )
            catalog_path = root / "state" / "workspaces.json"
            from angelus.modules.workspace_module import WorkspaceCatalog

            catalog = WorkspaceCatalog(catalog_path)
            imported = catalog.import_legacy_sessions(legacy, root / "state" / "sessions")
            by_id = {workspace.session_id: workspace for workspace in imported}

            self.assertEqual(set(by_id), {"bound", "unbound"})
            self.assertEqual(by_id["bound"].project_path, project.resolve())
            self.assertIsNone(by_id["unbound"].project_path)
            catalog.remove("bound")
            self.assertEqual(catalog.import_legacy_sessions(legacy, root / "state" / "sessions"), ())
            self.assertEqual([item.session_id for item in catalog.list()], ["unbound"])

    def test_delete_removes_session_registry_and_durable_state(self) -> None:
        """A confirmed deletion cannot be rehydrated by a later core instance."""
        with tempfile.TemporaryDirectory() as temporary:
            state_root = Path(temporary) / "state"
            project = Path(temporary) / "project"
            project.mkdir()
            core = AngelusCore(state_root=state_root)
            workspace = core.session_service.create("alpha", "Alpha", project)
            workspace.state_path.mkdir(parents=True)
            (workspace.state_path / "marker").write_text("state", encoding="utf-8")

            core.session_service.delete("alpha", confirmation="alpha")
            restored = AngelusCore(state_root=state_root)

            self.assertFalse(core.sessions.exists("alpha"))
            self.assertFalse(workspace.state_path.exists())
            self.assertFalse(restored.sessions.exists("alpha"))


if __name__ == "__main__":
    unittest.main()
