"""Unified context-length estimation for history stats and previews.

One pure entry point estimates the wire length of a message/tool payload.
The character basis is the JSON serialization used by
``llmfetcher.context_handlers.linear``'s compaction estimator
(``len(json.dumps(x, ensure_ascii=False, default=str))``), and the token
proxy is the same ceiling division ``(characters + 3) // 4`` used by the
request-preview statistics. Real token usage stays on the usage ledger and
is deliberately not part of this estimator.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ContextLengthStats:
    """Character and token estimate for one message/tool-schema payload.

    Attributes:
        messages: Number of serializable message dicts in the input list.
        characters: Total serialized character length of the messages.
        tool_schemas: Number of tool-schema dicts supplied (0 when absent).
        tool_schema_characters: Total serialized character length of the
            tool schemas (0 when no schemas were supplied).
        estimated_tokens: Ceiling-divided token proxy for ``characters``
            only, matching ``(characters + 3) // 4``.
    """

    messages: int
    characters: int
    tool_schemas: int
    tool_schema_characters: int
    estimated_tokens: int


def estimate_context_length(
    messages: list[dict[str, Any]],
    tool_schemas: list[dict[str, Any]] | None = None,
) -> ContextLengthStats:
    """Estimate the serialized wire length of one provider message payload.

    Args:
        messages: Provider message dicts, usually in send order. Non-dict
            entries are skipped defensively so malformed checkpoints cannot
            break the estimator.
        tool_schemas: Optional tool definitions that travel with the request.
            When ``None`` the schema counts stay at zero.

    Returns:
        A frozen :class:`ContextLengthStats` with serialized character counts
        and the derived token estimate. ``estimated_tokens`` covers only the
        message characters; tool schemas are reported separately so callers
        decide whether to include them.
    """
    valid_messages = [item for item in messages if isinstance(item, dict)]
    characters = sum(
        len(json.dumps(item, ensure_ascii=False, default=str))
        for item in valid_messages
    )
    if tool_schemas is None:
        return ContextLengthStats(
            messages=len(valid_messages),
            characters=characters,
            tool_schemas=0,
            tool_schema_characters=0,
            estimated_tokens=(characters + 3) // 4,
        )
    valid_tools = [item for item in tool_schemas if isinstance(item, dict)]
    tool_characters = sum(
        len(json.dumps(item, ensure_ascii=False, default=str))
        for item in valid_tools
    )
    return ContextLengthStats(
        messages=len(valid_messages),
        characters=characters,
        tool_schemas=len(valid_tools),
        tool_schema_characters=tool_characters,
        estimated_tokens=(characters + 3) // 4,
    )
