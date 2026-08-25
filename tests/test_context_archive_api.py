"""Read-only visibility of raw context archived during compaction."""

import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from fastapi.testclient import TestClient

from angelus import storage, webapp


class ContextArchiveApiTests(unittest.TestCase):
    def test_agent_context_graph_is_bounded_and_exposes_only_visible_relations(self) -> None:
        """The graph inspector receives a safe per-Agent persisted snapshot."""
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(directory)
            try:
                graph_path = webapp._context_path("work", "session", "worker")
                graph_path.with_name(f"{graph_path.name}.graph.json").write_text(json.dumps({
                    "nodes": {
                        "file:a.py": {"id": "file:a.py", "name": "a.py", "entity_type": "file", "last_seen": 5, "freq": 2},
                        "tool:rg": {"id": "tool:rg", "name": "rg", "entity_type": "tool", "last_seen": 4, "freq": 1},
                        "concept:hidden": {"id": "concept:hidden", "name": "hidden", "last_seen": 1},
                    },
                    "edges": [
                        {"source_id": "file:a.py", "target_id": "tool:rg", "relation": "uses", "weight": 2, "last_seen": 5, "evidence": [3]},
                        {"source_id": "file:a.py", "target_id": "concept:hidden", "relation": "mentions"},
                    ],
                    "communities": {"0": [{"level": 0, "community_id": "one", "summary": "source tools"}]},
                }), encoding="utf-8")

                payload = webapp._agent_context_graph("work", "worker", limit=2)

                self.assertTrue(payload.available)
                self.assertTrue(payload.truncated)
                self.assertEqual(payload.node_count, 3)
                self.assertEqual([node.id for node in payload.nodes], ["file:a.py", "tool:rg"])
                self.assertEqual(payload.edges[0].relation, "uses")
                self.assertEqual(payload.edges[0].evidence, [3])
                self.assertEqual(payload.community_count, 1)
            finally:
                storage.WORKSPACE_ROOT = original_root

    def test_agent_context_graph_is_empty_when_companion_file_is_missing(self) -> None:
        """Old linear-only contexts remain inspectable without an API error."""
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(directory)
            try:
                payload = webapp._agent_context_graph("work", "coordinator")
                self.assertFalse(payload.available)
                self.assertEqual(payload.nodes, [])
                self.assertEqual(payload.edges, [])
            finally:
                storage.WORKSPACE_ROOT = original_root

    def test_archive_page_exposes_raw_evidence_and_timeline_with_pagination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(directory)
            try:
                context = webapp._context_path("work", "session", "coordinator")
                context.write_text(json.dumps({"archive": [
                    {"timeline": 1, "role": "user", "content": "first", "tags": ["request"]},
                    {"timeline": 2, "role": "assistant", "content": "second", "content_reasoning": "why",
                     "tool_calls": [{"call": {"name": "search", "arguments": {"q": "x"}}, "result": "found"}]},
                    {"timeline": 3, "role": "user", "content": "third"},
                ], "messages": []}), encoding="utf-8")

                newest = webapp._archived_context_page("work", "session", limit=2)
                self.assertEqual(newest["total"], 3)
                self.assertEqual(newest["next_before"], 1)
                self.assertEqual([item["timeline"] for item in newest["evidence"]], [3, 2])
                self.assertEqual(newest["evidence"][1]["reasoning"], "why")
                self.assertEqual(newest["evidence"][1]["tool_calls"][0]["result"], "found")

                older = webapp._archived_context_page("work", "session", before=newest["next_before"], limit=2)
                self.assertIsNone(older["next_before"])
                self.assertEqual([item["timeline"] for item in older["evidence"]], [1])
            finally:
                storage.WORKSPACE_ROOT = original_root

    def test_active_context_preview_matches_model_message_shape(self) -> None:
        """The viewer receives the full persisted prompt in send order."""
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(directory)
            try:
                context = webapp._context_path("work", "session", "coordinator")
                context.write_text(json.dumps({"messages": [
                    {"timeline": 1, "role": "user", "content": "first"},
                    {"timeline": 2, "role": "assistant", "content": "second", "tool_calls": [{
                        "call": {"name": "plan", "arguments": {"id": 2}},
                        "result": {"ok": True},
                    }]},
                    {"timeline": 3, "role": "user", "content": "third"},
                ]}), encoding="utf-8")

                preview = webapp._agent_context_preview("work", "coordinator")
                self.assertEqual(preview.total, 4)
                self.assertEqual([item["role"] for item in preview.messages], ["user", "assistant", "tool", "user"])
                self.assertEqual(preview.messages[1]["tool_calls"][0]["arguments"], {"id": 2})
                self.assertEqual(preview.messages[2]["content"], "{'ok': True}")
                self.assertEqual([(item.index, item.source, item.type, item.length, item.timeline) for item in preview.metadata], [
                    (1, "coordinator", "user", 5, "1"),
                    (2, "coordinator", "assistant", 6, "2"),
                    (3, "tool · plan", "tool", 12, "2"),
                    (4, "coordinator", "user", 5, "3"),
                ])
            finally:
                storage.WORKSPACE_ROOT = original_root

    def test_context_preview_uses_latest_captured_remote_request(self) -> None:
        """Prefer the actual credential-free request snapshot over a rebuild."""
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(directory)
            try:
                webapp._context_path("work", "work", "worker").write_text(
                    json.dumps({"messages": []}), encoding="utf-8"
                )
                storage._append_session_event("work", "work", {
                    "event": "lifecycle",
                    "agent": "worker",
                    "type": "agent:remote_request",
                    "data": {"request": {
                        "model": "test-model",
                        "messages": [{"role": "user", "content": "exact request"}],
                        "tools": [{"type": "function", "function": {"name": "search"}}],
                    }},
                })

                preview = webapp._agent_context_preview("work", "worker")

                self.assertEqual(preview.request["messages"][0]["content"], "exact request")
                self.assertEqual(preview.request["tools"][0]["function"]["name"], "search")
                self.assertEqual(preview.total, 1)
                self.assertEqual(preview.metadata[0].type, "user")
                self.assertEqual(preview.metadata[0].timeline, "request")
                self.assertEqual(preview.stats.messages, 1)
                self.assertEqual(preview.stats.tool_schemas, 1)
            finally:
                storage.WORKSPACE_ROOT = original_root

    def test_archive_page_is_empty_for_legacy_or_malformed_contexts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(directory)
            try:
                context = webapp._context_path("work", "legacy", "coordinator")
                context.write_text(json.dumps({"messages": [{"role": "user", "content": "old"}]}), encoding="utf-8")
                self.assertEqual(webapp._archived_context_page("work", "legacy"), {
                    "evidence": [], "total": 0, "next_before": None,
                })

                context.write_text(json.dumps({"archive": [{"timeline": "bad", "role": "user"}, None]}), encoding="utf-8")
                self.assertEqual(webapp._archived_context_page("work", "legacy")["evidence"], [])
            finally:
                storage.WORKSPACE_ROOT = original_root


