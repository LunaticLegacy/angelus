"""Regression tests for the durable SSE event stream."""

from __future__ import annotations

import json
import tempfile
import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient

from angelus import storage, webapp
from angelus.classes import ActiveRun, BrowserRunControl


def _seed_events(count: int = 3) -> None:
    for index in range(count):
        storage._append_session_event("demo", "demo", {
            "event": "lifecycle", "type": f"OLD-{index}", "timestamp": index,
        })


def _collect(client: TestClient, url: str, seconds: float = 1.0):
    received: list[dict] = []
    def consume() -> None:
        try:
            with client.stream("GET", url) as response:
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        received.append(json.loads(line[6:]))
        except Exception as exc:  # pragma: no cover - defensive
            received.append({"error": str(exc)})
    thread = threading.Thread(target=consume, daemon=True)
    thread.start()
    time.sleep(seconds)
    return thread, received


class TestSseStream:
    """Exercise after-offset replay and no-active-run behaviour."""

    def test_after_offset_skips_replayed_history(self) -> None:
        """A refresh that already rendered N events must not receive them again."""
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(directory)
            try:
                _seed_events(3)
                key = ("demo", "demo")
                with storage._sessions_lock:
                    storage._sessions[key] = storage.BrowserSession()
                session = storage._get_session("demo", "demo")
                active = ActiveRun(control=BrowserRunControl())
                session.active = active
                client = TestClient(webapp.app)
                thread, received = _collect(
                    client,
                    "/api/workspaces/demo/runs/demo/events?after=3",
                    seconds=0.6,
                )
                # 追加一条新事件，应被流推送
                storage._append_session_event("demo", "demo", {
                    "event": "lifecycle", "type": "NEW-1", "timestamp": 3,
                })
                time.sleep(0.6)
                active.done.set()
                thread.join(timeout=5)
                types = [event.get("type") for event in received]
                assert "NEW-1" in types, f"expected NEW-1, got {types}"
                assert all(not str(t).startswith("OLD-") for t in types), (
                    f"after=3 must not replay OLD events, got {types}"
                )
            finally:
                storage.WORKSPACE_ROOT = original_root
                with storage._sessions_lock:
                    storage._sessions.pop(key, None)

    def test_no_active_run_replays_tail_and_closes(self) -> None:
        """A finished run must not leave the browser retrying a 404 forever."""
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(directory)
            try:
                _seed_events(2)
                client = TestClient(webapp.app)
                thread, received = _collect(
                    client,
                    "/api/workspaces/demo/runs/demo/events?after=0",
                    seconds=1.0,
                )
                thread.join(timeout=5)
                assert len(received) == 2, f"expected 2 replayed events, got {len(received)}"
                assert [e.get("type") for e in received] == ["OLD-0", "OLD-1"]
            finally:
                storage.WORKSPACE_ROOT = original_root
