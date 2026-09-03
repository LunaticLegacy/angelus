"""Regression coverage for durable per-message usage metadata."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from angelus.core import AngelusCore
from llmfetcher.context_handlers.linear import ContextHandlerLinear, read_persisted_context_page
from llmfetcher.llm_types import LLMContext, LLMOutput, TokenUsage


class _NoopCompactor:
    """Offline placeholder; these tests deliberately never compact."""



class _UsageSwarm:
    """Minimal aggregate exposing distinct Coordinator/Worker accounting."""

    def total_usage(self) -> dict[str, int]:
        return {"input": 150, "cached": 90, "output": 35, "reasoning": 11, "total": 185}

    def agent_usage(self) -> dict[str, dict[str, int]]:
        return {
            "coordinator": {"input": 120, "cached": 75, "output": 30, "reasoning": 9, "total": 150},
            "worker": {"input": 30, "cached": 15, "output": 5, "reasoning": 2, "total": 35},
        }


def _assistant() -> LLMOutput:
    """Return one assistant response with provider-normalised token data."""
    return LLMOutput(
        content="durable assistant reply",
        provider="test",
        backend_name="test",
        model="test-model",
        usage=TokenUsage(
            input_tokens=120,
            cached_tokens=75,
            output_tokens=30,
            reasoning_tokens=9,
            total_tokens=150,
        ),
    )


class MessageUsageMetadataTests(unittest.TestCase):
    """Ensure message detail cards survive checkpoint, paging, and restart."""

    def test_sqlite_page_round_trips_usage_and_timing(self) -> None:
        """SQLite payload rows retain per-reply metrics rather than totals."""
        with TemporaryDirectory() as directory:
            path = Path(directory) / "context.json"
            writer = ContextHandlerLinear(_NoopCompactor())
            writer.add_assistant_message(
                _assistant(),
                usage={"input": 120, "cached": 75, "output": 30, "reasoning": 9, "total": 150},
                model_duration_ms=400,
                round_duration_ms=725,
                created_at=1_725_000_000.25,
            )
            self.assertTrue(writer.save(path))

            # Check the actual SQLite-backed reader, not only in-memory state.
            page, cursor, total = read_persisted_context_page(path)
            self.assertEqual((None, 1), (cursor, total))
            entry = page[0]
            self.assertEqual(
                {"input": 120, "cached": 75, "output": 30, "reasoning": 9, "total": 150},
                entry.usage,
            )
            self.assertEqual(400, entry.model_duration_ms)
            self.assertEqual(725, entry.round_duration_ms)
            self.assertEqual(1_725_000_000.25, entry.created_at)

    def test_legacy_context_without_usage_fields_remains_readable(self) -> None:
        """Old JSON checkpoints get safe empty metadata defaults."""
        with TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.json"
            path.write_text(json.dumps({
                "compress_threshold": 1000,
                "messages": [{"role": "assistant", "timeline": 1, "content": "old"}],
            }), encoding="utf-8")
            handler = ContextHandlerLinear(_NoopCompactor())
            self.assertTrue(handler.load(path))
            entry = handler.messages[0]
            self.assertEqual({}, entry.usage)
            self.assertIsNone(entry.model_duration_ms)
            self.assertIsNone(entry.round_duration_ms)
            self.assertIsNone(entry.created_at)

    def test_graph_handler_forwards_usage_metadata_to_its_linear_store(self) -> None:
        """The default graph wrapper must not discard message observability."""
        from llmfetcher.graph_memory.handler import GraphContextHandler

        handler = GraphContextHandler(
            compacting_fetcher=_NoopCompactor(),
            graph_update_every=100,
        )
        handler.add_assistant_message(
            _assistant(),
            usage={"input": 120, "cached": 75, "output": 30, "reasoning": 9, "total": 150},
            model_duration_ms=400,
            round_duration_ms=725,
            created_at=1_725_000_000.25,
        )
        entry = handler.linear.messages[0]
        self.assertEqual(75, entry.usage["cached"])
        self.assertEqual(400, entry.model_duration_ms)
        self.assertEqual(725, entry.round_duration_ms)
        self.assertEqual(1_725_000_000.25, entry.created_at)

    def test_chat_projection_keeps_metadata_across_restart_and_page(self) -> None:
        """History API returns per-message data after Session reconstruction."""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            core = AngelusCore(state_root=root / "state")
            workspace = core.session_service.create("demo", "Demo", project)
            handler = ContextHandlerLinear(_NoopCompactor())
            handler.messages.append(LLMContext(
                role="assistant", timeline=1, content="reply",
                usage={"input": 120, "cached": 75, "output": 30, "reasoning": 9, "total": 150},
                model_duration_ms=400, round_duration_ms=725, created_at=1_725_000_000.25,
            ))
            handler._round = 1
            self.assertTrue(handler.save(workspace.state_path / "agents" / "coordinator" / "context.json"))

            restored = AngelusCore(state_root=root / "state")
            page = restored.console_service.messages("demo", "all", None, 1)
            self.assertFalse(page["has_more"])
            message = page["messages"][0]
            self.assertEqual("reply", message["content"])
            self.assertEqual(75, message["usage"]["cached"])
            self.assertEqual(400, message["model_duration_ms"])
            self.assertEqual(725, message["round_duration_ms"])
            self.assertEqual(1_725_000_000.25, message["created_at"])

    def test_usage_projection_includes_each_agent_not_only_session_total(self) -> None:
        """Usage inspector can distinguish a cache hit made by each Agent."""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            core = AngelusCore(state_root=root / "state")
            core.session_service.create("demo", "Demo", project)
            core.sessions.get("demo").swarm = _UsageSwarm()  # type: ignore[assignment]

            payload = core.console_service.usage("demo")
            self.assertEqual(185, payload["usage"]["total"])
            self.assertEqual(
                [
                    {"id": "coordinator", "usage": {"input": 120, "cached": 75, "output": 30, "reasoning": 9, "total": 150}},
                    {"id": "worker", "usage": {"input": 30, "cached": 15, "output": 5, "reasoning": 2, "total": 35}},
                ],
                payload["agents"],
            )


if __name__ == "__main__":
    unittest.main()
