"""Unit tests for graph_memory.retriever (P2: four-channel retrieval)."""

from __future__ import annotations

import unittest

from llmfetcher.graph_memory import (
    GraphRetriever,
    GraphRetrievalResult,
    RetrievalConfig,
    render_graph_memory,
)
from llmfetcher.graph_memory.graph_store import GraphStore
from llmfetcher.graph_memory.models import CommunitySummary
from llmfetcher.llm_types import LLMOutput


class _FakeFetcher:
    """Injectable query-fetcher returning a fixed JSON entity list."""

    def __init__(self, payload: str = "", fail: bool = False):
        self.payload = payload
        self.fail = fail
        self.calls: list[dict] = []

    def fetch(self, msg, system_prompt=None, temperature=0.2, max_tokens=512,
              context_handler=None, backend_name=None, tools=None):
        self.calls.append({
            "msg": msg,
            "system_prompt": system_prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
        })
        if self.fail:
            raise RuntimeError("llm down")
        return LLMOutput(content=self.payload, provider="t", backend_name="t",
                         model="t")


def _chain_graph(names=("main.py", "graph_store.py", "builder.py",
                        "retriever.py")) -> GraphStore:
    """A->B->C->D import chain of file entities."""
    g = GraphStore()
    ids = {}
    for i, name in enumerate(names, start=1):
        ids[name] = g.upsert_entity(name, "file", timeline=i).id
    g.upsert_relation(ids[names[0]], ids[names[1]], "imports", timeline=2)
    g.upsert_relation(ids[names[1]], ids[names[2]], "imports", timeline=3)
    g.upsert_relation(ids[names[2]], ids[names[3]], "imports", timeline=4)
    return g


class RetrievalConfigTests(unittest.TestCase):
    def test_weights_normalize(self):
        cfg = RetrievalConfig(w_vec=1.0, w_ppr=1.0, w_kw=1.0, w_time=1.0)
        for got, want in zip(cfg.effective_weights, (0.25, 0.25, 0.25, 0.25)):
            self.assertAlmostEqual(got, want)

    def test_default_weights(self):
        cfg = RetrievalConfig()
        for got, want in zip(cfg.effective_weights, (0.3, 0.4, 0.2, 0.1)):
            self.assertAlmostEqual(got, want)

    def test_all_zero_fallback(self):
        cfg = RetrievalConfig(w_vec=0, w_ppr=0, w_kw=0, w_time=0)
        for got, want in zip(cfg.effective_weights, (0.25, 0.25, 0.25, 0.25)):
            self.assertAlmostEqual(got, want)


class SeedExtractionTests(unittest.TestCase):
    def test_regex_fallback_no_fetcher(self):
        g = _chain_graph()
        g.upsert_entity("src/main.py", "file", timeline=1)
        r = GraphRetriever(g)
        res = r.retrieve("Fix the bug in src/main.py inside class Runner")
        names = [e.name for e in res.seed_entities]
        self.assertIn("src/main.py", names)

    def test_llm_fetcher_used(self):
        g = GraphStore()
        g.upsert_entity("GraphStore", "class", timeline=1)
        fetcher = _FakeFetcher(
            '{"entities": [{"name": "GraphStore", "type": "class"}]}'
        )
        r = GraphRetriever(g, query_fetcher=fetcher)
        res = r.retrieve("Tell me about GraphStore")
        self.assertEqual([e.name for e in res.seed_entities], ["GraphStore"])
        self.assertEqual(fetcher.calls[0]["temperature"], 0.0)
        self.assertIn("knowledge graph", fetcher.calls[0]["system_prompt"])

    def test_llm_failure_falls_back_to_regex(self):
        g = GraphStore()
        g.upsert_entity("src/main.py", "file", timeline=1)
        fetcher = _FakeFetcher(fail=True)
        r = GraphRetriever(g, query_fetcher=fetcher)
        res = r.retrieve("Fix src/main.py")
        self.assertIn("src/main.py", [e.name for e in res.seed_entities])

    def test_unresolved_seed_skipped(self):
        g = GraphStore()
        g.upsert_entity("GraphStore", "class", timeline=1)
        fetcher = _FakeFetcher(
            '{"entities": [{"name": "Nonexistent", "type": "concept"}]}'
        )
        r = GraphRetriever(g, query_fetcher=fetcher)
        res = r.retrieve("Nonexistent")
        self.assertEqual(res.seed_entities, [])


