"""Regression coverage for safe local workspace removal."""

import json
import tempfile
from pathlib import Path

from angelus import storage, webapp


def test_remove_workspace_deletes_only_its_directory_and_registry_record() -> None:
    """Remove a stopped non-default workspace while retaining the default one."""
    with tempfile.TemporaryDirectory() as directory:
        old_root, old_index = storage.WORKSPACE_ROOT, storage.WORKSPACE_INDEX
        storage.WORKSPACE_ROOT = Path(directory) / "workspaces"
        storage.WORKSPACE_INDEX = Path(directory) / "workspaces.json"
        storage.WORKSPACE_ROOT.mkdir()
        storage.WORKSPACE_INDEX.write_text(json.dumps([
            {"id": "default", "name": "默认工作空间"},
            {"id": "remove_me", "name": "Remove me"},
        ]), encoding="utf-8")
        target = storage.WORKSPACE_ROOT / "remove_me"
        target.mkdir()
        (target / "context.json").write_text("{}", encoding="utf-8")
        try:
            webapp._remove_workspace("remove_me")
            assert not target.exists()
            assert webapp._read_workspaces() == [{"id": "default", "name": "默认工作空间"}]
        finally:
            storage.WORKSPACE_ROOT, storage.WORKSPACE_INDEX = old_root, old_index
