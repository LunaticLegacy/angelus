"""Regression tests: one failed Agent must not abort the whole swarm.

A raised exception inside an Agent is recorded as an ``AgentFailure`` in the
graph outputs, published as an ``agent:failed`` event, delivered to the
coordinator as a ``status="failed"`` task report (for dispatched workers),
and does **not** cancel or abort sibling Agents.
"""

from __future__ import annotations

import unittest

from llmfetcher.agent import Agent
from llmfetcher.llm_fetcher import LLMBackendConfig, LLMFetcher
from llmfetcher.swarm_module import AgentFailure, ExecutionGraph, TaskReport


class _StubAgent(Agent):
    """Agent whose ``run`` returns a canned value or raises, no network."""

    def __init__(self, result: str = "ok", error: Exception | None = None) -> None:
        super().__init__(
            llm_fetcher=LLMFetcher(
                [LLMBackendConfig(name="primary", provider="openai", model="example", api_key="test")]
            ),
            system_prompt="stub",
        )
        self._result = result
        self._error = error

    def run(self, message: str, max_rounds: int | None = None, control=None):
        if self._error is not None:
            raise self._error
        return self._result


class SwarmFailureIsolationTests(unittest.TestCase):
    """Verify failures are isolated to the failing Agent."""

    def test_static_graph_failure_is_isolated_and_downstream_skipped(self) -> None:
        """A failing Agent does not cancel siblings; its dependents are skipped."""
        graph = ExecutionGraph(max_concurrency_agents=3)
        graph.add_agent("root", _StubAgent(result="root-done"))
        graph.add_agent("flaky", _StubAgent(error=RuntimeError("boom")))
        graph.add_agent("healthy", _StubAgent(result="healthy-done"))
        graph.add_agent("merge", _StubAgent(result="merge-done"))
        graph.add_connection("root", "flaky")
        graph.add_connection("root", "healthy")
        graph.add_connection("flaky", "merge")
        graph.add_connection("healthy", "merge")

        outputs = graph.run("start")  # must NOT raise

        self.assertIsInstance(outputs["flaky"], AgentFailure)
        self.assertEqual(outputs["flaky"].agent_name, "flaky")
        self.assertIn("boom", outputs["flaky"].error)
        # sibling ran normally
        self.assertEqual(outputs["healthy"], "healthy-done")
        self.assertEqual(outputs["root"], "root-done")
        # merge depended on the failed flaky -> skipped, no deadlock error
        self.assertNotIn("merge", outputs)

    def test_dispatched_worker_failure_report_reaches_coordinator(self) -> None:
        """A crashing dispatched worker still delivers a failed TaskReport."""
        graph = ExecutionGraph(max_concurrency_agents=2)
        graph.add_agent("coordinator", _StubAgent(result="coord-done"))
        assignment = graph.dispatch_task(
            agent_name="worker",
            agent_instance=_StubAgent(error=RuntimeError("worker exploded")),
            objective="do the thing",
            handoff="context",
            reply_to="coordinator",
        )

        outputs = graph.run("start")  # must NOT raise

        self.assertIsInstance(outputs["worker"], AgentFailure)
        self.assertEqual(outputs["coordinator"], "coord-done")
        reports = graph.wait_for_reports([assignment.id], timeout_seconds=0.5)
        self.assertEqual(len(reports), 1)
        report = reports[0]
        self.assertIsInstance(report, TaskReport)
        self.assertEqual(report.status, "failed")
        self.assertIn("worker exploded", report.summary)
        self.assertEqual(report.recipient, "coordinator")


if __name__ == "__main__":
    unittest.main()
