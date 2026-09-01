"""Regression coverage for model-visible tool-result budgeting."""
from __future__ import annotations

import unittest

from llmfetcher.context_handlers.linear import ContextHandlerLinear
from llmfetcher.llm_types import LLMContext, LLMToolCall, ToolInfo


class ToolResultPromptBudgetTests(unittest.TestCase):
    """Ensure immediate tool feedback wins over historical output."""

    def test_newest_tool_result_survives_historical_budget_exhaustion(self) -> None:
        """Keep the latest result visible while marking older output omitted."""
        handler = ContextHandlerLinear(object(), max_context_threshold=10_000_000)
        historical = "h" * 24_000
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

        messages = handler.build_messages()
        tool_messages = [message for message in messages if message["role"] == "tool"]

        self.assertEqual(
            tool_messages[-1]["content"],
            "Plan item frontend-agent-render saved as in_progress.",
        )
        self.assertIn("Historical tool result omitted", tool_messages[0]["content"])

