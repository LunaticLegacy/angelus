"""Unit tests for graph_memory.graph_store (P0: graph kernel)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from llmfetcher.graph_memory.graph_store import (
    GraphStore,
    normalize_entity_id,
    personalized_pagerank,
)


class NormalizeTests(unittest.TestCase):
    def test_casefold_and_space(self):
        self.assertEqual(
            normalize_entity_id("  GraphRAG  ", "framework"),
            "framework:graphrag",
        )

    def test_type_prefix_avoids_collision(self):
        a = normalize_entity_id("main.py", "file")
        b = normalize_entity_id("main.py", "concept")
        self.assertNotEqual(a, b)

    def test_unicode_nfkc(self):
        self.assertEqual(normalize_entity_id("ｇｒａｐｈ", "concept"), "concept:graph")


class UpsertEntityTests(unittest.TestCase):
    def setUp(self):
        self.g = GraphStore()

    def test_insert_and_merge(self):
        n1 = self.g.upsert_entity("GraphRAG", "framework", timeline=1)
        n2 = self.g.upsert_entity("GraphRAG", "framework", timeline=5)
        self.assertEqual(len(self.g), 1)
        self.assertEqual(n1.id, n2.id)
        self.assertEqual(n1.freq, 2)
        self.assertEqual(n1.first_seen, 1)
        self.assertEqual(n1.last_seen, 5)

    def test_alias_merge(self):
        self.g.upsert_entity("LLM", "concept", aliases=["大语言模型"], timeline=1)
        merged = self.g.upsert_entity("大语言模型", "concept", timeline=3)
        self.assertEqual(len(self.g), 1)
        self.assertEqual(merged.name, "LLM")
        self.assertIn("大语言模型", merged.aliases)

    def test_find_by_name(self):
        self.g.upsert_entity("main.py", "file", timeline=1)
        self.assertIsNotNone(self.g.find_entity_by_name("MAIN.PY", "file"))
        self.assertIsNotNone(self.g.find_entity_by_name("main.py"))

    def test_substring_fallback(self):
        self.g.upsert_entity("ContextHandlerLinear", "class", timeline=1)
        hit = self.g.find_entity_by_name("handlerlinear")
        self.assertIsNotNone(hit)


class RelationTests(unittest.TestCase):
    def setUp(self):
        self.g = GraphStore()
        self.a = self.g.upsert_entity("a", timeline=1)
        self.b = self.g.upsert_entity("b", timeline=1)
        self.c = self.g.upsert_entity("c", timeline=1)

    def test_upsert_aggregates(self):
        e1 = self.g.upsert_relation(self.a.id, self.b.id, "related_to", timeline=2)
        e2 = self.g.upsert_relation(self.b.id, self.a.id, "related_to", timeline=4)
        self.assertEqual(e1.weight, 2.0)
        self.assertEqual(e1.first_seen, 2)
        self.assertEqual(e1.last_seen, 4)
        self.assertEqual(len(self.g.edges()), 1)

    def test_distinct_relations_kept(self):
        self.g.upsert_relation(self.a.id, self.b.id, "depends_on", timeline=2)
        self.g.upsert_relation(self.a.id, self.b.id, "fixes", timeline=3)
        self.assertEqual(len(self.g.edges()), 2)

    def test_missing_endpoint_returns_none(self):
        self.assertIsNone(self.g.upsert_relation("missing", self.b.id, timeline=1))

    def test_neighbors_hops(self):
        self.g.upsert_relation(self.a.id, self.b.id, timeline=2)
        self.g.upsert_relation(self.b.id, self.c.id, timeline=3)
        hops = self.g.neighbors(self.a.id, max_hop=2)
        self.assertEqual(hops[self.b.id], 1)
        self.assertEqual(hops[self.c.id], 2)

    def test_invalidate(self):
        self.g.upsert_relation(self.a.id, self.b.id, timeline=2)
        self.assertEqual(self.g.invalidate_relation(self.a.id, self.b.id), 1)
        self.assertFalse(self.g.edges()[0].valid)


class PPRTests(unittest.TestCase):
    def test_pagerank_seed_dominates(self):
        g = GraphStore()
        ids = {}
        for name in ["A", "B", "C", "D"]:
            ids[name] = g.upsert_entity(name, timeline=1).id
        g.upsert_relation(ids["A"], ids["B"], timeline=2)
        g.upsert_relation(ids["B"], ids["C"], timeline=2)
        g.upsert_relation(ids["C"], ids["D"], timeline=2)
        scores = g.pagerank([ids["A"]])
        # Distance from seed A monotonically decays (hub B may outrank seed A
        # in an undirected graph because it receives mass from both sides).
        self.assertGreater(scores[ids["B"]], scores[ids["C"]])
        self.assertGreater(scores[ids["C"]], scores[ids["D"]])
        # Both A and its neighbor B dominate the far end of the chain.
        self.assertGreater(scores[ids["A"]], scores[ids["D"]])
    def test_pagerank_isolated(self):
        self.assertEqual(personalized_pagerank({}, ["x"]), {})


class CommunityTests(unittest.TestCase):
    def test_louvain_two_clusters(self):
        g = GraphStore()
        ids = {}
        for name in ["a1", "a2", "a3", "b1", "b2", "b3"]:
            ids[name] = g.upsert_entity(name, timeline=1).id
        for pair in [("a1", "a2"), ("a2", "a3"), ("a1", "a3"),
                     ("b1", "b2"), ("b2", "b3"), ("b1", "b3")]:
            g.upsert_relation(ids[pair[0]], ids[pair[1]], timeline=2, weight=5.0)
        # weak bridge between clusters
        g.upsert_relation(ids["a1"], ids["b1"], timeline=2, weight=0.1)
        comms = g.detect_communities()
        self.assertEqual(len(comms), 2)
        sizes = sorted(len(c) for c in comms)
        self.assertEqual(sizes, [3, 3])


class TimeDecayTests(unittest.TestCase):
    def test_decay_monotonic(self):
        self.assertAlmostEqual(GraphStore.time_decay(0), 1.0)
        self.assertGreater(GraphStore.time_decay(5), GraphStore.time_decay(50))

    def test_decay_range(self):
        self.assertLess(GraphStore.time_decay(1000), 1.0)


class SerializationTests(unittest.TestCase):
    def test_roundtrip(self):
        g = GraphStore()
        a = g.upsert_entity("GraphRAG", "framework", aliases=["grag"], timeline=1)
        b = g.upsert_entity("LightRAG", "framework", timeline=2)
        g.upsert_relation(a.id, b.id, "compares_to", timeline=3, evidence=[1, 2])
        data = g.to_dict()

        g2 = GraphStore()
        g2.from_dict(data)
        self.assertEqual(len(g2), 2)
        self.assertEqual(g2.edges()[0].relation, "compares_to")
        self.assertEqual(g2.edges()[0].evidence, [1, 2])
        self.assertEqual(g2.get_entity(a.id).aliases, ["grag"])

    def test_save_load(self):
        g = GraphStore()
        a = g.upsert_entity("X", timeline=1)
        g.upsert_relation(a.id, a.id, "self_ref", timeline=2) if False else None
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "graph.json"
            self.assertTrue(g.save(path))
            g2 = GraphStore()
            self.assertTrue(g2.load(path))
            self.assertEqual(len(g2), 1)
        self.assertFalse(GraphStore().save(""))
        self.assertFalse(GraphStore().load("/nonexistent/x.json"))


if __name__ == "__main__":
    unittest.main()