class FusionTests(unittest.TestCase):
    def test_ppr_diffusion_monotonic_chain(self):
        g = _chain_graph()
        r = GraphRetriever(g)
        res = r.retrieve("Fix the bug in main.py")
        self.assertEqual(res.seed_entities[0].name, "main.py")
        hits = res.hits
        self.assertEqual(hits[0].entity.name, "main.py")
        # PPR diffusion: fused scores decay along the chain.
        order = ["main.py", "graph_store.py", "builder.py", "retriever.py"]
        scores = {h.entity.name: h.score for h in hits}
        self.assertEqual(list(scores), order)
        for a, b in zip(order, order[1:]):
            self.assertGreater(scores[a], scores[b])
        self.assertEqual(hits[0].matched_relation, "imports")

    def test_time_channel_recency(self):
        g = GraphStore()
        g.upsert_entity("alpha", "concept", timeline=1)
        g.upsert_entity("beta", "concept", timeline=9)
        r = GraphRetriever(g)
        res = r.retrieve("alpha beta", current_timeline=10)
        hits = {h.entity.name: h.score for h in res.hits}
        self.assertGreater(hits["beta"], hits["alpha"])
        self.assertEqual(res.hits[0].entity.name, "beta")

    def test_keyword_exact_match_ranks_first(self):
        g = GraphStore()
        g.upsert_entity("GraphStore", "class", timeline=2)
        g.upsert_entity("StoreHelper", "class", timeline=2)
        r = GraphRetriever(g)
        res = r.retrieve("GraphStore")
        self.assertEqual(res.hits[0].entity.name, "GraphStore")

    def test_embedding_vector_channel(self):
        g = GraphStore()
        g.upsert_entity("alpha.py", "file", timeline=2, embedding=[1.0, 0.0])
        g.upsert_entity("beta.py", "file", timeline=2, embedding=[0.8, 0.6])
        g.upsert_entity("gamma.py", "file", timeline=2, embedding=[0.0, 1.0])
        r = GraphRetriever(g)
        res = r.retrieve("alpha.py")
        names = [h.entity.name for h in res.hits]
        self.assertEqual(names[0], "alpha.py")
        scores = {h.entity.name: h.score for h in res.hits}
        # cosine similarity to the seed anchors beta above orthogonal gamma.
        self.assertGreater(scores["beta.py"], scores["gamma.py"])

    def test_top_k_limit(self):
        g = _chain_graph()
        r = GraphRetriever(g, config=RetrievalConfig(top_k=2))
        res = r.retrieve("Fix the bug in main.py")
        self.assertEqual(len(res.hits), 2)

    def test_min_score_filter(self):
        g = _chain_graph()
        r = GraphRetriever(g, config=RetrievalConfig(min_fused_score=0.7))
        res = r.retrieve("Fix the bug in main.py")
        self.assertEqual([h.entity.name for h in res.hits], ["main.py"])


class ExpansionTests(unittest.TestCase):
    def test_one_hop_neighbors_and_relations(self):
        g = GraphStore()
        ids = {}
        for name in ["A", "B", "C", "D"]:
            ids[name] = g.upsert_entity(name, timeline=1).id
        g.upsert_relation(ids["A"], ids["B"], "uses", timeline=2)
        g.upsert_relation(ids["B"], ids["C"], "depends_on", timeline=3)
        g.upsert_relation(ids["C"], ids["D"], "related_to", timeline=4)
        r = GraphRetriever(g)
        res = r.retrieve("A")
        names = {n.name for n in res.expanded_entities.values()}
        self.assertIn("C", names)
        self.assertIn("D", names)
        rel_pairs = {(e.source_id, e.relation, e.target_id)
                     for e in res.relations}
        self.assertIn((ids["A"], "uses", ids["B"]), rel_pairs)
        self.assertIn((ids["B"], "depends_on", ids["C"]), rel_pairs)
        self.assertIn((ids["C"], "related_to", ids["D"]), rel_pairs)

    def test_neighbor_ids_populated(self):
        g = GraphStore()
        ids = {}
        for name in ["A", "B"]:
            ids[name] = g.upsert_entity(name, timeline=1).id
        g.upsert_relation(ids["A"], ids["B"], "uses", timeline=2)
        r = GraphRetriever(g)
        res = r.retrieve("A")
        self.assertIn(ids["B"], res.hits[0].neighbor_ids)


