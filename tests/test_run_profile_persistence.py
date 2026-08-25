"""Regression coverage for credential-safe run provenance and event writes."""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path

from angelus import run_profiles, runtime, storage, webapp
from angelus.classes import RunConfig
from angelus.classes import RunRequest
from llmfetcher.events import ExecutionEvent
from llmfetcher.llm_types import LLMOutput


class _CompletedAgent:
    """Minimal no-network Agent stand-in for the run persistence boundary."""

    usage = SimpleNamespace(input_tokens=1, output_tokens=2, total_tokens=3)

    def add_hook(self, _hook: object) -> None:
        pass

    def run(self, _message: str, **_kwargs: object) -> LLMOutput:
        return LLMOutput(content="done", provider="openai", backend_name="browser", model="test")


class _ToolLifecycleAgent(_CompletedAgent):
    """Emit a tool lifecycle event through the hook registered by ``start_run``."""

    def add_hook(self, hook: object) -> None:
        self._hook = hook

    def run(self, message: str, **kwargs: object) -> LLMOutput:
        self._hook(ExecutionEvent(  # type: ignore[attr-defined,operator]
            source="agent",
            agent_name="",
            event_type="agent:tools_completed",
            message="Completed 1 tool call(s)",
            data={"round": 1, "tool_calls": [{"name": "shell", "ok": True}]},
        ))
        return super().run(message, **kwargs)


class _CompletedSwarm:
    """Minimal retained Swarm stand-in for multi-turn run construction tests."""

    def run(self, _message: str, **_kwargs: object) -> dict[str, LLMOutput]:
        """Return the coordinator result expected by the browser run route."""
        return {
            "coordinator": LLMOutput(
                content="done", provider="openai", backend_name="browser", model="test",
            ),
        }

    def total_usage(self) -> dict[str, int]:
        """Provide the aggregate usage shape persisted by ``start_run``."""
        return {"input": 1, "output": 2, "total": 3, "cached": 0, "reasoning": 0}

    def finalize_tasks(self) -> None:
        """Match the terminal-cleanup method invoked by the run route."""

    def view_snapshot(self) -> dict[str, list[object]]:
        """Return the empty graph shape sufficient for persistence assertions."""
        return {"nodes": [], "edges": []}


class _ProfileAwareSwarm(_CompletedSwarm):
    """Retained Swarm double exposing one Coordinator for profile sync tests."""

    def __init__(self) -> None:
        self.coordinator = SimpleNamespace(
            default_max_rounds=12,
            default_max_tokens=4096,
            _agent_name_in_graph="coordinator",
        )

    def get_agent(self, name: str) -> SimpleNamespace | None:
        """Return the durable Coordinator addressed by the graph snapshot."""
        return self.coordinator if name == "coordinator" else None

    def view_snapshot(self) -> dict[str, list[object]]:
        """Expose the retained Coordinator without fabricating graph changes."""
        return {"nodes": [{"id": "coordinator"}], "edges": []}


class _ImmediateThread:
    """Execute a worker target synchronously while retaining Thread's start API."""

    def __init__(self, *, target: object, **_kwargs: object) -> None:
        self._target = target

    def start(self) -> None:
        self._target()  # type: ignore[operator]


