"""Regression coverage for non-JSON provider failures in live SSE payloads."""

from __future__ import annotations

import json

from angelus.event_stream.sse import encode_sse_event


class _ProviderFailure(Exception):
    """Minimal exception type representing a provider callback failure."""


def test_encode_sse_event_normalizes_nested_exception_values() -> None:
    """Keep SSE subscribers alive when a live error is an exception instance."""
    encoded = encode_sse_event({"event": "lifecycle", "data": {"error": _ProviderFailure("offline")}})

    payload = json.loads(encoded.removeprefix("data: ").strip())
    assert payload["data"]["error"] == "_ProviderFailure: offline"
