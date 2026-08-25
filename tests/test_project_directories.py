"""Project-directory separation and native picker regression coverage."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from angelus import runtime, storage
from angelus.api import sessions
from angelus.classes import ProjectPathRequest, RunConfig, WorkspaceRequest


@pytest.fixture
def isolated_state(tmp_path: Path):
    """Redirect the mutable session registry and state root for one test.

    Args:
        tmp_path: Pytest-owned temporary directory.

    Yields:
        State root used by storage and session APIs during the test.
    """
    old_root, old_index = storage.WORKSPACE_ROOT, storage.WORKSPACE_INDEX
    storage.WORKSPACE_ROOT = tmp_path / "state"
    storage.WORKSPACE_INDEX = storage.WORKSPACE_ROOT / "sessions.json"
    try:
        yield storage.WORKSPACE_ROOT
    finally:
        with storage._sessions_lock:
            storage._sessions.clear()
        storage.WORKSPACE_ROOT, storage.WORKSPACE_INDEX = old_root, old_index


def test_new_session_binds_existing_project_but_deletes_only_state(
    isolated_state: Path, tmp_path: Path,
) -> None:
    """Registry deletion must never remove files from the selected project."""
    project = tmp_path / "用户项目"
    project.mkdir()
    marker = project / "keep.txt"
    marker.write_text("user data", encoding="utf-8")

    created = sessions.create_session(
        WorkspaceRequest(name="Project chat", project_path=str(project)),
    )
    listed = next(item for item in sessions.list_sessions()["sessions"] if item["id"] == created["id"])

    assert created["project_path"] == str(project.resolve())
    assert listed["project_path"] == str(project.resolve())
    assert listed["path"] == str(isolated_state / created["id"])
    assert (isolated_state / created["id"]).is_dir()
    assert list(project.iterdir()) == [marker]

    storage._remove_workspace(created["id"])

    assert marker.read_text(encoding="utf-8") == "user data"
    assert not (isolated_state / created["id"]).exists()


def test_legacy_session_uses_internal_directory_as_project(
    isolated_state: Path,
) -> None:
    """Records created before project binding preserve their original cwd."""
    storage._write_workspaces([{"id": "legacy", "name": "Legacy"}])

    resolved = storage._project_path("legacy", "legacy")

    assert resolved == isolated_state / "legacy"
    assert resolved.is_dir()


def test_inactive_legacy_session_can_rebind_to_an_existing_project(
    isolated_state: Path, tmp_path: Path,
) -> None:
    """A legacy fallback remains usable until the user explicitly replaces it."""
    project = tmp_path / "replacement"
    project.mkdir()
    storage._write_workspaces([{"id": "legacy", "name": "Legacy"}])

    response = sessions.update_session_project_path(
        "legacy", ProjectPathRequest(project_path=str(project)),
    )

    assert response == {"id": "legacy", "project_path": str(project.resolve())}
    record = storage._read_workspaces()[0]
    assert record["project_path"] == str(project.resolve())
    assert storage._project_path("legacy", "legacy") == project.resolve()


def test_active_session_cannot_change_project_directory(
    isolated_state: Path, tmp_path: Path,
) -> None:
    """A running Agent must not have its working directory changed mid-turn."""
    project = tmp_path / "active-project"
    project.mkdir()
    storage._write_workspaces([{"id": "active", "name": "Active"}])
    storage._sessions[("active", "active")] = SimpleNamespace(
        active=SimpleNamespace(done=SimpleNamespace(is_set=lambda: False)),
    )

    with pytest.raises(HTTPException) as raised:
        sessions.update_session_project_path(
            "active", ProjectPathRequest(project_path=str(project)),
        )

    assert raised.value.status_code == 409
    assert "project_path" not in storage._read_workspaces()[0]


@pytest.mark.parametrize("value", ["relative/path", "/definitely/missing/angelus-project"])
def test_project_path_rejects_relative_or_missing_directories(value: str) -> None:
    """A prompt string cannot substitute for a real existing project root."""
    with pytest.raises(ValueError):
        storage._validate_project_path(value)


def test_agent_shell_and_prompt_use_registered_project(
    isolated_state: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The backend-enforced Shell cwd and explanatory prompt use one path."""
    project = tmp_path / "project"
    project.mkdir()
    storage._write_workspaces([{
        "id": "bound", "name": "Bound", "project_path": str(project.resolve()),
    }])
    shell_calls: list[dict[str, object]] = []
    monkeypatch.setattr(runtime, "create_shell_tools", lambda **kwargs: shell_calls.append(kwargs) or [])

    agent = runtime._build_agent(
        RunConfig(model="test", api_key="test", enable_shell=True), "bound", "bound",
    )

    assert shell_calls[0]["sandbox_cwd"] == str(project.resolve())
    assert str(project.resolve()) in agent.system_prompt
    assert "runtime state is stored separately" in agent.system_prompt


def test_native_picker_returns_canonical_path_or_cancellation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The loopback picker distinguishes a selected folder from cancellation."""
    project = tmp_path / "picked"
    project.mkdir()
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
    monkeypatch.setattr(sessions, "_directory_picker_command", lambda: ["picker"])
    monkeypatch.setattr(
        sessions.subprocess, "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout=f"{project}\n", stderr=""),
    )

    selected = sessions.pick_workspace_directory(request)

    assert selected == {"path": str(project.resolve()), "cancelled": False}

    monkeypatch.setattr(
        sessions.subprocess, "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stdout="", stderr="cancelled"),
    )
    assert sessions.pick_workspace_directory(request) == {"path": None, "cancelled": True}


def test_native_picker_rejects_remote_clients() -> None:
    """A network client cannot make the backend open host GUI windows."""
    request = SimpleNamespace(client=SimpleNamespace(host="192.0.2.10"))

    with pytest.raises(HTTPException) as raised:
        sessions.pick_workspace_directory(request)

    assert raised.value.status_code == 403
