"""Unit tests for graph_memory.builder (P1: incremental graph building)."""

from __future__ import annotations

import unittest

from llmfetcher.graph_memory.builder import GraphBuilder, IngestStats
from llmfetcher.graph_memory.extraction_prompts import extract_regex
from llmfetcher.graph_memory.graph_store import GraphStore
from llmfetcher.llm_types import LLMContext, LLMOutput


class _FakeFetcher:
    """Injectable fetcher returning a fixed JSON extraction."""

    def __init__(self, payload: str, fail: bool = False):
        self.payload = payload
        self.fail = fail
        self.calls: list[dict] = []

    def fetch(self, msg, system_prompt=None, temperature=0.2, max_tokens=512,
              context_handler=None, backend_name=None, tools=None):
        self.calls.append({
            "msg": msg, "system_prompt": system_prompt,
            "temperature": temperature, "max_tokens": max_tokens,
        })
        if self.fail:
            raise RuntimeError("llm down")
        return LLMOutput(content=self.payload, provider="t", backend_name="t", model="t")


def _msg(role: str, content: str, timeline: int) -> LLMContext:
    return LLMContext(role=role, timeline=timeline, content=content)


class BuilderLlmTests(unittest.TestCase):
    def test_llm_extraction_upserts(self):
        store = GraphStore()
        payload = (
            '```json\n{"entities": [{"name": "graph_store.py", "type": "file"},'
            '{"name": "GraphStore", "type": "class"},'
            '{"name": "PPR", "type": "concept", "aliases": ["Personalized PageRank"]}],'
            '"relations": [{"src": "GraphStore", "dst": "PPR", "relation": "uses"}]}\n```'
        )
        fetcher = _FakeFetcher(payload)
        builder = GraphBuilder(store, fetcher=fetcher)
        stats = builder.ingest([
            _msg("user", "graph_store.py implements GraphStore which uses PPR", 1),
        ])
        self.assertTrue(stats.llm_used)
        self.assertFalse(stats.fallback_regex)
        self.assertGreaterEqual(stats.entities_added, 3)
        self.assertGreaterEqual(stats.relations_added, 1)
        self.assertEqual(len(store), 3)
        # alias merges on second ingest
        builder.ingest([
            _msg("assistant", "Personalized PageRank powers the search", 2),
        ])
        self.assertEqual(len(store), 3)  # no new node

    def test_llm_failure_falls_back_to_regex(self):
        store = GraphStore()
        fetcher = _FakeFetcher("", fail=True)
        builder = GraphBuilder(store, fetcher=fetcher)
        stats = builder.ingest([
            _msg("user", "Fix the bug in src/main.py inside class Runner", 1),
        ])
        self.assertTrue(stats.fallback_regex)
        self.assertIn("src/main.py", [n.name for n in store.nodes.values()])
        self.assertIn("Runner", [n.name for n in store.nodes.values()])

    def test_no_fetcher_uses_regex_only(self):
        store = GraphStore()
        builder = GraphBuilder(store)
        stats = builder.ingest([
            _msg("user", "import os; from flask import Flask; def handle(): pass", 1),
        ])
        self.assertTrue(stats.fallback_regex)
        names = {n.name for n in store.nodes.values()}
        self.assertIn("os", names)
        self.assertIn("flask", names)
        self.assertIn("handle", names)

    def test_empty_messages_noop(self):
        builder = GraphBuilder(GraphStore())
        stats = builder.ingest([])
        self.assertEqual(stats.entities_added, 0)


class BuilderTimelineTests(unittest.TestCase):
    def test_first_last_seen_updated(self):
        store = GraphStore()
        builder = GraphBuilder(store)
        builder.ingest([_msg("user", "Work on src/a.py", 3)])
        builder.ingest([_msg("assistant", "src/a.py changed again", 9)])
        node = store.find_entity_by_name("src/a.py", "file")
        self.assertIsNotNone(node)
        self.assertEqual(node.first_seen, 3)
        self.assertEqual(node.last_seen, 9)
        self.assertEqual(node.freq, 2)

    def test_evidence_timeline_recorded(self):
        store = GraphStore()
        payload = (
            '{"entities": [{"name": "GraphRAG", "type": "framework"},'
            '{"name": "LightRAG", "type": "framework"}],'
            '"relations": [{"src": "GraphRAG", "dst": "LightRAG",'
            '"relation": "relates_to"}]}'
        )
        builder = GraphBuilder(store, fetcher=_FakeFetcher(payload))
        builder.ingest([_msg("user", "GraphRAG relates to LightRAG", 5)])
        edges = store.edges()
        self.assertTrue(edges)
        self.assertIn(5, edges[0].evidence)
        self.assertEqual(edges[0].relation, "relates_to")


class RegexExtractionTests(unittest.TestCase):
    def test_file_function_hashtag(self):
        out = extract_regex(
            "open src/util/parse.py, def run_parser(), topic #auth "
            "and #deployment"
        )
        names = {e["name"] for e in out["entities"]}
        self.assertIn("src/util/parse.py", names)
        self.assertIn("run_parser", names)
        self.assertIn("auth", names)
        self.assertIn("deployment", names)

    def test_relations_empty(self):
        out = extract_regex("just some text")
        self.assertEqual(out["relations"], [])


class StatsTests(unittest.TestCase):
    def test_stats_str(self):
        s = IngestStats(entities_added=2, llm_used=True)
        self.assertIn("entities=2", str(s))
        self.assertIn("llm=True", str(s))


if __name__ == "__main__":
    unittest.main()
