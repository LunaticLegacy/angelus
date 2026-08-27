"""Durability tests for one session execution attempt."""

from __future__ import annotations

import json
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from angelus.core import AngelusCore
from angelus.modules.swarm_module.session_executor import SessionExecutor
from angelus.modules.execution_module import ExecutionState, SigintSupervisor


class ExecutionAttemptTests(unittest.TestCase):
    """Verify one controller, journal, and committed checkpoint generation."""

    def test_force_stop_is_journaled_and_reaches_stopped(self) -> None:
        """A forced request is one event before the cooperative worker exits."""
        with TemporaryDirectory() as directory:
            executor = SessionExecutor("demo", Path(directory))
            entered = threading.Event()

            def operation(controller):
                entered.set()
                controller.wait_for_stop(1)
                return "released"

            attempt = executor.start(operation)
            self.assertTrue(entered.wait(1))
            executor.request_stop(force=True, reason="test")
            self.assertTrue(executor.wait(1))

            self.assertEqual(attempt.snapshot().state, ExecutionState.STOPPED)
            event_types = [event["type"] for event in attempt.journal.events()]
            self.assertEqual(event_types, ["execution_started", "stop_requested", "execution_stopped"])

    def test_checkpoint_is_retained_when_execution_reaches_terminal_state(self) -> None:
        """Terminal manifest updates preserve the last journal-committed generation."""
        with TemporaryDirectory() as directory:
            executor = SessionExecutor("demo", Path(directory))
            attempt = executor.start(lambda _controller: "done")
            manifest = attempt.commit_checkpoint(
                "ckpt_1",
                {"schema_version": 2, "scheduler": {"running": []}},
                {"coordinator": {"boundary": {"round": 1, "status": "completed"}, "linear": {}}},
                reason="completed_boundary",
            )
            self.assertTrue(executor.wait(1))

            persisted = json.loads(attempt.checkpoints.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["checkpoint"]["generation"], "ckpt_1")
            self.assertEqual(persisted["checkpoint"]["committed_event_id"], manifest["checkpoint"]["committed_event_id"])

    def test_sigint_drain_force_stops_live_attempt_without_signal_handler_io(self) -> None:
        """The signal receiver only marks pending work; drain performs shutdown."""
        with TemporaryDirectory() as directory:
            executor = SessionExecutor("demo", Path(directory))
            entered = threading.Event()
            attempt = executor.start(lambda control: (entered.set(), control.wait_for_stop(1))[1])
            self.assertTrue(entered.wait(1))
            supervisor = SigintSupervisor(lambda: (attempt,), deadline_seconds=1)

            supervisor._receive(0, None)
            self.assertTrue(supervisor.drain())
            self.assertTrue(executor.wait(1))
            self.assertEqual(attempt.snapshot().state, ExecutionState.STOPPED)

    def test_host_shutdown_force_stops_live_attempt(self) -> None:
        """An ASGI shutdown hook can persist termination without owning SIGINT."""
        with TemporaryDirectory() as directory:
            executor = SessionExecutor("demo", Path(directory))
            entered = threading.Event()
            attempt = executor.start(lambda control: (entered.set(), control.wait_for_stop(1))[1])
            self.assertTrue(entered.wait(1))
            supervisor = SigintSupervisor(lambda: (attempt,), deadline_seconds=1)

            supervisor.force_stop_all(reason="host_shutdown")

            self.assertTrue(executor.wait(1))
            self.assertEqual(attempt.snapshot().state, ExecutionState.STOPPED)

    def test_sigint_announces_and_requests_force_stop_before_host_shutdown(self) -> None:
        """SIGINT's immediate phase stops work; host shutdown only awaits it."""
        with TemporaryDirectory() as directory:
            state_root = Path(directory) / "state"
            core = AngelusCore(state_root=state_root)
            session = core.sessions.create("demo", execution_root=state_root / "sessions" / "demo")
            executor = session.execution
            self.assertIsNotNone(executor)
            assert executor is not None
            entered = threading.Event()
            attempt = executor.start(lambda control: (entered.set(), control.wait_for_stop(1))[1])
            self.assertTrue(entered.wait(1))

            core.receive_sigint()

            self.assertEqual(attempt.snapshot().state, ExecutionState.FORCE_STOPPING)
            core.shutdown()
            self.assertTrue(executor.wait(1))
            self.assertEqual(attempt.snapshot().state, ExecutionState.STOPPED)


if __name__ == "__main__":
    unittest.main()
