"""Regression coverage for lossless model-visible tool results."""
from __future__ import annotations

import unittest

from llmfetcher.context_handlers.linear import ContextHandlerLinear
from llmfetcher.llm_types import LLMContext, LLMToolCall, ToolInfo


class ToolResultPromptBudgetTests(unittest.TestCase):
    """Ensure historical tool output remains cache-stable across rounds."""

    def test_tool_results_are_not_truncated_or_rewritten(self) -> None:
        """Context reconstruction preserves a host-supplied result verbatim."""
        handler = ContextHandlerLinear(object(), max_context_threshold=10_000_000)
        historical = "h" * 50_000
        handler.messages = [
            LLMContext(
                role="assistant",
                timeline=index,
                content="",
                tool_calls=[ToolInfo(
                    call=LLMToolCall(name="shell", call_id=f"old-{index}"),
                    result=historical,
                )],
            )
            for index in range(1, 6)
        ]
        handler.messages.append(LLMContext(
            role="assistant",
            timeline=6,
            content="",
            tool_calls=[ToolInfo(
                call=LLMToolCall(name="plan_read", call_id="latest"),
                result="Plan item frontend-agent-render saved as in_progress.",
            )],
        ))

        first_messages = handler.build_messages()
        first_tools = [message for message in first_messages if message["role"] == "tool"]
        second_messages = handler.build_messages()
        tool_messages = [message for message in second_messages if message["role"] == "tool"]

        self.assertEqual(
            tool_messages[-1]["content"],
            "Plan item frontend-agent-render saved as in_progress.",
        )
        self.assertEqual(len(tool_messages), 6)
        self.assertEqual(
            [item["content"] for item in first_tools],
            [item["content"] for item in tool_messages],
        )
        self.assertTrue(all(
            "Historical tool result omitted" not in item["content"]
            for item in tool_messages[:-1]
        ))
        self.assertEqual(historical, tool_messages[0]["content"])
