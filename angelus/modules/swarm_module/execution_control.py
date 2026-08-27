"""Cooperative cancellation and steering control for one execution."""

from __future__ import annotations

import queue
import threading


class ExecutionControl:
    """Cancellation source supplied to every session execution operation.

    A normal stop is observed at an operation-defined safe boundary. A forced
    stop additionally sets ``force_stopped`` for model, tool, and transport
    adapters that can abandon blocking I/O. Arbitrary Python code must still
    cooperate or execute inside a killable external process.
    """

    def __init__(self) -> None:
        """Create fresh cooperative and terminal cancellation latches."""
        self._stopped = threading.Event()
        self._force_stopped = threading.Event()
        self._steers: queue.Queue[str] = queue.Queue()

    def should_stop(self) -> bool:
        """Return whether a cooperative or terminal stop was requested."""
        return self._stopped.is_set()

    @property
    def force_stopped(self) -> threading.Event:
        """Return the terminal event consumed by cancellable I/O adapters."""
        return self._force_stopped

    def request_stop(self) -> None:
        """Request a cooperative stop without discarding queued steering."""
        self._stopped.set()

    def request_force_stop(self) -> None:
        """Request terminal cancellation for every boundary using this control."""
        self._force_stopped.set()
        self._stopped.set()

    def steer(self, message: str) -> None:
        """Queue one non-empty steering instruction for a cooperative operation."""
        if message.strip():
            self._steers.put(message)

    def drain_steers(self) -> list[str]:
        """Return and consume queued steering instructions in FIFO order."""
        messages: list[str] = []
        while True:
            try:
                messages.append(self._steers.get_nowait())
            except queue.Empty:
                return messages
