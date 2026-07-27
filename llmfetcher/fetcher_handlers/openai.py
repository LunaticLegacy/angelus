from __future__ import annotations

import json
from typing import Any, Iterable, Mapping, Optional, Sequence, List

from ..llm_types import LLMOutput, LLMToolCall, Tool
from ._tool_schemas import to_openai_tool_schemas
from .base import LLMBackendHandler, ToolDefinition, ToolSchemaDict


class OpenAIHandler(LLMBackendHandler):
    provider_names = frozenset({"openai"})

    def __init__(self, fetcher, backend):
        super().__init__(fetcher, backend)
        import openai
        self.client = openai.OpenAI(
            api_key=backend.api_key,
            base_url=backend.api_url,
        )

    @staticmethod
    def _normalize_messages(
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Convert backend-neutral ``tool_calls`` to OpenAI format.

        The context handler emits flat tool-call dicts
        (``{"id", "name", "arguments"}``).  OpenAI's API requires
        ``{"type": "function", "function": {"name": ..., "arguments": "..."}}``.
        """
        out: list[dict[str, Any]] = []
        for msg in messages:
            tc = msg.get("tool_calls")
            if tc and isinstance(tc, list):
                normalized: list[dict[str, Any]] = []
                for call in tc:
                    normalized.append({
                        "id": call.get("id", ""),
                        "type": "function",
                        "function": {
                            "name": call.get("name", ""),
                            "arguments": json.dumps(
                                call.get("arguments", {}),
                                ensure_ascii=False,
                            ),
                        },
                    })
                msg = {**msg, "tool_calls": normalized}
            out.append(msg)
        return out

    def prepare_tools(
        self,
        tools: Optional[Sequence[ToolDefinition]],
    ) -> Optional[list[ToolSchemaDict]]:
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
        streamed_tool_calls: dict[int, dict[str, Any]] = {}

        def _read_tool_call_field(raw_call: object | Mapping[str, Any] | None, name: str, default: Any = None) -> Any:
            if isinstance(raw_call, dict):
                return raw_call.get(name, default)
            return getattr(raw_call, name, default)

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
                raw_tool_calls = delta.get("tool_calls") or []
            else:
                reasoning = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None) or getattr(delta, "thinking", None)
                content = getattr(delta, "content", None) or getattr(delta, "text", None)
                raw_tool_calls = getattr(delta, "tool_calls", None) or []

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

            for raw_call in raw_tool_calls:
                index = _read_tool_call_field(raw_call, "index", None)
                if index is None:
                    index = len(streamed_tool_calls)
                function = _read_tool_call_field(raw_call, "function", {}) or {}
                name = _read_tool_call_field(function, "name", "")
                entry = streamed_tool_calls.setdefault(
                    int(index),
                    {
                        "name": "",
                        "call_id": None,
                        "arguments_fragments": [],
                        "arguments_dict": None,
                    },
                )
                if name:
                    entry["name"] = str(name)
                if not entry["name"]:
                    continue
                call_id = _read_tool_call_field(raw_call, "id", None)
                if call_id:
                    entry["call_id"] = call_id

                raw_arguments = _read_tool_call_field(function, "arguments", None)
                if isinstance(raw_arguments, dict):
                    entry["arguments_dict"] = raw_arguments
                elif raw_arguments is not None:
                    entry["arguments_fragments"].append(str(raw_arguments))

        if in_thinking:
            yield "\n</think>\n"

        if streamed_tool_calls:
            for index in sorted(streamed_tool_calls):
                entry = streamed_tool_calls[index]
                raw_arguments = entry["arguments_dict"]
                if raw_arguments is None:
                    raw_arguments = "".join(entry["arguments_fragments"]).strip()
                arguments = self._parse_arguments(raw_arguments)
                payload = {
                    "name": entry["name"],
                    "arguments": arguments,
                }
                if entry["call_id"]:
                    payload["call_id"] = entry["call_id"]
                yield "\n<tool_call>\n"
                yield json.dumps(payload, ensure_ascii=False)
                yield "\n</tool_call>\n"
                
    def create_completion(
        self,
        *,
        messages,
        temperature: float,
        max_tokens: int,
        stream: bool,
        tools: List["Tool"] = None,
    ):
        messages = self._normalize_messages(messages)
        kwargs = {
            "model": self.backend.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream,
            "timeout": self.backend.timeout,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        kwargs.update(self.backend.extra)
        return self.client.chat.completions.create(**kwargs)

