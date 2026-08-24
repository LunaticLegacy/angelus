"""anime.* 事件模型：进 audit log + SSE。

事件类型：
    anime.project.created / updated / deleted
    anime.shot.state_changed
    anime.job.submitted / queued / running / succeeded / failed / cancelled / retried
    anime.qa.passed / failed
    anime.cost.recorded
    anime.budget.awaiting_approval
"""

from __future__ import annotations

import time
from typing import Any, Optional

from . import storage


def emit(project_id: str, event_type: str, payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """构造并持久化一个 anime.* 事件。"""
    event = {
        "type": event_type,
        "ts": time.time(),
        "payload": payload or {},
    }
    return storage.append_event(project_id, event)


def project_created(project_id: str, name: str) -> dict[str, Any]:
    return emit(project_id, "anime.project.created", {"project_id": project_id, "name": name})


def project_updated(project_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    return emit(project_id, "anime.project.updated", {"project_id": project_id, "fields": fields})


def project_deleted(project_id: str) -> dict[str, Any]:
    return emit(project_id, "anime.project.deleted", {"project_id": project_id})


def shot_state_changed(project_id: str, shot_id: str, old: str, new: str) -> dict[str, Any]:
    return emit(
        project_id,
        "anime.shot.state_changed",
        {"project_id": project_id, "shot_id": shot_id, "old": old, "new": new},
    )


def job_submitted(project_id: str, job_id: str, shot_id: str, provider: str) -> dict[str, Any]:
    return emit(
        project_id,
        "anime.job.submitted",
        {"project_id": project_id, "job_id": job_id, "shot_id": shot_id, "provider": provider},
    )


def job_status(project_id: str, job_id: str, status: str, error: Optional[str] = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"project_id": project_id, "job_id": job_id, "status": status}
    if error:
        payload["error"] = error
    return emit(project_id, f"anime.job.{status.lower()}", payload)


def qa_result(project_id: str, shot_id: str, verdict: str, report_id: str) -> dict[str, Any]:
    return emit(
        project_id,
        f"anime.qa.{'passed' if verdict == 'PASS' else 'failed'}",
        {"project_id": project_id, "shot_id": shot_id, "verdict": verdict, "report_id": report_id},
    )


def cost_recorded(project_id: str, amount: float, job_id: str = "") -> dict[str, Any]:
    return emit(
        project_id,
        "anime.cost.recorded",
        {"project_id": project_id, "amount": amount, "job_id": job_id},
    )


def budget_awaiting_approval(project_id: str, amount: float, reason: str) -> dict[str, Any]:
    return emit(
        project_id,
        "anime.budget.awaiting_approval",
        {"project_id": project_id, "amount": amount, "reason": reason},
    )
