"""Coalescing durable buffer for high-frequency transport deltas.

``agent:stream_delta`` is too frequent to fsync per record and too valuable to
keep only in memory. This buffer appends to memory, flushes a batch on a short
interval or when the batch fills, and fsyncs the batch in one write. A hard
kill therefore loses at most one flush window instead of the whole in-flight
round, while terminal and interrupt paths flush synchronously.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path


class TraceBuffer:
    """Append transport deltas to one NDJSON file with bounded coalescing.

    Args:
        path: Destination NDJSON file, created on first flush.
        flush_interval: Seconds between background flushes.
        flush_at: Record count that forces an immediate flush.
    """

    def __init__(
        self,
        path: Path,
        *,
        flush_interval: float = 0.25,
        flush_at: int = 64,
    ) -> None:
        self._path = path
        self._flush_interval = flush_interval
        self._flush_at = max(1, flush_at)
        self._lock = threading.RLock()
        self._pending: list[dict[str, object]] = []
        self._sequence = 0
        self._last_committed_sequence = 0
        self._stop = threading.Event()
        self._closed = False
        self._error: BaseException | None = None
        self._thread: threading.Thread | None = None

    @property
    def last_committed_sequence(self) -> int:
        """Return the highest sequence already fsynced."""
        with self._lock:
            return self._last_committed_sequence

    @property
    def error(self) -> BaseException | None:
        """Return the first background flush failure instead of hiding it."""
        with self._lock:
            return self._error

    def append(self, record: dict[str, object]) -> None:
        """Buffer one record, flushing synchronously once the batch is full."""
        with self._lock:
            if self._closed:
                return
            self._sequence += 1
            entry = {
                **record,
                "stream_sequence": self._sequence,
                "stream_timestamp": time.time(),
            }
            self._pending.append(entry)
            if self._thread is None:
                # Start the flusher only when a delta actually exists, so idle
                # attempts never hold a timer thread.
                self._thread = threading.Thread(
                    target=self._run,
                    name=f"angelus-trace-{self._path.stem}",
                    daemon=True,
                )
                self._thread.start()
            if len(self._pending) >= self._flush_at:
                self._flush_locked()

    def flush(self) -> None:
        """Write and fsync every buffered record, raising on failure."""
        with self._lock:
            self._flush_locked()

    def close(self) -> None:
        """Flush the tail, stop the flusher, and surface any write failure."""
        with self._lock:
            if self._closed:
                return
            self._flush_locked()
            self._closed = True
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        with self._lock:
            if self._error is not None:
                raise RuntimeError("trace stream flush failed") from self._error

    def _run(self) -> None:
        """Flush on a fixed interval until closed."""
        while not self._stop.wait(self._flush_interval):
            with self._lock:
                try:
                    self._flush_locked()
                except OSError as exc:
                    self._error = exc

    def _flush_locked(self) -> None:
        """Write the pending batch as one NDJSON append and fsync it."""
        if not self._pending:
            return
        batch = self._pending
        self._pending = []
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._path.open("a", encoding="utf-8") as handle:
                for record in batch:
                    handle.write(
                        json.dumps(
                            record,
                            ensure_ascii=False,
                            separators=(",", ":"),
                            default=str,
                        )
                        + "\n"
                    )
                handle.flush()
                os.fsync(handle.fileno())
        except OSError:
            # Keep the records for the next attempt instead of dropping them.
            self._pending = batch + self._pending
            raise
        self._last_committed_sequence = int(batch[-1]["stream_sequence"])


__all__ = ["TraceBuffer"]