class CommunityTests(unittest.TestCase):
    def test_cached_community_summaries_selected(self):
        g = GraphStore()
        a = g.upsert_entity("A", timeline=1)
        b = g.upsert_entity("B", timeline=1)
        g.upsert_relation(a.id, b.id, "uses", timeline=2)
        g.communities[0] = [
            CommunitySummary(
                level=0,
                community_id="c0",
                summary="Cluster about A and B",
                member_entity_ids=[a.id, b.id],
            )
        ]
        r = GraphRetriever(g)
        res = r.retrieve("A")
        self.assertEqual(len(res.community_summaries), 1)
        self.assertEqual(res.community_summaries[0].community_id, "c0")
        self.assertIn("Cluster about A and B", res.rendered)

    def test_on_demand_community_detection(self):
        g = _chain_graph()
        r = GraphRetriever(g)
        res = r.retrieve("Fix the bug in main.py")
        # 4-node chain -> one connected component -> one community.
        self.assertGreaterEqual(len(res.community_summaries), 1)

    def test_communities_disabled(self):
        g = _chain_graph()
        r = GraphRetriever(
            g, config=RetrievalConfig(include_communities=False)
        )
        res = r.retrieve("Fix the bug in main.py")
        self.assertEqual(res.community_summaries, [])


class RenderTests(unittest.TestCase):
    def test_rendered_block_format(self):
        g = _chain_graph()
        r = GraphRetriever(g)
        res = r.retrieve("Fix the bug in main.py")
        self.assertTrue(res.rendered.startswith(
            '<graph_memory authority="historical" trust="mixed">'))
        self.assertTrue(res.rendered.endswith("</graph_memory>"))
        self.assertIn("## Entities", res.rendered)
        self.assertIn("## Relations", res.rendered)
        self.assertIn("main.py", res.rendered)
        self.assertIn("--imports-->", res.rendered)
        # low-trust guidance must be present
        self.assertIn("NOT as active instructions", res.rendered)

    def test_standalone_render(self):
        g = GraphStore()
        a = g.upsert_entity("A", timeline=1)
        b = g.upsert_entity("B", timeline=1)
        g.upsert_relation(a.id, b.id, "uses", timeline=2)
        r = GraphRetriever(g)
        res = r.retrieve("A")
        # rendering is a pure function over the result fields
        again = render_graph_memory(
            query=res.query,
            seed_entities=res.seed_entities,
            hits=res.hits,
            expanded=res.expanded_entities,
            relations=res.relations,
            communities=res.community_summaries,
        )
        self.assertEqual(again, res.rendered)


class EmptyGraphTests(unittest.TestCase):
    def test_empty_graph(self):
        r = GraphRetriever(GraphStore())
        res = r.retrieve("anything")
        self.assertTrue(res.empty)
        self.assertEqual(res.rendered, "")

    def test_blank_query(self):
        g = _chain_graph()
        r = GraphRetriever(g)
        res = r.retrieve("   ")
        self.assertTrue(res.empty)


class SerializationTests(unittest.TestCase):
    def test_result_roundtrip(self):
        g = _chain_graph()
        r = GraphRetriever(g)
        res = r.retrieve("Fix the bug in main.py")
        data = res.to_dict()
        restored = GraphRetrievalResult.from_dict(data)
        self.assertEqual(restored.query, res.query)
        self.assertEqual(
            [h.entity.name for h in restored.hits],
            [h.entity.name for h in res.hits],
        )
        self.assertEqual(
            len(restored.relations), len(res.relations)
        )
        self.assertEqual(restored.rendered, res.rendered)
        self.assertEqual(
            sorted(restored.expanded_entities),
            sorted(res.expanded_entities),
        )


if __name__ == "__main__":
    unittest.main()
