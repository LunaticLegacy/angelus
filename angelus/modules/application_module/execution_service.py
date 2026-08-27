"""The one host-neutral entry point for session execution lifecycle actions."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from ..execution_module import ExecutionAttempt, ExecutionSnapshot, ExecutionState

if TYPE_CHECKING:
    from ...core import AngelusCore


class UnknownSession(LookupError):
    """Raised when a lifecycle request does not name a registered session."""


class ExecutionService:
    """Perform Session execution lifecycle use cases without transport code.

    It never owns an executor: every lookup traverses ``Session.execution``.
    The current coordinator-only start path is explicitly a temporary adapter,
    not a hidden replacement for the Session's configured AgentSwarm.
    """

    def __init__(self, core: "AngelusCore") -> None:
        """Use the process's single ``AngelusCore`` as lifecycle authority.

        Args:
            core: Composition root that owns Session aggregates and services.
        """
        # Service dependency; it grants access to Session-owned execution.
        self._core = core

    def start(self, session_id: str, message: str) -> ExecutionSnapshot:
        """Start the temporary coordinator adapter under a fresh attempt.

        Args:
            session_id: Existing Session whose execution boundary is used.
            message: Initial user instruction passed to the coordinator.

        Returns:
            Snapshot immediately after the worker is scheduled.

        Raises:
            UnknownSession: If the Session is not registered.
            RuntimeError: If it lacks an Agent/boundary or another attempt runs.
        """
        try:
            session = self._core.sessions.get(session_id)
        except KeyError as exc:
            raise UnknownSession(session_id) from exc
        self._core.session_service.ensure_coordinator(session_id)
        # ``ensure_coordinator`` installs the required role at index zero.
        # Keep this defensive guard so a malformed custom Session cannot run.
        if not session.agents:
            raise RuntimeError("Session coordinator could not be constructed")
        executor = session.execution
        if executor is None:
            raise RuntimeError("Session has no execution boundary")
        coordinator = session.agents[0]
        attempt = executor.start(lambda controller: coordinator.run(message, control=controller))
        return attempt.snapshot()

    def status(self, session_id: str) -> ExecutionSnapshot:
        """Return current in-process execution state, or synthetic idle state.

        A synthetic idle snapshot is returned for a valid Session whose
        execution boundary has not been configured; unknown Sessions still
        raise ``UnknownSession``.
        """
        self._require_session(session_id)
        session = self._core.sessions.get(session_id)
        if session.execution is None:
            return ExecutionSnapshot(session_id, None, 0, ExecutionState.IDLE, None, None, None)
        return session.execution.snapshot()

    def stop(self, session_id: str, *, force: bool, reason: str) -> ExecutionSnapshot:
        """Request graceful or forced cancellation through the same controller.

        ``force`` changes cancellation strategy only.  Both paths converge on
        the same stopped outcome and journal/checkpoint lifecycle.
        """
        self._require_session(session_id)
        executor = self._core.sessions.get(session_id).execution
        if executor is None:
            return self.status(session_id)
        return executor.request_stop(force=force, reason=reason)

    def events(self, session_id: str) -> Iterator[dict[str, Any]]:
        """Yield durable events from the most recent in-process attempt.

        Raises:
            UnknownSession: If ``session_id`` is not registered.
            LookupError: If no attempt has been started in this process.
        """
        self._require_session(session_id)
        executor = self._core.sessions.get(session_id).execution
        attempt = executor.attempt if executor is not None else None
        if attempt is None:
            raise LookupError("Session has no execution attempt")
        yield from attempt.journal.events()

    def _require_session(self, session_id: str) -> None:
        """Raise ``UnknownSession`` before an operation reaches Session state."""
        if not self._core.sessions.exists(session_id):
            raise UnknownSession(session_id)
