"""Agent-scoped controls layered over one Session execution controller."""
from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass

from llmfetcher.execution import ExecutionController, StopMode, StopRequest


class _CombinedForceEvent:
    """Expose the force state of a global and local controller as one event."""

    def __init__(self, global_control: ExecutionController, local_control: ExecutionController) -> None:
        """Retain the two cancellation sources.

        Args:
            global_control: Session-wide attempt controller.
            local_control: One Agent-only controller.
        """
        self._global_control = global_control
        self._local_control = local_control

    def is_set(self) -> bool:
        """Return whether either force-stop source is active.

        Returns:
            ``True`` when this Agent's provider I/O must be cancelled.
        """
        return self._global_control.force_stopped.is_set() or self._local_control.force_stopped.is_set()

    def wait(self, timeout: float | None = None) -> bool:
        """Wait briefly for either force-stop source.

        Args:
            timeout: Maximum wait duration in seconds.

        Returns:
            Whether either source became active before the deadline.
        """
        if self.is_set():
            return True
        awakened = threading.Event()
        timer = threading.Timer(max(0.0, timeout or 0.0), awakened.set)
        timer.daemon = True
        timer.start()
        try:
            while not awakened.wait(0.025):
                if self.is_set():
                    return True
            return self.is_set()
        finally:
            timer.cancel()


class AgentControlView:
    """Duck-typed llmfetcher control view for one concrete Agent."""

    def __init__(self, owner: "SessionRunControl", agent_id: str) -> None:
        """Bind a view to one Agent identity.

        Args:
            owner: Session-level control registry.
            agent_id: Agent receiving this local view.
        """
        self._owner = owner
        self._agent_id = agent_id
        self._local = ExecutionController()
        self.force_stopped = _CombinedForceEvent(owner.global_control, self._local)

    def should_stop(self) -> bool:
        """Return whether global or local cooperative stop is requested.

        Returns:
            ``True`` when the Agent must stop at its next safe boundary.
        """
        return self.stop_request is not None

    @property
    def stop_request(self) -> StopRequest | None:
        """Return the effective global-or-local stop request for this Agent.

        A force request always wins over a graceful request so downstream
        LLMFetcher code can reliably decide whether to cancel active provider
        I/O.  This mirrors :class:`ExecutionController`'s control contract.

        Returns:
            The effective request, or ``None`` while this Agent may continue.
        """
        global_request = self._owner.global_control.stop_request
        local_request = self._local.stop_request
        if global_request is not None and global_request.mode is StopMode.FORCE:
            return global_request
        if local_request is not None and local_request.mode is StopMode.FORCE:
            return local_request
        return global_request or local_request

    def drain_steers(self) -> list[str]:
        """Return pending steering messages in FIFO order.

        Returns:
            Pending user instructions for this Agent only.
        """
        return self._local.drain_steers()

    def steer(self, message: str) -> None:
        """Queue one Agent-specific steering message.

        Args:
            message: Non-empty instruction applied at a safe boundary.
        """
        self._local.steer(message)

    def request_stop(self, force: bool, reason: str) -> None:
        """Request a local cooperative or forceful stop.

        Args:
            force: Whether active provider and tool resources must be cancelled.
            reason: Journal-safe explanation for the interruption.
        """
        self._local.request_stop(StopMode.FORCE if force else StopMode.GRACEFUL, reason=reason)

    def register_force_canceller(self, cancel: Callable[[StopRequest], None]) -> Callable[[], None]:
        """Register a resource canceller with both global and local scope.

        Args:
            cancel: Provider or tool resource closer.

        Returns:
            Idempotent callback removing both registrations.
        """
        unregister_local = self._local.register_force_canceller(cancel)
        unregister_global = self._owner.global_control.register_force_canceller(cancel)

        def unregister() -> None:
            """Detach both force-cancellation registrations."""
            unregister_local()
            unregister_global()
        return unregister


class SessionRunControl:
    """Route Session-wide and Agent-local controls to active swarm Agents."""

    def __init__(self, global_control: ExecutionController) -> None:
        """Create an empty Agent-control registry.

        Args:
            global_control: Existing attempt controller owning Session-wide stop.
        """
        self.global_control = global_control
        self._lock = threading.RLock()
        self._agents: dict[str, AgentControlView] = {}

    def for_agent(self, agent_id: str) -> AgentControlView:
        """Return the persistent local control view for one Agent.

        Args:
            agent_id: Runtime graph Agent identity.

        Returns:
            Independent control view used by llmfetcher Agent execution.
        """
        with self._lock:
            view = self._agents.get(agent_id)
            if view is None:
                view = AgentControlView(self, agent_id)
                self._agents[agent_id] = view
            return view

    def should_stop(self, agent_id: str = "all") -> bool:
        """Return the stop state used by AgentSwarm scheduling.

        Args:
            agent_id: ``all`` for the Session or one concrete Agent identity.

        Returns:
            Whether the requested scope has a stop request.
        """
        if agent_id == "all":
            return self.global_control.should_stop()
        return self.for_agent(agent_id).should_stop()

    def steer(self, agent_id: str, message: str) -> tuple[str, ...]:
        """Queue steering for all Agents or one existing Agent.

        Args:
            agent_id: ``all`` for every Agent registered at submission time,
                or one concrete Agent identity.
            message: Non-empty instruction applied at the next safe boundary.

        Returns:
            Agent IDs that will receive the instruction.

        Raises:
            KeyError: If a targeted Agent has not entered the active graph.
        """
        if not message.strip():
            raise ValueError("message is required")
        with self._lock:
            if agent_id == "all":
                targets = tuple(sorted(self._agents))
                for target in targets:
                    self._agents[target].steer(message)
                return targets
            if agent_id not in self._agents:
                raise KeyError(agent_id)
            self._agents[agent_id].steer(message)
            return (agent_id,)

    def stop(self, agent_id: str, force: bool, reason: str) -> tuple[str, ...]:
        """Request stop for all Agents or one active Agent.

        Args:
            agent_id: ``all`` for Session cancellation or a concrete Agent.
            force: Whether to cancel active provider and tool I/O immediately.
            reason: Journal-safe interruption explanation.

        Returns:
            Agent IDs receiving the request; empty for an early global stop.

        Raises:
            KeyError: If a targeted Agent has not entered the active graph.
        """
        if agent_id == "all":
            self.global_control.request_stop(StopMode.FORCE if force else StopMode.GRACEFUL, reason=reason)
            with self._lock:
                return tuple(sorted(self._agents))
        with self._lock:
            if agent_id not in self._agents:
                raise KeyError(agent_id)
            self._agents[agent_id].request_stop(force, reason)
            return (agent_id,)

@dataclass(frozen=True)
class AgentControlReceipt:
    """Acknowledgement for one accepted Agent control command.

    Args:
        session_id: Owning Session identity.
        execution_id: Active execution receiving the command.
        agent_id: Requested ``all`` or concrete Agent identity.
        action: Accepted action identifier.
        target_agents: Concrete Agent recipients known at acceptance time.
        queued: Whether execution applies the command at a safe boundary.
    """

    session_id: str
    execution_id: str
    agent_id: str
    action: str
    target_agents: tuple[str, ...]
    queued: bool
