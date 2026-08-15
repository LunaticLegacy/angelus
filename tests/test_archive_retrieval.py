"""Regression tests for bounded raw-context archive retrieval."""

from __future__ import annotations

import unittest

from llmfetcher.context_handlers.archive_retrieval import (
    ArchiveRetrievalConfig,
    retrieve_archive,
)
from llmfetcher.llm_types import LLMContext, LLMToolCall, ToolInfo


class ArchiveRetrievalTests(unittest.TestCase):
    def test_returns_ranked_evidence_with_source_timeline(self) -> None:
        records = [
            LLMContext(role="user", timeline=2, content="Please inspect auth.py"),
            LLMContext(role="assistant", timeline=3, content="The token cache is in auth.py"),
            LLMContext(role="assistant", timeline=4, content="Database migration completed"),
        ]

        result = retrieve_archive("auth token", records)

        self.assertEqual(result.scanned_records, 3)
        self.assertEqual([hit.timeline_start for hit in result.evidence], [3, 2])
        self.assertTrue(all(hit.timeline_start == hit.timeline_end for hit in result.evidence))
        self.assertIn("auth", result.evidence[0].matched_terms)
        self.assertIn("timeline 3", result.evidence[0].text)

    def test_tool_output_is_searchable_but_returned_evidence_is_bounded(self) -> None:
        records = [
            LLMContext(
                role="assistant",
                timeline=8,
                content="Ran the diagnostic command.",
                tool_calls=[ToolInfo(
                    call=LLMToolCall(name="shell", arguments={"cmd": "check"}),
                    result="unique-failure-signature " + "x" * 500,
                )],
            )
        ]

        result = retrieve_archive(
            "unique-failure-signature",
            records,
            config=ArchiveRetrievalConfig(max_chars_per_record=80),
        )

        self.assertEqual(len(result.evidence), 1)
        self.assertLessEqual(len(result.evidence[0].text), 80)
        self.assertTrue(result.evidence[0].text.endswith("…"))

    def test_cjk_terms_match_and_limits_are_enforced(self) -> None:
        records = [
            LLMContext(role="user", timeline=1, content="修复上下文持久化"),
            LLMContext(role="assistant", timeline=2, content="上下文已经保存"),
            LLMContext(role="assistant", timeline=3, content="无关内容"),
        ]

        result = retrieve_archive(
            "上下文",
            records,
            config=ArchiveRetrievalConfig(max_results=1),
        )

        self.assertEqual(len(result.evidence), 1)
        self.assertEqual(result.evidence[0].timeline_start, 2)

    def test_empty_query_and_invalid_bounds_do_not_create_unbounded_results(self) -> None:
        records = [LLMContext(role="user", timeline=1, content="anything")]
        self.assertEqual(retrieve_archive("", records).evidence, ())
        with self.assertRaises(ValueError):
            ArchiveRetrievalConfig(max_results=0)
        with self.assertRaises(ValueError):
            ArchiveRetrievalConfig(max_chars_per_record=0)


if __name__ == "__main__":
    unittest.main()
