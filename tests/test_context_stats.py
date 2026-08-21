"""Spec coverage for unified context-length statistics.

Contract source: ``docs/context-stats-unification-spec.md``.

- ``angelus.context_stats.estimate_context_length`` is the single estimation
  entry point (characters = JSON serialized length, ``estimated_tokens =
  (characters + 3) // 4``).
- ``angelus.history._agent_context_stats`` exposes the new ``estimated_tokens``
  and ``tool_schema_characters`` keys while keeping the legacy
  messages/characters/abstract_characters/compacted/threshold/round/ratio keys.
- ``angelus.history._agent_context_preview`` builds a complete
  ``RemoteRequestStats`` from ``estimate_context_length``.

The ``context_stats`` module is developed by a parallel worker; the tests skip
with a clear reason if it is not importable yet.
"""

from __future__ import annotations

import dataclasses
import json
import tempfile
import unittest
from pathlib import Path

from angelus import storage
from angelus.history import (
    RemoteRequestStats,
    _agent_context_preview,
    _agent_context_stats,
)

try:
    from angelus.context_stats import ContextLengthStats, estimate_context_length
    HAS_CONTEXT_STATS = True
except ImportError:  # pragma: no cover - parallel-worker backend not landed yet
    estimate_context_length = None
    HAS_CONTEXT_STATS = False


def _json_length(value: object) -> int:
    """Reference serializer matching the spec's unique character basis."""
    return len(json.dumps(value, ensure_ascii=False, default=str))


