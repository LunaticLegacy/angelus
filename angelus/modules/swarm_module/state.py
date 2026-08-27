"""Value objects describing one session executor lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ExecutionState(StrEnum):
    """Observable lifecycle of one session-owned execution."""

    IDLE = "idle"
    RUNNING = "running"
    STOPPING = "stopping"
    FORCE_STOPPING = "force_stopping"
    COMPLETED = "completed"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass(frozen=True)
class ExecutionSnapshot:
    """Read-only process-local status of one execution attempt.

    Args:
        session_id: Session that owns this executor.
        state: Current lifecycle state.
        started_at: UNIX timestamp at operation launch, if started.
        finished_at: UNIX timestamp at terminal completion, if terminal.
        error: Exception type and message for failed operations only.
    """

    session_id: str
    state: ExecutionState
    started_at: float | None
    finished_at: float | None
    error: str | None
