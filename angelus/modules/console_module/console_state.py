"""Typed durable console state; JSON is storage, dataclasses are the domain."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import re
import threading
from pathlib import Path

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
class PlanItem:
    """A durable Agent-authored task-plan item."""
    id: str
    status: str
    agent: str = ""
    title: str = ""


@dataclass
class ConsoleBlueprint:
    """Complete serializable console state owned by one Session."""
    workers: dict[str, WorkerBlueprint] = field(default_factory=dict)
    connections: list[ConnectionBlueprint] = field(default_factory=list)
    mappers: dict[str, str] = field(default_factory=dict)
    routers: dict[str, list[str]] = field(default_factory=dict)
    plan: list[PlanItem] = field(default_factory=list)
    schema_version: int = 1

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
        plan = [PlanItem(id=item["id"], status=item["status"], agent=str(item.get("agent", "")), title=str(item.get("title", ""))) for item in value.get("plan", []) if isinstance(item, dict) and isinstance(item.get("id"), str) and isinstance(item.get("status"), str)]
        return cls(workers=workers, connections=connections, mappers=mappers, routers=routers, plan=plan, schema_version=int(value.get("schema_version", 1)))


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

    def plan(self, agent: str | None = None) -> list[PlanItem]:
        """Return a typed plan snapshot optionally scoped to one Agent.

        Args:
            agent: Optional Agent identity used to filter plan ownership.

        Returns:
            Copy of matching durable plan items in stored order.
        """
        with self._lock: return [item for item in self._blueprint.plan if not agent or item.agent == agent]

    def set_plan(self, items: list[PlanItem]) -> None:
        """Replace the plan with already-validated Agent-authored items.

        Args:
            items: Typed plan items supplied by the controlled plan tool.
        """
        with self._lock: self._blueprint.plan = list(items); self.save()

    def upsert_plan_item(self, item: PlanItem) -> None:
        """Create or replace a durable task-plan item by identity.

        Args:
            item: Typed Agent-authored item whose ``id`` is stable within the
                owning Session plan.

        Returns:
            None. The changed plan is atomically persisted.
        """
        with self._lock:
            self._blueprint.plan = [current for current in self._blueprint.plan if current.id != item.id]
            self._blueprint.plan.append(item)
            self.save()
