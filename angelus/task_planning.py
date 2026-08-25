"""Persistent task plans and Agent tools for supervising user work."""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from llmfetcher.llm_types import Tool, ToolParameter, ToolSchema

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
        normalized_tasks = self._normalize_tasks(tasks)
        self._assert_unique_ids(normalized_tasks)
        plan = {"goal": goal.strip(), "summary": summary.strip(), "tasks": normalized_tasks, "updated_at": time.time()}
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
            task = self._find_task(plan.get("tasks", []), task_id)
            if task is None:
                raise ValueError(f"Unknown task: {task_id}")
            if task.get("subtasks"):
                raise ValueError(
                    "Parent task status is derived from its subtasks; update a leaf task instead"
                )
            task["status"] = status
            self._reconcile_parent_statuses(plan.get("tasks", []))
            plan["updated_at"] = time.time()
            self._write(plan)
        return plan

    def bind_execution(self, task_id: str, assignment_id: str) -> dict[str, Any]:
        """Bind one dispatched Swarm assignment to a leaf task.

        Args:
            task_id: Stable ID of a leaf in this plan.
            assignment_id: Stable TaskBus assignment ID created for that leaf.

        Returns:
            The updated plan with durable execution correlation metadata.

        Raises:
            ValueError: If either ID is blank, the task is unknown, or the
                selected task is a parent whose status must remain derived.
        """
        normalized_assignment = assignment_id.strip()
        if not normalized_assignment:
            raise ValueError("Swarm assignment ID is required")
        with self._lock:
            plan = self.read()
            task = self._find_task(plan.get("tasks", []), task_id)
            if task is None:
                raise ValueError(f"Unknown task: {task_id}")
            if task.get("subtasks"):
                raise ValueError("Only a leaf task can be bound to a Swarm assignment")
            execution = task.setdefault("execution", {
                "assignment_ids": [], "active_assignment_id": "", "updated_at": None,
            })
            assignment_ids = execution.setdefault("assignment_ids", [])
            if normalized_assignment not in assignment_ids:
                assignment_ids.append(normalized_assignment)
            execution["active_assignment_id"] = normalized_assignment
            execution["updated_at"] = time.time()
            task["status"] = "in_progress"
            self._reconcile_parent_statuses(plan.get("tasks", []))
            plan["updated_at"] = time.time()
            self._write(plan)
        return plan

    def is_bindable_leaf(self, task_id: str) -> bool:
        """Return whether ``task_id`` currently names a coordinator-plan leaf."""
        with self._lock:
            task = self._find_task(self.read().get("tasks", []), task_id)
            return task is not None and not bool(task.get("subtasks"))

    def update_execution_status(
        self, task_id: str, assignment_id: str, status: str,
    ) -> dict[str, Any]:
        """Apply one authoritative Swarm lifecycle state to its bound leaf.

        Stale events from an earlier revival are retained for audit but cannot
        overwrite the active assignment's status.
        """
        if status not in _STATUSES:
            raise ValueError(f"Unknown task status: {status}")
        with self._lock:
            plan = self.read()
            task = self._find_task(plan.get("tasks", []), task_id)
            if task is None:
                raise ValueError(f"Unknown task: {task_id}")
            execution = task.get("execution")
            if not isinstance(execution, dict) or execution.get("active_assignment_id") != assignment_id:
                return plan
            task["status"] = status
            execution["updated_at"] = time.time()
            self._reconcile_parent_statuses(plan.get("tasks", []))
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
            normalized_task = {
                # ``task_id`` is retained as an input alias because models and
                # older clients commonly use it in tool arguments.  The public
                # persisted field remains the stable ``id``.
                "id": str(value.get("id") or value.get("task_id") or uuid.uuid4().hex), "title": str(value["title"]).strip(),
                "description": str(value.get("description", "")).strip(), "status": status,
                "priority": priority, "estimated_minutes": value.get("estimated_minutes"),
                "subtasks": self._normalize_tasks(value.get("subtasks", [])),
            }
            execution = value.get("execution")
            if isinstance(execution, Mapping):
                normalized_task["execution"] = {
                    "assignment_ids": [str(item) for item in execution.get("assignment_ids", []) if str(item)],
                    "active_assignment_id": str(execution.get("active_assignment_id", "")),
                    "updated_at": execution.get("updated_at"),
                }
            normalized.append(normalized_task)
        self._reconcile_parent_statuses(normalized)
        return normalized

    @staticmethod
    def _assert_unique_ids(tasks: list[dict[str, Any]]) -> None:
        """Reject duplicate task IDs before a plan can be bound to execution."""
        seen: set[str] = set()

        def visit(values: list[dict[str, Any]]) -> None:
            for task in values:
                task_id = str(task["id"])
                if task_id in seen:
                    raise ValueError(f"Duplicate task ID: {task_id}")
                seen.add(task_id)
                visit(task.get("subtasks", []))

        visit(tasks)

    @staticmethod
    def _find_task(tasks: list[dict[str, Any]], task_id: str) -> dict[str, Any] | None:
        """Return one task from a recursive plan tree by its stable ID."""
        for task in tasks:
            if task.get("id") == task_id:
                return task
            found = TaskPlanStore._find_task(task.get("subtasks", []), task_id)
            if found is not None:
                return found
        return None

    @staticmethod
    def _reconcile_parent_statuses(tasks: list[dict[str, Any]]) -> None:
        """Derive every parent state from its direct child states.

        Parent completion is never cascaded downward: marking a parent as
        complete must not invent evidence for unfinished descendants.
        """
        for task in tasks:
            children = task.get("subtasks", [])
            if not children:
                continue
            TaskPlanStore._reconcile_parent_statuses(children)
            states = {str(child.get("status", "not_started")) for child in children}
            if "blocked" in states:
                task["status"] = "blocked"
            elif "in_progress" in states:
                task["status"] = "in_progress"
            elif states == {"completed"}:
                task["status"] = "completed"
            else:
                task["status"] = "not_started"

    def _write(self, plan: Mapping[str, Any]) -> None:
        """Atomically write a normalized task plan to the session path."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f"{self.path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)


def create_task_planning_tools(
    store: TaskPlanStore,
    *,
    on_changed: Callable[[str, dict[str, Any]], None] | None = None,
) -> list[Tool]:
    """Create Agent tools that let a model publish and supervise a task plan.

    Args:
        store: Session-local task plan store mutated by the returned handlers.
        on_changed: Optional callback invoked as ``on_changed(event_type, plan)``
            after every successful plan mutation, where *event_type* is
            ``"plan:set"`` or ``"plan:status"``.

    Returns:
        ``read_task_plan``, ``set_task_plan`` and ``update_task_status`` Tool
        instances.
    """
    def read_task_plan() -> dict[str, Any]:
        """Return the current persisted task plan (goal, summary, nested tasks)."""
        return {"ok": True, "plan": store.read()}

    def set_task_plan(goal: str, summary: str, tasks: list[dict[str, Any]]) -> dict[str, Any]:
        """Persist a complete plan supplied by the model in structured arguments."""
        plan = store.replace(goal=goal, summary=summary, tasks=tasks)
        if on_changed is not None:
            on_changed("plan:set", plan)
        return {"ok": True, "plan": plan}

    def update_task_status(task_id: str, status: str) -> dict[str, Any]:
        """Persist a user-visible task status transition requested by the model."""
        plan = store.update_status(task_id, status)
        if on_changed is not None:
            on_changed("plan:status", plan)
        return {"ok": True, "plan": plan}

    return [
        Tool(name="read_task_plan", description="Read the current persisted task plan (goal, summary and nested tasks) without modifying it.", schemas=ToolSchema(properties=[]), handler=read_task_plan),
        Tool(name="set_task_plan", description="Create or replace the user's nested task plan. Use it for multi-step goals before executing work.", schemas=ToolSchema(properties=[ToolParameter(name="goal", description="User goal", required=True), ToolParameter(name="summary", description="Planning summary", required=True), ToolParameter(name="tasks", type="array", description="Nested tasks with title, optional stable id (or task_id), description, priority, estimated_minutes and subtasks", required=True)]), handler=set_task_plan),
        Tool(name="update_task_status", description="Update a planned task as work progresses.", schemas=ToolSchema(properties=[ToolParameter(name="task_id", description="Task ID from the current plan", required=True), ToolParameter(name="status", description="not_started, in_progress, completed or blocked", enum=sorted(_STATUSES), required=True)]), handler=update_task_status),
    ]
