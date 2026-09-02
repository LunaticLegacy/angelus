"""Main-thread SIGINT coordination for live execution attempts."""

from __future__ import annotations

import signal
import threading
from collections.abc import Callable, Iterable

from .execution_attempt import ExecutionAttempt


class SigintSupervisor:
    """Translate Ctrl+C into a bounded forced shutdown of Session attempts.

    The signal callback only sets an event.  Cancellation, journaling and
    checkpoint persistence occur in ``drain`` or the host shutdown lifecycle,
    where Python permits ordinary locking and I/O.
    """

    def __init__(self, live_attempts: Callable[[], Iterable[ExecutionAttempt[object]]], deadline_seconds: float = 5.0) -> None:
        """Construct one host-facing signal coordinator.

        Args:
            live_attempts: Callback returning a stable-enough snapshot from
                Session ownership, never a separate global executor registry.
            deadline_seconds: Per-attempt bounded wait before interruption is
                durably recorded for an uncooperative worker.
        """
        # Pull callback avoids duplicating live-attempt ownership here.
        self._live_attempts = live_attempts
        # Maximum graceful host wait after requesting forced cancellation.
        self.deadline_seconds = deadline_seconds
        # Signal-safe-ish receipt flag consumed outside the handler.
        self._pending = threading.Event()
        # Host handler restored when Angelus shuts down or is disposed.
        self._previous: signal.Handlers | None = None

    def install(self) -> None:
        """Install minimal receipt handler from host main thread.

        Python raises if called from a non-main thread; callers must let the
        ASGI/CLI host decide whether this replacement is appropriate.
        """
        self._previous = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, self._receive)

    def restore(self) -> None:
        """Restore prior host handler once, leaving no Angelus signal residue."""
        if self._previous is not None:
            signal.signal(signal.SIGINT, self._previous)
            self._previous = None

    def drain(self) -> bool:
        """Consume one pending SIGINT and perform its durable shutdown work.

        Returns:
            ``False`` when no signal was pending, otherwise ``True``.
        """
        if not self._pending.is_set():
            return False
        self._pending.clear()
        self.force_stop_all(reason="sigint")
        return True

    def request_force_stop_all(self, *, reason: str) -> tuple[ExecutionAttempt[object], ...]:
        """Immediately request force-stop on a stable snapshot of live attempts.

        This phase does not wait.  It sets each attempt's controller to force
        mode, which closes every resource registered by LLMFetcher/tool code,
        then returns the exact attempts that the host must await during its
        shutdown lifecycle.
        """
        attempts = tuple(self._live_attempts())
        for attempt in attempts:
            attempt.request_stop(force=True, reason=reason)
        return attempts

    def wait_for_stop_all(
        self,
        attempts: Iterable[ExecutionAttempt[object]],
        *,
        reason: str,
    ) -> None:
        """Wait boundedly and persist interruption for each unfinished worker."""
        for attempt in attempts:
            if not attempt.wait(self.deadline_seconds):
                attempt.mark_interrupted(f"{reason}_shutdown_deadline")

    def force_stop_all(self, *, reason: str) -> None:
        """Request and then boundedly await every live attempt before exit.

        Hosts such as Uvicorn own their process signal handlers.  Their
        shutdown callback invokes this method after deciding to exit, which
        keeps durable attempt shutdown independent from signal ownership.
        """
        attempts = self.request_force_stop_all(reason=reason)
        self.wait_for_stop_all(attempts, reason=reason)

    def _receive(self, _signum: int, _frame: object) -> None:
        """Mark SIGINT pending without performing locks, joins, or disk I/O."""
        self._pending.set()
