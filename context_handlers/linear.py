from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .base import ContextHandler
from ..llm_types import (
    LLMContext,
    LLMContextCompacted,
    LLMOutput,
    LLMToolCall,
    ToolInfo,
)


class ContextHandlerLinear(ContextHandler):
    """A simple context handler that stores messages in a flat list.

    History is kept verbatim — no summarisation or compaction is applied.
    """

    def __init__(
        self,
        max_context_threshold: int = 262144,
    ) -> None:
        """Initialise the linear context handler.

        Args:
            max_context_threshold:
                When the accumulated context size exceeds this value,
                older messages are compacted into a single
                ``LLMContextCompacted`` entry.  Defaults to 256K.
        """
        super().__init__()

        self.compress_threshold: int = max_context_threshold

        self.abstract: Optional[LLMContextCompacted] = None
        self.messages: List[LLMContext] = []

    # -- public API ---------------------------------------------------------

    def add_assistant_message(
        self,
        message: LLMOutput,
        tool_results: Optional[Dict[str, str]] = None,
    ) -> None:
        """Append an LLM output to the conversation history.

        Each tool call in *message* is paired with its result from
        *tool_results* (keyed by ``call_id``).  Later, when messages are
        reconstructed via ``build_messages``, the assistant ``tool_calls``
        block and any available tool results are emitted as separate
        API turns.

        Args:
            message: The output from a previous LLM call.
            tool_results:
                Mapping from ``call_id`` to the execution result text.
                Calls without a result entry are stored without a result.
        """
        tool_calls: List[ToolInfo] = []
        for tc in message.tool_calls:
            call_id = tc.call_id
            result = tool_results.get(call_id) if tool_results else None
            tool_calls.append(ToolInfo(call=tc, result=result))

        self.messages.append(LLMContext(
            role=message.role,
            content=message.content,
            content_reasoning=message.reasoning_content,
            tool_calls=tool_calls,
        ))

    def get_prev_messages(self) -> List[LLMContext | LLMContextCompacted]:
        """Return the stored conversation history.

        Returns:
            The list of context entries accumulated so far.
        """
        result: List[LLMContext | LLMContextCompacted] = list(self.messages)
        if self.abstract is not None:
            result.insert(0, self.abstract)
        return result

    def build_messages(
        self,
        msg: str,
        system_prompt: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Build the complete message list for an LLM request.

        Combines the system prompt, stored conversation history, and the
        current user message into a list of dicts compatible with
        OpenAI-style chat completion APIs.

        Tool call history is expanded into two turns per entry:
        an assistant ``tool_calls`` message followed by ``{"role":
        "tool", ...}`` result messages for every call that has a result.

        Args:
            msg: The current user message text.
            system_prompt:
                Optional system-level instruction prepended to the message
                list.

        Returns:
            A list of message dicts (``{"role": ..., "content": ...}``),
            with ``tool_calls`` embedded where applicable.
        """
        messages: List[Dict[str, Any]] = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        for item in self.messages:
            self._append_context_messages(messages, item)

        if self.abstract is not None:
            messages.append({"role": "user", "content": str(self.abstract)})

        if msg:
            messages.append({"role": "user", "content": msg})

        return messages

    # -- internal helpers ---------------------------------------------------

    def _append_context_messages(
        self,
        messages: List[Dict[str, Any]],
        item: LLMContext,
    ) -> None:
        """Append API messages for a single ``LLMContext`` entry.

        For assistant entries with tool calls, this emits:
        1. An assistant ``tool_calls`` message.
        2. A ``{"role": "tool", ...}`` message for each call that has
           a result, preserving the original order.

        For all other entries a single ``{"role": ..., "content": ...}``
        message is appended.

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

        # Assistant turn with tool calls → emit tool_calls + results.
        if role == "assistant" and item.tool_calls:
            messages.append({
                "role": "assistant",
                "content": content or None,
                "tool_calls": _tool_calls_to_api_dicts(item.tool_calls),
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


def _tool_calls_to_api_dicts(
    tool_calls: List[ToolInfo],
) -> List[Dict[str, Any]]:
    """Convert ``ToolInfo`` objects to OpenAI API ``tool_calls`` dicts.

    Args:
        tool_calls: Structured tool call objects (each wrapping an
                    ``LLMToolCall``).

    Returns:
        A list of dicts in the standard API format
        (``{"id": ..., "type": "function", "function": {...}}``).
    """
    result: List[Dict[str, Any]] = []
    for index, ti in enumerate(tool_calls):
        call_id = ti.call.call_id or f"call_{index}"
        result.append({
            "id": call_id,
            "type": "function",
            "function": {
                "name": ti.call.name,
                "arguments": json.dumps(
                    ti.call.arguments, ensure_ascii=False
                ),
            },
        })
    return result
