"""In-memory ownership of the Agents belonging to each logical session."""

from __future__ import annotations

from pathlib import Path
import re
from typing import TYPE_CHECKING, Any, List
import threading
from collections.abc import Iterable

from llmfetcher import Agent, AgentSwarm
from ..swarm_module.session_executor import SessionExecutor
from ..execution_module import ExecutionAttempt, ExecutionState
from ..console_module import ConsoleState
from .artifact_store import SessionArtifactStore

if TYPE_CHECKING:
    from ..application_module.agent_control import SessionRunControl


SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")


def validate_session_id(session_id: str) -> str:
    """Validate and return one filesystem-safe durable Session identity.

    Args:
        session_id: Proposed Session identifier from an API or catalog record.

    Returns:
        The unchanged validated Session identifier.

    Raises:
        ValueError: If the identifier is blank, padded, too long, or unsafe
            for use as one directory-name component.
    """
    if not isinstance(session_id, str) or not SESSION_ID_PATTERN.fullmatch(session_id):
        raise ValueError("session_id must use 1-80 letters, numbers, underscores, or hyphens and cannot start with punctuation")
    return session_id

class Session:
    """One logical session and all state that has Session ownership.

    ``agents`` and ``swarm`` describe reusable configuration.  ``execution``
    owns at most one currently active or most recent attempt; it is kept here
    so execution can never be indexed independently of its Session.
    """

    def __init__(self) -> None:
        """Create an empty session aggregate."""
        # Ordered Agent definitions.  The first entry is temporarily the
        # coordinator until the Session execution-mode abstraction replaces it.
        self.agents: List[Agent] = []
        # Stable required role name.  It exists before credentials can safely
        # construct the concrete llmfetcher Agent object.
        self.coordinator_name = "coordinator"
        # Concrete coordinator once a saved profile has usable credentials.
        # ``None`` denotes an unconfigured role, never a fabricated Agent.
        self.coordinator: Agent | None = None
        # Profile fingerprint used to avoid rebuilding coordinator/context on
        # a later run when its effective future-run configuration is unchanged.
        self._coordinator_fingerprint: tuple[object, ...] | None = None
        # The llmfetcher graph/configuration aggregate, retained across runs.
        self.swarm: AgentSwarm = AgentSwarm()
        # This is deliberately session-owned.  It is not an AgentSwarm: it
        # owns the current execution attempt, its controller, and its durable
        # attempt directory for this logical session.
        self.execution: SessionExecutor[Any] | None = None
        # Ephemeral control registry for the currently active execution. It is
        # deliberately never persisted: only durable Agent context survives a
        # process restart, not an in-flight provider request.
        self.run_control: SessionRunControl | None = None
        # Durable console-only state (plans and safe graph blueprints).  It is
        # attached when the session receives its durable state root.
        self.console: ConsoleState | None = None
        # Complete large tool outputs live in this session's attempt roots;
        # Agents retain only stable artifact references in their model context.
        self.artifacts: SessionArtifactStore | None = None

    def add_agent(self, agent: Agent) -> None:
        """Append one fully configured Agent to this session.

        Args:
            agent: Agent definition retained by reference for later execution.
        """
        self.agents.append(agent)

    def configure_execution(self, session_id: str, root: Path) -> None:
        """Attach this Session's single durable execution boundary exactly once.

        Args:
            session_id: Identity recorded in every resulting attempt journal.
            root: Directory containing this Session's execution attempt roots.

        Raises:
            RuntimeError: If a second execution owner is requested.
        """
        if self.execution is not None:
            raise RuntimeError("Session execution is already configured")
        self.execution = SessionExecutor(session_id, root)
        self.console = ConsoleState(root)
        self.artifacts = SessionArtifactStore(session_id, root, self.execution)

    def set_coordinator(self, agent: Agent, fingerprint: tuple[object, ...]) -> None:
        """Install the required coordinator and retain it as ``agents[0]``.

        Args:
            agent: Concrete coordinator built from a validated saved profile.
            fingerprint: Immutable configuration identity used by later runs.

        Side Effects:
            Replaces only the old coordinator while preserving future worker
            Agents already registered after index zero.
        """
        if self.coordinator is agent and self._coordinator_fingerprint == fingerprint:
            return
        previous = self.coordinator
        self.coordinator = agent
        self._coordinator_fingerprint = fingerprint
        self.agents = [agent, *[item for item in self.agents if item is not previous]]

    def coordinator_matches(self, fingerprint: tuple[object, ...]) -> bool:
        """Return whether this Session already has coordinator for ``fingerprint``."""
        return self.coordinator is not None and self._coordinator_fingerprint == fingerprint

class SessionHandler:
    """Register and retrieve ``Session`` aggregates.

    This registry owns complete Session aggregates.  Each aggregate in turn
    owns its reusable Agents, its AgentSwarm definition, and its execution
    boundary; cancellation therefore cannot detach execution state from the
    session it belongs to.
    """

    def __init__(self) -> None:
        """Create an empty, thread-safe session aggregate registry."""
        # Maps stable session IDs to their sole in-process aggregate.
        self._sessions: dict[str, Session] = {}
        # Protects publication/removal and consistent aggregate snapshots.
        self._lock = threading.RLock()

    def create(
        self,
        session_id: str,
        agents: Iterable[Agent] = (),
        *,
        execution_root: Path | None = None,
    ) -> Session:
        """Create one session with an optional initial Agent collection.

        Args:
            session_id: Non-empty process-local session identifier.
            agents: Agent instances owned by the newly created session.
            execution_root: Durable directory for this Session's attempts.

        Returns:
            Newly registered Session aggregate.

        Raises:
            ValueError: If the ID is blank or already registered.
        """
        normalized = validate_session_id(session_id)
        with self._lock:
            if normalized in self._sessions:
                raise ValueError(f"Session already exists: {normalized}")
        session = Session()
        for agent in agents:
            session.add_agent(agent)
        if execution_root is not None:
            session.configure_execution(normalized, execution_root)
        with self._lock:
            # Retain the final publication check: callers may perform costly
            # Agent construction outside the lock, so another creator can win
            # after the early check above.
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
        """Return whether a session is registered without mutating state.

        The answer is process-local; durable identity belongs to
        ``WorkspaceCatalog`` and is rehydrated by ``AngelusCore`` on startup.
        """
        with self._lock:
            return session_id in self._sessions

    def live_attempts(self) -> tuple[ExecutionAttempt[Any], ...]:
        """Return live attempts owned by Sessions for coordinated shutdown.

        The registry lock is released before snapshotting each attempt so a
        slow worker cannot block Session registration or deletion.
        """
        with self._lock:
            attempts = [session.execution.attempt for session in self._sessions.values()
                        if session.execution is not None]
        return tuple(
            attempt for attempt in attempts
            if attempt is not None and attempt.snapshot().state in {
                ExecutionState.RUNNING,
                ExecutionState.STOPPING,
                ExecutionState.FORCE_STOPPING,
            }
        )
