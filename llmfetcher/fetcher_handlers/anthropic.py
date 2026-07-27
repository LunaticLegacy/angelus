from __future__ import annotations

import json
from typing import Iterable, Mapping, Optional, Sequence

from ..llm_types import LLMOutput, LLMToolCall
from ._tool_schemas import to_anthropic_tool_schemas
from .base import JSONValue, LLMBackendConfig, LLMBackendHandler, ToolDefinition, ToolSchemaDict


class AnthropicHandler(LLMBackendHandler):
    provider_names = frozenset({"anthropic"})

    def __init__(self, fetcher, backend: LLMBackendConfig) -> None:
        super().__init__(fetcher, backend)
        import anthropic

        client_kwargs = {
            "api_key": backend.api_key,
            "timeout": backend.timeout,
        }
        if backend.api_url:
            client_kwargs["base_url"] = backend.api_url
        self.client = anthropic.Anthropic(**client_kwargs)

    def convert_messages(self, messages: list[dict[str, str]]) -> tuple[list[dict[str, JSONValue]], Optional[str]]:
        anthropic_messages: list[dict[str, JSONValue]] = []
        system_message: Optional[str] = None

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "system":
                system_message = content
                continue
            if role == "tool":
                tool_call_id = msg.get("tool_call_id", "")
                anthropic_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_call_id,
                                "content": content,
                            }
                        ],
                    }
                )
            else:
                anthropic_messages.append({"role": role, "content": content})

        return anthropic_messages, system_message

    def prepare_tools(
        self,
        tools: Optional[Sequence[ToolDefinition]],
    ) -> Optional[list[ToolSchemaDict]]:
        """Prepare tools for Anthropic's `input_schema` tool format."""
        return to_anthropic_tool_schemas(tools)

    def _normalize_anthropic_blocks(
        self,
        blocks: Iterable[object | Mapping[str, JSONValue]],
    ) -> tuple[str, str, list[LLMToolCall]]:
        text_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_calls: list[LLMToolCall] = []

        for block in blocks:
            block_type = self._read_field(block, "type", None)
            if block_type == "text":
                text_parts.append(str(self._read_field(block, "text", "")))
            elif block_type in {"thinking", "reasoning"}:
                reasoning = self._read_field(block, "thinking", None)
                if reasoning is None:
                    reasoning = self._read_field(block, "text", "")
                reasoning_parts.append(str(reasoning))
            elif block_type == "tool_use":
                name = self._read_field(block, "name", "")
                if not name:
                    continue
                tool_calls.append(
                    LLMToolCall(
                        name=str(name),
                        arguments=self._parse_arguments(self._read_field(block, "input", {})),
                        call_id=self._read_field(block, "id", None),
                        source="anthropic",
                    )
                )

        return "".join(text_parts), "".join(reasoning_parts), tool_calls

    def create_completion(
        self,
        *,
        messages,
        temperature: float,
        max_tokens: int,
        stream: bool,
        tools=None,
    ):
        anthropic_messages, system_prompt = self.convert_messages(messages)
        kwargs = {
            "model": self.backend.model,
            "messages": anthropic_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if tools:
            kwargs["tools"] = tools
        kwargs.update(self.backend.extra)
        return self.client.messages.create(**kwargs)

    def normalize_completion_response(self, response) -> LLMOutput:
        blocks = self._read_field(response, "content", None) or []
        content, reasoning, tool_calls = self._normalize_anthropic_blocks(blocks)
        return LLMOutput(
            content=content,
            provider=self.backend.provider,
            backend_name=self.backend.name,
            model=self.backend.model,
            role=self._read_field(response, "role", "assistant") or "assistant",
            reasoning_content=reasoning,
            tool_calls=tool_calls,
            stop_reason=self._read_field(response, "stop_reason", None),
            usage=self.normalize_usage(self._read_field(response, "usage", None)),
        )

    def iter_stream_text(self, response, *, output_reasoning: bool) -> Iterable[str]:
        in_thinking = False
        streamed_tool_calls: dict[int, dict[str, object | None]] = {}

        def _read_tool_block_field(block: object | Mapping[str, JSONValue] | None, name: str, default: object | JSONValue | None = None):
            return self._read_field(block, name, default)

        def _merge_tool_call(
            index: int,
            *,
            call_id: object | JSONValue | None = None,
            name: object | JSONValue | None = None,
            input_payload: object | JSONValue | None = None,
        ) -> None:
            entry = streamed_tool_calls.setdefault(
                index,
                {
                    "name": "",
                    "call_id": None,
                    "input_dict": None,
                    "input_fragments": [],
                },
            )
            if name:
                entry["name"] = str(name).strip()
            if call_id:
                entry["call_id"] = str(call_id).strip() or None

            if isinstance(input_payload, dict):
                existing_dict = entry.get("input_dict")
                merged = dict(existing_dict) if isinstance(existing_dict, dict) else {}
                merged.update(input_payload)
                entry["input_dict"] = merged
            elif isinstance(input_payload, str) and input_payload.strip():
                fragments = entry.setdefault("input_fragments", [])
                if isinstance(fragments, list):
                    fragments.append(input_payload)

        for chunk in response:
            if isinstance(chunk, dict):
                event_type = chunk.get("type")
                delta = chunk.get("delta")
            else:
                event_type = getattr(chunk, "type", None)
                delta = getattr(chunk, "delta", None)
            
            match event_type:

                case "content_block_start":
                    block = chunk.get("content_block") if isinstance(chunk, dict) else getattr(chunk, "content_block", None)
                    block_type = self._read_field(block, "type", None)
                    if block_type == "text":
                        content = self._read_field(block, "text", None)
                        if in_thinking and content:
                            yield "\n</think>\n"
                            in_thinking = False
                        if content:
                            yield str(content)
                    elif block_type in {"thinking", "reasoning"} and output_reasoning:
                        reasoning = self._extract_reasoning(block)
                        if reasoning:
                            if not in_thinking:
                                yield "\n<think>\n"
                                in_thinking = True
                            yield reasoning
                    elif block_type == "tool_use":
                        index = self._read_field(chunk, "index", len(streamed_tool_calls))
                        _merge_tool_call(
                            int(index),
                            call_id=self._read_field(block, "id", None),
                            name=self._read_field(block, "name", None),
                            input_payload=self._read_field(block, "input", None),
                        )
                    continue

                case "content_block_delta":
                    delta_type = self._read_field(delta, "type", None)
                    if delta_type == "text_delta":
                        text = self._read_field(delta, "text", None)
                        if in_thinking and text:
                            yield "\n</think>\n"
                            in_thinking = False
                        if text:
                            yield str(text)
                    elif delta_type in {"thinking_delta", "reasoning_delta"} and output_reasoning:
                        reasoning = self._extract_reasoning(delta)
                        if reasoning:
                            if not in_thinking:
                                yield "\n<think>\n"
                                in_thinking = True
                            yield reasoning
                    elif delta_type in {"input_json_delta", "tool_use_delta", "input_json"}:
                        index = self._read_field(chunk, "index", None)
                        if index is None:
                            index = len(streamed_tool_calls)
                        payload = self._read_field(delta, "partial_json", None)
                        if payload is None:
                            payload = self._read_field(delta, "input", None)
                        _merge_tool_call(int(index), input_payload=payload)
                    continue

                case "text_delta":
                    content = self._extract_content(delta or chunk)
                    if in_thinking and content:
                        yield "\n</think>\n"
                        in_thinking = False
                    if content:
                        yield content
                    continue

            if event_type in {"thinking_delta", "reasoning_delta"} and output_reasoning:
                reasoning = self._extract_reasoning(delta or chunk)
                if reasoning:
                    if not in_thinking:
                        yield "\n<think>\n"
                        in_thinking = True
                    yield reasoning

        if in_thinking:
            yield "\n</think>\n"

        if streamed_tool_calls:
            for index in sorted(streamed_tool_calls):
                entry = streamed_tool_calls[index]
                name = str(entry.get("name", "") or "").strip()
                if not name:
                    continue
                raw_arguments = entry.get("input_dict")
                fragments = entry.get("input_fragments", [])
                if isinstance(raw_arguments, dict):
                    parsed_fragments: dict[str, object] = {}
                    if isinstance(fragments, list) and fragments:
                        payload = "".join(str(fragment) for fragment in fragments).strip()
                        if payload:
                            try:
                                parsed = json.loads(payload)
                            except json.JSONDecodeError:
                                parsed = {}
                            if isinstance(parsed, dict):
                                parsed_fragments.update(parsed)
                    if parsed_fragments:
                        merged = dict(raw_arguments)
                        merged.update(parsed_fragments)
                        raw_arguments = merged
                elif isinstance(fragments, list) and fragments:
                    raw_arguments = "".join(str(fragment) for fragment in fragments).strip()
                arguments = raw_arguments
                if isinstance(raw_arguments, str):
                    try:
                        parsed = json.loads(raw_arguments)
                    except json.JSONDecodeError:
                        parsed = {}
                    arguments = parsed if isinstance(parsed, dict) else {}
                elif not isinstance(raw_arguments, dict):
                    arguments = {}
                payload = {
                    "name": name,
                    "arguments": arguments,
                }
                call_id = entry.get("call_id")
                if call_id:
                    payload["call_id"] = call_id
                yield "\n<tool_call>\n"
                yield json.dumps(payload, ensure_ascii=False)
                yield "\n</tool_call>\n"
