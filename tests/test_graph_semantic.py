"""Focused tests for stateless graph semantic extraction and reranking."""

from __future__ import annotations

import unittest

from llmfetcher.graph_memory import GraphRetriever, GraphStore, SemanticGraphWorker
from llmfetcher.graph_memory.builder import GraphBuilder
from llmfetcher.llm_types import LLMContext
from llmfetcher.llm_types import LLMOutput, TokenUsage


class _RecordingFetcher:
    def __init__(self, replies: list[str], usage: TokenUsage | None = None) -> None:
        self.replies = list(replies)
        self.calls: list[dict] = []
        self.usage = usage

    def fetch(self, **kwargs):
        self.calls.append(kwargs)
        return LLMOutput(
            content=self.replies.pop(0), provider="test", backend_name="test", model="test",
            usage=self.usage,
        )


class SemanticGraphWorkerTests(unittest.TestCase):
    def test_worker_always_removes_history_and_tools(self):
        source = _RecordingFetcher(['{"entities": []}'])
        worker = SemanticGraphWorker(source, backend_name="retrieval")
        worker.fetch(
            msg="extract this",
            context_handler=object(),
            tools=[{"name": "unsafe"}],
        )
        call = source.calls[0]
        self.assertIsNone(call["context_handler"])
        self.assertEqual(call["tools"], [])
        self.assertEqual(call["backend_name"], "retrieval")

    def test_rerank_uses_only_valid_candidate_ids(self):
        source = _RecordingFetcher(
            ['{"entity_ids": ["b", "missing", "a", "b"]}'],
            TokenUsage(2, 1, 3, 1, 0),
        )
        worker = SemanticGraphWorker(source)
        result = worker.rerank("which", [{"id": "a"}, {"id": "b"}])
        self.assertEqual(result, ["b", "a"])
        self.assertIsNone(source.calls[0]["context_handler"])
        self.assertEqual(source.calls[0]["tools"], [])
        self.assertEqual(
            [(record.kind, record.usage.total_tokens) for record in worker.drain_rerank_usage_records()],
            [("graph_query", 3)],
        )
        self.assertEqual(worker.drain_rerank_usage_records(), [])

    def test_worker_drives_relation_extraction_without_agent_context(self):
        source = _RecordingFetcher([
            '{"entities": [{"name": "A", "type": "concept"}, '
            '{"name": "B", "type": "concept"}], '
            '"relations": [{"src": "A", "dst": "B", "relation": "uses"}]}'
        ])
        graph = GraphStore()
        stats = GraphBuilder(graph, fetcher=SemanticGraphWorker(source)).ingest([
            LLMContext(role="user", content="A uses B", timeline=4),
        ])
        self.assertTrue(stats.llm_used)
        self.assertEqual(len(graph.edges()), 1)
        self.assertIsNone(source.calls[0]["context_handler"])
        self.assertEqual(source.calls[0]["tools"], [])


class SemanticRerankIntegrationTests(unittest.TestCase):
    def test_valid_rerank_reorders_fused_hits_and_keeps_omitted_candidates(self):
        source = _RecordingFetcher([
            '{"entities": [{"name": "alpha", "type": "concept"}]}',
            '{"entity_ids": ["concept:gamma", "concept:alpha"]}',
        ])
        graph = GraphStore()
        graph.upsert_entity("alpha", timeline=1)
        graph.upsert_entity("beta", timeline=2)
        graph.upsert_entity("gamma", timeline=3)
        result = GraphRetriever(graph, query_fetcher=SemanticGraphWorker(source)).retrieve("alpha")
        self.assertEqual([hit.entity.name for hit in result.hits], ["gamma", "alpha", "beta"])

    def test_invalid_rerank_keeps_deterministic_order(self):
        source = _RecordingFetcher([
            '{"entities": [{"name": "alpha", "type": "concept"}]}',
            '{"entity_ids": ["not-a-node"]}',
        ])
        graph = GraphStore()
        graph.upsert_entity("alpha", timeline=1)
        graph.upsert_entity("beta", timeline=2)
        result = GraphRetriever(graph, query_fetcher=SemanticGraphWorker(source)).retrieve("alpha")
        self.assertEqual([hit.entity.name for hit in result.hits], ["alpha", "beta"])


if __name__ == "__main__":
    unittest.main()
