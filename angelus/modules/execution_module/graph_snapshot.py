"""Safe interruption evidence for a graph that cannot be resumed in place."""

from __future__ import annotations

import time
from typing import Any

from llmfetcher.swarm_module import ExecutionGraph


def interruption_snapshot(graph: ExecutionGraph, *, execution_id: str, reason: str) -> dict[str, Any]:
    """Capture live logical graph state without serializing threads or clients.

    This snapshot is deliberately not fed to ``ExecutionGraph.load``. Its
    running entries are evidence for recovery policy; only a previously
    committed quiescent llmfetcher graph snapshot may be restored as topology.
    """
    view = graph.view_snapshot()
    states = dict(view.get("node_states", {}))
    tasks = dict(view.get("task_states", {}))
    running_agents = [
        agent_id
        for agent_id, state in states.items()
        if isinstance(state, dict) and state.get("state") in {"running", "submitted"}
    ]
    return {
        "schema_version": 2,
        "kind": "angelus.graph-interruption",
        "execution_id": execution_id,
        "captured_at": time.time(),
        "reason": reason,
        "topology": {
            "nodes": view.get("nodes", []),
            "edges": view.get("edges", []),
            "max_concurrency_agents": view.get("max_concurrency_agents"),
            "assignments": view.get("assignments", {}),
        },
        "scheduler": {
            "node_states": states,
            "running_agents": running_agents,
        },
        "task_bus": {
            "task_states": tasks,
        },
        "recovery_policy": {
            "running_agents": "interrupted",
            "queued_tasks": "cancelled",
            "automatic_replay": False,
        },
    }
