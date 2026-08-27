"""Registry connecting session identities to their execution boundaries."""

from __future__ import annotations

import threading
from typing import Any

from .session_executor import SessionExecutor
from .state import ExecutionState


class SwarmHandler:
    """Own one replaceable SessionExecutor per session.

    This bridge knows neither Agents nor HTTP. It maps session identity to an
    executor, so every future AgentSwarm adapter receives the same control and
    lifecycle contract.
    """

    def __init__(self) -> None:
        """Create an empty, thread-safe session executor registry."""
        self._executors: dict[str, SessionExecutor[Any]] = {}
        self._lock = threading.RLock()

    def create(self, session_id: str) -> SessionExecutor[Any]:
        """Create and register an idle executor for a session.

        Raises:
            ValueError: If the session already has an executor.
        """
        executor: SessionExecutor[Any] = SessionExecutor(session_id)
        with self._lock:
            if session_id in self._executors:
                raise ValueError(f"Executor already exists: {session_id}")
            self._executors[session_id] = executor
        return executor

    def get(self, session_id: str) -> SessionExecutor[Any]:
        """Return an existing session executor.

        Raises:
            KeyError: If the session has no execution owner.
        """
        with self._lock:
            return self._executors[session_id]

    def remove(self, session_id: str) -> SessionExecutor[Any]:
        """Remove an idle or terminal executor from the registry.

        Raises:
            RuntimeError: If the executor remains live.
            KeyError: If the session has no execution owner.
        """
        with self._lock:
            executor = self._executors[session_id]
            if executor.snapshot().state in {
                ExecutionState.RUNNING, ExecutionState.STOPPING, ExecutionState.FORCE_STOPPING,
            }:
                raise RuntimeError("Cannot remove a live session executor")
            return self._executors.pop(session_id)
