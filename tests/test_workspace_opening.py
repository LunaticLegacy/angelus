"""Workspace-folder opening tests."""

from __future__ import annotations

from pathlib import Path

from angelus import storage
from angelus.api import sessions


def test_open_session_folder_launches_windows_explorer(monkeypatch, tmp_path: Path) -> None:
    old_root, old_index = storage.WORKSPACE_ROOT, storage.WORKSPACE_INDEX
    storage.WORKSPACE_ROOT = tmp_path / "workspace"
    storage.WORKSPACE_INDEX = storage.WORKSPACE_ROOT / "sessions.json"
    launched: list[list[str]] = []
    monkeypatch.setattr(sessions.sys, "platform", "win32")
    monkeypatch.setattr(sessions.subprocess, "Popen", lambda command: launched.append(command))
    try:
        project = tmp_path / "selected-project"
        project.mkdir()
        storage._write_workspaces([{
            "id": "default", "name": "default", "project_path": str(project),
        }])
        result = sessions.open_session_folder("default")
        assert launched == [["explorer.exe", str(project)]]
        assert result == {"path": str(project)}
    finally:
        storage.WORKSPACE_ROOT, storage.WORKSPACE_INDEX = old_root, old_index