class ContextLengthStatsTests(unittest.TestCase):
    """``estimate_context_length`` produces spec-compliant size statistics."""

    def test_empty_list_is_all_zeros(self) -> None:
        if not HAS_CONTEXT_STATS:
            self.skipTest("angelus.context_stats not implemented yet")
        stats = estimate_context_length([])
        self.assertEqual(stats.messages, 0)
        self.assertEqual(stats.characters, 0)
        self.assertEqual(stats.tool_schemas, 0)
        self.assertEqual(stats.tool_schema_characters, 0)
        self.assertEqual(stats.estimated_tokens, 0)

    def test_empty_list_with_empty_tools_is_all_zeros(self) -> None:
        if not HAS_CONTEXT_STATS:
            self.skipTest("angelus.context_stats not implemented yet")
        stats = estimate_context_length([], [])
        self.assertEqual(stats.messages, 0)
        self.assertEqual(stats.characters, 0)
        self.assertEqual(stats.tool_schemas, 0)
        self.assertEqual(stats.tool_schema_characters, 0)
        self.assertEqual(stats.estimated_tokens, 0)

    def test_plain_messages_are_measured_and_tokens_derived(self) -> None:
        if not HAS_CONTEXT_STATS:
            self.skipTest("angelus.context_stats not implemented yet")
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        expected_characters = sum(_json_length(item) for item in messages)

        stats = estimate_context_length(messages)

        self.assertEqual(stats.messages, 2)
        self.assertEqual(stats.characters, expected_characters)
        self.assertEqual(stats.estimated_tokens, (expected_characters + 3) // 4)
        self.assertEqual(stats.tool_schemas, 0)
        self.assertEqual(stats.tool_schema_characters, 0)

    def test_tool_schemas_are_counted_separately(self) -> None:
        if not HAS_CONTEXT_STATS:
            self.skipTest("angelus.context_stats not implemented yet")
        messages = [{"role": "user", "content": "call a tool"}]
        tool_schemas = [
            {"type": "function", "function": {"name": "search", "parameters": {"q": "x"}}},
            {"type": "function", "function": {"name": "summarize"}},
        ]
        expected_characters = sum(_json_length(item) for item in messages)
        expected_tool_characters = sum(_json_length(item) for item in tool_schemas)

        stats = estimate_context_length(messages, tool_schemas)

        self.assertEqual(stats.messages, 1)
        self.assertEqual(stats.characters, expected_characters)
        self.assertEqual(stats.tool_schemas, 2)
        self.assertEqual(stats.tool_schema_characters, expected_tool_characters)
        self.assertEqual(stats.estimated_tokens, (expected_characters + 3) // 4)

    def test_non_dict_entries_are_skipped_defensively(self) -> None:
        if not HAS_CONTEXT_STATS:
            self.skipTest("angelus.context_stats not implemented yet")
        messages = [
            {"role": "user", "content": "kept"},
            "not-a-dict",
            None,
            42,
        ]
        tool_schemas = [
            {"type": "function", "function": {"name": "search"}},
            "junk-tool",
        ]
        expected_characters = sum(_json_length(item) for item in messages if isinstance(item, dict))

        stats = estimate_context_length(messages, tool_schemas)

        self.assertEqual(stats.messages, 1)
        self.assertEqual(stats.characters, expected_characters)
        self.assertEqual(stats.tool_schemas, 1)
        self.assertEqual(stats.tool_schema_characters, _json_length(tool_schemas[0]))
        self.assertEqual(stats.estimated_tokens, (expected_characters + 3) // 4)

    def test_result_is_a_frozen_dataclass_with_full_fields(self) -> None:
        if not HAS_CONTEXT_STATS:
            self.skipTest("angelus.context_stats not implemented yet")
        stats = estimate_context_length([{"role": "user", "content": "x"}])
        self.assertTrue(dataclasses.is_dataclass(stats))
        self.assertIsInstance(stats, ContextLengthStats)
        self.assertEqual(
            [field.name for field in dataclasses.fields(stats)],
            ["messages", "characters", "tool_schemas", "tool_schema_characters", "estimated_tokens"],
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            stats.messages = 99  # type: ignore[misc]


class AgentContextStatsTests(unittest.TestCase):
    """``_agent_context_stats`` keeps legacy keys and adds the spec fields."""

    SPEC_KEYS = (
        "messages",
        "characters",
        "abstract_characters",
        "compacted",
        "threshold",
        "round",
        "ratio",
        "estimated_tokens",
        "tool_schema_characters",
    )

    def _assert_all_spec_keys_present(self, stats: dict) -> None:
        self.assertEqual(set(self.SPEC_KEYS), set(stats))

    def test_missing_context_yields_all_zero_spec_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(directory)
            try:
                stats = _agent_context_stats("work", "coordinator")
                self._assert_all_spec_keys_present(stats)
                self.assertEqual(stats["messages"], 0)
                self.assertEqual(stats["characters"], 0)
                self.assertEqual(stats["abstract_characters"], 0)
                self.assertEqual(stats["compacted"], False)
                self.assertEqual(stats["threshold"], 0)
                self.assertEqual(stats["round"], 0)
                self.assertEqual(stats["ratio"], 0.0)
                self.assertEqual(stats["estimated_tokens"], 0)
                self.assertEqual(stats["tool_schema_characters"], 0)
            finally:
                storage.WORKSPACE_ROOT = original_root

    def test_context_stats_include_estimated_tokens_and_keep_legacy_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(directory)
            try:
                messages = [
                    {"role": "user", "content": "hello"},
                    {"role": "assistant", "content": "hi"},
                    {"role": "user", "content": "third"},
                ]
                expected_characters = sum(_json_length(item) for item in messages)
                storage._context_path("work", "work", "coordinator").write_text(
                    json.dumps({"messages": messages}), encoding="utf-8"
                )

                stats = _agent_context_stats("work", "coordinator")

                self._assert_all_spec_keys_present(stats)
                self.assertEqual(stats["messages"], 3)
                self.assertEqual(stats["characters"], expected_characters)
                self.assertEqual(stats["estimated_tokens"], (expected_characters + 3) // 4)
                self.assertEqual(stats["tool_schema_characters"], 0)
                # Checkpoint-only stats stay at their legacy defaults.
                self.assertEqual(stats["abstract_characters"], 0)
                self.assertEqual(stats["compacted"], False)
                self.assertEqual(stats["threshold"], 0)
                self.assertEqual(stats["round"], 0)
                self.assertEqual(stats["ratio"], 0.0)
            finally:
                storage.WORKSPACE_ROOT = original_root

    def test_context_stats_preserve_compaction_and_ratio_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(directory)
            try:
                messages = [
                    {"role": "user", "content": "hello"},
                    {"role": "assistant", "content": "world"},
                ]
                abstract = {"summary": "compacted conversation", "source_timeline": [1, 2]}
                threshold = 200
                expected_characters = sum(_json_length(item) for item in messages)
                expected_abstract = _json_length(abstract)
                storage._context_path("work", "work", "coordinator").write_text(
                    json.dumps({
                        "messages": messages,
                        "abstract": abstract,
                        "compress_threshold": threshold,
                        "round": 4,
                    }),
                    encoding="utf-8",
                )

                stats = _agent_context_stats("work", "coordinator")

                self._assert_all_spec_keys_present(stats)
                self.assertEqual(stats["messages"], 2)
                self.assertEqual(stats["characters"], expected_characters)
                self.assertEqual(stats["estimated_tokens"], (expected_characters + 3) // 4)
                self.assertEqual(stats["tool_schema_characters"], 0)
                self.assertTrue(stats["compacted"])
                self.assertEqual(stats["abstract_characters"], expected_abstract)
                self.assertEqual(stats["threshold"], threshold)
                self.assertEqual(stats["round"], 4)
                expected_ratio = round(min(1.0, (expected_characters + expected_abstract) / threshold), 4)
                self.assertEqual(stats["ratio"], expected_ratio)
            finally:
                storage.WORKSPACE_ROOT = original_root


class AgentContextPreviewStatsTests(unittest.TestCase):
    """``RemoteRequestStats`` from ``_agent_context_preview`` stays complete."""

    STAT_FIELDS = ("messages", "characters", "tool_schemas", "tool_schema_characters", "estimated_tokens")

    def test_remote_request_stats_dataclass_fields_are_complete(self) -> None:
        self.assertEqual([field.name for field in dataclasses.fields(RemoteRequestStats)], list(self.STAT_FIELDS))
        self.assertTrue(all(field.type in ("int", int) for field in dataclasses.fields(RemoteRequestStats)))
        self.assertTrue(dataclasses.is_dataclass(RemoteRequestStats))

    def test_preview_stats_match_estimate_context_length(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(directory)
            try:
                storage._context_path("work", "work", "worker").write_text(
                    json.dumps({"messages": []}), encoding="utf-8"
                )
                request = {
                    "model": "test-model",
                    "messages": [{"role": "user", "content": "exact request"}],
                    "tools": [
                        {"type": "function", "function": {"name": "search", "parameters": {"q": "x"}}},
                    ],
                }
                storage._append_session_event("work", "work", {
                    "event": "lifecycle",
                    "type": "agent:remote_request",
                    "agent": "worker",
                    "data": {"request": request},
                })

                preview = _agent_context_preview("work", "worker")

                self.assertIsNotNone(preview.stats)
                message_chars = sum(_json_length(item) for item in request["messages"])
                tool_chars = sum(_json_length(item) for item in request["tools"])
                self.assertEqual(preview.stats.messages, len(request["messages"]))
                self.assertEqual(preview.stats.characters, message_chars)
                self.assertEqual(preview.stats.tool_schemas, len(request["tools"]))
                self.assertEqual(preview.stats.tool_schema_characters, tool_chars)
                self.assertEqual(preview.stats.estimated_tokens, (message_chars + 3) // 4)

                serialized = preview.to_dict()
                self.assertEqual(set(serialized["stats"]), set(self.STAT_FIELDS))
            finally:
                storage.WORKSPACE_ROOT = original_root

    def test_preview_without_remote_request_has_no_stats(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(directory)
            try:
                storage._context_path("work", "work", "worker").write_text(
                    json.dumps({"messages": [{"role": "user", "content": "hello"}]}), encoding="utf-8"
                )

                preview = _agent_context_preview("work", "worker")

                self.assertIsNone(preview.stats)
                self.assertIsNone(preview.request)
                serialized = preview.to_dict()
                self.assertIsNone(serialized["stats"])
                self.assertEqual(set(serialized), {"messages", "metadata", "request", "total", "stats"})
            finally:
                storage.WORKSPACE_ROOT = original_root


if __name__ == "__main__":
    unittest.main()
