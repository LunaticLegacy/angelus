"""SSE serialization and durable-to-live handoff generators."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Iterator

from ..storage import _read_session_event_records_from

if TYPE_CHECKING:
    from ..classes.active_run import ActiveRun


def _sse_json_fallback(value: Any) -> str:
    """Render unexpected live-only values without terminating an SSE stream.

    Args:
        value: Object rejected by the standard JSON encoder, commonly an
            exception captured by a provider or MCP lifecycle callback.

    Returns:
        A bounded type-prefixed text representation safe for the browser's
        trace view. Normal JSON values never reach this fallback.

    Side Effects:
        None. This function deliberately does not mutate the original payload
        because the event broker can have multiple simultaneous subscribers.
    """
    text = str(value)
    return f"{type(value).__name__}: {text}"[:4_000]


def encode_sse_event(
    payload: dict[str, Any], durable_offset: int | None = None,
) -> str:
    """Serialize one payload without advancing SSE IDs for live-only data.

    Args:
        payload: JSON-compatible event sent to the browser.
        durable_offset: End byte offset of its NDJSON record, or ``None`` for
            an ephemeral stream fragment.

    Returns:
        One complete Server-Sent Events record.
    """
    # Live callbacks can carry provider exceptions before their producer has
    # normalized an error field. Keep that one bad value from closing every
    # subscriber's stream while preserving ordinary nested JSON unchanged.
    data = f"data: {json.dumps(payload, ensure_ascii=False, default=_sse_json_fallback)}\n\n"
    return f"id: {durable_offset}\n{data}" if durable_offset is not None else data


def historical_event_stream(
    workspace_id: str, session_id: str, start_offset: int,
) -> Iterator[str]:
    """Replay durable records once for a session without a live worker.

    Args:
        workspace_id: Storage partition owning the durable event log.
        session_id: Browser-stable session identity.
        start_offset: Last durable byte offset already rendered by the client.

    Yields:
        Encoded durable SSE records in log order.
    """
    records, _ = _read_session_event_records_from(
        workspace_id, session_id, start_offset,
    )
    for payload, durable_offset in records:
        yield encode_sse_event(payload, durable_offset)


def live_event_stream(
    workspace_id: str,
    session_id: str,
    active: ActiveRun,
    start_offset: int,
    *,
    keepalive_timeout: float = 15.0,
) -> Iterator[str]:
    """Replay a durable snapshot, then consume event-driven broadcasts.

    Args:
        workspace_id: Storage partition owning the durable event log.
        session_id: Browser-stable session identity.
        active: Live run whose broker supplies post-handoff events.
        start_offset: Last durable byte offset already rendered by the client.
        keepalive_timeout: Idle seconds between SSE keepalive comments.

    Yields:
        Encoded durable, ephemeral, and keepalive SSE records in order.
    """
    active.event_broker.attach_subscriber()
    try:
        durable_offset = start_offset
        handoff = active.event_broker.snapshot()
        records, durable_offset = _read_session_event_records_from(
            workspace_id, session_id, durable_offset, handoff.durable_offset,
        )
        for payload, record_offset in records:
            yield encode_sse_event(payload, record_offset)
        sequence = handoff.sequence
        if handoff.closed:
            return

        while True:
            batch = active.event_broker.wait_after(
                sequence, timeout=keepalive_timeout,
            )
            if batch.gap:
                records, durable_offset = _read_session_event_records_from(
                    workspace_id, session_id, durable_offset, batch.durable_offset,
                )
                for payload, record_offset in records:
                    yield encode_sse_event(payload, record_offset)
                sequence = batch.latest_sequence
            else:
                for envelope in batch.events:
                    if envelope.durable_offset is None:
                        yield encode_sse_event(envelope.payload)
                    elif envelope.durable_offset > durable_offset:
                        yield encode_sse_event(envelope.payload, envelope.durable_offset)
                        durable_offset = envelope.durable_offset
                    sequence = envelope.sequence
            if batch.closed and sequence >= batch.latest_sequence:
                break
            if batch.timed_out:
                yield ": keepalive\n\n"
    finally:
        active.event_broker.detach_subscriber()
