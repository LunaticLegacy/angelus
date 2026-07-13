from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import ClassVar, Iterable, Mapping, Optional, Protocol, Sequence, TYPE_CHECKING, TypeAlias, Type, Any

from ..llm_types import LLMBackendConfig, LLMOutput, TokenUsage, Tool

if TYPE_CHECKING:  # pragma: no cover - imported only for type checking
    from .openvino import OpenVINOGenerateResult, OpenVINOHistory
    from ..llm_fetcher import LLMFetcher


JSONValue: TypeAlias = str | int | float | bool | None | list["JSONValue"] | dict[str, "JSONValue"]
JSONObject: TypeAlias = dict[str, JSONValue]
ToolSchemaDict: TypeAlias = dict[str, JSONValue]
ToolDefinition: TypeAlias = Tool | ToolSchemaDict


class _UsageLike(Protocol):
    """
    A protocol for a usage object.
    """
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    input_tokens: int | None
    output_tokens: int | None

    def model_dump(self) -> JSONObject: ...


class LLMBackendHandler(ABC):
    """Base class for backend-specific request/response handlers."""

    # Names of providers handled by this handler
    provider_names: ClassVar[frozenset[str]] = frozenset()

    def __init__(
        self, 
        fetcher: "LLMFetcher", 
        backend: LLMBackendConfig
    ) -> None:
        """
        Creates a new handler instance.

        Args:
            fetcher: The LLMFetcher instance that owns this handler.
            backend: The configuration for the backend.
        """
        self.fetcher = fetcher
        self.backend = backend

    @classmethod
    def supports_backend(
        cls: Type["LLMBackendHandler"], 
        backend: LLMBackendConfig
    ) -> bool:
        """
        Args:
            cls: The class to check. Should be a subclass of `LLMBackendHandler`.
            backend: The backend configuration to check.
        """
        return backend.provider in cls.provider_names

    @classmethod
    def from_backend(
        cls: Type["LLMBackendHandler"], 
        fetcher: "LLMFetcher", 
        backend: LLMBackendConfig
    ) -> "LLMBackendHandler":
        """
        Create an instance from a backend config.

        Args:
            cls: The class to create. Should be a subclass of `LLMBackendHandler`.
            fetcher: The LLMFetcher instance.
            backend: The backend config.
        """
        return cls(fetcher, backend)

    @classmethod
    def _iter_descendants(cls) -> Iterable[type["LLMBackendHandler"]]:
        for subclass in cls.__subclasses__():
            yield subclass
            yield from subclass._iter_descendants()

    @classmethod
    def create_for_backend(
        cls,
        fetcher: "LLMFetcher",
        backend: LLMBackendConfig,
    ) -> "LLMBackendHandler":
        for handler_cls in cls._iter_descendants():
            if handler_cls.supports_backend(backend):
                return handler_cls.from_backend(fetcher, backend)
        raise ValueError(f"Unsupported provider: {backend.provider}")

    @abstractmethod
    def create_completion(
        self,
        *,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        stream: bool,
        tools: Optional[list[ToolSchemaDict]] = None,
    ) -> Any:
        raise NotImplementedError

    @abstractmethod
    def normalize_completion_response(self, response) -> LLMOutput:
        raise NotImplementedError

    @abstractmethod
    def iter_stream_text(self, response, *, output_reasoning: bool) -> Iterable[str]:
        raise NotImplementedError
    
    @abstractmethod
    def prepare_tools(
        self,
        tools: Optional[Sequence[ToolDefinition]],
    ) -> Optional[list[ToolSchemaDict]]:
        """
        Convert registry tools or prebuilt schemas into this provider's shape.

        Args:
            tools: Runtime tools as `Tool` objects, or already serialized schema
                dictionaries kept for compatibility with older callers.

        Returns:
            Provider-specific schema dictionaries, or `None` when no tools were
            supplied.
        """
        raise NotImplementedError

    def build_chat_history(
        self,
        messages: list[dict[str, str]],
        tools: Optional[list[ToolSchemaDict]] = None,
    ):
        return messages

    def generation_config(self, *, temperature: float, max_tokens: int) -> JSONObject:
        """
        Generate a JSON object for the LLM backend to use as a generation configuration.
        Optional for inhereting classes.
        """
        return {}

    def result_text(self, result) -> str:
        return str(result)
    
    def _read_field(
        self,
        value: object | Mapping[str, JSONValue] | None,
        name: str,
        default: object | JSONValue | None = None,
    ) -> object | JSONValue | None:
        """
        Read a field from a value.

        Args:
            value: The value to read from.
            name: The name of the field to read.
            default: The default value to return if the field is not found.
        """
        if isinstance(value, dict):
            return value.get(name, default)
        return getattr(value, name, default)

    def _coerce_content_to_text(
        self,
        content: str | Sequence[JSONValue] | object | None,
    ) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") == "text":
                        parts.append(str(part.get("text", "")))
                    elif "text" in part:
                        parts.append(str(part["text"]))
                else:
                    text = getattr(part, "text", None)
                    if text:
                        parts.append(str(text))
            return "".join(parts)
        return str(content)

    def _usage_to_dict(self, usage: _UsageLike | Mapping[str, JSONValue] | None) -> JSONObject:
        """
        Deprecated: use _normalize_usage() instead.
        Kept for subclasses that may override this method.
        """
        if usage is None:
            return {}
        if isinstance(usage, dict):
            return dict(usage)
        if hasattr(usage, "model_dump"):
            dumped = usage.model_dump()
            return dict(dumped) if isinstance(dumped, dict) else {}

        result: JSONObject = {}
        for name in (
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "input_tokens",
            "output_tokens",
        ):
            value = getattr(usage, name, None)
            if value is not None:
                result[name] = value
        return result

    def normalize_usage(self, usage: _UsageLike | Mapping[str, JSONValue] | None) -> TokenUsage:
        """Normalize a provider-specific usage response into a platform-irrelevant TokenUsage.

        Override this in each handler to handle provider-specific fields.
        The default implementation handles OpenAI-compatible and Anthropic-like dict shapes.
        """
        raw = self._usage_to_dict(usage)
        if not raw:
            return TokenUsage()

        # Flatten nested details (OpenAI: prompt_tokens_details.cached_tokens, etc.).
        for key, value in list(raw.items()):
            if isinstance(value, dict):
                for nested_key, nested_value in value.items():
                    if isinstance(nested_value, (int, float)):
                        raw[nested_key] = int(nested_value)

        return TokenUsage(
            input_tokens=int(raw.get("input_tokens", raw.get("prompt_tokens", 0)) or 0),
            output_tokens=int(raw.get("output_tokens", raw.get("completion_tokens", 0)) or 0),
            total_tokens=int(raw.get("total_tokens", 0) or 0),
            cached_tokens=int(
                raw.get("cached_tokens", raw.get("cache_read_input_tokens", 0)) or 0
                + raw.get("cache_creation_input_tokens", 0) or 0
            ),
            reasoning_tokens=int(raw.get("reasoning_tokens", 0) or 0),
        )

    def _parse_arguments(self, arguments: str | Mapping[str, JSONValue] | None) -> JSONObject:
        if isinstance(arguments, dict):
            return dict(arguments)
        if isinstance(arguments, str) and arguments.strip():
            try:
                parsed = json.loads(arguments)
            except json.JSONDecodeError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    def _extract_content(
        self,
        delta: object | Mapping[str, JSONValue] | None,
    ) -> Optional[str]:
        if delta is None:
            return None
        if isinstance(delta, dict):
            content = delta.get("content") or delta.get("text")
            return str(content) if content is not None else None
        content = getattr(delta, "content", None) or getattr(delta, "text", None)
        return str(content) if content is not None else None

    def _extract_reasoning(
        self,
        delta: object | Mapping[str, JSONValue] | None,
    ) -> Optional[str]:
        if delta is None:
            return None
        if isinstance(delta, dict):
            reasoning = delta.get("reasoning_content") or delta.get("reasoning") or delta.get("thinking")
            return str(reasoning) if reasoning is not None else None
        reasoning = (
            getattr(delta, "reasoning_content", None)
            or getattr(delta, "reasoning", None)
            or getattr(delta, "thinking", None)
        )
        return str(reasoning) if reasoning is not None else None
