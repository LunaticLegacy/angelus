from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from typing import Iterable, Optional, Protocol, Sequence, TypeAlias

from ..llm_types import LLMBackendConfig, LLMOutput
from ._tool_schemas import to_openai_tool_schemas
from .base import JSONValue, JSONObject, ToolDefinition, ToolSchemaDict, LLMBackendHandler


class _OpenVINOChatHistory(Protocol):
    def append(self, item: dict[str, JSONValue]) -> None: ...

    def set_tools(self, tools: Sequence[ToolSchemaDict]) -> None: ...

    def set_extra_context(self, extra_context: JSONValue) -> None: ...


class _OpenVINOTextsResult(Protocol):
    texts: Sequence[str]


class _OpenVINOTextResult(Protocol):
    text: str


class _StreamSentinel:
    pass


StreamQueueItem: TypeAlias = str | BaseException | _StreamSentinel
OpenVINOHistory: TypeAlias = _OpenVINOChatHistory | list[dict[str, JSONValue]]
OpenVINOGenerateInputs: TypeAlias = str | Sequence[str] | _OpenVINOChatHistory
OpenVINOGenerateResult: TypeAlias = str | _OpenVINOTextResult | _OpenVINOTextsResult


@dataclass
class _OpenVINOCompletionResponse:
    content: str
    raw: str = ""
    usage: JSONObject = field(default_factory=dict)
    stop_reason: Optional[str] = None


class OpenVINOHandler(LLMBackendHandler):
    provider_names = frozenset({"openvino"})

    def __init__(self, fetcher, backend: LLMBackendConfig) -> None:
        super().__init__(fetcher, backend)
        import openvino_genai as ov_genai

        model_path = backend.extra.get("model_path") or backend.api_url or backend.model
        device = backend.extra.get("device", "AUTO")
        pipeline_kwargs = dict(backend.extra.get("pipeline_kwargs") or {})
        pipeline_kwargs.update(dict(backend.extra.get("pipeline_config") or {}))
        self.ov_genai = ov_genai
        self.pipeline = ov_genai.LLMPipeline(
            model_path,
            device,
            **pipeline_kwargs,
        )

    def prepare_tools(
        self,
        tools: Optional[Sequence[ToolDefinition]],
    ) -> Optional[list[ToolSchemaDict]]:
        """Prepare tools for OpenVINO chat history/template consumption.
        当前的实现采用的仍然是 openai 的 tool schema，这个……可以改。
        """
        return to_openai_tool_schemas(tools)

    def build_chat_history(
        self,
        messages: list[dict[str, str]],
        tools: Optional[list[ToolSchemaDict]] = None,
    ) -> OpenVINOHistory:
        chat_history_cls = getattr(self.ov_genai, "ChatHistory", None)
        history: OpenVINOHistory = chat_history_cls() if chat_history_cls is not None else []

        append = getattr(history, "append", None)
        for message in messages:
            item = {
                "role": str(message.get("role", "")),
                "content": str(message.get("content", "")),
            }
            if append is not None:
                append(item)
            else:
                history.append(item)

        if tools and hasattr(history, "set_tools"):
            history.set_tools(tools)

        extra_context = self.backend.extra.get("extra_context")
        if extra_context and hasattr(history, "set_extra_context"):
            history.set_extra_context(extra_context)

        return history

    def generation_config(self, *, temperature: float, max_tokens: int) -> JSONObject:
        config = dict(self.backend.extra.get("generation_config") or {})
        config.setdefault("max_new_tokens", max_tokens)
        config.setdefault("temperature", temperature)
        config["do_sample"] = temperature > 0
        return config

    def result_text(self, result: OpenVINOGenerateResult) -> str:
        if isinstance(result, str):
            return result
        texts = self._read_field(result, "texts", None)
        if texts:
            return str(texts[0])
        text = self._read_field(result, "text", None)
        if text is not None:
            return str(text)
        return str(result)

    def create_completion(
        self,
        *,
        messages,
        temperature: float,
        max_tokens: int,
        stream: bool,
        tools=None,
    ):
        history = self.build_chat_history(messages, tools=tools)
        config = self.generation_config(temperature=temperature, max_tokens=max_tokens)
        if stream:
            return self.create_stream(history, config)
        result = self.call_generate(history, config)
        return _OpenVINOCompletionResponse(
            content=self.result_text(result),
            raw=result if isinstance(result, str) else self.result_text(result),
        )

    def call_generate(self, prompt_or_history: OpenVINOGenerateInputs, config: JSONObject) -> OpenVINOGenerateResult:
        return self.pipeline.generate(prompt_or_history, generation_config=config)

    def create_stream(
        self,
        prompt_or_history: OpenVINOGenerateInputs,
        config: JSONObject,
    ) -> Iterable[str]:
        items: queue.Queue[StreamQueueItem] = queue.Queue(maxsize=10)
        sentinel = _StreamSentinel()

        streaming_status = getattr(self.ov_genai, "StreamingStatus", None)
        running_status = getattr(streaming_status, "RUNNING", None) if streaming_status else None

        def streamer(text: str) -> int | None:
            if text:
                items.put(text if isinstance(text, str) else str(text), block=True)
            return running_status if running_status is not None else False

        def worker() -> None:
            try:
                self.pipeline.generate(prompt_or_history, config, streamer=streamer)
            except BaseException as exc:
                items.put(exc)
            finally:
                items.put(sentinel)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        while True:
            item = items.get()
            if item is sentinel:
                break
            if isinstance(item, BaseException):
                raise item
            yield item if isinstance(item, str) else str(item)

    def normalize_completion_response(self, response) -> LLMOutput:
        return LLMOutput(
            content=self._coerce_content_to_text(self._read_field(response, "content", response)),
            provider=self.backend.provider,
            backend_name=self.backend.name,
            model=self.backend.model,
            role="assistant",
            stop_reason=self._read_field(response, "stop_reason", None),
            usage=self.normalize_usage(self._read_field(response, "usage", None)),
        )

    def iter_stream_text(self, response, *, output_reasoning: bool) -> Iterable[str]:
        for chunk in response:
            if isinstance(chunk, str):
                if chunk:
                    yield chunk
            else:
                text = str(chunk)
                if text:
                    yield text
