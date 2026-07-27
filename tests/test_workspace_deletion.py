"""Regression coverage for safe local workspace removal."""

import json
import tempfile
from pathlib import Path

from llmfetcher import webapp


def test_remove_workspace_deletes_only_its_directory_and_registry_record() -> None:
    """Remove a stopped non-default workspace while retaining the default one."""
    with tempfile.TemporaryDirectory() as directory:
        old_root, old_index = webapp.WORKSPACE_ROOT, webapp.WORKSPACE_INDEX
        webapp.WORKSPACE_ROOT = Path(directory) / "workspaces"
        webapp.WORKSPACE_INDEX = Path(directory) / "workspaces.json"
        webapp.WORKSPACE_ROOT.mkdir()
        webapp.WORKSPACE_INDEX.write_text(json.dumps([
            {"id": "default", "name": "默认工作空间"},
            {"id": "remove_me", "name": "Remove me"},
        ]), encoding="utf-8")
        target = webapp.WORKSPACE_ROOT / "remove_me"
        target.mkdir()
        (target / "context.json").write_text("{}", encoding="utf-8")
        try:
            webapp._remove_workspace("remove_me")
            assert not target.exists()
            assert webapp._read_workspaces() == [{"id": "default", "name": "默认工作空间"}]
        finally:
            webapp.WORKSPACE_ROOT, webapp.WORKSPACE_INDEX = old_root, old_index
