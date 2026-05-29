from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional, Sequence

from ..llm_types import LLMOutput, LLMToolCall
from ._tool_schemas import to_openai_tool_schemas
from .base import LLMBackendHandler, ToolDefinition, ToolSchema


class OpenAICompatibleHandler(LLMBackendHandler):
    def prepare_tools(
        self,
        tools: Optional[Sequence[ToolDefinition]],
    ) -> Optional[list[ToolSchema]]:
        """Prepare tools for OpenAI-compatible chat-completion APIs."""
        return to_openai_tool_schemas(tools)

    def _normalize_openai_tool_calls(self, message: object | Mapping[str, Any] | None) -> list[LLMToolCall]:
        raw_calls = self._read_field(message, "tool_calls", None) or []
        calls: list[LLMToolCall] = []
        for raw_call in raw_calls:
            function = self._read_field(raw_call, "function", {}) or {}
            name = self._read_field(function, "name", "")
            if not name:
                continue
            calls.append(
                LLMToolCall(
                    name=str(name),
                    arguments=self._parse_arguments(self._read_field(function, "arguments", {})),
                    call_id=self._read_field(raw_call, "id", None),
                    source="openai_native",
                )
            )
        return calls

    def normalize_completion_response(self, response) -> LLMOutput:
        choices = self._read_field(response, "choices", None) or []
        choice = choices[0] if choices else None
        message = self._read_field(choice, "message", None) if choice is not None else None
        content = self._coerce_content_to_text(self._read_field(message, "content", None))
        reasoning = self._read_field(message, "reasoning_content", None)
        if reasoning is None:
            reasoning = self._read_field(message, "reasoning", "")

        return LLMOutput(
            content=content,
            provider=self.backend.provider,
            backend_name=self.backend.name,
            model=self.backend.model,
            role=self._read_field(message, "role", "assistant") or "assistant",
            reasoning_content=str(reasoning or ""),
            tool_calls=self._normalize_openai_tool_calls(message),
            stop_reason=self._read_field(choice, "finish_reason", None),
            usage=self.normalize_usage(self._read_field(response, "usage", None)),
        )

    def iter_stream_text(self, response, *, output_reasoning: bool) -> Iterable[str]:
        in_thinking = False
        for chunk in response:
            if isinstance(chunk, dict):
                choices = chunk.get("choices")
            else:
                choices = getattr(chunk, "choices", None)
            if not choices:
                continue

            first_choice = choices[0]
            if isinstance(first_choice, dict):
                delta = first_choice.get("delta")
            else:
                delta = getattr(first_choice, "delta", None)
            if delta is None:
                continue

            if isinstance(delta, dict):
                reasoning = delta.get("reasoning_content") or delta.get("reasoning") or delta.get("thinking")
                content = delta.get("content") or delta.get("text")
            else:
                reasoning = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None) or getattr(delta, "thinking", None)
                content = getattr(delta, "content", None) or getattr(delta, "text", None)

            if reasoning and output_reasoning:
                if not in_thinking:
                    yield "\n<think>\n"
                    in_thinking = True
                yield str(reasoning)

            if content:
                if in_thinking:
                    yield "\n</think>\n"
                    in_thinking = False
                yield str(content)

        if in_thinking:
            yield "\n</think>\n"
