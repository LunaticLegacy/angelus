"""Regression coverage for Session-swarm execution outcome ownership."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from angelus.api import include_api_routes
from angelus.core import AngelusCore
from angelus.modules.execution_module import ExecutionState
from llmfetcher.multimodal import UserMessage
from llmfetcher.swarm_module import AgentFailure


class _FailingSwarm:
    """Minimal graph facade that reports an unsuccessful root Agent."""

    def __init__(self) -> None:
        """Create a facade with hook-registration accounting."""
        self.hooks: list[object] = []

    def add_hook(self, hook: object) -> None:
        """Retain a hook supplied by the execution service.

        Args:
            hook: Callback to retain for this simulated run.

        Returns:
            None.
        """
        self.hooks.append(hook)

    def remove_hook(self, hook: object) -> bool:
        """Remove one retained hook.

        Args:
            hook: Exact callback to remove.

        Returns:
            Whether the callback was registered.
        """
        if hook not in self.hooks:
            return False
        self.hooks.remove(hook)
        return True

    def run(self, _message: str, *, control: object) -> dict[str, object]:
        """Return the graph's normal non-fatal root failure marker.

        Args:
            _message: User instruction, unused by this deterministic double.
            control: Attempt controller passed through by the service.

        Returns:
            Output map containing the failed coordinator marker.
        """
        return {"coordinator": AgentFailure("coordinator", "provider unavailable")}


class ExecutionServiceTests(unittest.TestCase):
    """Ensure graph-level root failures become terminal attempt failures."""

    def test_root_agent_failure_marks_attempt_failed_and_removes_hook(self) -> None:
        """A coordinator AgentFailure cannot be recorded as completed output."""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "project").mkdir()
            core = AngelusCore(state_root=root / "state")
            core.session_service.create("demo", "Demo", root / "project")
            session = core.sessions.get("demo")
            swarm = _FailingSwarm()
            session.swarm = swarm  # type: ignore[assignment]
            session.agents = [object()]  # type: ignore[list-item]
            core.session_service.ensure_coordinator = lambda _session_id: None  # type: ignore[method-assign]

            core.execution_service.start("demo", "hello")
            self.assertTrue(session.execution.wait(1.0))
            snapshot = session.execution.snapshot()
            self.assertEqual(snapshot.state, ExecutionState.FAILED)
            self.assertIn("provider unavailable", snapshot.error or "")
            self.assertEqual(swarm.hooks, [])

    def test_recovery_starts_a_new_attempt_from_verified_run_graph_checkpoint(self) -> None:
        """Recovery journals its source and never tries to revive old threads."""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "project").mkdir()
            core = AngelusCore(state_root=root / "state")
            core.session_service.create("demo", "Demo", root / "project")
            session = core.sessions.get("demo")
            source_root = session.execution.root / "executions" / "source-run"
            (source_root / "run-graph").mkdir(parents=True)
            run_graph = {
                "schema_version": 1, "kind": "angelus.run-graph", "session_id": "demo",
                "execution_id": "source-run", "attempt": 1, "state": "interrupted",
                "nodes": [], "edges": [], "event_cursor": 1, "started_at": 1,
                "finished_at": 2, "error": "host shutdown", "stop_reason": None, "checkpoint": None,
            }
            encoded = json.dumps(run_graph, indent=2, sort_keys=True).encode()
            (source_root / "run-graph" / "safe.json").write_bytes(encoded)
            (source_root / "execution-manifest.json").write_text(json.dumps({
                "execution_id": "source-run", "attempt": 1, "state": "interrupted",
                "checkpoint": {
                    "generation": "safe", "run_graph": {"path": "run-graph/safe.json", "sha256": hashlib.sha256(encoded).hexdigest()},
                    "recovery": {"schema_version": 1, "strategy": "new_attempt"},
                },
            }), encoding="utf-8")
            (source_root / "execution.events.ndjson").write_text(
                json.dumps({"type": "execution_started", "data": {"message": "original request"}}) + "\n",
                encoding="utf-8",
            )
            swarm = _FailingSwarm()
            session.swarm = swarm  # type: ignore[assignment]
            session.agents = [object()]  # type: ignore[list-item]
            core.session_service.ensure_coordinator = lambda _session_id: None  # type: ignore[method-assign]

            core.execution_service.recover("demo", "source-run")
            self.assertTrue(session.execution.wait(1.0))

            attempt = session.execution.attempt
            self.assertIsNotNone(attempt)
            assert attempt is not None
            events = list(attempt.journal.events())
            recovery = next(item for item in events if item["type"] == "execution_recovery_started")
            self.assertEqual(recovery["data"]["source_execution_id"], "source-run")
            self.assertNotEqual(attempt.execution_id, "source-run")


class _RecordingSwarm:
    """Swarm facade that captures the validated initial user input."""

    def __init__(self) -> None:
        """Create a facade with hook-registration accounting."""
        self.hooks: list[object] = []
        self.received: object = None

    def add_hook(self, hook: object) -> None:
        """Retain a hook supplied by the execution service.

        Args:
            hook: Callback to retain for this simulated run.

        Returns:
            None.
        """
        self.hooks.append(hook)

    def remove_hook(self, hook: object) -> bool:
        """Remove one retained hook.

        Args:
            hook: Exact callback to remove.

        Returns:
            Whether the callback was registered.
        """
        if hook not in self.hooks:
            return False
        self.hooks.remove(hook)
        return True

    def view_snapshot(self) -> dict[str, object]:
        """Return a minimal live topology for control pre-registration.

        Returns:
            One coordinator Agent node so the service registers its control view.
        """
        return {"nodes": [{"id": "coordinator", "kind": "agent"}]}

    def run(self, message: object, *, control: object) -> dict[str, object]:
        """Record the exact initial input handed to the graph.

        Args:
            message: Initial user input; a ``UserMessage`` when images exist.
            control: Attempt controller passed through by the service.

        Returns:
            Successful coordinator output marker.
        """
        self.received = message
        return {"coordinator": "ok"}


class _PreviewHandler:
    """Minimal provider facade proving request composition performs no I/O."""

    def prepare_tools(self, _tools: object) -> list[object]:
        """Return an empty schema list for the isolated preview test.

        Args:
            _tools: Model-visible tools that would be provider-prepared.

        Returns:
            Empty schema list because this test does not exercise providers.
        """
        return []


def _png() -> bytes:
    """Return one small valid PNG payload.

    Returns:
        Encoded 3x4 red PNG bytes shared by the image wiring tests.
    """
    buffer = io.BytesIO()
    Image.new("RGB", (3, 4), "red").save(buffer, format="PNG")
    return buffer.getvalue()


class ExecutionImageWiringTests(unittest.TestCase):
    """Native image references flow from the Session store into providers."""

    def _session(self, directory: str) -> tuple[AngelusCore, object]:
        """Create a runnable-shaped Session without building a real coordinator.

        Args:
            directory: Temporary directory owning project and state roots.

        Returns:
            The process core and the registered Session aggregate.
        """
        root = Path(directory)
        (root / "project").mkdir()
        core = AngelusCore(state_root=root / "state")
        core.session_service.create("demo", "Demo", root / "project")
        session = core.sessions.get("demo")
        session.agents = [object()]  # type: ignore[list-item]
        core.session_service.ensure_coordinator = lambda _session_id: None  # type: ignore[method-assign]
        return core, session

    def test_start_validates_store_refs_and_passes_user_message(self) -> None:
        """Validated references reach the swarm as one UserMessage, not a dict."""
        with TemporaryDirectory() as directory:
            core, session = self._session(directory)
            metadata = session.attachments.put(_png())
            swarm = _RecordingSwarm()
            session.swarm = swarm  # type: ignore[assignment]
            ref = {"attachment_id": metadata["attachment_id"], "media_type": "image/png"}

            core.execution_service.start("demo", "describe this", images=[ref])
            self.assertTrue(session.execution.wait(1.0))

            received = swarm.received
            self.assertIsInstance(received, UserMessage)
            assert isinstance(received, UserMessage)
            self.assertEqual(received.text, "describe this")
            self.assertEqual(received.images, [{
                "attachment_id": metadata["attachment_id"],
                "media_type": "image/png",
                "detail": "auto",
            }])
            self.assertEqual(str(received), "describe this")
            self.assertEqual(swarm.hooks, [])

            attempt = session.execution.attempt
            assert attempt is not None
            started = next(
                event for event in attempt.journal.events() if event["type"] == "execution_started"
            )
            self.assertEqual(started["data"]["images"], received.images)

    def test_image_only_turn_is_accepted_and_blank_text_is_rejected(self) -> None:
        """An image-only turn runs; blank text without images stays invalid."""
        with TemporaryDirectory() as directory:
            core, session = self._session(directory)
            metadata = session.attachments.put(_png())
            swarm = _RecordingSwarm()
            session.swarm = swarm  # type: ignore[assignment]
            ref = {"attachment_id": metadata["attachment_id"], "media_type": "image/png"}

            with self.assertRaises(ValueError):
                core.execution_service.start("demo", "   ")

            core.execution_service.start("demo", "", images=[ref])
            self.assertTrue(session.execution.wait(1.0))
            received = swarm.received
            assert isinstance(received, UserMessage)
            self.assertEqual(received.text, "")
            self.assertEqual(len(received.images), 1)

    def test_start_rejects_refs_outside_the_session_store(self) -> None:
        """Unknown, mismatched, and over-budget references fail before dispatch."""
        with TemporaryDirectory() as directory:
            core, session = self._session(directory)
            metadata = session.attachments.put(_png())
            valid = {"attachment_id": metadata["attachment_id"], "media_type": "image/png"}

            with self.assertRaises(ValueError):
                core.execution_service.start(
                    "demo", "hi", images=[{"attachment_id": "0" * 64, "media_type": "image/png"}],
                )
            with self.assertRaises(ValueError):
                core.execution_service.start(
                    "demo", "hi", images=[{**valid, "media_type": "image/jpeg"}],
                )
            with self.assertRaises(ValueError):
                core.execution_service.start(
                    "demo", "hi", images=[valid, {"attachment_id": "1" * 64, "media_type": "image/png"}],
                )
            with self.assertRaises(ValueError):
                core.execution_service.start("demo", "hi", images=[valid] * 9)
            # None of the rejected calls may leave a live or recorded attempt.
            self.assertIsNone(session.execution.attempt)

    def test_coordinator_fetcher_resolves_session_attachment(self) -> None:
        """The real Agent factory binds the Session store as its image resolver."""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "project").mkdir()
            core = AngelusCore(state_root=root / "state")
            core.session_service.create("demo", "Demo", root / "project")
            session = core.sessions.get("demo")
            metadata = session.attachments.put(_png())
            connector = core.settings_service.create_connector({
                "name": "Test", "provider": "openai", "model": "vision-model",
                "api_url": "", "api_key": "secret",
            })
            profile = core.settings_service.session_profile("demo")["effective"]
            profile["connector_id"] = connector["id"]
            core.settings_service.replace_session_profile("demo", profile)

            with patch(
                "llmfetcher.llm_fetcher.LLMBackendHandler.create_for_backend",
                return_value=_PreviewHandler(),
            ):
                agent = core.session_service.preview_agent("demo", "coordinator")

            resolver = agent.llm_fetcher.image_resolver
            self.assertEqual(resolver, session.attachments.resolve)
            payload = resolver({
                "attachment_id": metadata["attachment_id"],
                "media_type": "image/png",
                "detail": "auto",
            })
            self.assertEqual(payload["media_type"], "image/png")
            self.assertEqual(base64.b64decode(payload["data"]), _png())


class ControlImageRejectionTests(unittest.TestCase):
    """Steering stays text-only; attached images fail loudly, never silently."""

    def test_image_steering_is_rejected_before_execution_lookup(self) -> None:
        """A non-empty images field returns 422 even with no live execution."""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "project").mkdir()
            core = AngelusCore(state_root=root / "state")
            core.session_service.create("demo", "Demo", root / "project")
            app = FastAPI()
            include_api_routes(app, core)
            with TestClient(app) as client:
                payload = {
                    "agent_id": "all",
                    "action": "steer",
                    "message": "look at this",
                    "images": [{
                        "attachment_id": "a" * 64,
                        "media_type": "image/png",
                        "detail": "auto",
                    }],
                }
                response = client.post("/api/runs/demo/control", json=payload)
                self.assertEqual(response.status_code, 422)
                self.assertIn("Image steering is not supported", response.json()["detail"])

                # A malformed reference never reaches the handler at all.
                malformed = {**payload, "images": [{"attachment_id": "not-an-id"}]}
                self.assertEqual(client.post("/api/runs/demo/control", json=malformed).status_code, 422)

                # Text-only steering still reaches the real lifecycle guard.
                text_only = {"agent_id": "all", "action": "steer", "message": "look"}
                text_response = client.post("/api/runs/demo/control", json=text_only)
                self.assertEqual(text_response.status_code, 409)
                self.assertIn("no active Agent control", text_response.json()["detail"])


class _BlockingSwarm:
    """Swarm facade that holds an attempt open until the test releases it."""

    def __init__(self) -> None:
        """Create a facade with hook accounting and one release gate."""
        self.hooks: list[object] = []
        self.entered = threading.Event()
        self.release = threading.Event()

    def add_hook(self, hook: object) -> None:
        """Retain the attempt journal hook supplied by the service.

        Args:
            hook: Callback to retain for this simulated run.

        Returns:
            None.
        """
        self.hooks.append(hook)

    def remove_hook(self, hook: object) -> bool:
        """Remove one retained hook.

        Args:
            hook: Exact callback to remove.

        Returns:
            Whether the callback was registered.
        """
        if hook not in self.hooks:
            return False
        self.hooks.remove(hook)
        return True

    def view_snapshot(self) -> dict[str, object]:
        """Return a minimal live topology for control pre-registration.

        Returns:
            One coordinator Agent node so control commands resolve a target.
        """
        return {"nodes": [{"id": "coordinator", "kind": "agent"}]}

    def run(self, _message: object, *, control: object) -> dict[str, object]:
        """Signal entry and block until the test releases the attempt.

        Args:
            _message: Initial user input, unused by this deterministic double.
            control: Attempt control registry proving ``run_control`` is live.

        Returns:
            Stopped coordinator output marker.
        """
        self.entered.set()
        self.release.wait(5)
        return {"coordinator": "stopped"}


class RuntimeAgentDirtyTests(unittest.TestCase):
    """Forced stops invalidate cached runtime Agents; graceful stops do not."""

    def _session(self, directory: str) -> tuple[AngelusCore, object]:
        """Create a runnable-shaped Session without building a real coordinator.

        Args:
            directory: Temporary directory owning project and state roots.

        Returns:
            The process core and the registered Session aggregate.
        """
        root = Path(directory)
        (root / "project").mkdir()
        core = AngelusCore(state_root=root / "state")
        core.session_service.create("demo", "Demo", root / "project")
        session = core.sessions.get("demo")
        session.agents = [object()]  # type: ignore[list-item]
        core.session_service.ensure_coordinator = lambda _session_id: None  # type: ignore[method-assign]
        return core, session

    def test_graceful_stop_keeps_runtime_agents_reusable(self) -> None:
        """A graceful stop leaves the cached coordinator valid for reuse."""
        with TemporaryDirectory() as directory:
            core, session = self._session(directory)

            core.execution_service.stop("demo", force=False, reason="graceful")

            self.assertFalse(session.runtime_agents_dirty)

    def test_forced_stop_marks_runtime_agents_dirty(self) -> None:
        """A forced stop invalidates cached Agents so clients are rebuilt."""
        with TemporaryDirectory() as directory:
            core, session = self._session(directory)

            core.execution_service.stop("demo", force=True, reason="forced")

            self.assertTrue(session.runtime_agents_dirty)

    def test_control_marks_runtime_agents_dirty_only_when_forced(self) -> None:
        """Browser control invalidates Agents only for ``force_stop``."""
        with TemporaryDirectory() as directory:
            core, session = self._session(directory)

            graceful = _BlockingSwarm()
            session.swarm = graceful  # type: ignore[assignment]
            core.execution_service.start("demo", "first")
            self.assertTrue(graceful.entered.wait(5))
            core.execution_service.control("demo", "all", "stop", "", "graceful")
            self.assertFalse(session.runtime_agents_dirty)
            graceful.release.set()
            self.assertTrue(session.execution.wait(5))
            self.assertEqual(session.execution.snapshot().state, ExecutionState.STOPPED)

            forced = _BlockingSwarm()
            session.swarm = forced  # type: ignore[assignment]
            core.execution_service.start("demo", "second")
            self.assertTrue(forced.entered.wait(5))
            core.execution_service.control("demo", "all", "force_stop", "", "forced")
            self.assertTrue(session.runtime_agents_dirty)
            forced.release.set()
            self.assertTrue(session.execution.wait(5))

    def test_ensure_coordinator_rebuilds_dirty_agents_for_same_profile(self) -> None:
        """A dirty flag defeats an unchanged fingerprint and resets on rebuild."""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "project").mkdir()
            core = AngelusCore(state_root=root / "state")
            core.session_service.create("demo", "Demo", root / "project")
            connector = core.settings_service.create_connector({
                "name": "Test", "provider": "openai", "model": "test-model",
                "api_url": "", "api_key": "secret",
            })
            profile = core.settings_service.session_profile("demo")["effective"]
            profile["connector_id"] = connector["id"]
            core.settings_service.replace_session_profile("demo", profile)
            session = core.sessions.get("demo")
            first, second = object(), object()

            with patch(
                "angelus.modules.application_module.session_service.create_agent",
                side_effect=[first, second],
            ) as factory:
                core.session_service.ensure_coordinator("demo")
                self.assertEqual(factory.call_count, 1)
                self.assertIs(session.coordinator, first)

                # A matching fingerprint with a clean flag reuses the Agent.
                core.session_service.ensure_coordinator("demo")
                self.assertEqual(factory.call_count, 1)

                # A forced-stop flag must defeat the matching fingerprint.
                session.runtime_agents_dirty = True
                core.session_service.ensure_coordinator("demo")

                self.assertEqual(factory.call_count, 2)
                self.assertIs(session.coordinator, second)
                self.assertFalse(session.runtime_agents_dirty)


if __name__ == "__main__":
    unittest.main()
