"""Public JSON model for an execution attempt's graph projection."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class RunNodeState(StrEnum):
    """Normalized state exposed by the run-graph API."""

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    STOPPED = "stopped"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class RunState(StrEnum):
    """Attempt-wide state exposed by the run-graph API."""

    IDLE = "idle"
    RUNNING = "running"
    STOPPING = "stopping"
    FORCE_STOPPING = "force_stopping"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"
    INTERRUPTED = "interrupted"


@dataclass
class RunGraphNode:
    """One concrete node as it participated in a single attempt."""

    id: str
    kind: str = "agent"
    origin: str = "blueprint"
    parent_id: str | None = None
    state: RunNodeState = RunNodeState.PENDING
    task_id: str | None = None
    plan_task_id: str | None = None
    message: str = ""
    error: str | None = None
    reason: str | None = None
    updated_at: float | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "id": self.id, "kind": self.kind, "origin": self.origin,
            "parent_id": self.parent_id, "state": self.state,
            "task_id": self.task_id, "plan_task_id": self.plan_task_id,
            "message": self.message, "error": self.error,
            "reason": self.reason, "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class RunGraphEdge:
    """A relation between two graph nodes in one attempt."""

    source: str
    target: str
    kind: str = "dependency"

    def to_json(self) -> dict[str, str]:
        return {"source": self.source, "target": self.target, "kind": self.kind}


@dataclass
class RunGraph:
    """The versioned, transport-safe execution graph read model."""

    session_id: str
    execution_id: str | None
    attempt: int = 0
    state: RunState = RunState.IDLE
    nodes: dict[str, RunGraphNode] = field(default_factory=dict)
    edges: dict[tuple[str, str, str], RunGraphEdge] = field(default_factory=dict)
    event_cursor: int = 0
    started_at: float | None = None
    finished_at: float | None = None
    error: str | None = None
    stop_reason: str | None = None
    checkpoint: dict[str, object] | None = None

    def ensure_node(self, node_id: str, **changes: Any) -> RunGraphNode:
        node = self.nodes.get(node_id)
        if node is None:
            node = RunGraphNode(id=node_id)
            self.nodes[node_id] = node
        for key, value in changes.items():
            if value is not None and hasattr(node, key):
                setattr(node, key, value)
        return node

    def add_edge(self, source: str, target: str, kind: str = "dependency") -> None:
        if source and target:
            edge = RunGraphEdge(source, target, kind)
            self.edges[(source, target, kind)] = edge

    def to_json(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "kind": "angelus.run-graph",
            "session_id": self.session_id,
            "execution_id": self.execution_id,
            "attempt": self.attempt,
            "state": self.state,
            "nodes": [node.to_json() for _, node in sorted(self.nodes.items())],
            "edges": [edge.to_json() for _, edge in sorted(self.edges.items())],
            "event_cursor": self.event_cursor,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "stop_reason": self.stop_reason,
            "checkpoint": self.checkpoint,
        }