if __name__ == "__main__":
    unittest.main()


def _seed_linear_context(
    directory: Path,
    agent: str = "coordinator",
    messages: list[dict] | None = None,
    threshold: int = 262144,
    round_: int = 2,
) -> Path:
    """Write a linear-context checkpoint for one Agent under a temp root."""
    context_dir = Path(directory) / "demo" / "contexts"
    context_dir.mkdir(parents=True, exist_ok=True)
    path = context_dir / f"{agent}.json"
    payload = {
        "compress_threshold": threshold,
        "round": round_,
        "abstract": None,
        "messages": messages if messages is not None else [
            {"role": "user", "timeline": 1, "content": "第一条", "content_reasoning": "", "tool_calls": [], "tags": []},
            {"role": "assistant", "timeline": 2, "content": "第二条", "content_reasoning": "", "tool_calls": [], "tags": []},
        ],
        "archive": [],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


class CompactionInputPreviewApiTests(unittest.TestCase):
    """Read-only preview of the exact text the context compactor would send."""

    def test_compaction_input_preview_matches_compactor_transcript(self) -> None:
        """The endpoint returns the bounded transcript plus budget metadata."""
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(directory)
            try:
                _seed_linear_context(Path(directory))
                client = TestClient(webapp.app)
                response = client.get(
                    "/api/sessions/demo/agents/coordinator/context/compaction-input"
                )
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertEqual(payload["agent"], "coordinator")
                self.assertIn("第一条", payload["text"])
                self.assertIn("第二条", payload["text"])
                self.assertEqual(payload["characters"], len(payload["text"]))
                self.assertEqual(payload["threshold"], 262144)
                self.assertEqual(payload["round"], 2)
                self.assertEqual(payload["messages"], 2)
                self.assertEqual(payload["omitted"], 0)
                self.assertEqual(payload["estimated_tokens"], (len(payload["text"]) + 3) // 4)
            finally:
                storage.WORKSPACE_ROOT = original_root

    def test_compaction_input_preview_omits_oldest_entries_when_over_budget(self) -> None:
        """Newest-first retention must match the compactor's omitted prefix."""
        import llmfetcher.context_handlers.linear as linear_module

        original = linear_module.ContextHandlerLinear

        class SmallBudgetHandler(original):
            def __init__(self, *args, **kwargs):
                kwargs.setdefault("compaction_input_char_limit", 120)
                super().__init__(*args, **kwargs)

        newest = "最新的一条消息内容，长度足够长以便超过压缩预算"
        oldest = "最旧的一条消息内容，应当被省略掉"
        messages = [
            {"role": "user", "timeline": i, "content": content, "content_reasoning": "", "tool_calls": [], "tags": []}
            for i, content in enumerate([oldest, "中间消息甲", "中间消息乙", newest], start=1)
        ]
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(directory)
            try:
                _seed_linear_context(Path(directory), messages=messages)
                with mock.patch.object(linear_module, "ContextHandlerLinear", SmallBudgetHandler):
                    client = TestClient(webapp.app)
                    response = client.get(
                        "/api/sessions/demo/agents/coordinator/context/compaction-input"
                    )
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertEqual(payload["messages"], 4)
                self.assertGreater(payload["omitted"], 0)
                self.assertTrue(payload["text"].startswith("[Earlier context entries omitted"))
                self.assertIn(newest, payload["text"])
                self.assertNotIn(oldest, payload["text"])
                self.assertEqual(payload["characters"], len(payload["text"]))
            finally:
                storage.WORKSPACE_ROOT = original_root

    def test_compaction_input_preview_is_empty_for_missing_agent(self) -> None:
        """An Agent without a persisted checkpoint renders an empty state."""
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(directory)
            try:
                client = TestClient(webapp.app)
                response = client.get(
                    "/api/sessions/demo/agents/worker/context/compaction-input"
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {
                    "agent": "worker", "text": "", "characters": 0, "threshold": 0,
                    "round": 0, "messages": 0, "omitted": 0, "estimated_tokens": 0,
                })
            finally:
                storage.WORKSPACE_ROOT = original_root

    def test_compaction_input_preview_is_empty_for_malformed_context(self) -> None:
        """A corrupt checkpoint must not crash the read-only preview."""
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(directory)
            try:
                _seed_linear_context(Path(directory))
                context = webapp._context_path("demo", "demo", "coordinator")
                context.write_text("{not valid json", encoding="utf-8")
                client = TestClient(webapp.app)
                response = client.get(
                    "/api/sessions/demo/agents/coordinator/context/compaction-input"
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["text"], "")
                self.assertEqual(response.json()["messages"], 0)
            finally:
                storage.WORKSPACE_ROOT = original_root

    def test_compaction_input_preview_rejects_aggregate_agent(self) -> None:
        """The aggregate ``all`` filter is not a single Agent checkpoint."""
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(directory)
            try:
                client = TestClient(webapp.app)
                response = client.get(
                    "/api/sessions/demo/agents/all/context/compaction-input"
                )
                self.assertEqual(response.status_code, 422)
            finally:
                storage.WORKSPACE_ROOT = original_root

    def test_compaction_input_preview_rejects_invalid_ids(self) -> None:
        """Unsafe identifiers are rejected before any file access."""
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(directory)
            try:
                client = TestClient(webapp.app)
                response = client.get(
                    "/api/sessions/bad%20id/agents/coordinator/context/compaction-input"
                )
                self.assertEqual(response.status_code, 400)
                response = client.get(
                    "/api/sessions/demo/agents/bad%20id/context/compaction-input"
                )
                self.assertEqual(response.status_code, 400)
            finally:
                storage.WORKSPACE_ROOT = original_root
