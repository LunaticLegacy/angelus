"""Persistent task plans and Agent tools for supervising user work."""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Iterable, Mapping

from .llm_types import Tool, ToolParameter, ToolSchema

_STATUSES = {"not_started", "in_progress", "completed", "blocked"}
_PRIORITIES = {"low", "medium", "high", "critical"}
_PLAN_LOCKS: dict[Path, threading.RLock] = {}
_PLAN_LOCKS_GUARD = threading.Lock()


def _lock_for_path(path: Path) -> threading.RLock:
    """Return the process-local lock shared by all stores for one plan path.

    Args:
        path: Canonical session task-plan destination.

    Returns:
        Re-entrant lock used to serialize all in-process writes to ``path``.
    """
    resolved = path.resolve()
    with _PLAN_LOCKS_GUARD:
        return _PLAN_LOCKS.setdefault(resolved, threading.RLock())


class TaskPlanStore:
    """Own one session's task-plan JSON file and validate task-tree updates."""

    def __init__(self, path: str | Path) -> None:
        """Bind the store to one plan file.

        Args:
            path: Session-local plan JSON destination. Parent directories are
                created when a plan is saved.
        """
        self.path = Path(path)
        self._lock = _lock_for_path(self.path)

    def read(self) -> dict[str, Any]:
        """Load the plan or return an empty plan when no file exists.

        Returns:
            JSON-compatible plan containing ``goal``, ``summary``, ``tasks``
            and ``updated_at``.
        """
        if not self.path.exists():
            return {"goal": "", "summary": "", "tasks": [], "updated_at": None}
        try:
            plan = json.loads(self.path.read_text(encoding="utf-8"))
            return plan if isinstance(plan, dict) else {"goal": "", "summary": "", "tasks": [], "updated_at": None}
        except (OSError, json.JSONDecodeError):
            return {"goal": "", "summary": "", "tasks": [], "updated_at": None}

    def replace(self, *, goal: str, summary: str, tasks: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
        """Validate and atomically replace the complete task tree.

        Args:
            goal: User objective supervised by this plan.
            summary: Short planning rationale for the user.
            tasks: Nested task dictionaries with title, status and subtasks.

        Returns:
            Persisted normalized plan.

        Raises:
            ValueError: If the goal or a task field is invalid.
        """
        if not goal.strip():
            raise ValueError("Plan goal is required")
        plan = {"goal": goal.strip(), "summary": summary.strip(), "tasks": self._normalize_tasks(tasks), "updated_at": time.time()}
        with self._lock:
            self._write(plan)
        return plan

    def update_status(self, task_id: str, status: str) -> dict[str, Any]:
        """Change one task status and persist the containing plan.

        Args:
            task_id: Stable task identifier in the nested plan.
            status: One of not_started, in_progress, completed or blocked.

        Returns:
            Updated full plan.

        Raises:
            ValueError: If status is invalid or task does not exist.
        """
        if status not in _STATUSES:
            raise ValueError(f"Unknown task status: {status}")
        # Keep read-modify-write atomic for concurrent worker tool calls.
        with self._lock:
            plan = self.read()
            if not self._set_status(plan.get("tasks", []), task_id, status):
                raise ValueError(f"Unknown task: {task_id}")
            plan["updated_at"] = time.time()
            self._write(plan)
        return plan

    def _normalize_tasks(self, values: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
        """Normalize recursive task input into the persisted public contract."""
        normalized = []
        for value in values:
            if not isinstance(value, Mapping) or not str(value.get("title", "")).strip():
                raise ValueError("Every task needs a title")
            status = str(value.get("status", "not_started"))
            priority = str(value.get("priority", "medium"))
            if status not in _STATUSES or priority not in _PRIORITIES:
                raise ValueError("Task has an invalid status or priority")
            normalized.append({
                "id": str(value.get("id") or uuid.uuid4().hex), "title": str(value["title"]).strip(),
                "description": str(value.get("description", "")).strip(), "status": status,
                "priority": priority, "estimated_minutes": value.get("estimated_minutes"),
                "subtasks": self._normalize_tasks(value.get("subtasks", [])),
            })
        return normalized

    @staticmethod
    def _set_status(tasks: list[dict[str, Any]], task_id: str, status: str) -> bool:
        """Find one recursive task and mutate only its status field."""
        for task in tasks:
            if task.get("id") == task_id:
                task["status"] = status
                return True
            if TaskPlanStore._set_status(task.get("subtasks", []), task_id, status):
                return True
        return False

    def _write(self, plan: Mapping[str, Any]) -> None:
        """Atomically write a normalized task plan to the session path."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f"{self.path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)


def create_task_planning_tools(store: TaskPlanStore) -> list[Tool]:
    """Create Agent tools that let a model publish and supervise a task plan.

    Args:
        store: Session-local task plan store mutated by the returned handlers.

    Returns:
        ``set_task_plan`` and ``update_task_status`` Tool instances.
    """
    def set_task_plan(goal: str, summary: str, tasks: list[dict[str, Any]]) -> dict[str, Any]:
        """Persist a complete plan supplied by the model in structured arguments."""
        return {"ok": True, "plan": store.replace(goal=goal, summary=summary, tasks=tasks)}

    def update_task_status(task_id: str, status: str) -> dict[str, Any]:
        """Persist a user-visible task status transition requested by the model."""
        return {"ok": True, "plan": store.update_status(task_id, status)}

    return [
        Tool(name="set_task_plan", description="Create or replace the user's nested task plan. Use it for multi-step goals before executing work.", schemas=ToolSchema(properties=[ToolParameter(name="goal", description="User goal", required=True), ToolParameter(name="summary", description="Planning summary", required=True), ToolParameter(name="tasks", type="array", description="Nested tasks with title, description, priority, estimated_minutes and subtasks", required=True)]), handler=set_task_plan),
        Tool(name="update_task_status", description="Update a planned task as work progresses.", schemas=ToolSchema(properties=[ToolParameter(name="task_id", description="Task ID from the current plan", required=True), ToolParameter(name="status", description="not_started, in_progress, completed or blocked", enum=sorted(_STATUSES), required=True)]), handler=update_task_status),
    ]
