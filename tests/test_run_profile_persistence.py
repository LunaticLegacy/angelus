"""Regression coverage for credential-safe run provenance and event writes."""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path

from angelus import webapp
from angelus.classes import RunConfig
from angelus.classes import RunRequest
from llmfetcher.llm_types import LLMOutput


class _CompletedAgent:
    """Minimal no-network Agent stand-in for the run persistence boundary."""

    usage = SimpleNamespace(input_tokens=1, output_tokens=2, total_tokens=3)

    def add_hook(self, _hook: object) -> None:
        pass

    def run(self, _message: str, **_kwargs: object) -> LLMOutput:
        return LLMOutput(content="done", provider="openai", backend_name="browser", model="test")


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
            original_root = webapp.WORKSPACE_ROOT
            webapp.WORKSPACE_ROOT = Path(directory)
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
                webapp.WORKSPACE_ROOT = original_root

    def test_start_run_persists_profile_in_state_and_event_log(self) -> None:
        """Run provenance survives both the active and terminal state rewrite."""
        with tempfile.TemporaryDirectory() as directory:
            original_root = webapp.WORKSPACE_ROOT
            key = ("demo", "demo")
            webapp.WORKSPACE_ROOT = Path(directory)
            with webapp._sessions_lock:
                prior = webapp._sessions.pop(key, None)
            request = RunRequest(
                workspace_id="demo", session_id="demo", message="hello",
                config=RunConfig(model="test", api_key="hidden", system_prompt="private"),
            )
            try:
                with (
                    patch.object(webapp, "_workspace_exists", return_value=True),
                    patch.object(webapp, "_build_agent", return_value=_CompletedAgent()),
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
                webapp.WORKSPACE_ROOT = original_root
                with webapp._sessions_lock:
                    webapp._sessions.pop(key, None)
                    if prior is not None:
                        webapp._sessions[key] = prior
