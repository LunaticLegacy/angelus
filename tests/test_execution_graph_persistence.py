"""Regression tests for quiescent execution-graph persistence."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from llmfetcher.agent import Agent
from llmfetcher.llm_fetcher import LLMBackendConfig, LLMFetcher
from llmfetcher.swarm_module import ExecutionGraph, GraphPersistenceError


def _agent(prompt: str) -> Agent:
    """Build a tool-free Agent suitable for default persistence tests.

    Args:
        prompt: System instruction retained in the serialized Agent spec.

    Returns:
        Standard Agent with an OpenAI-compatible backend configuration.
    """
    return Agent(
        llm_fetcher=LLMFetcher([LLMBackendConfig(name="primary", provider="openai", model="example", api_key="test-key")]),
        system_prompt=prompt,
    )


class ExecutionGraphPersistenceTests(unittest.TestCase):
    """Verify graph topology and callback identity survive a disk round trip."""

    def test_save_and_load_restores_agents_edges_and_callbacks(self) -> None:
        """Restore a graph with mapper/router callbacks through a registry."""
        graph = ExecutionGraph(max_concurrency_agents=3)
        graph.add_agent("source", _agent("source prompt"))
        graph.add_agent("writer", _agent("writer prompt"))
        graph.add_connection("source", "writer")

        mapper = lambda outputs: str(outputs["source"])
        router = lambda _output: ["writer"]
        graph.set_mapper("writer", mapper)
        graph.set_router("source", router)
        callback_ids = {id(mapper): "source_text", id(router): "writer_path"}

        with tempfile.TemporaryDirectory() as directory:
            path = graph.save(
                Path(directory) / "graph.json",
                callback_serializer=lambda _name, _role, callback: callback_ids[id(callback)],
            )
            restored = ExecutionGraph.load(
                path,
                callback_resolver=lambda _name, role, callback_id: mapper if role == "mapper" and callback_id == "source_text" else router,
            )

        self.assertEqual(restored.max_concurrency_agents, 3)
        self.assertEqual(restored.agent_dict["source"].system_prompt, "source prompt")
        self.assertEqual(restored._successors["source"], {"writer"})
        self.assertEqual(restored._mappers["writer"]({"source": "ok"}), "ok")
        self.assertEqual(restored._routers["source"]("anything"), ["writer"])

    def test_callbacks_require_explicit_registry(self) -> None:
        """Reject implicit serialization of arbitrary executable callbacks."""
        graph = ExecutionGraph()
        graph.add_agent("source", _agent("source"))
        graph.set_router("source", lambda _output: [])
        with self.assertRaises(GraphPersistenceError):
            graph.to_snapshot()
