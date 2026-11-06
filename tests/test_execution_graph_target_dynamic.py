"""Regression coverage for dynamic dispatch inside a targeted turn.

A browser turn runs with ``target_agent`` set, which used to skip the
``_dynamic_ready`` drain entirely: workers revived by ``revive_agent`` stayed
``queued`` forever *and* the scheduler loop busy-spun (no sleep, no emit, no
stop check) because the loop condition kept seeing the undrained queue. The
caller therefore never returned, so the attempt could never reach a terminal
state.
"""
from __future__ import annotations

from collections import deque
import threading
import time
import unittest

from llmfetcher.swarm_module.execution_graph import ExecutionGraph


class _CountingAgent:
    """Minimal graph node that records its inputs and can run extra work."""

    def __init__(self, name: str, work=None) -> None:
        self.name = name
        self.work = work
        self.messages: list[object] = []
        self.hooks: list[object] = []
        self.system_prompt = f"prompt for {name}"

    def add_hook(self, hook: object) -> None:
        self.hooks.append(hook)

    def run(self, message: object, **_kwargs: object) -> str:
        self.messages.append(message)
        if self.work is not None:
            self.work()
        return f"{self.name}:out"


class _StopControl:
    """Cooperative control whose Session-wide stop can be flipped."""

    def __init__(self) -> None:
        self.stopped = False

    def should_stop(self, agent_id: str = "all") -> bool:
        return self.stopped

    def drain_steers(self) -> list[str]:
        return []


class TargetTurnDynamicDispatchTests(unittest.TestCase):
    """A targeted turn must still run the workers it dispatches or revives."""

    def test_target_turn_runs_dispatched_worker(self) -> None:
        graph = ExecutionGraph()
        worker = _CountingAgent("worker")

        def dispatch() -> None:
            graph.dispatch_task(
                agent_name="worker",
                agent_instance=worker,
                objective="整理资料",
                handoff="coordinator state",
                reply_to="coordinator",
            )

        coordinator = _CountingAgent("coordinator", dispatch)
        graph.add_agent("coordinator", coordinator)

        started = time.monotonic()
        outputs = graph.run("开始", target_agent="coordinator")
        elapsed = time.monotonic() - started

        self.assertIn("worker", outputs)
        self.assertEqual(1, len(worker.messages))
        self.assertIn("整理资料", str(worker.messages[0]))
        self.assertLess(elapsed, 2.0)

    def test_target_turn_runs_revived_worker(self) -> None:
        graph = ExecutionGraph()
        worker = _CountingAgent("worker")
        first = graph.dispatch_task(
            agent_name="worker",
            agent_instance=worker,
            objective="第一轮目标",
            handoff="coordinator state",
            reply_to="coordinator",
        )
        graph.task_bus.set_terminal_state(first.id, "completed")
        # A completed earlier turn already consumed the dispatch entry.
        graph._drain_dynamic_ready(deque(), {})

        def revive() -> None:
            graph.redispatch_task(
                agent_name="worker",
                objective="复活后的目标",
                handoff="coordinator state",
                reply_to="coordinator",
            )

        coordinator = _CountingAgent("coordinator", revive)
        graph.add_agent("coordinator", coordinator)

        started = time.monotonic()
        outputs = graph.run("继续", target_agent="coordinator")
        elapsed = time.monotonic() - started

        self.assertIn("worker", outputs)
        self.assertEqual(1, len(worker.messages))
        self.assertIn("复活后的目标", str(worker.messages[0]))
        self.assertLess(elapsed, 2.0)

    def test_target_turn_drops_unschedulable_dynamic_entry(self) -> None:
        """An undrainable queue entry must not become a busy-spin loop."""
        graph = ExecutionGraph()
        coordinator = _CountingAgent("coordinator")
        graph.add_agent("coordinator", coordinator)
        graph._dynamic_ready.put("ghost-worker")

        started = time.monotonic()
        outputs = graph.run("你好", target_agent="coordinator")
        elapsed = time.monotonic() - started

        self.assertEqual(["coordinator"], list(outputs))
        self.assertEqual(["你好"], coordinator.messages)
        self.assertLess(elapsed, 2.0)

    def test_target_turn_does_not_run_worker_after_stop(self) -> None:
        graph = ExecutionGraph()
        worker = _CountingAgent("worker")
        control = _StopControl()

        def dispatch_then_stop() -> None:
            control.stopped = True
            graph.dispatch_task(
                agent_name="worker",
                agent_instance=worker,
                objective="不该执行的活",
                handoff="coordinator state",
                reply_to="coordinator",
            )

        coordinator = _CountingAgent("coordinator", dispatch_then_stop)
        graph.add_agent("coordinator", coordinator)

        started = time.monotonic()
        outputs = graph.run("你好", target_agent="coordinator", control=control)
        elapsed = time.monotonic() - started

        self.assertEqual([], worker.messages)
        self.assertIn("coordinator", outputs)
        self.assertLess(elapsed, 2.0)

    def test_target_turn_still_skips_connected_successors(self) -> None:
        graph = ExecutionGraph()
        coordinator = _CountingAgent("coordinator")
        worker = _CountingAgent("worker")
        graph.add_agent("coordinator", coordinator)
        graph.add_agent("worker", worker)
        graph.add_connection("coordinator", "worker")

        outputs = graph.run("你好", target_agent="coordinator")

        self.assertEqual(["coordinator"], list(outputs))
        self.assertEqual([], worker.messages)

    def test_entry_agent_turn_keeps_dynamic_dispatch(self) -> None:
        """The non-target dynamic path must stay intact after the refactor."""
        graph = ExecutionGraph()
        worker = _CountingAgent("worker")

        def dispatch() -> None:
            graph.dispatch_task(
                agent_name="worker",
                agent_instance=worker,
                objective="并行任务",
                handoff="coordinator state",
                reply_to="coordinator",
            )

        coordinator = _CountingAgent("coordinator", dispatch)
        graph.add_agent("coordinator", coordinator)

        outputs = graph.run("你好", entry_agent="coordinator")

        self.assertIn("worker", outputs)
        self.assertEqual(1, len(worker.messages))

    def test_target_turn_returns_while_stop_arrives_from_other_thread(
        self,
    ) -> None:
        """A stop raised from another thread must not leave the turn spinning."""
        graph = ExecutionGraph()
        control = _StopControl()
        coordinator = _CountingAgent("coordinator")
        graph.add_agent("coordinator", coordinator)

        def stop_later() -> None:
            control.stopped = True

        timer = threading.Timer(0.05, stop_later)
        timer.daemon = True
        timer.start()
        try:
            started = time.monotonic()
            graph.run("你好", target_agent="coordinator", control=control)
            elapsed = time.monotonic() - started
        finally:
            timer.cancel()

        self.assertLess(elapsed, 2.0)


if __name__ == "__main__":
    unittest.main()
