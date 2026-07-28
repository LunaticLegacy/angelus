"""Regression coverage for Angelus superproject workspace discovery."""

import tempfile
import unittest
from pathlib import Path

from angelus.webapp import _default_state_root


class StateRootTests(unittest.TestCase):
    """Verify standalone and Git-submodule workspace defaults."""

    def test_standalone_project_uses_its_own_workspace(self) -> None:
        """A normal LLMFetcher checkout keeps runtime state in-project."""
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory) / "llmfetcher"
            project_root.mkdir()

            self.assertEqual(
                _default_state_root(project_root),
                project_root / "workspace",
            )

    def test_angelus_submodule_uses_the_superproject_workspace(self) -> None:
        """A registered submodule must recover Angelus sessions by default."""
        with tempfile.TemporaryDirectory() as directory:
            superproject_root = Path(directory) / "angelus"
            project_root = superproject_root / "llmfetcher"
            project_root.mkdir(parents=True)
            (superproject_root / ".gitmodules").write_text(
                '[submodule "llmfetcher"]\n\tpath = llmfetcher\n',
                encoding="utf-8",
            )

            self.assertEqual(
                _default_state_root(project_root),
                superproject_root / "workspace",
            )
