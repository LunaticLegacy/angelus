"""Commit durable run events before broadcasting them to live clients."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..classes.active_run import ActiveRun


def publish_durable_event(
    active: ActiveRun | None,
    workspace_id: str,
    session_id: str,
    payload: dict[str, Any],
) -> int:
    """Append, fsync, then broadcast one durable browser event.

    Args:
        active: Live run broker, or ``None`` for audit-only producers.
        workspace_id: Storage partition owning the session log.
        session_id: Browser-stable session identity.
        payload: JSON-compatible browser event.

    Returns:
        Byte offset immediately after the committed NDJSON record.
    """
    # Import lazily so ActiveRun can own EventBroker without creating a
    # storage -> classes -> event_stream package initialization cycle.
    from ..storage import _append_session_event

    durable_offset = _append_session_event(workspace_id, session_id, payload)
    if active is not None:
        active.event_broker.publish(payload, durable_offset=durable_offset)
    return durable_offset
