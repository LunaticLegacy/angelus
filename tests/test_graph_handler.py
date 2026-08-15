"""Unit tests for graph_memory.handler (P2: GraphContextHandler)."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from llmfetcher.graph_memory import (
    GraphContextHandler,
    GraphStore,
    RetrievalConfig,
)
from llmfetcher.graph_memory.handler import GraphContextHandler as _H
from llmfetcher.llm_types import LLMOutput, LLMToolCall


class _RecordingCompactor:
    """Fake fetcher that returns a valid compaction payload."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def fetch(self, msg, system_prompt=None, temperature=0.4, max_tokens=4096,
              context_handler=None, backend_name=None, tools=None):
        self.calls.append({"msg": msg, "system_prompt": system_prompt})
        return LLMOutput(
            content=(
                "<context_abstract>bounded summary</context_abstract>\n"
                "<source_timelines>[1, 2]</source_timelines>"
            ),
            provider="test", backend_name="test", model="test",
        )


class _FakeExtractionFetcher:
    """Fake LLM that returns a fixed entity/relation JSON payload."""

    def __init__(self, payload: str):
        self.payload = payload
        self.calls: list[dict] = []

    def fetch(self, msg, system_prompt=None, temperature=0.2, max_tokens=512,
              context_handler=None, backend_name=None, tools=None):
        self.calls.append({"msg": msg, "system_prompt": system_prompt})
        return LLMOutput(content=self.payload, provider="t", backend_name="t",
                         model="t")


class _FakeQueryFetcher:
    """Fake LLM that returns fixed seed entities for a query."""

    def __init__(self, payload: str):
        self.payload = payload
        self.calls: list[dict] = []

    def fetch(self, msg, system_prompt=None, temperature=0.0, max_tokens=256,
              context_handler=None, backend_name=None, tools=None):
        self.calls.append({"msg": msg})
        return LLMOutput(content=self.payload, provider="t", backend_name="t",
                         model="t")


