"""Offline regression tests for structured swarm task handoffs."""

from __future__ import annotations

import unittest
from typing import Any, cast

from llmfetcher.agent import Agent
from llmfetcher.llm_fetcher import LLMBackendConfig
from llmfetcher.llm_types import LLMOutput, LLMToolCall, Tool, ToolSchema
from llmfetcher.swarm_module import ExecutionGraph, TaskBus


class _CompletionFetcher:
    """Return a terminal-tool request and record how often the Agent fetches."""

    def __init__(self) -> None:
        """Initialize the fake backend metadata and invocation counter."""
        self.default_backend_config = LLMBackendConfig(
            name="test",
            provider="test",
            model="test-model",
        )
        self.call_count = 0

    def fetch(self, **kwargs: Any) -> LLMOutput:
        """Return a deterministic terminal tool call for one Agent round.

        Args:
            **kwargs: Model-request arguments supplied by ``Agent.run``.

        Returns:
            Output requesting the worker's terminal tool.
        """
        del kwargs
        self.call_count += 1
        return LLMOutput(
            content="Submitting the completed report.",
            provider="test",
            backend_name="test",
            model="test-model",
            tool_calls=[LLMToolCall(name="finish", call_id="finish-1")],
        )


class _ReportingWorker:
    """Minimal worker that reports its assigned task through the graph bus."""

    def __init__(self, graph: ExecutionGraph, task_id: str) -> None:
        """Store the graph and task identity used by the fake worker.

        Args:
            graph: Graph whose task bus receives the final report.
            task_id: Correlation identifier assigned before the worker runs.
        """
        self.graph = graph
        self.task_id = task_id
        self.received_message = ""

    def run(self, message: str, control: Any = None) -> str:
        """Record the task package and send a structured completion report.

        Args:
            message: Explicit assignment rendered by ``ExecutionGraph``.
            control: Unused compatibility argument matching ``Agent.run``.

        Returns:
            Deliberately opaque raw output that must not reach the coordinator.
        """
        del control
        self.received_message = message
        self.graph.report_task(
            task_id=self.task_id,
            reporter="researcher",
            status="completed",
            summary="Structured result only.",
            findings=["official endpoint identified"],
            artifacts=["workspace/researcher/report.md"],
        )
        return "RAW WORKER TRANSCRIPT MUST NOT BE HANDED OFF"


class _WaitingCoordinator:
    """Minimal coordinator that dispatches one worker then waits for its report."""

    def __init__(self, graph: ExecutionGraph) -> None:
        """Store the graph and placeholders used to assert the feedback loop.

        Args:
            graph: Graph used to dispatch and await the worker task.
        """
        self.graph = graph
        self.worker: _ReportingWorker | None = None
        self.reports = []

    def run(self, message: str, control: Any = None) -> str:
        """Dispatch one worker and synthesize only its structured report.

        Args:
            message: Root input, retained only to verify normal call shape.
            control: Unused compatibility argument matching ``Agent.run``.

        Returns:
            Coordinator conclusion derived from structured report fields.
        """
        del message, control
        task_id = "research-task"
        worker = _ReportingWorker(self.graph, task_id)
        self.worker = worker
        self.graph.dispatch_task(
            agent_name="researcher",
            agent_instance=cast(Agent, worker),
            objective="Find the official API documentation.",
            handoff="Focus on the provider's documented customer-service API.",
            reply_to="coordinator",
            expected_artifacts=["workspace/researcher/report.md"],
            task_id=task_id,
        )
        self.reports = self.graph.wait_for_reports([task_id], timeout_seconds=3.0)
        return self.reports[0].summary if self.reports else "missing report"


class _DynamicChild:
    """Minimal dynamic successor used to validate router-scope behavior."""

    def run(self, message: str, control: Any = None) -> str:
        """Return a deterministic value after receiving the graph input.

        Args:
            message: Input aggregated by the graph.
            control: Unused compatibility argument matching ``Agent.run``.

        Returns:
            Fixed output proving that the dynamically connected child ran.
        """
        del message, control
        return "dynamic child executed"


