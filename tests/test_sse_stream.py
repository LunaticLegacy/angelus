"""Regression tests for the durable SSE event stream."""

from __future__ import annotations

import json
from types import SimpleNamespace
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch
from starlette.requests import Request

from angelus import storage
from angelus.classes import ActiveRun, BrowserRunControl
from angelus.api.runs import _event_resume_offset
from angelus.event_stream import (
    EventBroker,
    historical_event_stream,
    live_event_stream,
    publish_durable_event,
)
from llmfetcher.agent import Agent
from llmfetcher.context_handlers.linear import _COMPACTING_SYSTEM_PROMPT
from llmfetcher.llm_types import LLMOutput


def _seed_events(count: int = 3) -> None:
    for index in range(count):
        storage._append_session_event("demo", "demo", {
            "event": "lifecycle", "type": f"OLD-{index}", "timestamp": index,
        })


def _payloads(chunks: list[str]) -> list[dict]:
    """Decode data records while ignoring SSE IDs and keepalive comments."""
    return [
        json.loads(line[6:])
        for chunk in chunks
        for line in chunk.splitlines()
        if line.startswith("data: ")
    ]


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
                active = ActiveRun(
                    control=BrowserRunControl(),
                    event_broker=EventBroker(
                        durable_offset=storage._session_event_log_size("demo", "demo"),
                    ),
                )
                session.active = active
                start_offset = storage._session_event_offset_after("demo", "demo", 3)

                def publish() -> None:
                    time.sleep(0.02)
                    publish_durable_event(active, "demo", "demo", {
                        "event": "lifecycle", "type": "NEW-1", "timestamp": 3,
                    })
                    active.event_broker.close()
                    active.done.set()

                thread = threading.Thread(target=publish)
                thread.start()
                received = _payloads(list(live_event_stream(
                    "demo", "demo", active, start_offset,
                )))
                thread.join(timeout=2)
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
                received = _payloads(list(historical_event_stream(
                    "demo", "demo", 0,
                )))
                assert len(received) == 2, f"expected 2 replayed events, got {len(received)}"
                assert [e.get("type") for e in received] == ["OLD-0", "OLD-1"]
            finally:
                storage.WORKSPACE_ROOT = original_root

    def test_resume_cursor_precedence_and_legacy_count(self) -> None:
        """Last-Event-ID wins over cursor, which wins over legacy after."""
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(directory)
            try:
                _seed_events(2)
                first_offset = storage._session_event_offset_after("demo", "demo", 1)
                request = Request({
                    "type": "http",
                    "headers": [(b"last-event-id", str(first_offset).encode())],
                })
                assert _event_resume_offset(
                    request, "demo", "demo", after=0, cursor=1,
                ) == first_offset
                assert _event_resume_offset(
                    Request({"type": "http", "headers": []}),
                    "demo", "demo", after=0, cursor=first_offset,
                ) == first_offset
                assert _event_resume_offset(
                    Request({"type": "http", "headers": []}),
                    "demo", "demo", after=1, cursor=None,
                ) == first_offset
            finally:
                storage.WORKSPACE_ROOT = original_root

    def test_idle_keepalive_does_not_reread_event_log(self) -> None:
        """Idle live connections perform one handoff read, not timed polling."""
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(directory)
            active = ActiveRun(control=BrowserRunControl())
            try:
                from angelus.event_stream import sse

                original_reader = sse._read_session_event_records_from
                with patch.object(
                    sse, "_read_session_event_records_from", wraps=original_reader,
                ) as reader:
                    stream = live_event_stream(
                        "demo", "demo", active, 0, keepalive_timeout=0.02,
                    )
                    assert next(stream) == ": keepalive\n\n"
                    assert next(stream) == ": keepalive\n\n"
                    assert reader.call_count == 1
            finally:
                active.event_broker.close()
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
                    publish_durable_event(active, "demo", "demo", payload)

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

                # The same events must be readable back through SSE replay.
                session.active = None  # replay the durable tail once, then close
                received = _payloads(list(historical_event_stream(
                    "demo", "demo", 0,
                )))
                streamed = [e.get("type") for e in received]
                assert "context:compact_started" in streamed, streamed
                assert "context:compact_success" in streamed, streamed
            finally:
                storage.WORKSPACE_ROOT = original_root
                with storage._sessions_lock:
                    storage._sessions.pop(key, None)
