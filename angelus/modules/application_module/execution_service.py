"""The one host-neutral entry point for session execution lifecycle actions."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..execution_module import ExecutionAttempt, ExecutionSnapshot, ExecutionState
from llmfetcher.swarm_module import AgentFailure

if TYPE_CHECKING:
    from ...core import AngelusCore


class UnknownSession(LookupError):
    """Raised when a lifecycle request does not name a registered session."""


@dataclass
class _JournalBinding:
    """Attempt-scoped target used by a swarm hook before worker scheduling.

    Attributes:
        attempt: Durable attempt receiving normalized swarm events.
    """

    attempt: ExecutionAttempt[object] | None = None


def _remove_journal_hook(swarm: object, hook: object) -> None:
    """Best-effort remove an attempt-local hook across supported swarm builds.

    Args:
        swarm: Session-owned swarm that received the hook.
        hook: Exact callback object registered for the current Attempt.

    Returns:
        None. Cleanup failures are intentionally ignored so they cannot turn a
        successful model result into an execution failure.
    """
    remover = getattr(swarm, "remove_hook", None)
    if callable(remover):
        try:
            remover(hook)
        except (AttributeError, RuntimeError, ValueError):
            pass
        return
    graph = getattr(swarm, "_graph", None)
    hooks = getattr(graph, "hooks", None)
    if not isinstance(hooks, list):
        return
    lock = getattr(graph, "_hooks_lock", None)
    try:
        if lock is None:
            hooks.remove(hook)
        else:
            with lock:
                hooks.remove(hook)
    except (ValueError, RuntimeError):
        pass


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
        # Hooks are attached inside the attempt operation, before the swarm
        # scheduler starts, so even a very fast root Agent cannot outrun the
        # durable trace subscription.
        binding = _JournalBinding()
        def journal_hook(event: Any) -> None:
            attempt = binding.attempt
            if attempt is None:
                return
            data = event.data if isinstance(event.data, dict) else {"event_data": event.data}
            data = {**data, "agent": event.agent_name, "message": event.message}
            usage = data.get("usage") or data.get("round_usage") or {}
            attempt.journal.append(
                event.event_type or "swarm_event", data, agent=event.agent_name,
                message=event.message, usage=usage if isinstance(usage, dict) else {},
                duration_ms=data.get("duration_ms") or data.get("model_duration_ms"),
            )
        def install_hook(attempt: Any) -> None:
            binding.attempt = attempt
            session.swarm.add_hook(journal_hook)
        def run_swarm(controller: object) -> object:
            """Run the current swarm and convert root-agent failures to attempts.

            Args:
                controller: Attempt cancellation controller forwarded to Agents.

            Returns:
                The swarm output map when the root coordinator succeeded.

            Raises:
                RuntimeError: If the coordinator returned an ``AgentFailure``.
            """
            try:
                output = session.swarm.run(message, control=controller)
                root = output.get(session.coordinator_name) if isinstance(output, dict) else None
                if isinstance(root, AgentFailure):
                    raise RuntimeError(f"{root.agent_name} failed: {root.error}")
                return output
            finally:
                _remove_journal_hook(session.swarm, journal_hook)

        attempt = executor.start(run_swarm, before_start=install_hook)
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
