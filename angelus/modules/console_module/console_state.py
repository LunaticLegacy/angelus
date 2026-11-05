"""Typed durable console state; JSON is storage, dataclasses are the domain."""
from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
import json
import re
import threading
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from ..execution_module.checkpoint_store import _write_json_atomically
from ..settings_module.json_store import (
    JsonSchemaError,
    optional_string,
    reject_unknown_keys,
    require_int,
    require_list,
    require_mapping,
    require_number,
    require_string,
    string_list,
    string_list_map,
    string_map,
)


class ConsoleDomainError(ValueError):
    """A safe, user-visible failure caused by a console operation."""


_CONSOLE_LOCKS: dict[Path, threading.RLock] = {}
_CONSOLE_LOCKS_GUARD = threading.Lock()


def _console_lock(path: Path) -> threading.RLock:
    """Return the process-local lock shared by every ConsoleState for a path."""
    key = path.resolve()
    with _CONSOLE_LOCKS_GUARD:
        return _CONSOLE_LOCKS.setdefault(key, threading.RLock())


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
        """Decode exactly one documented on-disk schema, or fail.

        :meth:`to_json` emits ``asdict(self)``; this decoder consumes that same
        shape, so every persisted field has exactly one reader.  That includes
        ``WorkerBlueprint.role``, which the previous tolerant decoder dropped.
        Schema version 1 stored one flat ``plan`` list instead of per-agent
        ``plans``; that legacy shape stays readable.

        Args:
            value: Decoded JSON value read from the state file.

        Returns:
            Valid typed blueprint.

        Raises:
            ConsoleDomainError: If the document declares an unsupported
                version, carries an unknown field, or holds a wrong-typed value.
        """
        try:
            document = require_mapping(value, "console state")
            version = _schema_version(document)
            reject_unknown_keys(
                document,
                _BLUEPRINT_FIELDS_V1 if version == 1 else _BLUEPRINT_FIELDS_V2,
                f"console state schema {version}",
            )
            workers = _decode_workers(document.get("workers", {}))
            connections = _decode_connections(document.get("connections", []))
            mappers = string_map(document.get("mappers", {}), "console state.mappers")
            routers = string_list_map(
                document.get("routers", {}), "console state.routers"
            )
            plans = _decode_plans(document.get("plans", {}))
            if version == 1 and not plans:
                plans = _decode_legacy_plan(document.get("plan", []))
        except JsonSchemaError as exc:
            raise ConsoleDomainError(f"invalid console state: {exc}") from exc
        return cls(
            workers=workers,
            connections=connections,
            mappers=mappers,
            routers=routers,
            plans=plans,
            schema_version=_SCHEMA_VERSION,
        )


