"""Session-owned boundary that serializes replaceable execution attempts."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Generic, TypeVar

from llmfetcher.execution import ExecutionController

from ..execution_module import ExecutionAttempt, ExecutionSnapshot, ExecutionState


ResultT = TypeVar("ResultT")


class SessionExecutor(Generic[ResultT]):
    """Allocate replaceable attempts for one logical Session.

    Despite its historical module location, this is not a swarm registry and
    never owns another Session.  ``Session.execution`` owns exactly one of
    these objects, which retains the latest attempt for inspection/replay.
    """

    def __init__(self, session_id: str, root: Path) -> None:
        """Create an idle execution owner rooted in one Session directory.

        Args:
            session_id: Stable logical Session identifier written to attempts.
            root: Parent directory where attempt directories are created.
        """
        normalized = session_id.strip()
        if not normalized:
            raise ValueError("session_id must not be blank")
        # Normalized identity shared by synthetic idle snapshots and attempts.
        self.session_id = normalized
        # Session-owned durable parent; each attempt adds executions/<uuid>.
        self.root = root
        # Monotonic number that distinguishes retries within this process.
        self._attempt_number = 0
        # Latest attempt; retained after terminal completion for inspection.
        self._attempt: ExecutionAttempt[ResultT] | None = None
        # Serializes start/stop/snapshot against concurrent API callers.
        self._lock = threading.RLock()

    def start(self, operation: Callable[[ExecutionController], ResultT]) -> ExecutionAttempt[ResultT]:
        """Start one operation in its attempt's non-daemon worker thread.

        Args:
            operation: Callable receiving this attempt's unique controller.

        Raises:
            RuntimeError: If a prior attempt remains live.
        """
        with self._lock:
            if self._attempt is not None and self._attempt.snapshot().state in {
                ExecutionState.RUNNING, ExecutionState.STOPPING, ExecutionState.FORCE_STOPPING,
            }:
                raise RuntimeError(f"Executor {self.session_id!r} already has a live attempt")
            self._attempt_number += 1
            self._attempt = ExecutionAttempt(self.session_id, self._attempt_number, self.root)
            self._attempt.start(operation)
            return self._attempt

    def request_stop(self, *, force: bool = False, reason: str = "user_requested") -> ExecutionSnapshot:
        """Signal cancellation and return the immediately visible state.

        Args:
            force: Also set the terminal I/O cancellation event when true.

        Returns:
            Updated execution snapshot. Terminal executors are unchanged.
        """
        with self._lock:
            return self._attempt.request_stop(force=force, reason=reason) if self._attempt else self.snapshot()

    def wait(self, timeout: float | None = None) -> bool:
        """Wait for operation exit without joining its worker thread.

        Args:
            timeout: Maximum seconds to wait; ``None`` waits indefinitely.

        Returns:
            ``True`` when no attempt exists or the current attempt is terminal.
        """
        with self._lock:
            return self._attempt.wait(timeout) if self._attempt else True

    def snapshot(self) -> ExecutionSnapshot:
        """Return current attempt snapshot or a synthetic Session-idle snapshot."""
        with self._lock:
            return self._attempt.snapshot() if self._attempt else ExecutionSnapshot(
                self.session_id, None, self._attempt_number, ExecutionState.IDLE, None, None, None,
            )

    @property
    def result(self) -> ResultT | None:
        """Return only the successful worker result of the latest attempt."""
        """Return the completed operation result, or ``None`` before success."""
        with self._lock:
            return self._attempt.result if self._attempt else None

    @property
    def attempt(self) -> ExecutionAttempt[ResultT] | None:
        """Return current/latest attempt identity without creating a new one."""
        with self._lock:
            return self._attempt
