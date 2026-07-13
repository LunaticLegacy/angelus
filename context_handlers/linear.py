from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import ContextHandler
from ..llm_types import (
    LLMContext,
    LLMContextCompacted,
    LLMOutput,
    ToolInfo,
)


class ContextHandlerLinear(ContextHandler):
    """A simple context handler that stores messages in a flat list.

    History is kept verbatim — no summarisation or compaction is applied.
    Tool calls are kept as structured ``ToolInfo`` objects; the backend
    handler is responsible for converting them to the provider-specific
    wire format.
    """

    def __init__(
        self,
        max_context_threshold: int = 262144,
    ) -> None:
        super().__init__()

        self.compress_threshold: int = max_context_threshold

        self.abstract: Optional[LLMContextCompacted] = None
        self.messages: List[LLMContext] = []

    # -- public API ---------------------------------------------------------

    def add_assistant_message(
        self,
        message: LLMOutput,
        timeline: int,
        tool_results: Optional[Dict[str, str]] = None,
    ) -> None:
        """Append an LLM output to the conversation history.

        Each tool call in *message* is paired with its result from
        *tool_results* (keyed by ``call_id``).
        """
        tool_calls: List[ToolInfo] = []
        for tc in message.tool_calls:
            call_id = tc.call_id
            result = tool_results.get(call_id) if tool_results else None
            tool_calls.append(ToolInfo(call=tc, result=result))

        self.messages.append(LLMContext(
            role=message.role,
            timeline=timeline,
            content=message.content,
            content_reasoning=message.reasoning_content,
            tool_calls=tool_calls,
        ))

    def get_prev_messages(self) -> List[LLMContext | LLMContextCompacted]:
        """Return the stored conversation history."""
        result: List[LLMContext | LLMContextCompacted] = list(self.messages)
        if self.abstract is not None:
            result.insert(0, self.abstract)
        return result

    def build_messages(self) -> List[Dict[str, Any]]:
        """Build context messages for an LLM request.

        Returns stored conversation history only — the caller
        (``LLMFetcher``) prepends the system prompt and appends the
        current user message.

        Tool call data uses a flat structure:
        ``{"id": ..., "name": ..., "arguments": {...}}`` — no
        provider-specific wrapping.

        Compacted context summaries (``LLMContextCompacted``) are
        emitted with ``role: "system"``.

        Returns:
            A list of message dicts.
        """
        messages: List[Dict[str, Any]] = []

        for item in self.get_prev_messages():
            if isinstance(item, LLMContext):
                self._append_context_messages(messages, item)
            elif isinstance(item, LLMContextCompacted):
                messages.append({
                    "role": "system",
                    "content": str(item),
                })

        return messages

    # -- internal helpers ---------------------------------------------------

    def _append_context_messages(
        self,
        messages: List[Dict[str, Any]],
        item: LLMContext,
    ) -> None:
        """Append backend-neutral messages for a single context entry.

        For assistant entries with tool calls this emits:
        1. An assistant message with ``tool_calls`` as a list of
           flat ``{"id", "name", "arguments"}`` dicts.
        2. A ``{"role": "tool", ...}`` message per tool call that has
           a result.

        Args:
            messages: The message list being built (mutated in place).
            item: The context entry to convert.
        """
        role = item.role
        content = item.content

        # Prepend reasoning block when present.
        if item.content_reasoning.strip():
            reasoning_block = (
                f"<think>\n{item.content_reasoning.strip()}\n</think>"
            )
            content = (
                f"{reasoning_block}\n{content}"
                if content
                else reasoning_block
            )

        # Assistant turn with tool calls.
        if role == "assistant" and item.tool_calls:
            messages.append({
                "role": "assistant",
                "content": content or None,
                "tool_calls": [
                    {
                        "id": ti.call.call_id or f"call_{i}",
                        "name": ti.call.name,
                        "arguments": ti.call.arguments,
                    }
                    for i, ti in enumerate(item.tool_calls)
                ],
            })
            for ti in item.tool_calls:
                if ti.result is not None:
                    call_id = ti.call.call_id or f"call_{id(ti)}"
                    messages.append({
                        "role": "tool",
                        "content": ti.result,
                        "tool_call_id": call_id,
                    })
            return

        messages.append({"role": role, "content": content or ""})
