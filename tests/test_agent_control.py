"""Regression coverage for all-Agent and targeted execution controls."""
from __future__ import annotations

import unittest

from angelus.modules.application_module.agent_control import SessionRunControl
from llmfetcher.execution import ExecutionController


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