class _RouterCoordinator:
    """Creates a successor after setting an initially empty router scope."""

    def __init__(self, graph: ExecutionGraph) -> None:
        """Store the graph used to mutate topology during execution.

        Args:
            graph: Running graph whose router and successor are configured.
        """
        self.graph = graph

    def run(self, message: str, control: Any = None) -> str:
        """Add a child after router configuration to exercise the regression.

        Args:
            message: Initial root input, unused by the topology operation.
            control: Unused compatibility argument matching ``Agent.run``.

        Returns:
            Fixed coordinator output consumed by the router callback.
        """
        del message, control
        self.graph.dynamic_set_router("coordinator", [])
        self.graph.dynamic_add_agent("late_child", cast(Agent, _DynamicChild()))
        self.graph.dynamic_add_connection("coordinator", "late_child")
        return "coordinator complete"


class TaskBusGraphTests(unittest.TestCase):
    """Verify report-only feedback loops and dynamic-router compatibility."""

    def test_coordinator_receives_structured_report_not_worker_raw_output(self) -> None:
        """Run a task loop and verify the worker's raw text is not handed off.

        The worker still has a raw graph output for auditability, but the
        coordinator can receive only the report it explicitly waits for.
        """
        graph = ExecutionGraph(max_concurrency_agents=2)
        coordinator = _WaitingCoordinator(graph)
        graph.add_agent("coordinator", coordinator)  # type: ignore[arg-type]

        outputs = graph.run("Research one provider.")

        self.assertEqual(outputs["coordinator"], "Structured result only.")
        self.assertEqual(outputs["researcher"], "RAW WORKER TRANSCRIPT MUST NOT BE HANDED OFF")
        worker = coordinator.worker
        self.assertIsNotNone(worker)
        assert worker is not None
        self.assertIn("Find the official API documentation.", worker.received_message)
        self.assertEqual(len(coordinator.reports), 1)
        self.assertNotIn("RAW WORKER TRANSCRIPT", coordinator.reports[0].summary)

    def test_router_does_not_skip_successor_added_after_router_setup(self) -> None:
        """Run a late successor that was outside the router's original scope."""
        graph = ExecutionGraph(max_concurrency_agents=2)
        graph.add_agent("coordinator", _RouterCoordinator(graph))  # type: ignore[arg-type]

        outputs = graph.run("Create one late child.")

        self.assertEqual(outputs["late_child"], "dynamic child executed")

    def test_terminal_tool_stops_agent_before_another_model_round(self) -> None:
        """Stop the Agent after a terminal tool rather than using its full budget."""
        fetcher = _CompletionFetcher()
        agent = Agent(
            llm_fetcher=fetcher,  # type: ignore[arg-type]
            system_prompt="Use finish to end the task.",
            default_max_rounds=4,
            default_max_tokens=512,
        )
        agent.add_tool(Tool(
            name="finish",
            description="Commit the final result and end the worker.",
            schemas=ToolSchema(),
            handler=lambda: agent.request_completion(),
        ))

        result = agent.run("Finish this task.")

        self.assertEqual(result.content, "Submitting the completed report.")
        self.assertEqual(fetcher.call_count, 1)

    def test_report_outcome_and_unfinished_cleanup_use_precise_terminals(self) -> None:
        """Preserve reports while interrupting running and cancelling queued work."""
        bus = TaskBus()
        completed = bus.create_assignment(
            recipient="done", reply_to="coordinator", objective="finish"
        )
        failed = bus.create_assignment(
            recipient="failed", reply_to="coordinator", objective="fail"
        )
        running = bus.create_assignment(
            recipient="running", reply_to="coordinator", objective="continue"
        )
        queued = bus.create_assignment(
            recipient="queued", reply_to="coordinator", objective="wait"
        )
        bus.claim_assignment(completed.id)
        bus.claim_assignment(failed.id)
        bus.claim_assignment(running.id)
        bus.submit_report(
            task_id=completed.id, reporter="done", status="completed", summary="ok"
        )
        bus.submit_report(
            task_id=failed.id, reporter="failed", status="failed", summary="bad"
        )

        changed = bus.finalize_unfinished()

        self.assertEqual(changed, {running.id: "interrupted", queued.id: "cancelled"})
        self.assertEqual(bus.task_states(), {
            completed.id: "completed",
            failed.id: "failed",
            running.id: "interrupted",
            queued.id: "cancelled",
        })
        self.assertFalse(bus.set_terminal_state(completed.id, "failed"))
        with self.assertRaises(ValueError):
            bus.submit_report(
                task_id=running.id,
                reporter="running",
                status="completed",
                summary="late result",
            )


if __name__ == "__main__":
    unittest.main()
