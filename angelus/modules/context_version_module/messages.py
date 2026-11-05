"""Typed message and compacted-summary records for context revisions.

The revision document stores the same message projection the linear context
handler persists, but as dataclasses so the write and read schemas share one
definition.  ``ContextMessage`` mirrors ``LLMContext``; ``ContextCompactedMessage``
mirrors ``LLMContextCompacted``.  A revision's ``messages`` may contain the
compacted summary first, followed by the active transcript.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Mapping, cast

from llmfetcher.llm_types import (
    AssistantContextItem,
    ContextItem,
    ContextItemId,
    ContextSummaryItem,
    JsonObject,
    JsonValue,
    LLMContext,
    LLMContextCompacted,
    LLMToolCall,
    TokenUsage,
    ToolCallRecord,
    ToolInfo,
    ToolResultId,
    ToolResultRecord,
    UserContextItem,
)
from llmfetcher.multimodal import ImageReference

_IMAGE_DETAILS = {"auto", "low", "high"}


@dataclass(frozen=True)
class ContextImage:
    """One durable image reference attached to a message or tool result."""

    attachment_id: str
    media_type: str
    detail: Literal["auto", "low", "high"] = "auto"

    @classmethod
    def from_reference(cls, value: ImageReference) -> "ContextImage":
        """Decode one ``ImageReference`` TypedDict."""
        detail = value.get("detail", "auto")
        if detail not in _IMAGE_DETAILS:
            raise ValueError(f"unsupported image detail: {detail}")
        return cls(
            attachment_id=value["attachment_id"],
            media_type=value["media_type"],
            detail=cast('Literal["auto", "low", "high"]', detail),
        )

    def to_reference(self) -> ImageReference:
        """Encode the record back to the llmfetcher TypedDict."""
        return cast(
            "ImageReference",
            {
                "attachment_id": self.attachment_id,
                "media_type": self.media_type,
                "detail": self.detail,
            },
        )


@dataclass(frozen=True)
class ContextToolCall:
    """One tool invocation emitted by the model."""

    name: str
    arguments: JsonObject = field(default_factory=dict)
    call_id: str | None = None
    source: str | None = None

    @classmethod
    def from_call(cls, value: LLMToolCall) -> "ContextToolCall":
        """Decode one ``LLMToolCall``."""
        return cls(
            name=value.name,
            arguments=dict(value.arguments),
            call_id=value.call_id,
            source=value.source,
        )

    def to_call(self) -> LLMToolCall:
        """Encode the record back to ``LLMToolCall``."""
        return LLMToolCall(
            name=self.name,
            arguments=dict(self.arguments),
            call_id=self.call_id,
            source=self.source,
        )


@dataclass(frozen=True)
class ContextToolInfo:
    """A tool call paired with its execution result and image outputs."""

    call: ContextToolCall
    result: str | None = None
    images: tuple[ContextImage, ...] = ()

    @classmethod
    def from_tool_info(cls, value: ToolInfo) -> "ContextToolInfo":
        """Decode one ``ToolInfo``."""
        return cls(
            call=ContextToolCall.from_call(value.call),
            result=value.result,
            images=tuple(ContextImage.from_reference(image) for image in value.images),
        )

    def to_tool_info(self) -> ToolInfo:
        """Encode the record back to ``ToolInfo``."""
        return ToolInfo(
            call=self.call.to_call(),
            result=self.result,
            images=[image.to_reference() for image in self.images],
        )


@dataclass(frozen=True)
class ContextMessage:
    """One active transcript message, mirroring ``LLMContext``."""

    role: str
    timeline: int
    content: str
    content_reasoning: str = ""
    tool_calls: tuple[ContextToolInfo, ...] = ()
    tags: tuple[str, ...] = ()
    usage: dict[str, int] = field(default_factory=dict)
    model_duration_ms: int | None = None
    round_duration_ms: int | None = None
    created_at: float | None = None
    images: tuple[ContextImage, ...] = ()

    @classmethod
    def from_context(cls, value: LLMContext) -> "ContextMessage":
        """Decode one ``LLMContext`` into the revision record."""
        return cls(
            role=value.role,
            timeline=value.timeline,
            content=value.content,
            content_reasoning=value.content_reasoning,
            tool_calls=tuple(
                ContextToolInfo.from_tool_info(info) for info in value.tool_calls
            ),
            tags=tuple(value.tags),
            usage=dict(value.usage),
            model_duration_ms=value.model_duration_ms,
            round_duration_ms=value.round_duration_ms,
            created_at=value.created_at,
            images=tuple(
                ContextImage.from_reference(image) for image in value.images
            ),
        )

    def to_context(self) -> LLMContext:
        """Encode the record back to ``LLMContext``."""
        return LLMContext(
            role=self.role,
            timeline=self.timeline,
            content=self.content,
            content_reasoning=self.content_reasoning,
            tool_calls=[info.to_tool_info() for info in self.tool_calls],
            tags=list(self.tags),
            usage=dict(self.usage),
            model_duration_ms=self.model_duration_ms,
            round_duration_ms=self.round_duration_ms,
            created_at=self.created_at,
            images=[image.to_reference() for image in self.images],
        )

    @classmethod
    def from_item(
        cls,
        value: ContextItem,
        results: Mapping[str, ToolResultRecord],
    ) -> "ContextEntry":
        """Decode one v2 context item into the revision projection."""
        match value.kind:
            case "user":
                return cls(
                    role="user",
                    timeline=value.timeline,
                    content=value.content,
                    images=tuple(
                        ContextImage.from_reference(image) for image in value.images
                    ),
                )
            case "assistant":
                tool_calls: list[ContextToolInfo] = []
                for call in value.tool_calls:
                    result = (
                        results.get(call.result_id.value)
                        if call.result_id is not None
                        else None
                    )
                    tool_calls.append(ContextToolInfo(
                        call=ContextToolCall(
                            name=call.name,
                            arguments=dict(call.arguments),
                            call_id=call.call_id,
                        ),
                        result=result.output if result is not None else None,
                        images=tuple(
                            ContextImage.from_reference(image)
                            for image in (result.images if result is not None else ())
                        ),
                    ))
                return cls(
                    role="assistant",
                    timeline=value.timeline,
                    content=value.content,
                    content_reasoning=value.reasoning,
                    tool_calls=tuple(tool_calls),
                    usage={
                        "input_tokens": value.usage.input_tokens,
                        "output_tokens": value.usage.output_tokens,
                        "total_tokens": value.usage.total_tokens,
                        "cached_tokens": value.usage.cached_tokens,
                        "reasoning_tokens": value.usage.reasoning_tokens,
                    },
                    model_duration_ms=value.model_duration_ms,
                    round_duration_ms=value.round_duration_ms,
                    created_at=value.created_at,
                )
            case "summary":
                return ContextCompactedMessage.from_summary(value)
            case _:
                raise ValueError(f"unsupported context item kind: {value.kind!r}")

    def to_item_with_results(self) -> tuple[ContextItem, list[ToolResultRecord]]:
        """Rebuild one v2 item plus the result rows its calls reference."""
        if self.role == "user":
            return UserContextItem(
                item_id=ContextItemId.new(),
                timeline=self.timeline,
                content=self.content,
                images=tuple(image.to_reference() for image in self.images),
            ), []
        if self.role != "assistant":
            raise ValueError(f"unsupported revision role: {self.role!r}")
        calls: list[ToolCallRecord] = []
        records: list[ToolResultRecord] = []
        for info in self.tool_calls:
            call_id = info.call.call_id
            if not call_id:
                raise ValueError("revision tool call is missing call_id")
            result_id = None
            if info.result is not None:
                result_id = ToolResultId.new()
                records.append(ToolResultRecord(
                    result_id=result_id,
                    call_id=call_id,
                    tool_name=info.call.name,
                    output=info.result,
                    images=tuple(image.to_reference() for image in info.images),
                    ok=None,
                    duration_ms=None,
                    created_at=None,
                ))
            calls.append(ToolCallRecord(
                call_id=call_id,
                name=info.call.name,
                arguments=dict(info.call.arguments),
                result_id=result_id,
            ))
        return AssistantContextItem(
            item_id=ContextItemId.new(),
            timeline=self.timeline,
            content=self.content,
            reasoning=self.content_reasoning,
            tool_calls=tuple(calls),
            usage=TokenUsage(
                input_tokens=int(self.usage.get("input_tokens", 0)),
                output_tokens=int(self.usage.get("output_tokens", 0)),
                total_tokens=int(self.usage.get("total_tokens", 0)),
                cached_tokens=int(self.usage.get("cached_tokens", 0)),
                reasoning_tokens=int(self.usage.get("reasoning_tokens", 0)),
            ),
            model_duration_ms=self.model_duration_ms,
            round_duration_ms=self.round_duration_ms,
            created_at=self.created_at,
        ), records


@dataclass(frozen=True)
class ContextCompactedMessage:
    """One compacted summary, mirroring ``LLMContextCompacted``."""

    abstract_msg: str
    source_timeline: tuple[int, ...] = ()
    source_uuid: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()

    @classmethod
    def from_context(cls, value: LLMContextCompacted) -> "ContextCompactedMessage":
        """Decode one ``LLMContextCompacted``."""
        return cls(
            abstract_msg=value.abstract_msg,
            source_timeline=tuple(value.source_timeline),
            source_uuid=tuple(value.source_uuid),
            tags=tuple(value.tags),
        )

    def to_context(self) -> LLMContextCompacted:
        """Encode the record back to ``LLMContextCompacted``."""
        return LLMContextCompacted(
            abstract_msg=self.abstract_msg,
            source_timeline=list(self.source_timeline),
            source_uuid=list(self.source_uuid),
            tags=list(self.tags),
        )

    @classmethod
    def from_summary(cls, value: ContextSummaryItem) -> "ContextCompactedMessage":
        """Decode one v2 summary item into the revision projection."""
        return cls(
            abstract_msg=value.abstract,
            source_timeline=tuple(value.source_timeline),
            source_uuid=tuple(item.value for item in value.source_item_ids),
        )

    def to_summary(self) -> ContextSummaryItem:
        """Encode the revision summary back to a v2 context item."""
        return ContextSummaryItem(
            item_id=ContextItemId.new(),
            timeline=0,
            abstract=self.abstract_msg,
            source_item_ids=tuple(
                ContextItemId(value) for value in self.source_uuid
            ),
            source_timeline=self.source_timeline,
            source_result_ids=(),
        )


ContextEntry = ContextMessage | ContextCompactedMessage

__all__ = [
    "ContextCompactedMessage",
    "ContextEntry",
    "ContextImage",
    "ContextMessage",
    "ContextToolCall",
    "ContextToolInfo",
]
