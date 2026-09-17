"""Thin HTTP adapter for session execution attempts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..core import AngelusCore
from ..modules.application_module import UnknownSession
from ..modules.execution_module import ExecutionState


router = APIRouter()


class RunRequest(BaseModel):
    """HTTP input for one configured Session execution."""

    session_id: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=100_000)


class StopRequest(BaseModel):
    """HTTP input for either graceful or forced stop."""

    reason: str = Field(default="user_requested", min_length=1, max_length=512)


@dataclass
class AgentControlRequest:
    """Typed input for an all-Agent or targeted runtime command.

    Args:
        agent_id: ``all`` for broadcast or one concrete live Agent identity.
        action: ``steer``, ``stop``, or ``force_stop``.
        message: Required non-empty instruction for ``steer``.
        reason: Journal-safe reason for stop actions.
    """

    agent_id: str = "all"
    action: str = "steer"
    message: str = ""
    reason: str = "user_requested"


def _core(request: Request) -> AngelusCore:
    """Resolve the app-owned core without constructing a fallback instance."""
    core = getattr(request.app.state, "angelus_core", None)
    if not isinstance(core, AngelusCore):
        raise RuntimeError("AngelusCore is not installed on this application")
    return core


@router.post("/api/runs")
def start_run(payload: RunRequest, request: Request) -> dict[str, Any]:
    """Start one attempt against the Session's configured coordinator."""
    core = _core(request)
    try:
        snapshot = core.execution_service.start(payload.session_id, payload.message)
    except UnknownSession as exc:
        raise HTTPException(status_code=404, detail="Unknown session") from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "session_id": snapshot.session_id,
        "execution_id": snapshot.execution_id,
        "attempt": snapshot.attempt,
        "state": snapshot.state,
    }


@router.get("/api/runs/{session_id}/status")
def run_status(session_id: str, request: Request) -> dict[str, Any]:
    """Return current process state; manifest is the restart source."""
    try:
        snapshot = _core(request).execution_service.status(session_id)
    except UnknownSession as exc:
        raise HTTPException(status_code=404, detail="Unknown session") from exc
    return {
        "session_id": snapshot.session_id,
        "execution_id": snapshot.execution_id,
        "attempt": snapshot.attempt,
        "state": snapshot.state,
        "started_at": snapshot.started_at,
        "finished_at": snapshot.finished_at,
        "error": snapshot.error,
    }


def _stop(session_id: str, payload: StopRequest, request: Request, *, force: bool) -> dict[str, Any]:
    try:
        snapshot = _core(request).execution_service.stop(session_id, force=force, reason=payload.reason)
    except UnknownSession as exc:
        raise HTTPException(status_code=404, detail="Unknown session") from exc
    return {
        "session_id": snapshot.session_id,
        "execution_id": snapshot.execution_id,
        "state": snapshot.state,
        "accepted": snapshot.state in {ExecutionState.STOPPING, ExecutionState.FORCE_STOPPING},
    }


@router.post("/api/runs/{session_id}/stop")
def stop_run(session_id: str, payload: StopRequest, request: Request) -> dict[str, Any]:
    """Request graceful stop through the attempt's only controller."""
    return _stop(session_id, payload, request, force=False)


@router.post("/api/runs/{session_id}/force-stop")
def force_stop_run(session_id: str, payload: StopRequest, request: Request) -> dict[str, Any]:
    """Escalate the same request and close every registered live resource."""
    return _stop(session_id, payload, request, force=True)


@router.post("/api/runs/{session_id}/control")
def control_run(session_id: str, payload: AgentControlRequest, request: Request) -> dict[str, object]:
    """Apply one control command to every Agent or one selected Agent.

    Args:
        session_id: Session owning the active execution.
        payload: Validated control scope, action, and optional instruction.
        request: Incoming request carrying the Angelus application core.

    Returns:
        Accepted command receipt including resolved target Agent identities.
    """
    try:
        receipt = _core(request).execution_service.control(
            session_id, payload.agent_id, payload.action, payload.message, payload.reason,
        )
    except UnknownSession as exc:
        raise HTTPException(status_code=404, detail="Unknown session") from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown active agent") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return asdict(receipt)


__all__ = ["router"]
