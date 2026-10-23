"""Regression coverage for lossless model-visible tool results."""
from __future__ import annotations

import unittest

from llmfetcher.context_handlers.linear import ContextHandlerLinear
from llmfetcher.llm_types import (
    AssistantTurnInput,
    TokenUsage,
    ToolCallInput,
    ToolResultInput,
)


class ToolResultPromptBudgetTests(unittest.TestCase):
    """Ensure historical tool output remains cache-stable across rounds."""

    def test_tool_results_are_not_truncated_or_rewritten(self) -> None:
        """Context reconstruction preserves a host-supplied result verbatim."""
        handler = ContextHandlerLinear(object(), max_context_threshold=10_000_000)
        historical = "h" * 50_000

        def add(call_id: str, tool_name: str, output: str) -> None:
            """Append one v2 assistant turn with its stored tool result."""
            handler.add_assistant_message(
                AssistantTurnInput(
                    content="",
                    reasoning="",
                    tool_calls=(
                        ToolCallInput(call_id=call_id, name=tool_name, arguments={}),
                    ),
                    usage=TokenUsage(),
                    model_duration_ms=None,
                    round_duration_ms=None,
                    created_at=None,
                ),
                [
                    ToolResultInput(
                        call_id=call_id,
                        tool_name=tool_name,
                        output=output,
                        images=(),
                        ok=True,
                        duration_ms=1,
                        created_at=None,
                    )
                ],
            )

        for index in range(1, 6):
            add(f"old-{index}", "shell", historical)
        add("latest", "plan_read", "Plan item frontend-agent-render saved as in_progress.")

        first_messages = [message.to_dict() for message in handler.build_messages()]
        first_tools = [message for message in first_messages if message["role"] == "tool"]
        second_messages = [message.to_dict() for message in handler.build_messages()]
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


if __name__ == "__main__": unittest.main()
