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
    QUEUED = "queued"
    PREPARING = "preparing"
    MATERIALIZING_TOOLS = "materializing_tools"
    CONNECTING_MCP = "connecting_mcp"
    MATERIALIZING_SWARM = "materializing_swarm"
    LOADING_CONTEXT = "loading_context"
    RUNNING = "running"
    STOPPING = "stopping"
    FORCE_STOPPING = "force_stopping"
    COMPLETED = "completed"
    STOPPED = "stopped"
    INTERRUPTED = "interrupted"
    FAILED = "failed"


# Every state in which an attempt still owns live work.  This is the single
# table that "keep following / keep waiting" decisions must use: the run-status
# route derives its ``active`` flag from it and both console SSE routes stop on
# its complement.  Splitting the table is what makes a browser flap forever --
# the client reconnects whenever ``active`` is true, so a stream that treats an
# active state as terminal closes, is resumed one delay later, and closes again.
# A swarm spends seconds in the preparation states below before ``RUNNING``,
# which is why such a split only becomes visible with a swarm enabled.
ACTIVE_STATE_VALUES: frozenset[str] = frozenset({
    ExecutionState.QUEUED.value,
    ExecutionState.PREPARING.value,
    ExecutionState.MATERIALIZING_TOOLS.value,
    ExecutionState.CONNECTING_MCP.value,
    ExecutionState.MATERIALIZING_SWARM.value,
    ExecutionState.LOADING_CONTEXT.value,
    ExecutionState.RUNNING.value,
    ExecutionState.STOPPING.value,
    ExecutionState.FORCE_STOPPING.value,
})


def is_active_state(state: ExecutionState | str) -> bool:
    """Return whether ``state`` still represents live work.

    Args:
        state: Canonical lifecycle state or its lowercase wire string.

    Returns:
        ``True`` for the nine non-terminal states, including the startup
        phases an attempt passes through before it starts running.
    """
    return getattr(state, "value", state) in ACTIVE_STATE_VALUES


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
