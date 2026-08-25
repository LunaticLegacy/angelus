"""Regression tests for the durable SSE event stream."""

from __future__ import annotations

import json
from types import SimpleNamespace
import tempfile
import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient

from angelus import storage, webapp
from angelus.classes import ActiveRun, BrowserRunControl
from llmfetcher.agent import Agent
from llmfetcher.context_handlers.linear import _COMPACTING_SYSTEM_PROMPT
from llmfetcher.llm_types import LLMOutput


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


class _CompactionFetcher:
    """Return normal replies, and an abstract for compaction requests."""

    default_backend_config = SimpleNamespace(
        name="test",
        provider="test",
        model="test-model",
    )

    def fetch(self, **kwargs):
        if kwargs.get("system_prompt") == _COMPACTING_SYSTEM_PROMPT:
            return LLMOutput(
                content="<context_abstract>compacted summary</context_abstract>",
                provider="test",
                backend_name="test",
                model="test-model",
            )
        return LLMOutput(
            content="plain assistant reply",
            provider="test",
            backend_name="test",
            model="test-model",
        )


class TestCompactionLifecycleStream:
    """Agent auto-compaction events persist and reach the SSE stream."""

    def test_compaction_events_persist_and_replay_over_sse(self) -> None:
        """A tiny threshold triggers compaction whose events land in events.ndjson."""
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(directory)
            key = ("demo", "demo")
            try:
                with storage._sessions_lock:
                    storage._sessions[key] = storage.BrowserSession()
                session = storage._get_session("demo", "demo")
                active = ActiveRun(control=BrowserRunControl())
                session.active = active

                agent = Agent(
                    _CompactionFetcher(),  # type: ignore[arg-type]
                    system_prompt="test",
                    max_context_threshold=1,
                    default_max_rounds=1,
                )

                def capture(event) -> None:
                    """Mirror the single-Agent capture used by the run API."""
                    payload = {
                        "event": "lifecycle",
                        "type": event.event_type,
                        "source": event.source,
                        "agent": event.agent_name or "coordinator",
                        "message": event.message,
                        "data": event.data,
                        "timestamp": event.timestamp,
                    }
                    storage._append_session_event("demo", "demo", payload)
                    active.events.put(payload)

                agent.add_hook(capture)
                agent.run("trigger a compaction")

                log = storage._read_session_event_log("demo", "demo")
                types = [entry.get("type") for entry in log]
                compact = [
                    entry for entry in log
                    if str(entry.get("type", "")).startswith("context:compact_")
                ]
                assert compact, f"expected compaction events, got {types}"
                assert [e["type"] for e in compact] == [
                    "context:compact_started",
                    "context:compact_success",
                ]
                for entry in compact:
                    assert entry["source"] == "context", entry
                    assert entry["agent"] == "coordinator", entry
                started = compact[0]["data"]
                assert started["round"] == 2  # user round 1, assistant round 2
                assert started["context_size"] > 0
                assert started["compress_threshold"] == 1
                assert started["ratio"] > 0
                success = compact[1]["data"]
                assert success["archived_messages"] >= 1
                assert success["abstract_characters"] > 0

                # The same events must be readable back over the SSE endpoint.
                client = TestClient(webapp.app)
                session.active = None  # replay the durable tail once, then close
                thread, received = _collect(
                    client,
                    "/api/workspaces/demo/runs/demo/events?after=0",
                    seconds=0.8,
                )
                thread.join(timeout=5)
                streamed = [e.get("type") for e in received]
                assert "context:compact_started" in streamed, streamed
                assert "context:compact_success" in streamed, streamed
            finally:
                storage.WORKSPACE_ROOT = original_root
                with storage._sessions_lock:
                    storage._sessions.pop(key, None)
