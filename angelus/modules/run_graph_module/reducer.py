"""Deterministic reduction from current journal facts to :mod:`run_graph` state."""

from __future__ import annotations

from typing import Any, Mapping

from .models import RunGraph, RunNodeState, RunState


_NODE_STATES = {
    "idle": RunNodeState.PENDING, "pending": RunNodeState.PENDING,
    "queued": RunNodeState.QUEUED, "submitted": RunNodeState.RUNNING,
    "running": RunNodeState.RUNNING, "completed": RunNodeState.SUCCEEDED,
    "succeeded": RunNodeState.SUCCEEDED, "failed": RunNodeState.FAILED,
    "stopped": RunNodeState.STOPPED, "interrupted": RunNodeState.STOPPED,
    "cancelled": RunNodeState.CANCELLED, "skipped": RunNodeState.SKIPPED,
}


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def apply_live_snapshot(graph: RunGraph, snapshot: Mapping[str, Any]) -> None:
    """Seed or refresh a graph from llmfetcher's safe view snapshot."""
    assignments = snapshot.get("assignments", {})
    task_states = snapshot.get("task_states", {})
    node_states = snapshot.get("node_states", {})
    task_to_agent = assignments if isinstance(assignments, Mapping) else {}
    for raw in snapshot.get("nodes", []):
        if not isinstance(raw, Mapping) or not isinstance(raw.get("id"), str):
            continue
        node_id = raw["id"]
        node = graph.ensure_node(
            node_id, kind=str(raw.get("kind", "agent")),
            origin="runtime" if raw.get("dynamic") else "blueprint",
            parent_id=_text(raw.get("parent")),
        )
        record = node_states.get(node_id) if isinstance(node_states, Mapping) else None
        if isinstance(record, Mapping):
            state = _NODE_STATES.get(str(record.get("state", "")))
            if state is not None:
                node.state = state
            node.message = str(record.get("message", ""))
            node.updated_at = record.get("updated_at") if isinstance(record.get("updated_at"), (int, float)) else None
            node.task_id = _text(record.get("task_id")) or node.task_id
    for task_id, agent_id in task_to_agent.items():
        if not isinstance(task_id, str) or not isinstance(agent_id, str):
            continue
        node = graph.ensure_node(agent_id, origin="runtime")
        node.task_id = task_id
        state = task_states.get(task_id) if isinstance(task_states, Mapping) else None
        if isinstance(state, str) and state in _NODE_STATES:
            node.state = _NODE_STATES[state]
    for raw in snapshot.get("edges", []):
        if isinstance(raw, Mapping):
            graph.add_edge(str(raw.get("source", "")), str(raw.get("target", "")), str(raw.get("kind", "dependency")))


def apply_run_graph_snapshot(graph: RunGraph, snapshot: Mapping[str, Any]) -> None:
    """Hydrate a graph from a previously committed RunGraph checkpoint."""
    if snapshot.get("kind") != "angelus.run-graph":
        return
    graph.execution_id = _text(snapshot.get("execution_id")) or graph.execution_id
    graph.attempt = int(snapshot.get("attempt", 0)) if isinstance(snapshot.get("attempt"), int) else graph.attempt
    graph.state = _run_state(snapshot.get("state"), graph.state)
    graph.event_cursor = int(snapshot.get("event_cursor", 0)) if isinstance(snapshot.get("event_cursor"), int) else graph.event_cursor
    graph.started_at = snapshot.get("started_at") if isinstance(snapshot.get("started_at"), (int, float)) else graph.started_at
    graph.finished_at = snapshot.get("finished_at") if isinstance(snapshot.get("finished_at"), (int, float)) else graph.finished_at
    graph.error = _text(snapshot.get("error")) or graph.error
    graph.stop_reason = _text(snapshot.get("stop_reason")) or graph.stop_reason
    for raw in snapshot.get("nodes", []):
        if not isinstance(raw, Mapping) or not isinstance(raw.get("id"), str):
            continue
        node = graph.ensure_node(raw["id"], kind=str(raw.get("kind", "agent")), origin=str(raw.get("origin", "blueprint")), parent_id=_text(raw.get("parent_id")))
        node.state = _NODE_STATES.get(str(raw.get("state", "")), node.state)
        node.task_id = _text(raw.get("task_id")) or node.task_id
        node.plan_task_id = _text(raw.get("plan_task_id")) or node.plan_task_id
        node.message = str(raw.get("message", node.message))
        node.error = _text(raw.get("error")) or node.error
        node.reason = _text(raw.get("reason")) or node.reason
        node.updated_at = raw.get("updated_at") if isinstance(raw.get("updated_at"), (int, float)) else node.updated_at
    for raw in snapshot.get("edges", []):
        if isinstance(raw, Mapping):
            graph.add_edge(str(raw.get("source", "")), str(raw.get("target", "")), str(raw.get("kind", "dependency")))


def apply_journal_event(graph: RunGraph, event: Mapping[str, Any], *, cursor: int) -> None:
    """Apply one durable execution-journal record without side effects."""
    graph.event_cursor = cursor
    event_type = str(event.get("type", ""))
    data = event.get("data")
    data = data if isinstance(data, Mapping) else {}
    timestamp = event.get("timestamp")
    when = float(timestamp) if isinstance(timestamp, (int, float)) else None
    agent = _text(event.get("agent")) or _text(data.get("agent"))
    message = str(event.get("message", ""))

    if event_type == "execution_started":
        graph.state = RunState.RUNNING
        graph.started_at = when or graph.started_at
        return
    if event_type == "stop_requested":
        graph.state = RunState.FORCE_STOPPING if data.get("mode") == "force" else RunState.STOPPING
        graph.stop_reason = _text(data.get("reason"))
        return
    terminal = {
        "execution_completed": RunState.COMPLETED,
        "execution_failed": RunState.FAILED,
        "execution_stopped": RunState.STOPPED,
        "execution_interrupted": RunState.INTERRUPTED,
    }.get(event_type)
    if terminal is not None:
        graph.state = terminal
        graph.finished_at = when
        graph.error = _text(data.get("error")) or _text(data.get("reason")) or graph.error
        return
    if event_type == "checkpoint_committed":
        graph.checkpoint = dict(data)
        return
    if not agent:
        return
    node = graph.ensure_node(agent, origin="runtime" if _text(data.get("task_id")) else "blueprint")
    node.task_id = _text(data.get("task_id")) or node.task_id
    node.plan_task_id = _text(data.get("plan_task_id")) or node.plan_task_id
    node.message = message or node.message
    node.updated_at = when or node.updated_at
    if event_type == "task:dispatched":
        node.state = RunNodeState.QUEUED
    elif event_type in {"agent:completed", "agent:complete"}:
        node.state = RunNodeState.SUCCEEDED
    elif event_type in {"agent:failed", "agent:error", "task:report_missing"}:
        node.state = RunNodeState.FAILED
        node.error = _text(data.get("error")) or message or node.error
    elif event_type in {"agent:stopped", "agent:termination"}:
        node.state = RunNodeState.STOPPED
        node.reason = _text(data.get("reason")) or _text(data.get("termination")) or message or node.reason
    elif event_type == "task:finalized":
        node.state = _NODE_STATES.get(str(data.get("state", "")), node.state)
    elif event_type == "task:reported":
        node.state = _NODE_STATES.get(str(data.get("status", "")), node.state)
    elif event_type.startswith("agent:"):
        node.state = RunNodeState.RUNNING


def _run_state(value: object, fallback: RunState) -> RunState:
    try:
        return RunState(str(value))
    except ValueError:
        return fallback
