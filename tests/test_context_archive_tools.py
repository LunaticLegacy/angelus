"""Regression coverage for Agent access to compacted-out context."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import unittest

from llmfetcher.llm_types import (
    AssistantContextItem,
    ContextItemId,
    TokenUsage,
    ToolCallRecord,
    ToolResultId,
    ToolResultRecord,
    UserContextItem,
)

from angelus.modules.context_version_module.store import (
    ArchiveRecordResult,
    ArchiveSearchResult,
    ContextVersionError,
    ContextVersionStore,
)
from angelus.modules.context_version_module.tool_provider import ContextVersionToolProvider
from angelus.modules.tool_module import ToolPolicy


def _linear() -> SimpleNamespace:
    result = ToolResultRecord(
        result_id=ToolResultId("r1"),
        call_id="call-1",
        tool_name="archive_search",
        output="beta result only",
        images=(),
        ok=True,
        duration_ms=1,
        created_at=1.0,
    )
    results = {"r1": result}

    def resolve_tool_result(result_id: ToolResultId) -> ToolResultRecord:
        try:
            return results[result_id.value]
        except KeyError:
            raise KeyError(f"no stored tool result for {result_id.value!r}") from None

    return SimpleNamespace(
        archive=[
            UserContextItem(
                item_id=ContextItemId("item-1"),
                timeline=1,
                content="alpha beta project notes",
                images=(),
            ),
            AssistantContextItem(
                item_id=ContextItemId("item-2"),
                timeline=2,
                content="alpha gamma decision",
                reasoning="",
                tool_calls=(
                    ToolCallRecord(
                        call_id="call-1",
                        name="archive_search",
                        arguments={},
                        result_id=result.result_id,
                    ),
                ),
                usage=TokenUsage(),
                model_duration_ms=None,
                round_duration_ms=None,
                created_at=None,
            ),
        ],
        tool_results=results,
        resolve_tool_result=resolve_tool_result,
    )


def _agent(directory: str, linear: SimpleNamespace | None = None) -> SimpleNamespace:
    path = Path(directory) / "agent" / "context.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return SimpleNamespace(
        context_path=path,
        context_handler=SimpleNamespace(linear=linear or _linear()),
    )


class ContextArchiveToolsTests(unittest.TestCase):
    def test_search_archive_returns_ranked_dataclass_evidence(self) -> None:
        with TemporaryDirectory() as directory:
            result = ContextVersionStore(_agent(directory), "coordinator").search_archive(
                "alpha beta", limit=2
            )

            self.assertIsInstance(result, ArchiveSearchResult)
            self.assertEqual(result.agent, "coordinator")
            self.assertEqual((result.archive_records, result.scanned_records), (2, 2))
            self.assertEqual(result.evidence[0].timeline_start, 2)
            self.assertIn("alpha", result.evidence[0].matched_terms)
            self.assertIn("beta", result.evidence[0].matched_terms)

    def test_search_archive_rejects_empty_query_and_clamps_limit(self) -> None:
        with TemporaryDirectory() as directory:
            store = ContextVersionStore(_agent(directory), "coordinator")

            with self.assertRaises(ContextVersionError):
                store.search_archive("   ")
            self.assertEqual(len(store.search_archive("beta", limit=0).evidence), 1)

    def test_read_archive_returns_full_record_by_timeline(self) -> None:
        with TemporaryDirectory() as directory:
            result = ContextVersionStore(_agent(directory), "coordinator").read_archive(2)

            self.assertIsInstance(result, ArchiveRecordResult)
            self.assertEqual(result.agent, "coordinator")
            self.assertEqual(result.record.timeline, 2)
            self.assertEqual(result.record.content, "alpha gamma decision")

    def test_read_archive_rejects_unknown_timeline(self) -> None:
        with TemporaryDirectory() as directory:
            with self.assertRaises(ContextVersionError):
                ContextVersionStore(_agent(directory), "coordinator").read_archive(99)

    def test_materialized_archive_tools_serialize_dataclass_results(self) -> None:
        with TemporaryDirectory() as directory:
            agent = _agent(directory)
            session = SimpleNamespace(
                coordinator=agent,
                coordinator_name="coordinator",
                swarm=SimpleNamespace(get_agent=lambda _name: None),
            )
            policy = ToolPolicy(
                frozenset({"context_version"}),
                frozenset({"search_agent_archive", "read_agent_archive"}),
            )
            tools = {
                tool.name: tool
                for tool in ContextVersionToolProvider(None).materialize(
                    session, policy, "coordinator", "coordinator"
                )
            }

            searched = json.loads(tools["search_agent_archive"].handler(query="alpha", limit=1))
            read = json.loads(tools["read_agent_archive"].handler(timeline=2))

            self.assertEqual(searched["agent"], "coordinator")
            self.assertEqual(len(searched["evidence"]), 1)
            self.assertEqual(read["record"]["timeline"], 2)


if __name__ == "__main__":
    unittest.main()
