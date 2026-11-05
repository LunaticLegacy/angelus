"""Regression coverage for browser turns entering at one graph Agent."""
from __future__ import annotations

import unittest

from llmfetcher.swarm_module.execution_graph import ExecutionGraph


class _RecordingAgent:
    def __init__(self) -> None:
        self.messages: list[object] = []
        self.hooks: list[object] = []

    def add_hook(self, hook: object) -> None:
        self.hooks.append(hook)

    def run(self, message: object, **_kwargs: object) -> str:
        self.messages.append(message)
        return f"output:{message}"


class EntryAgentRoutingTests(unittest.TestCase):
    def test_entry_agent_does_not_seed_unconnected_workers(self) -> None:
        graph = ExecutionGraph()
        coordinator = _RecordingAgent()
        worker = _RecordingAgent()
        graph.add_agent("coordinator", coordinator)
        graph.add_agent("worker", worker)

        outputs = graph.run("hello", entry_agent="coordinator")

        self.assertEqual(["coordinator"], list(outputs))
        self.assertEqual(["hello"], coordinator.messages)
        self.assertEqual([], worker.messages)

    def test_entry_agent_still_activates_connected_successors(self) -> None:
        graph = ExecutionGraph()
        coordinator = _RecordingAgent()
        worker = _RecordingAgent()
        graph.add_agent("coordinator", coordinator)
        graph.add_agent("worker", worker)
        graph.add_connection("coordinator", "worker")

        graph.run("hello", entry_agent="coordinator")

        self.assertEqual(["hello"], coordinator.messages)
        self.assertEqual(["output:hello"], worker.messages)


if __name__ == "__main__":
    unittest.main()
