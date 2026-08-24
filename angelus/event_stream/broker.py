"""Bounded multi-subscriber event broadcast for one active browser run."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import threading
from typing import Any


@dataclass(frozen=True)
class EventEnvelope:
    """One live event and its optional durable-log commit position.

    Attributes:
        sequence: Monotonic process-local broadcast sequence.
        payload: Browser-compatible event object.
        durable_offset: Byte offset immediately after the committed NDJSON
            record, or ``None`` for live-only stream fragments.
    """

    sequence: int
    payload: dict[str, Any]
    durable_offset: int | None = None


@dataclass(frozen=True)
class BrokerSnapshot:
    """Atomic handoff watermark captured before historical disk replay."""

    sequence: int
    durable_offset: int
    closed: bool


@dataclass(frozen=True)
class BrokerBatch:
    """Events available after one subscriber cursor and broker state."""

    events: tuple[EventEnvelope, ...]
    latest_sequence: int
    durable_offset: int
    gap: bool
    closed: bool
    timed_out: bool


class EventBroker:
    """Broadcast a bounded event history to independent SSE subscribers.

    Args:
        capacity: Maximum number of live envelopes retained for slow clients.
        durable_offset: Existing log size forming the initial commit watermark.

    Slow subscribers detect a sequence gap and recover durable records from
    disk. Ephemeral fragments are intentionally best effort across such gaps.
    """

    def __init__(self, capacity: int = 2048, durable_offset: int = 0) -> None:
        """Initialize an open broker with a bounded empty event ring.

        Args:
            capacity: Maximum envelopes retained for subscriber replay.
            durable_offset: Existing event-log byte length used as the first
                committed watermark.

        Raises:
            ValueError: If ``capacity`` is not positive.
        """
        if capacity <= 0:
            raise ValueError("capacity must be greater than zero")
        self.capacity = capacity
        self._events: deque[EventEnvelope] = deque(maxlen=capacity)
        self._condition = threading.Condition()
        self._next_sequence = 1
        self._durable_offset = max(0, durable_offset)
        self._closed = False

    def publish(
        self, payload: dict[str, Any], *, durable_offset: int | None = None,
    ) -> EventEnvelope:
        """Publish one event and wake every subscriber.

        Args:
            payload: Event object copied before storage in the ring.
            durable_offset: End byte offset returned after a durable append.

        Returns:
            The immutable envelope placed in the broadcast ring.

        Raises:
            RuntimeError: If publication is attempted after broker closure.
        """
        with self._condition:
            if self._closed:
                raise RuntimeError("event broker is closed")
            envelope = EventEnvelope(
                self._next_sequence, dict(payload), durable_offset,
            )
            self._next_sequence += 1
            self._events.append(envelope)
            if durable_offset is not None:
                self._durable_offset = max(self._durable_offset, durable_offset)
            self._condition.notify_all()
            return envelope

    def snapshot(self) -> BrokerSnapshot:
        """Return the current sequence and durable handoff watermark."""
        with self._condition:
            return BrokerSnapshot(
                self._next_sequence - 1, self._durable_offset, self._closed,
            )

    def wait_after(self, sequence: int, timeout: float) -> BrokerBatch:
        """Wait for and return events newer than one subscriber sequence.

        Args:
            sequence: Last process-local sequence consumed by the subscriber.
            timeout: Maximum seconds to wait before returning a keepalive tick.

        Returns:
            Available envelopes plus gap, closure, and timeout state captured
            under the same condition lock.
        """
        with self._condition:
            if self._next_sequence - 1 <= sequence and not self._closed:
                self._condition.wait_for(
                    lambda: self._next_sequence - 1 > sequence or self._closed,
                    timeout=max(0.0, timeout),
                )
            latest = self._next_sequence - 1
            oldest = self._events[0].sequence if self._events else self._next_sequence
            gap = sequence < oldest - 1
            events = tuple(event for event in self._events if event.sequence > sequence)
            return BrokerBatch(
                events=events,
                latest_sequence=latest,
                durable_offset=self._durable_offset,
                gap=gap,
                closed=self._closed,
                timed_out=latest <= sequence and not self._closed,
            )

    def close(self) -> None:
        """Close the broker and wake all waiting subscribers."""
        with self._condition:
            self._closed = True
            self._condition.notify_all()
