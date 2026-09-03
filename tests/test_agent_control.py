"""Regression coverage for all-Agent and targeted execution controls."""
from __future__ import annotations

import unittest

from angelus.modules.application_module.agent_control import SessionRunControl
from llmfetcher.execution import ExecutionController, StopMode


class AgentControlTests(unittest.TestCase):
    """Verify scope isolation while preserving Session-wide cancellation."""

    def test_targeted_steer_and_stop_do_not_affect_other_agents(self) -> None:
        """Deliver commands only to the selected Agent control view."""
        control = SessionRunControl(ExecutionController())
        coordinator = control.for_agent("coordinator")
        worker = control.for_agent("worker")

        self.assertEqual(control.steer("worker", "Inspect the API."), ("worker",))
        self.assertEqual(worker.drain_steers(), ["Inspect the API."])
        self.assertEqual(coordinator.drain_steers(), [])

        self.assertEqual(control.stop("worker", False, "not needed"), ("worker",))
        self.assertTrue(worker.should_stop())
        self.assertFalse(coordinator.should_stop())

    def test_all_scope_broadcasts_and_stops_every_agent(self) -> None:
        """Broadcast steering and global stop to every active Agent view."""
        control = SessionRunControl(ExecutionController())
        coordinator = control.for_agent("coordinator")
        worker = control.for_agent("worker")

        self.assertEqual(control.steer("all", "Summarize now."), ("coordinator", "worker"))
        self.assertEqual(coordinator.drain_steers(), ["Summarize now."])
        self.assertEqual(worker.drain_steers(), ["Summarize now."])

        self.assertEqual(control.stop("all", False, "user requested"), ("coordinator", "worker"))
        self.assertTrue(coordinator.should_stop())
        self.assertTrue(worker.should_stop())

    def test_all_scope_steer_does_not_reach_agents_created_later(self) -> None:
        """An ALL steer snapshots live Agent views at submission time."""
        control = SessionRunControl(ExecutionController())
        coordinator = control.for_agent("coordinator")
        worker = control.for_agent("worker")

        self.assertEqual(control.steer("all", "Use primary sources."), ("coordinator", "worker"))
        new_worker = control.for_agent("new-worker")

        self.assertEqual(coordinator.drain_steers(), ["Use primary sources."])
        self.assertEqual(worker.drain_steers(), ["Use primary sources."])
        self.assertEqual(new_worker.drain_steers(), [])

    def test_targeted_force_stop_cancels_only_target_resources(self) -> None:
        """Invoke only the selected Agent's registered resource canceller."""
        control = SessionRunControl(ExecutionController())
        coordinator = control.for_agent("coordinator")
        worker = control.for_agent("worker")
        cancelled: list[str] = []
        coordinator.register_force_canceller(lambda _request: cancelled.append("coordinator"))
        worker.register_force_canceller(lambda _request: cancelled.append("worker"))

        control.stop("worker", True, "blocked")

        self.assertEqual(cancelled, ["worker"])
        self.assertFalse(coordinator.force_stopped.is_set())
        self.assertTrue(worker.force_stopped.is_set())
        self.assertIsNotNone(worker.stop_request)
        self.assertIs(worker.stop_request.mode, StopMode.FORCE)
        self.assertIsNone(coordinator.stop_request)

    def test_effective_stop_request_prefers_force_across_scopes(self) -> None:
        """Expose the force request required by LLMFetcher cancellation checks."""
        global_control = ExecutionController()
        control = SessionRunControl(global_control)
        worker = control.for_agent("worker")

        global_control.request_stop(StopMode.GRACEFUL, reason="session completed")
        control.stop("worker", True, "worker must terminate")

        self.assertIsNotNone(worker.stop_request)
        self.assertIs(worker.stop_request.mode, StopMode.FORCE)
