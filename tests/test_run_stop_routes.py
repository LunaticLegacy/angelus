"""Regression coverage for browser stop routes and Swarm cancellation semantics."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import FastAPI
from fastapi.testclient import TestClient

from angelus.api import include_api_routes
from angelus.core import AngelusCore


class _BlockingSwarm:
    """Swarm facade holding one attempt open while recording legacy shutdown calls."""

    def __init__(self) -> None:
        """Create a facade with hook accounting and one release gate."""
        self.hooks: list[object] = []
        self.entered = threading.Event()
        self.release = threading.Event()
        self.shutdown_requested = False

    def request_shutdown(self) -> None:
        """Record the legacy scheduler shutdown call that must not be used here."""
        self.shutdown_requested = True

    def add_hook(self, hook: object) -> None:
        """Retain the attempt journal hook supplied by the service."""
        self.hooks.append(hook)

    def remove_hook(self, hook: object) -> bool:
        """Remove one retained hook, reporting whether it was registered."""
        if hook not in self.hooks:
            return False
        self.hooks.remove(hook)
        return True

    def view_snapshot(self) -> dict[str, object]:
        """Return a minimal live topology so control resolves a target Agent."""
        return {"nodes": [{"id": "coordinator", "kind": "agent"}]}

    def run(self, _message: object, *, control: object, entry_agent: str | None = None) -> dict[str, object]:
        """Signal entry and block until the test releases the attempt."""
        self.entered.set()
        self.release.wait(5)
        return {"coordinator": "stopped"}


def _install_active(directory: str) -> tuple[AngelusCore, object, _BlockingSwarm]:
    """Create one Session with a live, blocking execution attempt.

    Args:
        directory: Temporary directory owning project and state roots.

    Returns:
        The process core, the registered Session aggregate, and its swarm double.
    """
    root = Path(directory)
    (root / "project").mkdir()
    core = AngelusCore(state_root=root / "state")
    core.session_service.create("demo", "Demo", root / "project")
    session = core.sessions.get("demo")
    session.agents = [object()]  # type: ignore[list-item]
    core.session_service.ensure_coordinator = lambda _session_id: None  # type: ignore[method-assign]
    swarm = _BlockingSwarm()
    session.swarm = swarm  # type: ignore[assignment]
    core.execution_service.start("demo", "hello")
    assert swarm.entered.wait(5)
    return core, session, swarm


def _client(core: AngelusCore) -> TestClient:
    """Build a route client bound to one already-constructed core."""
    app = FastAPI()
    include_api_routes(app, core)
    return TestClient(app)


def test_cooperative_stop_uses_shared_control_without_short_circuiting_graph() -> None:
    """Graceful stop routes through the attempt controller and never forces the graph."""
    with TemporaryDirectory() as directory:
        core, session, swarm = _install_active(directory)
        try:
            with _client(core) as client:
                response = client.post("/api/runs/demo/stop", json={"reason": "user_requested"})
                assert response.status_code == 200
                body = response.json()
                assert body["accepted"] is True
                assert body["state"] == "stopping"
                assert session.run_control.should_stop()
                assert not session.execution.attempt.controller.force_stopped.is_set()
                assert not swarm.shutdown_requested
                swarm.release.set()
                assert session.execution.wait(5)
        finally:
            swarm.release.set()


def test_force_stop_uses_control_and_persists_force_stopping() -> None:
    """Forced stop sets the cancellation event and persists ``force_stopping``."""
    with TemporaryDirectory() as directory:
        core, session, swarm = _install_active(directory)
        try:
            with _client(core) as client:
                response = client.post("/api/runs/demo/force-stop", json={"reason": "user_requested"})
                assert response.status_code == 200
                body = response.json()
                assert body["accepted"] is True
                assert body["state"] == "force_stopping"
                attempt = session.execution.attempt
                assert attempt.controller.should_stop()
                assert attempt.controller.force_stopped.is_set()
                assert not swarm.shutdown_requested
                manifest = json.loads((attempt.root / "execution-manifest.json").read_text(encoding="utf-8"))
                assert manifest["state"] == "force_stopping"
                swarm.release.set()
                assert session.execution.wait(5)
        finally:
            swarm.release.set()
