"""Thread-safe run and Agent-scoped browser controls."""

from __future__ import annotations

import queue
import threading

from llmfetcher.agent import AgentRunControl


class _CombinedEvent:
    """Expose the union of global and Agent-local terminal stop events."""

    def __init__(self, *events: threading.Event) -> None:
        """Keep stable events owned by the run-level registry.

        Args:
            events: Events whose union is observed by one Agent.
        """
        self._events = events

    def is_set(self) -> bool:
        """Return whether any constituent terminal event is set."""
        return any(event.is_set() for event in self._events)

    def wait(self, timeout: float | None = None) -> bool:
        """Wait up to ``timeout`` seconds for a constituent event."""
        if self.is_set():
            return True
        self._events[0].wait(timeout)
        return self.is_set()


class AgentScopedRunControl(AgentRunControl):
    """Project one Agent's stop state from a run-level registry."""

    def __init__(self, owner: "BrowserRunControl", agent: str) -> None:
        """Bind this view to ``agent`` without copying registry events.

        Args:
            owner: Run-level control registry.
            agent: Concrete graph Agent identifier.
        """
        self._owner = owner
        self.agent = agent
        self._force_stopped = _CombinedEvent(
            owner._force_stopped, owner._agent_force_event(agent)
        )

    def should_stop(self) -> bool:
        """Return whether the run or this Agent should stop."""
        return self._owner.should_stop(self.agent)

    def drain_steers(self) -> list[str]:
        """Deliver session steering only to the coordinator."""
        return self._owner.drain_steers() if self.agent == "coordinator" else []

    @property
    def force_stopped(self) -> _CombinedEvent:
        """Return the global-or-local terminal cancellation event."""
        return self._force_stopped


class BrowserRunControl(AgentRunControl):
    """Thread-safe browser controls with cooperative and terminal stop modes.

    ``stop()`` is observed only at Agent safe boundaries.  ``force_stop()``
    additionally exposes ``force_stopped`` so the current model request can
    close its provider transport and the browser worker can end immediately.
    """

    def __init__(self) -> None:
        """Create an empty run-level control registry."""
        self._stopped = threading.Event()
        self._force_stopped = threading.Event()
        self._agent_stopped: dict[str, threading.Event] = {}
        self._agent_force_stopped: dict[str, threading.Event] = {}
        self._lock = threading.RLock()
        self._steers: queue.Queue[str] = queue.Queue()

    def register_agent(self, agent: str) -> None:
        """Ensure stable stop events exist for ``agent``.

        Args:
            agent: Concrete graph Agent identifier.
        """
        with self._lock:
            self._agent_stopped.setdefault(agent, threading.Event())
            self._agent_force_stopped.setdefault(agent, threading.Event())

    def known_agents(self) -> tuple[str, ...]:
        """Return registered Agent identifiers in deterministic order."""
        with self._lock:
            return tuple(sorted(self._agent_stopped))

    def _agent_force_event(self, agent: str) -> threading.Event:
        """Return the stable terminal event for ``agent``."""
        self.register_agent(agent)
        return self._agent_force_stopped[agent]

    def for_agent(self, agent: str) -> AgentScopedRunControl:
        """Return a control view combining global and ``agent`` state.

        Args:
            agent: Concrete Agent receiving the view.

        Returns:
            Control safe to pass to ``Agent.run``.
        """
        self.register_agent(agent)
        return AgentScopedRunControl(self, agent)

    def should_stop(self, agent: str = "all") -> bool:
        """Return whether global or selected-Agent cooperative stop is set."""
        if self._stopped.is_set() or agent == "all":
            return self._stopped.is_set()
        self.register_agent(agent)
        return self._agent_stopped[agent].is_set()

    def drain_steers(self) -> list[str]:
        """Drain all unapplied session-level steering messages."""
        messages: list[str] = []
        while True:
            try:
                messages.append(self._steers.get_nowait())
            except queue.Empty:
                return messages

    def stop(self, agent: str = "all") -> None:
        """Request cooperative stop for the whole run or one Agent.

        Args:
            agent: ``all`` or a concrete registered Agent identifier.
        """
        if agent == "all":
            self._stopped.set()
            return
        self.register_agent(agent)
        self._agent_stopped[agent].set()

    def force_stop(self, agent: str = "all") -> None:
        """Request terminal stop for the whole run or one Agent.

        Args:
            agent: ``all`` or a concrete registered Agent identifier.
        """
        if agent == "all":
            self._force_stopped.set()
            self._stopped.set()
            return
        self.register_agent(agent)
        self._agent_force_stopped[agent].set()
        self._agent_stopped[agent].set()

    def reset(self) -> None:
        """Clear terminal controls before the same session begins another run.

        This method is valid only after the prior run reached its terminal
        boundary. Keeping the control object itself stable lets persistent
        Swarm tool handlers retain their force-stop event reference across
        browser turns.

        Side Effects:
            Clears cooperative/force-stop flags and discards unapplied steer
            messages from the completed run.
        """
        self._stopped.clear()
        self._force_stopped.clear()
        with self._lock:
            for event in (*self._agent_stopped.values(), *self._agent_force_stopped.values()):
                event.clear()
        while True:
            try:
                self._steers.get_nowait()
            except queue.Empty:
                return

    @property
    def force_stopped(self) -> threading.Event:
        """Return the run-wide terminal cancellation event."""
        return self._force_stopped

    def steer(self, message: str) -> None:
        """Queue a session-level coordinator steering message.

        Args:
            message: User instruction applied at the next safe boundary.
        """
        self._steers.put(message)


__all__ = ["AgentScopedRunControl", "BrowserRunControl"]