class ConsoleState:
    """Atomically persist one Session's typed topology and task plan."""
    NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")

    def __init__(self, root: Path) -> None:
        """Open state below the given Session directory.

        Args:
            root: Durable root directory assigned to the owning Session.
        """
        self.root = root / "console"; self.path = self.root / "state.json"; self._lock = _console_lock(self.path); self._blueprint = self._load()

    def _load(self) -> ConsoleBlueprint:
        """Load prior state or initialize an empty blueprint.

        A missing document initializes an empty blueprint. An existing corrupt
        document is isolated before the error is surfaced, so the next start
        cannot silently overwrite user state.
        """
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ConsoleBlueprint()
        except OSError as exc:
            raise ConsoleDomainError(f"cannot read console state: {self.path}") from exc
        try:
            return ConsoleBlueprint.from_json(json.loads(raw))
        except (json.JSONDecodeError, ConsoleDomainError) as exc:
            quarantine = self.path.with_name(
                f"{self.path.name}.corrupt-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}-{uuid4().hex[:8]}"
            )
            try:
                self.path.replace(quarantine)
            except OSError as quarantine_error:
                raise ConsoleDomainError(
                    f"invalid console state and could not isolate it: {self.path}"
                ) from quarantine_error
            raise ConsoleDomainError(
                f"invalid console state; isolated as {quarantine.name}"
            ) from exc

    @contextmanager
    def transaction(self) -> Iterator["ConsoleState"]:
        """Hold one per-Session write transaction across read-modify-write.

        The lock is reentrant so mutations and :meth:`save` remain callable
        inside the transaction. Callers must use this boundary when they need
        to capture a snapshot, mutate, apply a live change, and optionally
        restore the snapshot as one atomic unit.

        Yields:
            This state object while its per-Session lock is held.
        """
        with self._lock:
            yield self

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
        with self._lock: return deepcopy(self._blueprint)

    def replace(self, blueprint: ConsoleBlueprint) -> None:
        """Restore a previously captured blueprint after a failed mutation.

        Args:
            blueprint: Isolated snapshot returned by :meth:`blueprint`.

        Returns:
            None. The restored snapshot is persisted atomically.
        """
        with self._lock:
            self._blueprint = deepcopy(blueprint)
            self.save()

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
            plan = deepcopy(self._blueprint.plans.get(agent, TaskPlan()))
            return plan

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
_SCHEMA_VERSION = 2
_BLUEPRINT_FIELDS_V1 = {
    "schema_version", "workers", "connections", "mappers", "routers", "plan",
}
_BLUEPRINT_FIELDS_V2 = {
    "schema_version", "workers", "connections", "mappers", "routers", "plans",
}
_WORKER_FIELDS = {"name", "system_prompt", "role"}
_CONNECTION_FIELDS = {"source", "target"}
_PLAN_FIELDS = {"goal", "summary", "tasks", "updated_at"}
_ITEM_FIELDS = {
    "id", "title", "description", "status", "priority",
    "estimated_minutes", "subtasks", "execution",
}
_LEGACY_ITEM_FIELDS = _ITEM_FIELDS | {"agent"}
_EXECUTION_FIELDS = {"assignment_ids", "active_assignment_id", "updated_at"}


def _schema_version(document: Mapping[str, object]) -> int:
    """Return the declared schema version; absence means the v1 layout."""
    if "schema_version" not in document:
        return 1
    version = require_int(document["schema_version"], "console state.schema_version")
    if version not in (1, 2):
        raise JsonSchemaError(
            f"console state.schema_version is not supported: {version}"
        )
    return version


def _decode_workers(value: object) -> dict[str, WorkerBlueprint]:
    """Decode the worker map, including the role the old decoder dropped."""
    raw_workers = require_mapping(value, "console state.workers")
    workers: dict[str, WorkerBlueprint] = {}
    for name, item in raw_workers.items():
        where = f"console state.workers[{name}]"
        if not ConsoleState.NAME.fullmatch(name):
            raise JsonSchemaError(f"{where} is not a valid agent name")
        worker = require_mapping(item, where)
        reject_unknown_keys(worker, _WORKER_FIELDS, where)
        declared = optional_string(worker, "name", name, where)
        if declared != name:
            raise JsonSchemaError(f"{where}.name does not match its key")
        workers[name] = WorkerBlueprint(
            name=name,
            system_prompt=optional_string(worker, "system_prompt", "", where),
            role=optional_string(worker, "role", "worker", where),
        )
    return workers


def _decode_connections(value: object) -> list[ConnectionBlueprint]:
    """Decode the directed topology edges."""
    raw_connections = require_list(value, "console state.connections")
    connections: list[ConnectionBlueprint] = []
    for index, item in enumerate(raw_connections):
        where = f"console state.connections[{index}]"
        connection = require_mapping(item, where)
        reject_unknown_keys(connection, _CONNECTION_FIELDS, where)
        connections.append(
            ConnectionBlueprint(
                source=require_string(connection.get("source"), f"{where}.source"),
                target=require_string(connection.get("target"), f"{where}.target"),
            )
        )
    return connections


