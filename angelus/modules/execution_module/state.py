"""Durable and process-local states for one execution attempt."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ExecutionState(StrEnum):
    """Canonical lifecycle states written by an execution attempt.

    ``STOPPING`` and ``FORCE_STOPPING`` are strategies in flight; both become
    ``STOPPED`` once a cooperative worker exits.  ``INTERRUPTED`` instead
    means host shutdown reached its deadline before worker confirmation.
    """

    IDLE = "idle"
    RUNNING = "running"
    STOPPING = "stopping"
    FORCE_STOPPING = "force_stopping"
    COMPLETED = "completed"
    STOPPED = "stopped"
    INTERRUPTED = "interrupted"
    FAILED = "failed"


@dataclass(frozen=True)
class ExecutionSnapshot:
    """Immutable process-local projection of one attempt lifecycle.

    Attributes:
        session_id: Session aggregate that owns the attempt.
        execution_id: Unique attempt ID, or ``None`` for synthetic idle state.
        attempt: Monotonic run number within ``session_id``.
        state: Current canonical lifecycle state.
        started_at: Worker scheduling wall-clock timestamp, if started.
        finished_at: Confirmed/interrupted terminal wall-clock time, if known.
        error: Compact failure/interruption summary; detailed facts are journaled.
    """

    session_id: str
    execution_id: str | None
    attempt: int
    state: ExecutionState
    started_at: float | None
    finished_at: float | None
    error: str | None