def _chain_store(names=("main.py", "graph_store.py", "builder.py",
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


def _assistant(content: str = "ok", **kwargs) -> LLMOutput:
    return LLMOutput(content=content, provider="t", backend_name="t",
                     model="t", **kwargs)


class InitTests(unittest.TestCase):
    def test_defaults(self):
        h = GraphContextHandler(compacting_fetcher=_RecordingCompactor())
        self.assertIsInstance(h.linear, object)
        self.assertEqual(len(h.store), 0)
        self.assertEqual(h.retrieval_trigger, "first_message")
        self.assertEqual(h.graph_update_every, 3)
        self.assertEqual(h.graph_save_suffix, ".graph.json")
        self.assertFalse(h.has_retrieved)
        self.assertEqual(h.graph_memory, "")
        self.assertEqual(h.compaction_generation, 0)
        self.assertEqual(h._pending, [])

    def test_keyword_only_constructor(self):
        with self.assertRaises(TypeError):
            GraphContextHandler(_RecordingCompactor())  # positional not allowed


class RetrievalTriggerTests(unittest.TestCase):
    def test_first_message_retrieval_injects_graph_memory(self):
        h = GraphContextHandler(
            compacting_fetcher=_RecordingCompactor(),
            store=_chain_store(),
        )
        h.add_user_message("how does graph_store.py relate to builder.py?")
        self.assertTrue(h.has_retrieved)
        msgs = h.build_messages()
        self.assertEqual(msgs[0]["role"], "user")
        self.assertIn("<graph_memory", msgs[0]["content"])
        self.assertEqual(msgs[1]["role"], "user")
        self.assertIn("graph_store.py", msgs[1]["content"])

    def test_first_message_retrieves_only_once(self):
        h = GraphContextHandler(
            compacting_fetcher=_RecordingCompactor(),
            store=_chain_store(),
        )
        calls: list[str] = []
        orig = h.retriever.retrieve

        def counting(query, current_timeline=None):
            calls.append(query)
            return orig(query, current_timeline=current_timeline)

        h.retriever.retrieve = counting
        h.add_user_message("one?")
        h.add_user_message("two?")
        h.add_user_message("three?")
        self.assertEqual(len(calls), 1)
        self.assertEqual(h._last_retrieved_gen, 0)

    def test_manual_trigger_requires_explicit_retrieve(self):
        h = GraphContextHandler(
            compacting_fetcher=_RecordingCompactor(),
            store=_chain_store(),
            retrieval_trigger="manual",
        )
        h.add_user_message("how does graph_store.py work?")
        self.assertFalse(h.has_retrieved)
        msgs = h.build_messages()
        self.assertEqual(len(msgs), 1)
        self.assertNotIn("<graph_memory", msgs[0]["content"])

        result = h.retrieve("graph_store.py")
        self.assertTrue(h.has_retrieved)
        self.assertTrue(result.hits)
        msgs = h.build_messages()
        self.assertEqual(msgs[0]["role"], "user")
        self.assertIn("<graph_memory", msgs[0]["content"])

    def test_auto_trigger_reretrieves_after_compaction(self):
        h = GraphContextHandler(
            compacting_fetcher=_RecordingCompactor(),
            store=_chain_store(),
            retrieval_trigger="auto",
            max_context_threshold=1,
        )
        h.add_user_message("first question")
        self.assertTrue(h.has_retrieved)
        self.assertEqual(h._last_retrieved_gen, 0)

        h.add_assistant_message(_assistant("answer " + "x" * 50))
        self.assertEqual(h.compaction_generation, 1)
        self.assertEqual(h._last_retrieved_gen, 0)  # not re-retrieved yet

        h.add_user_message("second question after compaction")
        self.assertEqual(h._last_retrieved_gen, 1)
        self.assertTrue(h.has_retrieved)
        self.assertIn("<graph_memory", h.build_messages()[0]["content"])

    def test_auto_no_reretrieval_without_compaction(self):
        h = GraphContextHandler(
            compacting_fetcher=_RecordingCompactor(),
            store=_chain_store(),
            retrieval_trigger="auto",
            max_context_threshold=10**9,
        )
        calls: list[str] = []
        orig = h.retriever.retrieve

        def counting(query, current_timeline=None):
            calls.append(query)
            return orig(query, current_timeline=current_timeline)

        h.retriever.retrieve = counting
        h.add_user_message("one?")
        h.add_user_message("two?")
        self.assertEqual(len(calls), 1)  # first message only

    def test_empty_graph_no_injection(self):
        h = GraphContextHandler(compacting_fetcher=_RecordingCompactor())
        h.add_user_message("hello world")
        self.assertTrue(h.has_retrieved)   # retrieval ran...
        msgs = h.build_messages()
        self.assertEqual(len(msgs), 1)     # ...but rendered nothing
        self.assertNotIn("<graph_memory", msgs[0]["content"])


class GraphUpdateTests(unittest.TestCase):
    def test_flush_after_graph_update_every_messages(self):
        h = GraphContextHandler(
            compacting_fetcher=_RecordingCompactor(),
            graph_update_every=2,
        )
        h.add_user_message("look at alpha.py")
        self.assertEqual(len(h.store), 0)          # only 1 pending
        h.add_assistant_message(_assistant("alpha.py is fine"))
        self.assertGreater(len(h.store), 0)        # 2 pending -> flushed
        self.assertEqual(h._pending, [])
        names = {n.name for n in h.store.nodes.values()}
        self.assertIn("alpha.py", names)

    def test_no_flush_before_threshold(self):
        h = GraphContextHandler(
            compacting_fetcher=_RecordingCompactor(),
            graph_update_every=5,
        )
        h.add_user_message("look at alpha.py")
        h.add_assistant_message(_assistant("ok"))
        self.assertEqual(len(h.store), 0)
        self.assertEqual(len(h._pending), 2)

    def test_compaction_forces_flush(self):
        h = GraphContextHandler(
            compacting_fetcher=_RecordingCompactor(),
            graph_update_every=100,
            max_context_threshold=1,
        )
        h.add_user_message("check graph_store.py and builder.py")
        h.add_assistant_message(_assistant("graph_store.py imports builder.py"))
        self.assertEqual(h.compaction_generation, 1)
        self.assertGreater(len(h.store), 0)        # flushed despite threshold
        self.assertEqual(h._pending, [])
        names = {n.name for n in h.store.nodes.values()}
        self.assertIn("graph_store.py", names)

    def test_flush_uses_extraction_fetcher(self):
        payload = (
            '{"entities": [{"name": "alpha.py", "type": "file"},'
            ' {"name": "beta.py", "type": "file"}],'
            ' "relations": [{"src": "alpha.py", "dst": "beta.py",'
            ' "relation": "imports"}]}'
        )
        fetcher = _FakeExtractionFetcher(payload)
        h = GraphContextHandler(
            compacting_fetcher=_RecordingCompactor(),
            extraction_fetcher=fetcher,
            graph_update_every=2,
        )
        h.add_user_message("what about alpha.py?")
        h.add_assistant_message(_assistant("alpha.py imports beta.py"))
        self.assertTrue(fetcher.calls)
        self.assertIn("## User", fetcher.calls[0]["msg"])
        self.assertIn("## Assistant", fetcher.calls[0]["msg"])
        names = {n.name for n in h.store.nodes.values()}
        self.assertIn("alpha.py", names)
        self.assertIn("beta.py", names)
        self.assertEqual(len(h.store.edges()), 1)

    def test_pending_timelines_match_linear_rounds(self):
        h = GraphContextHandler(
            compacting_fetcher=_RecordingCompactor(),
            graph_update_every=2,
        )
        h.add_user_message("see gamma.py")          # round 1
        h.add_assistant_message(_assistant("ok"))   # round 2 -> flush
        self.assertEqual(h.linear._round, 2)
        node = h.store.find_entity_by_name("gamma.py")
        self.assertIsNotNone(node)
        assert node is not None
        self.assertEqual(node.last_seen, 2)         # batch max timeline
        self.assertEqual(node.first_seen, 2)


class BuildMessageTests(unittest.TestCase):
    def test_graph_block_first_then_history(self):
        h = GraphContextHandler(
            compacting_fetcher=_RecordingCompactor(),
            store=_chain_store(),
        )
        h.add_user_message("explain main.py")
        h.add_assistant_message(_assistant("main.py imports graph_store.py"))
        msgs = h.build_messages()
        self.assertEqual(msgs[0]["role"], "user")
        self.assertIn("<graph_memory", msgs[0]["content"])
        self.assertEqual(msgs[1]["role"], "user")      # linear history
        self.assertEqual(msgs[2]["role"], "assistant")
        self.assertIn("main.py imports", msgs[2]["content"])

    def test_graph_block_before_compacted_abstract(self):
        h = GraphContextHandler(
            compacting_fetcher=_RecordingCompactor(),
            store=_chain_store(),
            max_context_threshold=1,
        )
        h.add_user_message("first?")
        h.add_assistant_message(_assistant("answer " + "x" * 50))
        msgs = h.build_messages()
        self.assertEqual(msgs[0]["role"], "user")
        self.assertIn("<graph_memory", msgs[0]["content"])
        self.assertEqual(msgs[1]["role"], "system")   # compacted abstract
        self.assertIn("bounded summary", msgs[1]["content"])

    def test_tool_results_forwarded_to_linear(self):
        h = GraphContextHandler(compacting_fetcher=_RecordingCompactor())
        out = _assistant(
            "tool result follows",
            tool_calls=[LLMToolCall(name="shell", call_id="call-1")],
        )
        h.add_assistant_message(out, tool_results={"call-1": "42"})
        msgs = h.build_messages()
        roles = [m["role"] for m in msgs]
        self.assertIn("tool", roles)
        tool_msg = next(m for m in msgs if m["role"] == "tool")
        self.assertEqual(tool_msg["content"], "42")


class PersistenceTests(unittest.TestCase):
    def test_save_flushes_pending_messages_before_persisting_graph(self):
        h = GraphContextHandler(
            compacting_fetcher=_RecordingCompactor(),
            graph_update_every=100,
        )
        h.add_user_message("inspect durable.py")
        self.assertEqual(len(h._pending), 1)
        self.assertEqual(len(h.store), 0)

        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "ctx.json"
            self.assertTrue(h.save(path))

            self.assertEqual(h._pending, [])
            restored = GraphStore()
            self.assertTrue(restored.load(f"{path}.graph.json"))
            self.assertIsNotNone(restored.find_entity_by_name("durable.py"))

    def test_save_load_roundtrip(self):
        store = _chain_store()
        h = GraphContextHandler(
            compacting_fetcher=_RecordingCompactor(),
            store=store,
            graph_update_every=2,
        )
        h.add_user_message("how does graph_store.py work?")
        h.add_assistant_message(_assistant("graph_store.py stores nodes"))
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "ctx.json"
            self.assertTrue(h.save(path))
            self.assertTrue(Path(f"{path}.graph.json").exists())

            h2 = GraphContextHandler(
                compacting_fetcher=_RecordingCompactor(),
                store=GraphStore(),
            )
            self.assertTrue(h2.load(path))
            self.assertEqual(len(h2.linear.messages), len(h.linear.messages))
            self.assertEqual(len(h2.store), len(h.store))
            self.assertEqual(
                {n.name for n in h2.store.nodes.values()},
                {n.name for n in h.store.nodes.values()},
            )

    def test_load_without_graph_file_resets_store(self):
        h = GraphContextHandler(
            compacting_fetcher=_RecordingCompactor(),
            store=_chain_store(),
        )
        self.assertEqual(len(h.store), 4)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "ctx.json"
            # Write only the linear context file (no companion graph).
            linear = _RecordingCompactor()
            from llmfetcher.context_handlers.linear import ContextHandlerLinear
            lin = ContextHandlerLinear(linear)
            lin.add_user_message("legacy context")
            self.assertTrue(lin.save(path))

            self.assertTrue(h.load(path))
            self.assertEqual(len(h.store), 0)          # stale graph cleared
            self.assertEqual(len(h.linear.messages), 1)
            self.assertFalse(h.has_retrieved)

    def test_load_missing_files_returns_false(self):
        h = GraphContextHandler(compacting_fetcher=_RecordingCompactor())
        with TemporaryDirectory() as tmp:
            self.assertFalse(h.load(Path(tmp) / "nope.json"))

    def test_load_sets_compaction_generation_from_abstract(self):
        h1 = GraphContextHandler(
            compacting_fetcher=_RecordingCompactor(),
            max_context_threshold=1,
        )
        h1.add_user_message("first")
        h1.add_assistant_message(_assistant("answer " + "x" * 50))
        self.assertEqual(h1.compaction_generation, 1)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "ctx.json"
            self.assertTrue(h1.save(path))
            h2 = GraphContextHandler(
                compacting_fetcher=_RecordingCompactor(),
            )
            self.assertTrue(h2.load(path))
            self.assertIsNotNone(h2.linear.abstract)
            self.assertEqual(h2.compaction_generation, 1)


class ClearTests(unittest.TestCase):
    def test_clear_context_keeps_long_term_graph(self):
        store = _chain_store()
        h = GraphContextHandler(
            compacting_fetcher=_RecordingCompactor(),
            store=store,
            graph_update_every=1,
        )
        h.add_user_message("check main.py")
        h.add_assistant_message(_assistant("main.py imports graph_store.py"))
        self.assertTrue(h.has_retrieved)
        self.assertGreaterEqual(len(h.store), 4)

        self.assertTrue(h.clear_context())
        self.assertFalse(h.has_retrieved)
        self.assertEqual(h.graph_memory, "")
        self.assertEqual(h.linear.messages, [])
        self.assertEqual(h._pending, [])
        self.assertEqual(h.compaction_generation, 0)
        self.assertGreaterEqual(len(h.store), 4)      # long-term graph kept


class RetrieveApiTests(unittest.TestCase):
    def test_retrieve_uses_current_timeline(self):
        h = GraphContextHandler(
            compacting_fetcher=_RecordingCompactor(),
            store=_chain_store(),
        )
        h.add_user_message("first")
        h.add_assistant_message(_assistant("ok"))
        self.assertEqual(h.linear._round, 2)
        result = h.retrieve("graph_store.py")
        self.assertEqual(result.current_timeline, 2)
        self.assertTrue(result.hits)
        self.assertEqual(h.graph_memory, result.rendered)

    def test_query_fetcher_used_for_seed_extraction(self):
        qf = _FakeQueryFetcher(
            '{"entities": [{"name": "graph_store.py", "type": "file"}]}'
        )
        h = GraphContextHandler(
            compacting_fetcher=_RecordingCompactor(),
            store=_chain_store(),
            query_fetcher=qf,
        )
        result = h.retrieve("tell me about graph_store.py")
        self.assertTrue(qf.calls)
        self.assertTrue(result.hits)
        self.assertEqual(result.seed_entities[0].name, "graph_store.py")

    def test_retriever_config_applied(self):
        cfg = RetrievalConfig(top_k=2, include_communities=False)
        h = GraphContextHandler(
            compacting_fetcher=_RecordingCompactor(),
            store=_chain_store(),
            retriever_config=cfg,
        )
        result = h.retrieve("graph_store.py")
        self.assertLessEqual(len(result.hits), 2)


if __name__ == "__main__":
    unittest.main()