class RunProfilePersistenceTests(unittest.TestCase):
    """Exercise provenance snapshots and concurrent event durability."""

    def test_runtime_profile_is_stable_and_never_serializes_credentials(self) -> None:
        """A resumed-session diagnosis needs semantics, but not API secrets."""
        config = RunConfig(
            provider="openai",
            model="deepseek-v4-flash",
            api_key="do-not-persist-me",
            api_url="https://alice:secret@example.test/v1?token=also-secret",
            system_prompt="Private instructions",
            temperature=0.2,
            enable_shell=True,
        )

        profile = webapp._runtime_profile_snapshot(config)

        self.assertEqual(profile, webapp._runtime_profile_snapshot(config))
        serialized = json.dumps(profile, sort_keys=True)
        self.assertNotIn("do-not-persist-me", serialized)
        self.assertNotIn("Private instructions", serialized)
        self.assertNotIn("secret", serialized)
        self.assertNotIn("also-secret", serialized)
        self.assertEqual(profile["api_url"], "https://example.test/v1")
        self.assertEqual(len(profile["fingerprint"]), 64)

    def test_concurrent_event_appends_remain_complete_json_records(self) -> None:
        """Swarm worker hooks must not interleave their NDJSON records."""
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(directory)
            try:
                workers = [
                    threading.Thread(
                        target=webapp._append_session_event,
                        args=("demo", "demo", {"event": "worker", "index": index}),
                    )
                    for index in range(32)
                ]
                for worker in workers:
                    worker.start()
                for worker in workers:
                    worker.join()

                events = webapp._read_session_event_log("demo", "demo")
                self.assertEqual(len(events), 32)
                self.assertEqual({event["index"] for event in events}, set(range(32)))
            finally:
                storage.WORKSPACE_ROOT = original_root

    def test_start_run_persists_profile_in_state_and_event_log(self) -> None:
        """Run provenance survives both the active and terminal state rewrite."""
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            key = ("demo", "demo")
            storage.WORKSPACE_ROOT = Path(directory)
            with storage._sessions_lock:
                prior = storage._sessions.pop(key, None)
            request = RunRequest(
                workspace_id="demo", session_id="demo", message="hello",
                config=RunConfig(model="test", api_key="hidden", system_prompt="private"),
            )
            try:
                with (
                    patch.object(storage, "_workspace_exists", return_value=True),
                    patch.object(runtime, "_build_agent", return_value=_CompletedAgent()),
                    patch.object(webapp.threading, "Thread", _ImmediateThread),
                ):
                    webapp.start_run(request)
                state = json.loads(webapp._run_state_path(*key).read_text(encoding="utf-8"))
                events = webapp._read_session_event_log(*key)
                self.assertEqual(state["status"], "completed")
                self.assertEqual(state["runtime_profile"]["model"], "test")
                self.assertNotIn("hidden", json.dumps(state))
                self.assertEqual(events[0]["event"], "run_started")
                self.assertEqual(
                    events[0]["runtime_profile"]["fingerprint"],
                    state["runtime_profile"]["fingerprint"],
                )
            finally:
                storage.WORKSPACE_ROOT = original_root
                with storage._sessions_lock:
                    storage._sessions.pop(key, None)
                    if prior is not None:
                        storage._sessions[key] = prior

    def test_start_run_persists_single_agent_tool_lifecycle_event(self) -> None:
        """Single-Agent hooks must survive serialization into the durable Trace."""
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            key = ("demo", "demo")
            storage.WORKSPACE_ROOT = Path(directory)
            with storage._sessions_lock:
                prior = storage._sessions.pop(key, None)
            request = RunRequest(
                workspace_id="demo", session_id="demo", message="use a tool",
                config=RunConfig(model="test", api_key="hidden"),
            )
            try:
                with (
                    patch.object(storage, "_workspace_exists", return_value=True),
                    patch.object(runtime, "_build_agent", return_value=_ToolLifecycleAgent()),
                    patch.object(webapp.threading, "Thread", _ImmediateThread),
                ):
                    webapp.start_run(request)

                events = webapp._read_session_event_log(*key)
                lifecycle = next(event for event in events if event["event"] == "lifecycle")
                self.assertEqual(lifecycle["type"], "agent:tools_completed")
                self.assertEqual(lifecycle["agent"], "coordinator")
                self.assertEqual(lifecycle["data"]["tool_calls"][0]["name"], "shell")
            finally:
                storage.WORKSPACE_ROOT = original_root
                with storage._sessions_lock:
                    storage._sessions.pop(key, None)
                    if prior is not None:
                        storage._sessions[key] = prior

    def test_start_run_reuses_completed_swarm_without_rebuilding_agents(self) -> None:
        """A second Swarm turn must run the retained graph instead of replacing it."""
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            key = ("demo", "demo")
            storage.WORKSPACE_ROOT = Path(directory)
            with storage._sessions_lock:
                prior = storage._sessions.pop(key, None)
            request = RunRequest(
                workspace_id="demo", session_id="demo", message="continue",
                config=RunConfig(model="test", api_key="hidden", enable_swarm=True),
            )
            swarm = _CompletedSwarm()
            try:
                with (
                    patch.object(storage, "_workspace_exists", return_value=True),
                    patch.object(runtime, "_build_swarm", return_value=swarm) as build_swarm,
                    patch.object(webapp.threading, "Thread", _ImmediateThread),
                ):
                    webapp.start_run(request)
                    webapp.start_run(request)

                self.assertEqual(build_swarm.call_count, 1)
                self.assertIs(storage._sessions[key].active.swarm, swarm)
            finally:
                storage.WORKSPACE_ROOT = original_root
                with storage._sessions_lock:
                    storage._sessions.pop(key, None)
                    if prior is not None:
                        storage._sessions[key] = prior

    def test_profile_change_updates_retained_swarm_with_zero_round_limit(self) -> None:
        """A new Agent profile updates retained Swarm budgets without rebuilding it."""
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            key = ("demo", "demo")
            storage.WORKSPACE_ROOT = Path(directory)
            with storage._sessions_lock:
                prior = storage._sessions.pop(key, None)
            request = RunRequest(
                workspace_id="demo", session_id="demo", message="continue",
                config=RunConfig(model="test", api_key="hidden", enable_swarm=True),
            )
            swarm = _ProfileAwareSwarm()
            profile_index = Path(directory) / "run-profiles.json"

            try:
                with (
                    patch.object(storage, "_workspace_exists", return_value=True),
                    patch.object(storage, "RUN_PROFILE_INDEX", profile_index),
                    patch.object(runtime, "_build_swarm", return_value=swarm) as build_swarm,
                    patch.object(runtime, "_fetcher_for_config", return_value=object()),
                    patch.object(webapp.threading, "Thread", _ImmediateThread),
                ):
                    webapp.start_run(request)
                    run_profiles.update_profile("demo", {
                        "model": "test", "max_rounds": 0, "max_tokens": 65536,
                        "enable_swarm": True,
                    })
                    webapp.start_run(request)

                self.assertEqual(build_swarm.call_count, 1)
                self.assertEqual(swarm.coordinator.default_max_rounds, 0)
                self.assertEqual(swarm.coordinator.default_max_tokens, 65536)
            finally:
                storage.WORKSPACE_ROOT = original_root
                with storage._sessions_lock:
                    storage._sessions.pop(key, None)
                    if prior is not None:
                        storage._sessions[key] = prior
