"""Process-local broadcast primitives for durable browser run events."""

from .broker import BrokerBatch, BrokerSnapshot, EventBroker, EventEnvelope

__all__ = [
    "BrokerBatch",
    "BrokerSnapshot",
    "EventBroker",
    "EventEnvelope",
    "publish_durable_event",
    "encode_sse_event",
    "historical_event_stream",
    "live_event_stream",
]


def __getattr__(name: str):
    """Load storage-dependent helpers lazily to avoid class import cycles.

    Args:
        name: Public helper requested from the package namespace.

    Returns:
        The requested publisher or SSE helper.

    Raises:
        AttributeError: If ``name`` is not exported by this package.
    """
    if name == "publish_durable_event":
        from .publisher import publish_durable_event

        return publish_durable_event
    if name in {"encode_sse_event", "historical_event_stream", "live_event_stream"}:
        from . import sse

        return getattr(sse, name)
    raise AttributeError(name)
