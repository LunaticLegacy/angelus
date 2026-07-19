"""Offline regression tests for bounded linear-context compaction."""

from __future__ import annotations

import unittest
from typing import Any

from llmfetcher.context_handlers.linear import (
    _COMPACTION_INPUT_CHAR_LIMIT,
    _COMPACTION_OUTPUT_MAX_TOKENS,
    _TOOL_RESULT_MAX_CHARS,
    ContextHandlerLinear,
)
from llmfetcher.llm_types import LLMOutput, LLMToolCall


class _RecordingCompactor:
    """Fake fetcher that records a compaction request without an LLM call."""

    def __init__(self) -> None:
        """Initialize storage for the latest compaction keyword arguments."""
        self.request: dict[str, Any] = {}

    def fetch(
        self,
        msg: str,
        system_prompt: str | None = None,
        temperature: float = 0.4,
        max_tokens: int = 4096,
        context_handler: Any = None,
        backend_name: str | None = None,
        tools: Any = None,
    ) -> LLMOutput:
        """Record the request and return a valid compacted-context payload.

        Args:
            msg: Text supplied to the compactor.
            system_prompt: System instruction for compaction.
            temperature: Sampling temperature requested by the handler.
            max_tokens: Response budget requested by the handler.
            context_handler: Must be ``None`` for standalone compaction.
            backend_name: Optional backend selector.
            tools: Optional tool definitions, unused during compaction.

        Returns:
            Synthetic response in the expected XML-like output format.
        """
        self.request = {
            "msg": msg,
            "system_prompt": system_prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "context_handler": context_handler,
            "backend_name": backend_name,
            "tools": tools,
        }
        return LLMOutput(
            content=(
                "<context_abstract>bounded summary</context_abstract>\n"
                "<source_timelines>[1, 2]</source_timelines>"
            ),
            provider="test",
            backend_name="test",
            model="test",
        )


class ContextCompactionTests(unittest.TestCase):
    """Verify oversized tool output cannot inflate a compaction request."""

    def test_compaction_uses_bounded_stateless_request(self) -> None:
        """Compact a large tool result without using full history as context."""
        compactor = _RecordingCompactor()
        handler = ContextHandlerLinear(compactor, max_context_threshold=1)
        handler.add_user_message("inspect one large command result")
        output = LLMOutput(
            content="tool result follows",
            provider="test",
            backend_name="test",
            model="test",
            tool_calls=[LLMToolCall(name="shell", call_id="call-1")],
        )

        handler.add_assistant_message(
            output,
            tool_results={"call-1": "x" * (_TOOL_RESULT_MAX_CHARS * 3)},
        )

        self.assertIsNone(compactor.request["context_handler"])
        self.assertEqual(compactor.request["max_tokens"], _COMPACTION_OUTPUT_MAX_TOKENS)
        self.assertLessEqual(
            len(compactor.request["msg"]),
            _COMPACTION_INPUT_CHAR_LIMIT + 200,
        )
        self.assertIsNotNone(handler.abstract)
        assert handler.abstract is not None
        self.assertEqual(handler.abstract.abstract_msg, "bounded summary")

    def test_tool_result_is_bounded_before_history_storage(self) -> None:
        """Retain a truncation marker instead of an unbounded shell transcript."""
        compactor = _RecordingCompactor()
        handler = ContextHandlerLinear(compactor, max_context_threshold=10**9)
        output = LLMOutput(
            content="tool result follows",
            provider="test",
            backend_name="test",
            model="test",
            tool_calls=[LLMToolCall(name="shell", call_id="call-1")],
        )

        handler.add_assistant_message(
            output,
            tool_results={"call-1": "x" * (_TOOL_RESULT_MAX_CHARS + 1)},
        )

        stored_result = handler.messages[-1].tool_calls[0].result
        self.assertIsNotNone(stored_result)
        assert stored_result is not None
        self.assertIn("[tool result truncated;", stored_result)
        self.assertLessEqual(len(stored_result), _TOOL_RESULT_MAX_CHARS + 100)


if __name__ == "__main__":
    unittest.main()
