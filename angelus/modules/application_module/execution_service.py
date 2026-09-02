"""The one host-neutral entry point for session execution lifecycle actions."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from ..execution_module import ExecutionAttempt, ExecutionSnapshot, ExecutionState
from llmfetcher.swarm_module import AgentFailure
from .agent_control import AgentControlReceipt, SessionRunControl

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
    Every execution starts the Session-owned ``AgentSwarm``; the coordinator
    remains the root result used to determine the request outcome.
    """

    def __init__(self, core: "AngelusCore") -> None:
        """Use the process's single ``AngelusCore`` as lifecycle authority.

        Args:
            core: Composition root that owns Session aggregates and services.
        """
        # Service dependency; it grants access to Session-owned execution.
        self._core = core

    def start(self, session_id: str, message: str) -> ExecutionSnapshot:
        """Start the configured Session AgentSwarm under a fresh attempt.

        Args:
            session_id: Existing Session whose execution boundary is used.
            message: Initial user instruction submitted through the root
                coordinator to the configured swarm.

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
            """Journal one swarm event and commit a safe graph generation.

            Args:
                event: LLMFetcher lifecycle event emitted by the Session swarm.

            Returns:
                None. Context-checkpoint events additionally commit a graph
                view and Agent-owned context references through the attempt.
            """
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
            if event.event_type == "agent:context_checkpoint":
                snapshotter = getattr(session.swarm, "view_snapshot", None)
                if not callable(snapshotter):
                    return
                graph = snapshotter()
                if not isinstance(graph, dict):
                    return
                round_value = data.get("round")
                nodes = graph.get("nodes", [])
                context_agents = [
                    node.get("id")
                    for node in nodes
                    if isinstance(node, dict)
                    and node.get("kind") == "agent"
                    and isinstance(node.get("id"), str)
                ]
                contexts = {
                    agent_name: {
                        "boundary": {"round": round_value},
                        "storage": "agent-owned-context-pointer",
                        "persisted": True,
                    }
                    for agent_name in context_agents
                }
                attempt.commit_checkpoint(
                    uuid4().hex,
                    graph,
                    contexts,
                    reason=f"{event.agent_name}:round:{round_value}",
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
            run_control = SessionRunControl(controller)
            # Register the persisted topology before scheduling begins.  A
            # worker can otherwise remain queued long enough for the browser
            # to select it, while its per-Agent control view does not exist
            # yet.  Pre-registration lets a stop or steering instruction
            # target every Agent that was present when this attempt began.
            snapshotter = getattr(session.swarm, "view_snapshot", None)
            topology = snapshotter() if callable(snapshotter) else {"nodes": []}
            nodes = topology.get("nodes", []) if isinstance(topology, dict) else []
            if isinstance(nodes, list):
                for node in nodes:
                    if not isinstance(node, dict):
                        continue
                    agent_name = node.get("id")
                    if node.get("kind") == "agent" and isinstance(agent_name, str):
                        run_control.for_agent(agent_name)
            session.run_control = run_control
            try:
                output = session.swarm.run(message, control=run_control)
                root = output.get(session.coordinator_name) if isinstance(output, dict) else None
                if isinstance(root, AgentFailure):
                    raise RuntimeError(f"{root.agent_name} failed: {root.error}")
                return output
            finally:
                _remove_journal_hook(session.swarm, journal_hook)
                session.run_control = None

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

    def control(
        self,
        session_id: str,
        agent_id: str,
        action: str,
        message: str,
        reason: str,
    ) -> AgentControlReceipt:
        """Route one typed browser command to all or one active Agent.

        Args:
            session_id: Session owning the current execution attempt.
            agent_id: ``all`` or one live graph Agent identity.
            action: ``steer``, ``stop``, or ``force_stop``.
            message: Required steering instruction; ignored by stop actions.
            reason: Journal-safe explanation for a stop request.

        Returns:
            Receipt recording the resolved target Agent identities.

        Raises:
            UnknownSession: If the Session does not exist.
            RuntimeError: If no active Session execution can accept control.
            KeyError: If the requested targeted Agent is not active.
            ValueError: If the action or required steering message is invalid.
        """
        self._require_session(session_id)
        session = self._core.sessions.get(session_id)
        executor = session.execution
        snapshot = executor.snapshot() if executor is not None else None
        control = session.run_control
        if snapshot is None or snapshot.state not in {ExecutionState.RUNNING, ExecutionState.STOPPING, ExecutionState.FORCE_STOPPING} or control is None:
            raise RuntimeError("Session has no active Agent control boundary")
        if action == "steer":
            targets = control.steer(agent_id, message)
            queued = True
        elif action == "stop":
            targets = control.stop(agent_id, False, reason)
            queued = True
        elif action == "force_stop":
            targets = control.stop(agent_id, True, reason)
            queued = False
        else:
            raise ValueError("action must be steer, stop, or force_stop")
        session.execution.attempt.journal.append(
            "agent:control",
            {"agent_id": agent_id, "action": action, "target_agents": list(targets), "reason": reason},
            agent=agent_id,
            message=message or reason,
        )
        return AgentControlReceipt(session_id, snapshot.execution_id or "", agent_id, action, targets, queued)

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
