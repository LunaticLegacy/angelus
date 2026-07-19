"""Offline compatibility checks for the installed public package."""

import unittest

import llmfetcher
from llmfetcher.swarm_module import ExecutionGraph


class PublicApiTests(unittest.TestCase):
    """Verify imports and graph diagnostics without contacting an LLM API."""

    def test_package_exports_core_types(self) -> None:
        """Expose the primary orchestration classes from the package root."""
        self.assertTrue(callable(llmfetcher.Agent))
        self.assertTrue(callable(llmfetcher.LLMFetcher))

    def test_execution_graph_prints_topology(self) -> None:
        """Render an empty graph with its configured concurrency limit."""
        graph = ExecutionGraph(max_concurrency_agents=3)
        rendered = str(graph)
        self.assertIn("Current agents:", rendered)
        self.assertIn("Current connections:", rendered)
        self.assertIn("Concurrency limit: 3", rendered)
