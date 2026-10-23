"""Regression coverage for the human-facing archive page projection."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from angelus.core import AngelusCore
from llmfetcher.context_handlers.linear import ContextHandlerLinear


class ContextArchivePageTests(unittest.TestCase):
    def test_archive_projection_pages_only_archived_rows(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            core = AngelusCore(state_root=root / "state")
            core.session_service.create("demo", "Demo", project)

            path = core.workspaces.get("demo").state_path / "agents" / "coordinator" / "context.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            writer = ContextHandlerLinear(None)
            for number in range(120):
                writer.add_user_message(f"message-{number}")
            self.assertTrue(writer.save(path))
            writer.archive.extend(writer.messages)
            writer.messages.clear()
            self.assertTrue(writer.save(path))

            page = core.console_service.archive("demo", "coordinator", limit=50)
            self.assertEqual(50, len(page["entries"]))
            self.assertEqual([71, 120], [page["entries"][0]["timeline"], page["entries"][-1]["timeline"]])
            self.assertEqual("message-70", page["entries"][0]["content"])
            self.assertTrue(page["has_more"])
            self.assertEqual(71, page["next_before"])

            active = core.console_service.context("demo", "coordinator")
            self.assertEqual([], active["metadata"])


if __name__ == "__main__":
    unittest.main()
