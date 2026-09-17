"""Typed durable console state; JSON is storage, dataclasses are the domain."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
import json
import re
import threading
from pathlib import Path
from uuid import uuid4

from ..execution_module.checkpoint_store import _write_json_atomically


class ConsoleDomainError(ValueError):
    """A safe, user-visible failure caused by a console operation."""


@dataclass(frozen=True)
class WorkerBlueprint:
    """Secret-free persisted definition of one reusable worker role."""
    name: str
    system_prompt: str = ""
    role: str = "worker"


@dataclass(frozen=True)
class ConnectionBlueprint:
    """One directed dependency in the static Session topology."""
    source: str
    target: str


@dataclass(frozen=True)
class PlanExecution:
    """Durable correlation between a plan leaf and TaskBus assignments."""
    assignment_ids: tuple[str, ...] = ()
    active_assignment_id: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class PlanItem:
    """One recursively nested Agent-authored task."""
    id: str
    title: str = ""
    description: str = ""
    status: str = "not_started"
    priority: str = "medium"
    estimated_minutes: float | None = None
    subtasks: tuple["PlanItem", ...] = ()
    execution: PlanExecution | None = None


@dataclass(frozen=True)
class TaskPlan:
    """One complete plan owned by a concrete Agent."""
    goal: str = ""
    summary: str = ""
    tasks: tuple[PlanItem, ...] = ()
    updated_at: str = ""

    def __getitem__(self, index: int) -> PlanItem:
        """Retain read compatibility with the former flat plan list."""
        return self.tasks[index]

    def __iter__(self):
        """Iterate root tasks for compatibility with legacy callers."""
        return iter(self.tasks)


@dataclass
class ConsoleBlueprint:
    """Complete serializable console state owned by one Session."""
    workers: dict[str, WorkerBlueprint] = field(default_factory=dict)
    connections: list[ConnectionBlueprint] = field(default_factory=list)
    mappers: dict[str, str] = field(default_factory=dict)
    routers: dict[str, list[str]] = field(default_factory=dict)
    plans: dict[str, TaskPlan] = field(default_factory=dict)
    schema_version: int = 2

    def to_json(self) -> dict[str, object]:
        """Encode the typed blueprint without secrets or runtime objects.

        Returns:
            JSON-compatible representation safe for durable storage.
        """
        return asdict(self)

    @classmethod
    def from_json(cls, value: object) -> "ConsoleBlueprint":
        """Decode a tolerant on-disk document, ignoring malformed entries.

        Args:
            value: Decoded JSON value read from the state file.

        Returns:
            Valid typed blueprint, or an empty blueprint for invalid input.
        """
        if not isinstance(value, dict): return cls()
        raw_workers = value.get("workers", {})
        workers = {name: WorkerBlueprint(name=name, system_prompt=str(item.get("system_prompt", ""))) for name, item in raw_workers.items() if isinstance(name, str) and isinstance(item, dict)} if isinstance(raw_workers, dict) else {}
        connections = [
            ConnectionBlueprint(str(item["source"]), str(item["target"]))
            for item in value.get("connections", [])
            if isinstance(item, dict) and isinstance(item.get("source"), str) and isinstance(item.get("target"), str)
        ]
        mappers = {name: mode for name, mode in value.get("mappers", {}).items() if isinstance(name, str) and isinstance(mode, str)} if isinstance(value.get("mappers"), dict) else {}
        routers = {name: [target for target in targets if isinstance(target, str)] for name, targets in value.get("routers", {}).items() if isinstance(name, str) and isinstance(targets, list)} if isinstance(value.get("routers"), dict) else {}
        plans: dict[str, TaskPlan] = {}
        raw_plans = value.get("plans", {})
        if isinstance(raw_plans, dict):
            for agent, raw_plan in raw_plans.items():
                if isinstance(agent, str) and isinstance(raw_plan, dict):
                    plans[agent] = _decode_plan(raw_plan)
        # Schema-v1 stored one flat list. Preserve ownership where present and
        # place unowned items under the coordinator rather than dropping them.
        raw_legacy = value.get("plan", [])
        if not plans and isinstance(raw_legacy, list):
            grouped: dict[str, list[PlanItem]] = {}
            for item in raw_legacy:
                if not isinstance(item, dict):
                    continue
                decoded = _decode_item(item)
                if decoded is not None:
                    grouped.setdefault(str(item.get("agent") or "coordinator"), []).append(decoded)
            plans = {agent: TaskPlan(tasks=tuple(items)) for agent, items in grouped.items()}
        return cls(workers=workers, connections=connections, mappers=mappers, routers=routers, plans=plans, schema_version=2)


class ConsoleState:
    """Atomically persist one Session's typed topology and task plan."""
    NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")

    def __init__(self, root: Path) -> None:
        """Open state below the given Session directory.

        Args:
            root: Durable root directory assigned to the owning Session.
        """
        self.root = root / "console"; self.path = self.root / "state.json"; self._lock = threading.RLock(); self._blueprint = self._load()

    def _load(self) -> ConsoleBlueprint:
        """Load prior state or initialize an empty blueprint."""
        try: return ConsoleBlueprint.from_json(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError): return ConsoleBlueprint()

    def save(self) -> None:
        """Atomically commit the current secret-free blueprint.

        Returns:
            None. The write is fsynced before this method returns.
        """
        with self._lock: _write_json_atomically(self.path, self._blueprint.to_json())

    def blueprint(self) -> ConsoleBlueprint:
        """Return an isolated typed snapshot for projection or swarm rebuild.

        Returns:
            Copy of the current blueprint that callers may inspect safely.
        """
        with self._lock: return ConsoleBlueprint.from_json(self._blueprint.to_json())

    def add_worker(self, name: str, system_prompt: str = "") -> None:
        """Add a worker after validating its stable identity.

        Args:
            name: Unique graph-safe worker identity.
            system_prompt: Worker-specific system instructions; never a secret.

        Raises:
            ConsoleDomainError: If the name is invalid or already exists.
        """
        if not self.NAME.fullmatch(name) or name == "coordinator": raise ConsoleDomainError("agent name must be a unique alphanumeric identifier")
        with self._lock:
            if name in self._blueprint.workers: raise ConsoleDomainError(f"agent already exists: {name}")
            self._blueprint.workers[name] = WorkerBlueprint(name, system_prompt); self.save()

    def remove_worker(self, name: str) -> None:
        """Remove a worker and every persisted setting that references it.

        Args:
            name: Existing worker identity to remove.

        Raises:
            ConsoleDomainError: If the worker is missing or is the coordinator.
        """
        if name == "coordinator": raise ConsoleDomainError("the coordinator cannot be removed")
        with self._lock:
            if name not in self._blueprint.workers: raise ConsoleDomainError(f"unknown agent: {name}")
            del self._blueprint.workers[name]
            self._blueprint.connections = [edge for edge in self._blueprint.connections if name not in (edge.source, edge.target)]
            self._blueprint.mappers.pop(name, None)
            self._blueprint.routers.pop(name, None)
            for source, targets in tuple(self._blueprint.routers.items()):
                self._blueprint.routers[source] = [target for target in targets if target != name]
            self.save()

    def _nodes(self) -> set[str]: return {"coordinator", *self._blueprint.workers}

    def add_connection(self, source: str, target: str) -> None:
        """Add a dependency, rejecting duplicates, self-links, and cycles.

        Args:
            source: Upstream Agent identity.
            target: Downstream Agent identity.

        Raises:
            ConsoleDomainError: If either role is unknown or the edge is invalid.
        """
        with self._lock:
            if source not in self._nodes() or target not in self._nodes(): raise ConsoleDomainError("connection refers to an unknown agent")
            if source == target: raise ConsoleDomainError("an agent cannot connect to itself")
            edge = ConnectionBlueprint(source, target)
            if edge in self._blueprint.connections: raise ConsoleDomainError("connection already exists")
            adjacency: dict[str, set[str]] = {}
            for item in self._blueprint.connections: adjacency.setdefault(item.source, set()).add(item.target)
            stack, seen = [target], set()
            while stack:
                current = stack.pop()
                if current == source: raise ConsoleDomainError("connection would create a cycle")
                if current not in seen: seen.add(current); stack.extend(adjacency.get(current, ()))
            self._blueprint.connections.append(edge); self.save()

    def remove_connection(self, source: str, target: str) -> None:
        """Remove one existing dependency edge.

        Args:
            source: Upstream Agent identity.
            target: Downstream Agent identity.

        Raises:
            ConsoleDomainError: If the connection is absent.
        """
        with self._lock:
            edge = ConnectionBlueprint(source, target)
            if edge not in self._blueprint.connections: raise ConsoleDomainError("connection does not exist")
            self._blueprint.connections.remove(edge); self.save()

    def mapper(self, agent: str, mode: str) -> None:
        """Store one supported declarative predecessor-output mapper.

        Args:
            agent: Agent receiving predecessor outputs.
            mode: One of ``concat``, ``json``, or ``labelled``.

        Raises:
            ConsoleDomainError: If the Agent or mapper mode is invalid.
        """
        if mode not in {"concat", "json", "labelled"}: raise ConsoleDomainError("mapper mode must be concat, json, or labelled")
        with self._lock:
            if agent not in self._nodes(): raise ConsoleDomainError("unknown agent")
            self._blueprint.mappers[agent] = mode; self.save()

    def router(self, agent: str, targets: list[str]) -> None:
        """Store a fixed safe router target set for an Agent.

        Args:
            agent: Source Agent whose completion selects targets.
            targets: Existing Agent identities selected by the router.

        Raises:
            ConsoleDomainError: If any referenced Agent is unknown.
        """
        with self._lock:
            if agent not in self._nodes() or any(target not in self._nodes() for target in targets): raise ConsoleDomainError("router refers to an unknown agent")
            self._blueprint.routers[agent] = list(dict.fromkeys(targets)); self.save()

    def plan(self, agent: str = "coordinator") -> TaskPlan:
        """Return one Agent's complete typed plan snapshot.

        Args:
            agent: Concrete plan owner.

        Returns:
            Isolated recursive plan, empty when the Agent has no plan.
        """
        with self._lock:
            plan = self._blueprint.plans.get(agent, TaskPlan())
            return _decode_plan(asdict(plan))

    def set_plan(self, agent: str, goal: str, summary: str, tasks: list[dict[str, object]]) -> TaskPlan:
        """Validate and atomically replace one complete recursive plan.

        Args:
            agent: Concrete Agent owning the plan.
            goal: Overall outcome.
            summary: Compact planning rationale.
            tasks: Full nested task tree.
        """
        if not isinstance(tasks, list):
            raise ConsoleDomainError("tasks must be an array")
        if not str(goal).strip():
            raise ConsoleDomainError("plan goal is required")
        seen: set[str] = set()
        normalized = tuple(_normalize_item(item, seen) for item in tasks)
        plan = TaskPlan(
            goal=str(goal).strip()[:4_000], summary=str(summary).strip()[:12_000],
            tasks=tuple(_derive_status(item) for item in normalized),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self._blueprint.plans[agent] = plan
            self.save()
        return plan

    def update_task_status(self, agent: str, task_id: str, status: str) -> TaskPlan:
        """Update one leaf and reconcile all ancestor states.

        Args:
            agent: Concrete plan owner.
            task_id: Existing leaf identity.
            status: Supported lifecycle state.

        Returns:
            None. The changed plan is atomically persisted.
        """
        if status not in _PLAN_STATUSES:
            raise ConsoleDomainError("invalid task status")
        with self._lock:
            plan = self._blueprint.plans.get(agent)
            if plan is None:
                raise ConsoleDomainError("task plan is not initialized")
            found = False
            def change(item: PlanItem) -> PlanItem:
                nonlocal found
                if item.id == task_id:
                    if item.subtasks:
                        raise ConsoleDomainError("parent task status is derived from subtasks")
                    found = True
                    return replace(item, status=status)
                children = tuple(change(child) for child in item.subtasks)
                return _derive_status(replace(item, subtasks=children))
            tasks = tuple(change(item) for item in plan.tasks)
            if not found:
                raise ConsoleDomainError("unknown task id")
            updated = TaskPlan(plan.goal, plan.summary, tasks, datetime.now(timezone.utc).isoformat())
            self._blueprint.plans[agent] = updated
            self.save()
            return updated

    def has_task(self, task_id: str) -> bool:
        """Return whether any Agent plan contains a task identity."""
        with self._lock:
            return any(_find_task(plan.tasks, task_id) is not None for plan in self._blueprint.plans.values())

    def is_bindable_leaf(self, task_id: str) -> bool:
        """Return whether an existing task is a leaf in any Agent plan."""
        with self._lock:
            return any((item := _find_task(plan.tasks, task_id)) is not None and not item.subtasks for plan in self._blueprint.plans.values())

    def bind_execution(self, task_id: str, assignment_id: str) -> None:
        """Bind a TaskBus assignment to a plan leaf and mark it in progress."""
        if not assignment_id.strip(): raise ConsoleDomainError("assignment id is required")
        with self._lock:
            owner = next((name for name, plan in self._blueprint.plans.items() if _find_task(plan.tasks, task_id) is not None), None)
            if owner is None: raise ConsoleDomainError("unknown task id")
            plan = self._blueprint.plans[owner]
            def bind(item: PlanItem) -> PlanItem:
                if item.id == task_id:
                    if item.subtasks: raise ConsoleDomainError("only a leaf task can be bound")
                    previous = item.execution or PlanExecution()
                    ids = tuple(dict.fromkeys((*previous.assignment_ids, assignment_id)))
                    return replace(item, status="in_progress", execution=PlanExecution(ids, assignment_id, datetime.now(timezone.utc).isoformat()))
                return _derive_status(replace(item, subtasks=tuple(bind(child) for child in item.subtasks)))
            self._blueprint.plans[owner] = TaskPlan(plan.goal, plan.summary, tuple(bind(item) for item in plan.tasks), datetime.now(timezone.utc).isoformat())
            self.save()

    def update_assignment_status(self, assignment_id: str, status: str) -> None:
        """Update only the leaf whose active assignment matches the report."""
        if status not in _PLAN_STATUSES: raise ConsoleDomainError("invalid task status")
        with self._lock:
            for owner, plan in tuple(self._blueprint.plans.items()):
                changed = False
                def update(item: PlanItem) -> PlanItem:
                    nonlocal changed
                    if item.execution is not None and item.execution.active_assignment_id == assignment_id:
                        changed = True
                        return replace(item, status=status, execution=replace(item.execution, updated_at=datetime.now(timezone.utc).isoformat()))
                    return _derive_status(replace(item, subtasks=tuple(update(child) for child in item.subtasks)))
                tasks = tuple(update(item) for item in plan.tasks)
                if changed:
                    self._blueprint.plans[owner] = TaskPlan(plan.goal, plan.summary, tasks, datetime.now(timezone.utc).isoformat())
                    self.save(); return


_PLAN_STATUSES = {"not_started", "in_progress", "completed", "blocked"}
_PLAN_PRIORITIES = {"low", "medium", "high", "critical"}


def _decode_item(value: object) -> PlanItem | None:
    if not isinstance(value, dict) or not isinstance(value.get("id"), str):
        return None
    children = tuple(item for raw in value.get("subtasks", []) if (item := _decode_item(raw)) is not None) if isinstance(value.get("subtasks", []), (list, tuple)) else ()
    estimate = value.get("estimated_minutes")
    raw_execution = value.get("execution")
    execution = None
    if isinstance(raw_execution, dict):
        raw_ids = raw_execution.get("assignment_ids", [])
        execution = PlanExecution(tuple(str(x) for x in raw_ids if str(x)) if isinstance(raw_ids, (list, tuple)) else (), str(raw_execution.get("active_assignment_id", "")), str(raw_execution.get("updated_at", "")))
    return PlanItem(
        id=value["id"], title=str(value.get("title", "")), description=str(value.get("description", "")),
        status=str(value.get("status", "not_started")), priority=str(value.get("priority", "medium")),
        estimated_minutes=float(estimate) if isinstance(estimate, (int, float)) else None, subtasks=children, execution=execution,
    )


def _decode_plan(value: dict[str, object]) -> TaskPlan:
    raw_tasks = value.get("tasks", [])
    tasks = tuple(item for raw in raw_tasks if (item := _decode_item(raw)) is not None) if isinstance(raw_tasks, (list, tuple)) else ()
    return TaskPlan(str(value.get("goal", "")), str(value.get("summary", "")), tasks, str(value.get("updated_at", "")))


def _normalize_item(value: object, seen: set[str]) -> PlanItem:
    if not isinstance(value, dict):
        raise ConsoleDomainError("every task must be an object")
    task_id = str(value.get("id") or value.get("task_id") or f"task_{uuid4().hex[:12]}").strip()
    if not task_id or task_id in seen:
        raise ConsoleDomainError("task IDs must be non-empty and unique")
    seen.add(task_id)
    status = str(value.get("status", "not_started"))
    priority = str(value.get("priority", "medium"))
    if status not in _PLAN_STATUSES or priority not in _PLAN_PRIORITIES:
        raise ConsoleDomainError("task has an invalid status or priority")
    raw_children = value.get("subtasks", [])
    if not isinstance(raw_children, list):
        raise ConsoleDomainError("subtasks must be an array")
    estimate = value.get("estimated_minutes")
    if estimate is not None and (not isinstance(estimate, (int, float)) or estimate < 0):
        raise ConsoleDomainError("estimated_minutes must be a non-negative number")
    title = str(value.get("title", "")).strip()
    if not title: raise ConsoleDomainError("every task needs a title")
    raw_execution = value.get("execution")
    execution = None
    if isinstance(raw_execution, dict):
        raw_ids = raw_execution.get("assignment_ids", [])
        execution = PlanExecution(tuple(str(x) for x in raw_ids if str(x)) if isinstance(raw_ids, (list, tuple)) else (), str(raw_execution.get("active_assignment_id", "")), str(raw_execution.get("updated_at", "")))
    return PlanItem(task_id, title[:1_000], str(value.get("description", ""))[:12_000], status, priority, float(estimate) if estimate is not None else None, tuple(_normalize_item(item, seen) for item in raw_children), execution)


def _derive_status(item: PlanItem) -> PlanItem:
    if not item.subtasks:
        return item
    children = tuple(_derive_status(child) for child in item.subtasks)
    states = {child.status for child in children}
    if states == {"completed"}: status = "completed"
    elif "blocked" in states: status = "blocked"
    elif states == {"not_started"}: status = "not_started"
    else: status = "in_progress"
    return PlanItem(item.id, item.title, item.description, status, item.priority, item.estimated_minutes, children, item.execution)


def _find_task(items: tuple[PlanItem, ...], task_id: str) -> PlanItem | None:
    for item in items:
        if item.id == task_id:
            return item
        found = _find_task(item.subtasks, task_id)
        if found is not None:
            return found
    return None
