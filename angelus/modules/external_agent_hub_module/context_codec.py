"""Strict decoding for the portable External Agent context envelope."""

from __future__ import annotations

from collections.abc import Mapping

from .models import ContextMessage, ContextPackage, ContextRole, ContextToolCall


def parse_context_package(payload: object) -> ContextPackage:
    """Decode one strict JSON-safe payload into a portable context package.

    Args:
        payload: Untrusted JSON body supplied by an HTTP caller.

    Returns:
        Typed context package with every accepted message normalized.

    Raises:
        ValueError: If a required field is absent, unknown, oversized, or has
            an incompatible primitive type.
    """
    if not isinstance(payload, Mapping):
        raise ValueError("context package body must be an object")
    allowed = {"format_version", "source", "source_session_id", "source_agent", "messages", "summary", "redactions"}
    unknown = sorted(str(key) for key in payload if key not in allowed)
    if unknown:
        raise ValueError(f"unknown context package fields: {', '.join(unknown)}")
    required = ("format_version", "source", "source_session_id", "source_agent", "messages")
    if any(key not in payload for key in required):
        raise ValueError("context package is missing required fields")
    version = payload["format_version"]
    if not isinstance(version, int) or isinstance(version, bool) or version != 1:
        raise ValueError("context package format_version must be 1")
    text_values = (payload["source"], payload["source_session_id"], payload["source_agent"])
    if any(not isinstance(value, str) or len(value) > 2_000 for value in text_values):
        raise ValueError("context package source fields must be strings of at most 2,000 characters")
    messages_raw = payload["messages"]
    if not isinstance(messages_raw, list) or len(messages_raw) > 200:
        raise ValueError("context package messages must contain from 0 through 200 records")
    summary = payload.get("summary", "")
    if not isinstance(summary, str) or len(summary) > 32_000:
        raise ValueError("context package summary must be a string of at most 32,000 characters")
    redactions_raw = payload.get("redactions", [])
    if not isinstance(redactions_raw, list) or any(not isinstance(value, str) or len(value) > 500 for value in redactions_raw):
        raise ValueError("context package redactions must be short strings")
    return ContextPackage(
        format_version=version,
        source=payload["source"],
        source_session_id=payload["source_session_id"],
        source_agent=payload["source_agent"],
        messages=tuple(_message(item) for item in messages_raw),
        summary=summary,
        redactions=tuple(redactions_raw),
    )


def _message(payload: object) -> ContextMessage:
    """Decode one strict context record from an untrusted JSON value.

    Args:
        payload: Candidate JSON object describing one context message.

    Returns:
        Typed normalized context message.

    Raises:
        ValueError: If a message field has an invalid type, role, or size.
    """
    if not isinstance(payload, Mapping):
        raise ValueError("every context message must be an object")
    allowed = {"sequence", "role", "content", "reasoning", "tool_calls", "created_at"}
    unknown = sorted(str(key) for key in payload if key not in allowed)
    if unknown:
        raise ValueError(f"unknown context message fields: {', '.join(unknown)}")
    sequence = payload.get("sequence")
    role = payload.get("role")
    content = payload.get("content")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
        raise ValueError("context message sequence must be a non-negative integer")
    if role not in {"system", "user", "assistant", "tool"}:
        raise ValueError("context message role is invalid")
    if not isinstance(content, str) or len(content) > 200_000:
        raise ValueError("context message content must be a string of at most 200,000 characters")
    reasoning = payload.get("reasoning", "")
    if not isinstance(reasoning, str) or len(reasoning) > 200_000:
        raise ValueError("context message reasoning must be a string of at most 200,000 characters")
    created_at = payload.get("created_at")
    if created_at is not None and (not isinstance(created_at, int) or isinstance(created_at, bool)):
        raise ValueError("context message created_at must be an integer or null")
    tools = payload.get("tool_calls", [])
    if not isinstance(tools, list) or len(tools) > 64:
        raise ValueError("context message tool_calls must contain at most 64 records")
    return ContextMessage(
        sequence=sequence,
        role=role,
        content=content,
        reasoning=reasoning,
        tool_calls=tuple(_tool(item) for item in tools),
        created_at=created_at,
    )


def _tool(payload: object) -> ContextToolCall:
    """Decode one non-executable historical tool record.

    Args:
        payload: Candidate JSON object describing a historical tool call.

    Returns:
        Typed non-executable tool record.

    Raises:
        ValueError: If a tool field is unknown, invalid, or oversized.
    """
    if not isinstance(payload, Mapping):
        raise ValueError("every context tool call must be an object")
    allowed = {"name", "arguments_json", "result"}
    unknown = sorted(str(key) for key in payload if key not in allowed)
    if unknown:
        raise ValueError(f"unknown context tool-call fields: {', '.join(unknown)}")
    values = (payload.get("name"), payload.get("arguments_json", ""), payload.get("result", ""))
    if any(not isinstance(value, str) or len(value) > 200_000 for value in values):
        raise ValueError("context tool-call fields must be strings of at most 200,000 characters")
    return ContextToolCall(*values)
