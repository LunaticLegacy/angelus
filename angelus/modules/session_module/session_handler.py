"""In-memory ownership of the Agents belonging to each logical session."""

from __future__ import annotations

from typing import List
import threading
from collections.abc import Iterable

from llmfetcher import Agent, AgentSwarm

class Session:
    """One logical session and the reusable Agents configured inside it."""

    def __init__(self) -> None:
        """Create an empty session aggregate."""
        self.agents: List[Agent] = []
        self.swarm: AgentSwarm = AgentSwarm()

    def add_agent(self, agent: Agent) -> None:
        """Append one fully configured Agent to this session.

        Args:
            agent: Agent definition retained by reference for later execution.
        """
        self.agents.append(agent)

class SessionHandler:
    """Register and retrieve ``Session`` aggregates.

    This registry never starts an Agent and never stores execution status;
    ``SwarmHandler`` owns that second concern. The split prevents a cancelled
    execution from deleting the session aggregate and its reusable Agents.
    """

    def __init__(self) -> None:
        """Create an empty, thread-safe session aggregate registry."""
        self._sessions: dict[str, Session] = {}
        self._lock = threading.RLock()

    def create(self, session_id: str, agents: Iterable[Agent] = ()) -> Session:
        """Create one session with an optional initial Agent collection.

        Args:
            session_id: Non-empty process-local session identifier.
            agents: Agent instances owned by the newly created session.

        Returns:
            Newly registered Session aggregate.

        Raises:
            ValueError: If the ID is blank or already registered.
        """
        normalized = session_id.strip()
        if not normalized:
            raise ValueError("session_id must not be blank")
        session = Session()
        for agent in agents:
            session.add_agent(agent)
        with self._lock:
            if normalized in self._sessions:
                raise ValueError(f"Session already exists: {normalized}")
            self._sessions[normalized] = session
        return session

    def add_agent(self, session_id: str, agent: Agent) -> None:
        """Attach one Agent definition to an existing session.

        Args:
            session_id: Existing session identifier.
            agent: Fully configured Agent retained by reference.

        Raises:
            KeyError: If the session has not been created.
        """
        with self._lock:
            self._sessions[session_id].add_agent(agent)

    def agents(self, session_id: str) -> tuple[Agent, ...]:
        """Return an immutable snapshot of a session's Agent definitions.

        Args:
            session_id: Existing session identifier.

        Raises:
            KeyError: If the session has not been created.
        """
        with self._lock:
            return tuple(self._sessions[session_id].agents)

    def get(self, session_id: str) -> Session:
        """Return the Session aggregate owned by ``session_id``.

        Args:
            session_id: Existing session identifier.

        Raises:
            KeyError: If the session has not been created.
        """
        with self._lock:
            return self._sessions[session_id]

    def remove(self, session_id: str) -> Session:
        """Delete one session aggregate from this registry.

        Args:
            session_id: Existing session identifier.

        Returns:
            Removed Session aggregate for a host that needs explicit teardown.

        Raises:
            KeyError: If the session has not been created.
        """
        with self._lock:
            return self._sessions.pop(session_id)

    def exists(self, session_id: str) -> bool:
        """Return whether a session is registered without mutating state."""
        with self._lock:
            return session_id in self._sessions