def _decode_plans(value: object) -> dict[str, TaskPlan]:
    """Decode one task plan per owning Agent."""
    raw_plans = require_mapping(value, "console state.plans")
    return {
        agent: _decode_plan(plan, f"console state.plans[{agent}]")
        for agent, plan in raw_plans.items()
    }


def _decode_legacy_plan(value: object) -> dict[str, TaskPlan]:
    """Decode the schema-v1 flat list, preserving each item's owner.

    Args:
        value: The legacy ``plan`` array.

    Returns:
        One TaskPlan per owner; unowned items belong to the coordinator.
    """
    grouped: dict[str, list[PlanItem]] = {}
    for index, item in enumerate(require_list(value, "console state.plan")):
        where = f"console state.plan[{index}]"
        raw_item = require_mapping(item, where)
        owner = optional_string(raw_item, "agent", "coordinator", where)
        grouped.setdefault(owner, []).append(_decode_item(raw_item, where, legacy=True))
    return {agent: TaskPlan(tasks=tuple(items)) for agent, items in grouped.items()}


def _decode_plan(value: object, where: str) -> TaskPlan:
    """Decode one complete per-Agent plan."""
    plan = require_mapping(value, where)
    reject_unknown_keys(plan, _PLAN_FIELDS, where)
    return TaskPlan(
        goal=optional_string(plan, "goal", "", where),
        summary=optional_string(plan, "summary", "", where),
        tasks=tuple(
            _decode_item(item, f"{where}.tasks[{index}]")
            for index, item in enumerate(
                require_list(plan.get("tasks", []), f"{where}.tasks")
            )
        ),
        updated_at=optional_string(plan, "updated_at", "", where),
    )


def _decode_item(value: object, where: str, *, legacy: bool = False) -> PlanItem:
    """Decode one recursively nested task, validating write-side invariants."""
    item = require_mapping(value, where)
    reject_unknown_keys(item, _LEGACY_ITEM_FIELDS if legacy else _ITEM_FIELDS, where)
    task_id = require_string(item.get("id"), f"{where}.id")
    if not task_id:
        raise JsonSchemaError(f"{where}.id must not be empty")
    status = optional_string(item, "status", "not_started", where)
    if status not in _PLAN_STATUSES:
        raise JsonSchemaError(f"{where}.status is not supported: {status}")
    priority = optional_string(item, "priority", "medium", where)
    if priority not in _PLAN_PRIORITIES:
        raise JsonSchemaError(f"{where}.priority is not supported: {priority}")
    raw_estimate = item.get("estimated_minutes")
    estimated_minutes = None
    if raw_estimate is not None:
        estimated_minutes = require_number(raw_estimate, f"{where}.estimated_minutes")
        if estimated_minutes < 0:
            raise JsonSchemaError(f"{where}.estimated_minutes must not be negative")
    return PlanItem(
        id=task_id,
        title=optional_string(item, "title", "", where),
        description=optional_string(item, "description", "", where),
        status=status,
        priority=priority,
        estimated_minutes=estimated_minutes,
        subtasks=tuple(
            _decode_item(child, f"{where}.subtasks[{index}]")
            for index, child in enumerate(
                require_list(item.get("subtasks", []), f"{where}.subtasks")
            )
        ),
        execution=_decode_execution(item.get("execution"), f"{where}.execution"),
    )


def _decode_execution(value: object, where: str) -> PlanExecution | None:
    """Decode the optional TaskBus correlation attached to one task."""
    if value is None:
        return None
    execution = require_mapping(value, where)
    reject_unknown_keys(execution, _EXECUTION_FIELDS, where)
    return PlanExecution(
        assignment_ids=tuple(
            string_list(
                execution.get("assignment_ids", []), f"{where}.assignment_ids"
            )
        ),
        active_assignment_id=optional_string(
            execution, "active_assignment_id", "", where
        ),
        updated_at=optional_string(execution, "updated_at", "", where),
    )


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
