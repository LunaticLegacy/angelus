"""Daemon-backed, session-scoped execution boundary."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Generic, TypeVar

from .execution_control import ExecutionControl
from .state import ExecutionSnapshot, ExecutionState


ResultT = TypeVar("ResultT")


class SessionExecutor(Generic[ResultT]):
    """Run one session operation with a stable cancellation control object.

    One executor allows one live operation. The operation receives an
    ``ExecutionControl`` and must pass it into each child execution boundary.
    This class owns lifecycle state and exception capture, not domain work.
    """

    def __init__(self, session_id: str) -> None:
        """Create an idle executor for one non-empty session identifier."""
        normalized = session_id.strip()
        if not normalized:
            raise ValueError("session_id must not be blank")
        self.session_id = normalized
        self.control = ExecutionControl()
        self._state = ExecutionState.IDLE
        self._started_at: float | None = None
        self._finished_at: float | None = None
        self._result: ResultT | None = None
        self._error: str | None = None
        self._done = threading.Event()
        self._lock = threading.RLock()

    def start(self, operation: Callable[[ExecutionControl], ResultT]) -> None:
        """Start one operation in a daemon thread.

        Args:
            operation: Callable receiving this executor's stable control.

        Raises:
            RuntimeError: If this executor is no longer idle.
        """
        with self._lock:
            if self._state is not ExecutionState.IDLE:
                raise RuntimeError(f"Executor {self.session_id!r} is not idle")
            self._state = ExecutionState.RUNNING
            self._started_at = time.time()
            self._done.clear()
        # The executor boundary must not block API control calls. The
        # operation is responsible for propagating the control into its work.
        threading.Thread(
            target=self._run_operation,
            args=(operation,),
            name=f"angelus-session-{self.session_id}",
            daemon=True,
        ).start()

    def _run_operation(self, operation: Callable[[ExecutionControl], ResultT]) -> None:
        """Capture terminal result/state without leaking worker exceptions."""
        try:
            result = operation(self.control)
        except BaseException as exc:
            with self._lock:
                self._error = f"{type(exc).__name__}: {exc}"
                self._state = ExecutionState.STOPPED if self.control.should_stop() else ExecutionState.FAILED
        else:
            with self._lock:
                self._result = result
                self._state = ExecutionState.STOPPED if self.control.should_stop() else ExecutionState.COMPLETED
        finally:
            with self._lock:
                self._finished_at = time.time()
            self._done.set()

    def request_stop(self, *, force: bool = False) -> ExecutionSnapshot:
        """Signal cancellation and return the immediately visible state.

        Args:
            force: Also set the terminal I/O cancellation event when true.

        Returns:
            Updated execution snapshot. Terminal executors are unchanged.
        """
        with self._lock:
            if self._state is not ExecutionState.RUNNING:
                return self.snapshot()
            if force:
                self.control.request_force_stop()
                self._state = ExecutionState.FORCE_STOPPING
            else:
                self.control.request_stop()
                self._state = ExecutionState.STOPPING
        return self.snapshot()

    def wait(self, timeout: float | None = None) -> bool:
        """Wait for operation exit without joining or blocking cancellation callers."""
        return self._done.wait(timeout)

    def snapshot(self) -> ExecutionSnapshot:
        """Return a consistent read-only status projection for this executor."""
        with self._lock:
            return ExecutionSnapshot(
                session_id=self.session_id,
                state=self._state,
                started_at=self._started_at,
                finished_at=self._finished_at,
                error=self._error,
            )

    @property
    def result(self) -> ResultT | None:
        """Return the completed operation result, or ``None`` before success."""
        with self._lock:
            return self._result
