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
        result = sessions.open_session_folder("default")
        expected = storage.WORKSPACE_ROOT / "default"
        assert expected.is_dir()
        assert launched == [["explorer.exe", str(expected)]]
        assert result == {"path": str(expected)}
    finally:
        storage.WORKSPACE_ROOT, storage.WORKSPACE_INDEX = old_root, old_index
