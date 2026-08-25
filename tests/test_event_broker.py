"""Concurrency and overflow tests for the process-local SSE event broker."""

from __future__ import annotations

import threading
import time

from angelus.event_stream import EventBroker


def test_two_subscribers_receive_the_same_event() -> None:
    """Independent cursors observe one publication without competing."""
    broker = EventBroker()
    batches = []

    def consume() -> None:
        batches.append(broker.wait_after(0, timeout=1.0))

    threads = [threading.Thread(target=consume) for _ in range(2)]
    for thread in threads:
        thread.start()
    time.sleep(0.02)
    broker.publish({"event": "lifecycle"}, durable_offset=42)
    for thread in threads:
        thread.join(timeout=2)

    assert len(batches) == 2
    assert [batch.events[0].payload for batch in batches] == [
        {"event": "lifecycle"}, {"event": "lifecycle"},
    ]


def test_overflow_reports_gap_and_durable_watermark() -> None:
    """A slow cursor receives an explicit disk-recovery boundary."""
    broker = EventBroker(capacity=2, durable_offset=10)
    broker.publish({"event": "one"}, durable_offset=20)
    broker.publish({"event": "delta"})
    broker.publish({"event": "two"}, durable_offset=30)

    batch = broker.wait_after(0, timeout=0)

    assert batch.gap is True
    assert batch.latest_sequence == 3
    assert batch.durable_offset == 30


def test_idle_wait_does_not_wake_until_timeout() -> None:
    """An idle broker waits instead of producing a polling tick."""
    broker = EventBroker()
    started = time.monotonic()
    batch = broker.wait_after(0, timeout=0.05)

    assert batch.timed_out is True
    assert time.monotonic() - started >= 0.04
