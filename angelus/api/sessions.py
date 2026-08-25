"""Session, workspace, plan, graph, archive, usage and memory routes."""

from __future__ import annotations

import ipaddress
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..context_editing import ContextEditError, ContextEditOperation, ContextEditStore
from ..classes import (
    ProjectPathRequest,
    TaskPlanRequest,
    TaskStatusRequest,
    WorkspaceDeleteRequest,
    WorkspaceRequest,
)
from ..history import (
    _agent_compaction_input_preview,
    _agent_context_preview,
    _agent_context_graph,
    _agent_context_stats,
    _archived_context_page,
    _agent_turns_page,
    _read_agent_history,
    _session_usage_summary,
)
from ..runtime import _build_http_worker_agent, _plan_store, _session_memory_store
from ..session_memory import CAPABILITIES, SessionMemoryError
from .. import storage
from ..storage import (
    _deleting_workspaces,
    _get_session,
    _persist_json,
    _project_path,
    _iter_session_event_log,
    _read_workspaces,
    _remove_workspace,
    _safe_id,
    _context_path,
    _sessions,
    _sessions_lock,
    _session_event_page,
    _session_id_from_name,
    _session_path,
    _stop_then_remove_workspace,
    _validate_project_path,
    _write_workspaces,
)
from .runs import get_run_status
from ..event_stream import publish_durable_event

router = APIRouter()



@router.get("/api/workspaces")
def list_workspaces() -> dict[str, list[dict[str, str]]]:
    """List local workspaces available to the browser console."""
    return {"workspaces": _read_workspaces()}

@router.get("/api/sessions")
def list_sessions() -> dict[str, list[dict[str, Any]]]:
    """List browser sessions with a compact durable run-status indicator."""
    sessions: list[dict[str, Any]] = []
    for workspace in _read_workspaces():
        session_id = str(workspace.get("id", ""))
        if not session_id:
            continue
        persisted = get_run_status(session_id, session_id).get("status", "idle")
        indicator = {
            "running": "running",
            "force_stopping": "running",
            "error": "error",
            "interrupted": "error",
            "completed": "done",
            "stopped": "done",
        }.get(str(persisted), "idle")
        sessions.append({
            **workspace,
            "status": indicator,
            "path": str(_session_path(session_id, session_id)),
            "project_path": str(_project_path(session_id, session_id)),
        })
    return {"sessions": sessions}

@router.get("/api/workspace-root")
def workspace_root() -> dict[str, str]:
    """Return the on-disk state root that owns every browser session.

    The value is the ``.angelus`` state directory (or the legacy workspace
    root) that contains ``sessions.json`` and one private directory per
    session. It is exposed for display only and never used as a UI label.
    """
    return {"path": str(storage.WORKSPACE_ROOT)}


@router.delete("/api/workspaces/{workspace_id}")
def delete_workspace(workspace_id: str, request: WorkspaceDeleteRequest) -> dict[str, Any]:
    """Delete a workspace only after explicit confirmation and safe stopping.

    Args:
        workspace_id: ID of the local workspace to remove.
        request: Second-confirmation text, which must exactly match its name.

    Returns:
        ``deleted`` when no run was active, or ``stopping`` when a daemon is
        waiting for active Agent steps to finish before removal.

    Raises:
        HTTPException: If confirmation is wrong, the workspace is missing, or
        the protected default workspace is targeted.
    """
    workspace_id = _safe_id(workspace_id, "workspace")
    with _sessions_lock:
        records = _read_workspaces()
        workspace = next((item for item in records if item["id"] == workspace_id), None)
        if workspace is None:
            raise HTTPException(status_code=404, detail="Workspace not found")
        if workspace_id == "default":
            raise HTTPException(status_code=409, detail="The default workspace cannot be deleted")
        if request.confirmation.strip() != workspace["name"]:
            raise HTTPException(status_code=422, detail="Confirmation must exactly match the workspace name")
        if workspace_id in _deleting_workspaces:
            return {"status": "stopping", "message": "Workspace deletion is already waiting for active runs"}

        # Reserve the workspace first so no new Agent can start while current
        # runs are asked to reach their cooperative safe stop boundary.
        _deleting_workspaces.add(workspace_id)
        active_runs = [
            session.active for (current_workspace, _), session in _sessions.items()
            if current_workspace == workspace_id and session.active and not session.active.done.is_set()
        ]
    if active_runs:
        threading.Thread(
            target=_stop_then_remove_workspace,
            args=(workspace_id, active_runs),
            name=f"llmfetcher-delete-{workspace_id}",
            daemon=True,
        ).start()
        return {"status": "stopping", "message": "Requested safe stop for active sessions; deletion will continue automatically"}
    _remove_workspace(workspace_id)
    return {"status": "deleted", "message": "Workspace and its session data were deleted"}

@router.get("/api/workspaces/{workspace_id}/sessions/{session_id}/plan")
def get_task_plan(
    workspace_id: str, session_id: str, agent: str = "coordinator"
) -> dict[str, Any]:
    """Return one selected Agent's persisted task plan for a browser session."""
    return _plan_store(workspace_id, session_id, agent).read()

@router.get("/api/sessions/{session_id}/plan")
def get_session_plan(session_id: str, agent: str = "coordinator") -> dict[str, Any]:
    """Return one selected Agent's task plan for an independent session."""
    return _plan_store(session_id, session_id, agent).read()

@router.get("/api/workspaces/{workspace_id}/sessions/{session_id}/messages")
def get_session_history(
    workspace_id: str,
    session_id: str,
    agent: str = "all",
    cursor: str | None = None,
    before: int | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    """Return a bounded page of persisted display turns for a browser refresh.

    Args:
        workspace_id: Internal workspace identifier owning the session context.
        session_id: Browser-stable identifier for the current chat.
        agent: Selected graph Agent, or ``all`` for the canonical chat.
        cursor: Opaque cursor from the preceding newer page.
        before: Deprecated exclusive chronological turn index.
        limit: Maximum number of turns to return, clamped to ``1..500``.

    Returns:
        ``{messages, total, next_cursor, has_more, next_before}`` with messages
        in chronological order and ``next_before`` retained for compatibility.
    """
    try:
        return _agent_turns_page(
            workspace_id, session_id, agent, cursor=cursor, before=before, limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.get("/api/workspaces/{workspace_id}/sessions/{session_id}/archive")
def get_session_archive(
    workspace_id: str,
    session_id: str,
    agent: str = "coordinator",
    before: int | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Expose archived raw context evidence without changing model context."""
    return _archived_context_page(
        workspace_id, session_id, agent, before=before, limit=limit,
    )

@router.get("/api/sessions/{session_id}/archive")
def get_session_archive_by_id(
    session_id: str,
    agent: str = "coordinator",
    before: int | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Expose archived coordinator evidence for standalone browser sessions."""
    return _archived_context_page(
        session_id, session_id, agent, before=before, limit=limit,
    )

@router.get("/api/sessions/{session_id}/messages")
def get_session_messages(
    session_id: str,
    agent: str = "all",
    cursor: str | None = None,
    before: int | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    """Return a bounded page of the aggregate or selected Agent transcript.

    Args:
        session_id: Browser-stable identifier for the current chat.
        agent: Selected graph Agent, or ``all`` for the canonical chat.
        cursor: Opaque cursor from the preceding newer page.
        before: Deprecated exclusive chronological turn index.
        limit: Maximum number of turns to return, clamped to ``1..500``.

    Returns:
        ``{messages, total, next_cursor, has_more, next_before}`` with messages
        in chronological order and ``next_before`` retained for compatibility.
    """
    try:
        return _agent_turns_page(
            session_id, session_id, agent, cursor=cursor, before=before, limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.get("/api/sessions/{session_id}/agents")
def get_session_agents(session_id: str) -> dict[str, list[dict[str, Any]]]:
    """Return selectable Agent identities from the persisted graph snapshot."""
    session_id = _safe_id(session_id, "session")
    graph = get_session_graph(session_id, session_id)
    nodes = graph.get("nodes", []) if isinstance(graph, dict) else []
    agents: list[dict[str, Any]] = [{"id": "all", "name": "全部", "kind": "filter"}]
    seen = {"all"}
    for node in nodes:
        if not isinstance(node, dict) or node.get("kind") != "agent":
            continue
        agent_id = str(node.get("id", "")).strip()
        if not agent_id or agent_id in seen:
            continue
        seen.add(agent_id)
        agents.append({
            "id": agent_id,
            "name": agent_id,
            "kind": "agent",
            "dynamic": bool(node.get("dynamic")),
            "parent": node.get("parent"),
            "context": _agent_context_stats(session_id, agent_id),
        })
    if len(agents) == 1 and (_session_path(session_id, session_id) / "contexts" / "coordinator.json").exists():
        agents.append({
            "id": "coordinator", "name": "coordinator", "kind": "agent",
            "dynamic": False, "parent": None,
            "context": _agent_context_stats(session_id, "coordinator"),
        })
    return {"agents": agents}


@router.get("/api/sessions/{session_id}/agents/{agent_name}/context-graph")
def get_agent_context_graph(session_id: str, agent_name: str) -> dict[str, Any]:
    """Expose one Agent's persisted long-term memory graph for inspection.

    Args:
        session_id: Browser-visible session that owns the Agent context.
        agent_name: Graph-local Agent identity. ``all`` is rejected because
            every Agent owns an isolated graph rather than a shared one.

    Returns:
        A bounded graph snapshot and linear-context statistics. The graph is
        read from its persisted companion file, so it reflects the most recent
        completed checkpoint rather than mutable in-process state.

    Raises:
        HTTPException: If ``agent_name`` is the aggregate UI filter.
    """
    safe_session = _safe_id(session_id, "session")
    if agent_name == "all":
        raise HTTPException(status_code=422, detail="Select one Agent to inspect its context graph")
    safe_agent = _safe_id(agent_name, "agent")
    # Keep graph and linear statistics separate: a graph is a retrieval index,
    # while the context file remains the authoritative active conversation.
    return {
        "agent": safe_agent,
        "context": _agent_context_stats(safe_session, safe_agent),
        "graph": _agent_context_graph(safe_session, safe_agent).to_dict(),
    }


@router.get("/api/sessions/{session_id}/agents/{agent_name}/context")
def get_agent_context_preview(session_id: str, agent_name: str) -> dict[str, Any]:
    """Expose the full model-ready preview of an Agent's active context.

    Args:
        session_id: Browser-visible session that owns the selected Agent.
        agent_name: One concrete Agent identity; aggregate ``all`` is invalid.

    Returns:
        Agent ID and chronological provider-neutral persisted history. The
        runtime combines it with its transient system prompt, next user
        message, and any query-specific graph retrieval at dispatch time.

    Raises:
        HTTPException: If the aggregate Agent filter is requested.
    """
    safe_session = _safe_id(session_id, "session")
    if agent_name == "all":
        raise HTTPException(status_code=422, detail="Select one Agent to inspect its context")
    safe_agent = _safe_id(agent_name, "agent")
    return {"agent": safe_agent, **_agent_context_preview(safe_session, safe_agent).to_dict()}


@router.get("/api/sessions/{session_id}/agents/{agent_name}/context/compaction-input")
def get_agent_compaction_input_preview(session_id: str, agent_name: str) -> dict[str, Any]:
    """Expose the exact text the context compactor would send for one Agent.

    Args:
        session_id: Browser-visible session that owns the selected Agent.
        agent_name: One concrete Agent identity; aggregate ``all`` is invalid.

    Returns:
        Agent ID plus the budget-bounded, newest-first compaction input
        rebuilt live from the persisted checkpoint, with character, threshold,
        round, message, omitted-entry, and estimated-token metadata. This is
        read-only: it never compacts, saves, or calls a model.

    Raises:
        HTTPException: If the aggregate Agent filter is requested.
    """
    safe_session = _safe_id(session_id, "session")
    if agent_name == "all":
        raise HTTPException(status_code=422, detail="Select one Agent to inspect its compaction input")
    safe_agent = _safe_id(agent_name, "agent")
    return {"agent": safe_agent, **_agent_compaction_input_preview(safe_session, safe_agent)}


def _editable_context_store(session_id: str, agent_name: str) -> ContextEditStore:
    """Bind browser context-edit requests to one inactive Agent checkpoint.

    Args:
        session_id: Browser-visible owner of the context directory.
        agent_name: Concrete Agent identity; the aggregate ``all`` is invalid.

    Returns:
        Store scoped to ``contexts/<agent>.json`` for this session.

    Raises:
        HTTPException: If the aggregate filter is used or a run is active.

    Notes:
        Browser edits intentionally reject live runs: only the Agent-owned
        tools can flush/reload an in-memory context safely during execution.
    """
    safe_session = _safe_id(session_id, "session")
    if agent_name == "all":
        raise HTTPException(status_code=422, detail="Select one Agent to edit its context")
    if get_run_status(safe_session, safe_session).get("active"):
        raise HTTPException(
            status_code=409,
            detail="Stop the active run before editing from the browser; use the Agent context tools during a run.",
        )
    safe_agent = _safe_id(agent_name, "agent")
    return ContextEditStore(_context_path(safe_session, safe_session, safe_agent), safe_agent)


@router.get("/api/sessions/{session_id}/agents/{agent_name}/context/editable")
def inspect_editable_agent_context(session_id: str, agent_name: str) -> dict[str, Any]:
    """Return stable active-context records plus every recovery revision.

    Args:
        session_id: Browser-visible session that owns the selected Agent.
        agent_name: Concrete Agent identity, never the aggregate selector.

    Returns:
        Agent-scoped record references, current revision, graph-staleness, and
        immutable restorable revision metadata.
    """
    return _editable_context_store(session_id, agent_name).inspect()


def _parse_context_edit_operations(value: Any) -> list[ContextEditOperation]:
    """Convert one browser JSON operation array into the typed edit schema.

    Args:
        value: JSON request field expected to contain operation objects.

    Returns:
        Validated dataclass operations in submitted order.

    Raises:
        ContextEditError: If the field or any operation has an invalid shape.
    """
    if not isinstance(value, list):
        raise ContextEditError("operations must be an array")
    operations: list[ContextEditOperation] = []
    for item in value:
        if not isinstance(item, dict):
            raise ContextEditError("each operation must be an object")
        operations.append(ContextEditOperation(
            kind=str(item.get("kind", "")),
            target_record_id=(str(item["target_record_id"]) if item.get("target_record_id") is not None else None),
            content=str(item.get("content", "")),
            role=str(item.get("role", "user")),
        ))
    return operations


@router.post("/api/sessions/{session_id}/agents/{agent_name}/context/edit")
def edit_agent_context(
    session_id: str,
    agent_name: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Apply a version-checked browser edit to an inactive Agent context.

    Args:
        session_id: Browser-visible owner session.
        agent_name: Concrete Agent whose checkpoint is edited.
        payload: ``expected_revision_id``, ordered ``operations``, and optional
            human-readable ``reason``.

    Returns:
        New immutable revision and the refreshed editable context projection.

    Raises:
        HTTPException: With 409 for stale revisions and 422 for invalid edits.
    """
    store = _editable_context_store(session_id, agent_name)
    try:
        return store.apply(
            payload.get("expected_revision_id"),
            _parse_context_edit_operations(payload.get("operations")),
            actor="browser_api",
            reason=str(payload.get("reason", "")),
        )
    except ContextEditError as exc:
        status = 409 if "stale" in str(exc) else 422
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.post("/api/sessions/{session_id}/agents/{agent_name}/context/restore")
def restore_agent_context(
    session_id: str,
    agent_name: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Restore one saved revision as a new audit-preserving active revision.

    Args:
        session_id: Browser-visible owner session.
        agent_name: Concrete Agent whose checkpoint is recovered.
        payload: Current ``expected_revision_id``, source ``revision_id``, and
            an optional recovery reason.

    Returns:
        New forward revision and the restored editable-record projection.
    """
    store = _editable_context_store(session_id, agent_name)
    try:
        return store.restore(
            payload.get("expected_revision_id"),
            str(payload.get("revision_id", "")),
            actor="browser_api",
            reason=str(payload.get("reason", "")),
        )
    except ContextEditError as exc:
        status = 409 if "stale" in str(exc) else 422
        raise HTTPException(status_code=status, detail=str(exc)) from exc

@router.get("/api/workspaces/{workspace_id}/sessions/{session_id}/graph")
def get_session_graph(workspace_id: str, session_id: str) -> dict[str, Any]:
    """Return the reconciled execution-graph view for a browser session.

    Args:
        workspace_id: Session storage partition.
        session_id: Browser-visible session identity.

    Returns:
        Safe topology, typed relationships, run status, node states,
        assignments, and precise task states. Agent prompts, model
        credentials, and live Python objects remain private to the backend.
    """
    graph_path = _session_path(workspace_id, session_id) / "graph-view.json"
    try:
        payload = json.loads(graph_path.read_text(encoding="utf-8"))
        graph = payload if isinstance(payload, dict) else {"nodes": [], "edges": []}
    except (OSError, json.JSONDecodeError):
        graph = {"nodes": [], "edges": [], "assignments": {}, "task_states": {}}
    return _reconcile_graph_view(workspace_id, session_id, graph)

def _reconcile_graph_view(
    workspace_id: str,
    session_id: str,
    graph: dict[str, Any],
) -> dict[str, Any]:
    """Merge a persisted graph snapshot with durable run and event terminals.

    Args:
        workspace_id: Session storage partition.
        session_id: Browser-visible session identity.
        graph: JSON-decoded ``graph-view.json`` payload, possibly produced by
            an older version with ``reported`` task states.

    Returns:
        A browser-safe graph whose task and node states reflect the latest
        durable lifecycle evidence. The input mapping is not mutated.

    Side Effects:
        May persist an ``interrupted`` run diagnosis through
        :func:`get_run_status` when a former live worker disappeared.
    """
    reconciled = dict(graph)
    raw_nodes = graph.get("nodes", [])
    raw_edges = graph.get("edges", [])
    nodes = [
        dict(node)
        for node in (raw_nodes if isinstance(raw_nodes, list) else [])
        if isinstance(node, dict)
    ]
    raw_assignments = graph.get("assignments", {})
    raw_task_states = graph.get("task_states", {})
    raw_node_states = graph.get("node_states", {})
    assignments = {
        str(task_id): str(agent)
        for task_id, agent in (raw_assignments.items() if isinstance(raw_assignments, dict) else ())
    }
    task_states = {
        str(task_id): str(state)
        for task_id, state in (raw_task_states.items() if isinstance(raw_task_states, dict) else ())
    }
    node_states = {
        str(agent): dict(record)
        for agent, record in (raw_node_states.items() if isinstance(raw_node_states, dict) else ())
        if isinstance(record, dict)
    }

    # Replay durable lifecycle evidence over stale snapshots. Newest evidence
    # wins while old sessions remain readable without an on-disk migration.
    task_agents = {agent: task_id for task_id, agent in assignments.items()}
    task_parents = {
        str(node.get("id", "")): str(node.get("parent", ""))
        for node in nodes
        if node.get("id") and node.get("parent")
    }
    for event in _iter_session_event_log(workspace_id, session_id):
        event_kind = str(event.get("event", ""))
        event_type = str(event.get("type", ""))
        agent = str(event.get("agent", "") or "")
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        task_id = str(data.get("task_id", "") or task_agents.get(agent, ""))
        state = ""
        if event_kind == "error" and (not agent or agent == "coordinator"):
            agent = "coordinator"
            state = "failed"
        elif event_type in {"task:dispatched", "task:redispatched"}:
            state = "queued"
            if agent and data.get("reply_to"):
                task_parents[agent] = str(data["reply_to"])
        elif event_type in {"agent:completed", "agent:complete"}:
            state = "completed"
        elif event_type in {"agent:failed", "agent:error"}:
            state = "failed"
        elif event_type == "agent:stopped":
            state = "interrupted"
        elif event_type == "task:report_missing":
            state = "failed"
        elif event_type == "task:reported":
            status = str(data.get("status", "")).strip().lower()
            if status in {"completed", "complete", "success", "succeeded", "done"}:
                state = "completed"
            elif status in {"interrupted", "stopped"}:
                state = "interrupted"
            elif status in {"cancelled", "canceled"}:
                state = "cancelled"
            else:
                state = "failed"
        elif event_type == "task:finalized":
            state = str(data.get("state", ""))
        elif event_type.startswith("agent:"):
            state = "running"
        try:
            event_timestamp = float(event.get("timestamp", 0.0) or 0.0)
        except (TypeError, ValueError):
            event_timestamp = 0.0
        if state and agent:
            node_states[agent] = {
                "state": state,
                "message": str(event.get("message", "") or event_type),
                "updated_at": event_timestamp,
                **({"task_id": task_id} if task_id else {}),
            }
        if state and task_id and event_type in {"task:dispatched", "task:redispatched"}:
            task_states.setdefault(task_id, state)
        elif state and task_id and event_type.startswith("task:"):
            task_states[task_id] = state

    run_status = get_run_status(workspace_id, session_id)
    terminal = run_status["status"] in {"completed", "error", "stopped", "interrupted"}
    if terminal:
        # Terminal run state has higher authority than an unfinished historical
        # snapshot, but never erases a task that already reached a real result.
        for task_id, prior in tuple(task_states.items()):
            agent = assignments.get(task_id, "")
            agent_state = str(node_states.get(agent, {}).get("state", ""))
            if prior == "reported":
                task_states[task_id] = "failed" if agent_state == "failed" else "completed"
            elif prior == "running":
                task_states[task_id] = "failed" if agent_state == "failed" else "interrupted"
            elif prior == "queued":
                task_states[task_id] = "cancelled"
            if agent:
                node_states[agent] = {
                    **node_states.get(agent, {}),
                    "state": task_states[task_id],
                    "task_id": task_id,
                    "updated_at": float(run_status.get("finished_at") or time.time()),
                }

        coordinator_state = {
            "completed": "completed",
            "error": "failed",
            "stopped": "interrupted",
            "interrupted": "interrupted",
        }[run_status["status"]]
        node_states["coordinator"] = {
            **node_states.get("coordinator", {}),
            "state": coordinator_state,
            "message": run_status.get("error") or run_status["status"],
            "updated_at": float(run_status.get("finished_at") or time.time()),
        }

    # Some historical snapshots retained assignments after dynamically
    # removing their nodes. Reconstruct those UI identities from the durable
    # assignment index and original dispatch parent.
    known_nodes = {str(node.get("id", "")) for node in nodes}
    coordinator_exists = "coordinator" in known_nodes
    for agent in assignments.values():
        if agent in known_nodes:
            continue
        parent = task_parents.get(agent) or ("coordinator" if coordinator_exists else None)
        nodes.append({
            "id": agent,
            "kind": "agent",
            "dynamic": True,
            "parent": parent,
        })
        known_nodes.add(agent)

    # Preserve dependency semantics while adding explicit dynamic-dispatch
    # relationships for the UI hierarchy.
    edges = []
    edge_keys: set[tuple[str, str, str]] = set()
    for edge in raw_edges if isinstance(raw_edges, list) else []:
        if not isinstance(edge, dict):
            continue
        normalized = {**edge, "kind": str(edge.get("kind", "dependency"))}
        key = (str(normalized.get("source", "")), str(normalized.get("target", "")), normalized["kind"])
        if key not in edge_keys:
            edge_keys.add(key)
            edges.append(normalized)
    for node in nodes:
        parent = str(node.get("parent", "") or "")
        child = str(node.get("id", "") or "")
        key = (parent, child, "dispatch")
        if parent and child and key not in edge_keys:
            edge_keys.add(key)
            edges.append({"source": parent, "target": child, "kind": "dispatch"})

    reconciled.update({
        "nodes": nodes,
        "edges": edges,
        "assignments": assignments,
        "task_states": task_states,
        "node_states": node_states,
        "run_status": run_status,
    })
    return reconciled

@router.get("/api/sessions/{session_id}/graph")
def get_session_graph_by_id(session_id: str) -> dict[str, Any]:
    """Return a session's safe persisted execution-graph view."""
    return get_session_graph(session_id, session_id)


class GraphAgentRequest(BaseModel):
    """Create one browser-added Swarm worker node."""

    name: str = Field(..., min_length=1, max_length=80)
    system_prompt: str = Field(..., min_length=1)


class GraphConnectionRequest(BaseModel):
    """Add one dependency edge between two existing graph nodes."""

    source: str = Field(..., min_length=1, max_length=80)
    target: str = Field(..., min_length=1, max_length=80)


class GraphMapperRequest(BaseModel):
    """Set a safe declarative input aggregator on one agent node."""

    agent: str = Field(..., min_length=1, max_length=80)
    mode: str = "labelled"


class GraphRouterRequest(BaseModel):
    """Set a declarative router on one agent after its completion."""

    agent: str = Field(..., min_length=1, max_length=80)
    targets: list[str] = Field(default_factory=list)


def _require_live_swarm(session_id: str) -> tuple[Any, Any]:
    """Return ``(session, swarm)`` or reject edits against a live graph.

    Browser-side graph editing requires the in-process Swarm that currently
    owns this session. A completed, absent, or still-running-outside-turn
    Swarm cannot accept safe topology mutations, so the request fails with
    a 409 before contacting the graph.

    Args:
        session_id: Browser-visible session identity.

    Returns:
        The session holder (for locking) and its live :class:`AgentSwarm`.

    Raises:
        HTTPException: 409 when no live Swarm is currently active.
    """
    safe_session_id = _safe_id(session_id, "session")
    session = _get_session(safe_session_id, safe_session_id)
    if (
        session.active is None
        or session.active.swarm is None
        or session.active.done.is_set()
    ):
        raise HTTPException(status_code=409, detail="No live swarm is active in this session")
    return session, session.active.swarm


def _persist_live_graph_view(session_id: str, swarm: Any) -> None:
    """Atomically persist the live topology for the browser graph inspector.

    Args:
        session_id: Browser-visible session identity.
        swarm: Live Swarm whose ``view_snapshot`` replaces ``graph-view.json``.
    """
    _persist_json(_session_path(session_id, session_id) / "graph-view.json", swarm.view_snapshot())


def _publish_graph_mutation(
    session: Any, session_id: str, action: str, detail: str,
) -> None:
    """Append one durable graph-edit event and relay it to live SSE clients.

    Args:
        session: Session holder carrying the live ``ActiveRun`` broker.
        session_id: Browser-visible session identity.
        action: Stable machine action (``add_agent``, ``remove_agent``, ...).
        detail: Short human-readable mutation summary.
    """
    publish_durable_event(session.active, session_id, session_id, {
        "event": "lifecycle",
        "type": f"graph_edit:{action}",
        "source": "graph",
        "agent": "coordinator",
        "message": detail,
        "data": {"action": action, "detail": detail, "session_id": session_id},
        "timestamp": time.time(),
    })


@router.post("/api/sessions/{session_id}/graph/agents")
def add_graph_agent(session_id: str, request: GraphAgentRequest) -> dict[str, Any]:
    """Create and register a new live Swarm worker from browser settings.

    The worker reuses the live coordinator's fetcher, compaction threshold,
    and execution budgets; its context stays isolated under its own path and
    it never receives the TaskBus-bound ``report_task`` tool.

    Args:
        session_id: Browser-visible session identity.
        request: New worker name and role prompt.

    Returns:
        Mutation status plus the live persisted graph snapshot.

    Raises:
        HTTPException: 409 when the graph rejects the requested identity.
    """
    agent_name = _safe_id(request.name, "agent")
    session, swarm = _require_live_swarm(session_id)
    with session.lock:
        coordinator = swarm.get_agent("coordinator")
        if coordinator is None:
            raise HTTPException(status_code=409, detail="Coordinator is missing from the live swarm")
        worker = _build_http_worker_agent(
            coordinator, session_id, session_id,
            session.active, agent_name, request.system_prompt,
        )
        status = swarm.dynamic_add_agent(agent_name, worker)
        if status.startswith("Error"):
            raise HTTPException(status_code=409, detail=status)
        _persist_live_graph_view(session_id, swarm)
    _publish_graph_mutation(session, session_id, "add_agent", status)
    return {"ok": True, "status": status, "agent": agent_name}


@router.delete("/api/sessions/{session_id}/graph/agents")
def remove_graph_agent(session_id: str, name: str) -> dict[str, Any]:
    """Remove a single live Swarm node and every edge touching it.

    Args:
        session_id: Browser-visible session identity.
        name: Existing graph node identity to remove.

    Returns:
        Mutation status plus the live persisted graph snapshot.

    Raises:
        HTTPException: 409 for unknown nodes or the protected coordinator.
    """
    agent_name = _safe_id(name, "agent")
    if agent_name == "coordinator":
        raise HTTPException(status_code=400, detail="The coordinator node cannot be removed")
    session, swarm = _require_live_swarm(session_id)
    with session.lock:
        if swarm.get_agent(agent_name) is None:
            raise HTTPException(status_code=409, detail=f"Agent '{agent_name}' does not exist")
        status = swarm.dynamic_remove_agent(agent_name)
        if status.startswith("Error"):
            raise HTTPException(status_code=409, detail=status)
        _persist_live_graph_view(session_id, swarm)
    _publish_graph_mutation(session, session_id, "remove_agent", status)
    return {"ok": True, "status": status, "agent": agent_name}


@router.post("/api/sessions/{session_id}/graph/connections")
def add_graph_connection(session_id: str, request: GraphConnectionRequest) -> dict[str, Any]:
    """Add one dependency edge between two existing live graph nodes.

    Args:
        session_id: Browser-visible session identity.
        request: Predecessor ``source`` and successor ``target`` identities.

    Returns:
        Mutation status plus the live persisted graph snapshot.
    """
    source = _safe_id(request.source, "agent")
    target = _safe_id(request.target, "agent")
    session, swarm = _require_live_swarm(session_id)
    with session.lock:
        status = swarm.dynamic_add_connection(source, target)
        if status.startswith("Error"):
            raise HTTPException(status_code=409, detail=status)
        _persist_live_graph_view(session_id, swarm)
    _publish_graph_mutation(session, session_id, "add_connection", status)
    return {"ok": True, "status": status, "source": source, "target": target}


@router.delete("/api/sessions/{session_id}/graph/connections")
def remove_graph_connection(session_id: str, source: str, target: str) -> dict[str, Any]:
    """Remove one dependency edge between two live graph nodes.

    Args:
        session_id: Browser-visible session identity.
        source: Predecessor node identity.
        target: Successor node identity.

    Returns:
        Mutation status plus the live persisted graph snapshot.
    """
    safe_source = _safe_id(source, "agent")
    safe_target = _safe_id(target, "agent")
    session, swarm = _require_live_swarm(session_id)
    with session.lock:
        status = swarm.dynamic_remove_connection(safe_source, safe_target)
        if status.startswith("Error"):
            raise HTTPException(status_code=409, detail=status)
        _persist_live_graph_view(session_id, swarm)
    _publish_graph_mutation(session, session_id, "remove_connection", status)
    return {"ok": True, "status": status, "source": safe_source, "target": safe_target}


@router.post("/api/sessions/{session_id}/graph/mapper")
def set_graph_mapper(session_id: str, request: GraphMapperRequest) -> dict[str, Any]:
    """Set a safe declarative input mapper on one live agent node.

    Args:
        session_id: Browser-visible session identity.
        request: Target agent and one of ``labelled``, ``concat``, ``json``.

    Returns:
        Mutation status plus the live persisted graph snapshot.
    """
    agent_name = _safe_id(request.agent, "agent")
    session, swarm = _require_live_swarm(session_id)
    with session.lock:
        status = swarm.dynamic_set_mapper(agent_name, request.mode)
        if status.startswith("Error"):
            raise HTTPException(status_code=409, detail=status)
        _persist_live_graph_view(session_id, swarm)
    _publish_graph_mutation(session, session_id, "set_mapper", status)
    return {"ok": True, "status": status, "agent": agent_name, "mode": request.mode}


@router.post("/api/sessions/{session_id}/graph/router")
def set_graph_router(session_id: str, request: GraphRouterRequest) -> dict[str, Any]:
    """Set a declarative successor router on one live agent node.

    Args:
        session_id: Browser-visible session identity.
        request: Source agent and an ordered list of successor names.

    Returns:
        Mutation status plus the live persisted graph snapshot.
    """
    agent_name = _safe_id(request.agent, "agent")
    targets = [_safe_id(str(target), "agent") for target in request.targets]
    session, swarm = _require_live_swarm(session_id)
    with session.lock:
        status = swarm.dynamic_set_router(agent_name, targets)
        if status.startswith("Error"):
            raise HTTPException(status_code=409, detail=status)
        _persist_live_graph_view(session_id, swarm)
    _publish_graph_mutation(session, session_id, "set_router", status)
    return {"ok": True, "status": status, "agent": agent_name, "targets": targets}


@router.get("/api/sessions/{session_id}/graph/info")
def get_graph_edit_info(session_id: str) -> dict[str, Any]:
    """Return a compact live topology view for the graph editing toolbar.

    Unlike the heavy reconciled graph view, this endpoint returns only the
    node names, dependency edges, and concurrency cap needed to populate
    editing pickers for a live Swarm.

    Args:
        session_id: Browser-visible session identity.

    Returns:
        Live ``nodes``, ``edges``, ``max_concurrency_agents`` and an ``ok``
        flag. Fails with 409 when no live Swarm is active.
    """
    swarm = _require_live_swarm(session_id)[1]
    snapshot = swarm.view_snapshot()
    nodes = sorted({
        str(node.get("id", ""))
        for node in snapshot.get("nodes", [])
        if isinstance(node, dict) and str(node.get("id", ""))
    })
    edges = [
        {
            "source": str(edge.get("source", "")),
            "target": str(edge.get("target", "")),
            "kind": str(edge.get("kind", "dependency")),
        }
        for edge in snapshot.get("edges", [])
        if isinstance(edge, dict)
    ]
    return {
        "ok": True,
        "nodes": nodes,
        "edges": edges,
        "max_concurrency_agents": snapshot.get("max_concurrency_agents"),
    }



@router.get("/api/sessions/{session_id}/events")
def get_session_events(
    session_id: str,
    cursor: str | None = None,
    before: int | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    """Return a paginated, newest-first durable trace for one session.

    Args:
        session_id: Browser-visible session identity.
        cursor: Opaque byte cursor from an earlier response.
        before: Deprecated exclusive chronological event index.
        limit: Maximum records to return. The server clamps it to ``1..500``.

    Returns:
        Event records, the next older cursor, and the durable SSE offset.
    """
    safe_session_id = _safe_id(session_id, "session")
    try:
        return _session_event_page(
            safe_session_id,
            safe_session_id,
            cursor=cursor,
            before=before,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.get("/api/sessions/{session_id}/steers")
def get_session_steers(session_id: str) -> dict[str, Any]:
    """Return every durable steering instruction applied to this session.

    Steers are reconstructed from the append-only event log, so they survive
    browser refreshes without a separate steering transcript.

    Args:
        session_id: Browser-visible session identity.

    Returns:
        Steer records in chronological order with round and message payloads.
    """
    safe_session_id = _safe_id(session_id, "session")
    steers = []
    for event in _iter_session_event_log(safe_session_id, safe_session_id):
        if event.get("event") != "lifecycle" or event.get("type") != "agent:steer_applied":
            continue
        data = event.get("data")
        if not isinstance(data, dict) or not data.get("messages"):
            continue
        steers.append({
            "round": data.get("round"),
            "messages": data.get("messages"),
            "timestamp": event.get("timestamp"),
        })
    return {"steers": steers}

@router.get("/api/sessions/{session_id}/usage")
def get_session_usage(session_id: str) -> dict[str, Any]:
    """Return completed token usage for all Agents in one browser session.

    Args:
        session_id: Browser-visible session identity.

    Returns:
        Session-wide token totals and individual Agent totals derived from the
        append-only event log. In-flight model calls are absent until they emit
        their completed ``agent:round`` lifecycle event.
    """
    safe_session_id = _safe_id(session_id, "session")
    return _session_usage_summary(_iter_session_event_log(safe_session_id, safe_session_id))

@router.put("/api/workspaces/{workspace_id}/sessions/{session_id}/plan")
def replace_task_plan(
    workspace_id: str, session_id: str, request: TaskPlanRequest,
    agent: str = "coordinator",
) -> dict[str, Any]:
    """Allow a user to replace one selected Agent's supervised task plan."""
    try:
        return _plan_store(workspace_id, session_id, agent).replace(goal=request.goal, summary=request.summary, tasks=request.tasks)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

@router.patch("/api/workspaces/{workspace_id}/sessions/{session_id}/plan/tasks/{task_id}")
def update_task_plan_status(
    workspace_id: str, session_id: str, task_id: str, request: TaskStatusRequest,
    agent: str = "coordinator",
) -> dict[str, Any]:
    """Persist a status change in one selected Agent's task plan."""
    try:
        return _plan_store(workspace_id, session_id, agent).update_status(task_id, request.status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

@router.patch("/api/sessions/{session_id}/plan/tasks/{task_id}")
def update_session_plan_status(
    session_id: str, task_id: str, request: TaskStatusRequest,
    agent: str = "coordinator",
) -> dict[str, Any]:
    """Persist one task-status transition within one selected Agent plan."""
    try:
        return _plan_store(session_id, session_id, agent).update_status(task_id, request.status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

@router.post("/api/workspaces", status_code=201)
def create_workspace(request: WorkspaceRequest) -> dict[str, str]:
    """Create a local session bound to an existing user project directory.

    Args:
        request: Display name plus the absolute directory selected by the user.

    Returns:
        Registry identity, display name, and canonical project path.

    Raises:
        HTTPException: If the name is blank or the project directory is not an
            existing readable and writable absolute path.
    """
    name = request.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Workspace name is required")
    try:
        project_path = _validate_project_path(request.project_path)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    workspace_id = uuid.uuid4().hex
    with _sessions_lock:
        workspaces = _read_workspaces()
        workspace_id = _session_id_from_name(name, {item["id"] for item in workspaces})
        record = {"id": workspace_id, "name": name, "project_path": str(project_path)}
        workspaces.append(record)
        _write_workspaces(workspaces)
    (storage.WORKSPACE_ROOT / workspace_id).mkdir(parents=True, exist_ok=True)
    return record

@router.post("/api/sessions", status_code=201)
def create_session(request: WorkspaceRequest) -> dict[str, str]:
    """Create one browser-visible session and its private workspace path."""
    return create_workspace(request)


@router.put("/api/sessions/{session_id}/project-path")
def update_session_project_path(
    session_id: str, request: ProjectPathRequest,
) -> dict[str, str]:
    """Rebind an inactive session to another existing project directory.

    Args:
        session_id: Registry identity of the browser session to update.
        request: Native-picker path selected by the local user.

    Returns:
        Session identity and canonical replacement project path.

    Raises:
        HTTPException: If the session is missing, currently running, or the
            replacement path is unusable.
    """
    safe_session = _safe_id(session_id, "session")
    try:
        project_path = _validate_project_path(request.project_path)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    with _sessions_lock:
        active = _sessions.get((safe_session, safe_session))
        if active and active.active and not active.active.done.is_set():
            raise HTTPException(status_code=409, detail="Stop the active run before changing its project directory")
        records = _read_workspaces()
        record = next((item for item in records if item.get("id") == safe_session), None)
        if record is None:
            raise HTTPException(status_code=404, detail="Session not found")
        record["project_path"] = str(project_path)
        _write_workspaces(records)
    return {"id": safe_session, "project_path": str(project_path)}


def _directory_picker_command() -> list[str] | None:
    """Return the host-native folder picker command for the current platform.

    Returns:
        Static command arguments that print a selected directory, or ``None``
        when the Linux desktop exposes neither Zenity nor KDialog.
    """
    if sys.platform == "win32":
        script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$d=New-Object System.Windows.Forms.FolderBrowserDialog; "
            "$d.Description='Select an existing Angelus project directory'; "
            "if($d.ShowDialog() -eq 'OK'){[Console]::Write($d.SelectedPath)}else{exit 1}"
        )
        return ["powershell.exe", "-NoProfile", "-STA", "-Command", script]
    if sys.platform == "darwin":
        return ["osascript", "-e", "POSIX path of (choose folder with prompt \"Select an Angelus project directory\")"]
    if shutil.which("zenity"):
        return ["zenity", "--file-selection", "--directory", "--title=Select an Angelus project directory"]
    if shutil.which("kdialog"):
        return ["kdialog", "--getexistingdirectory", str(Path.home()), "--title", "Select an Angelus project directory"]
    return None


def _request_is_loopback(request: Request) -> bool:
    """Return whether an HTTP request originated from this host.

    Args:
        request: FastAPI request whose peer address controls GUI authority.

    Returns:
        ``True`` only for an IP loopback peer such as ``127.0.0.1`` or ``::1``.
    """
    host = request.client.host if request.client is not None else ""
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@router.post("/api/workspace-directory/pick")
def pick_workspace_directory(request: Request) -> dict[str, Any]:
    """Open the host folder picker for a loopback Workbench client.

    Args:
        request: Browser request used to reject remote GUI activation.

    Returns:
        Canonical selected path and ``cancelled=false``; cancellation returns
        a null path with ``cancelled=true`` without creating session state.

    Raises:
        HTTPException: If called remotely, no supported picker is installed,
            the dialog fails, or its selected path is invalid.
    """
    if not _request_is_loopback(request):
        raise HTTPException(status_code=403, detail="Directory picker is available only to local clients")
    command = _directory_picker_command()
    if command is None:
        raise HTTPException(status_code=503, detail="Install zenity or kdialog to select a project directory")
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=1800, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HTTPException(status_code=503, detail="Unable to open the system directory picker") from exc
    selected_output = completed.stdout.rstrip("\r\n")
    if completed.returncode == 1 or not selected_output:
        return {"path": None, "cancelled": True}
    if completed.returncode != 0:
        raise HTTPException(status_code=503, detail=completed.stderr.strip() or "Directory picker failed")
    try:
        selected = _validate_project_path(selected_output)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"path": str(selected), "cancelled": False}


@router.post("/api/sessions/{session_id}/open-folder")
def open_session_folder(session_id: str) -> dict[str, str]:
    """Open one session's bound user project in the host file manager."""
    safe_session = _safe_id(session_id, "session")
    directory = _project_path(safe_session, safe_session)
    if not directory.is_dir():
        raise HTTPException(status_code=409, detail="The selected project directory is unavailable")
    command = (
        ["explorer.exe", str(directory)] if sys.platform == "win32"
        else ["open", str(directory)] if sys.platform == "darwin"
        else ["xdg-open", str(directory)]
    )
    try:
        subprocess.Popen(command)
    except OSError as exc:
        raise HTTPException(status_code=503, detail="Unable to open the workspace directory") from exc
    return {"path": str(directory)}

@router.get("/api/sessions/{session_id}/memory/capabilities")
def get_session_memory_capabilities(session_id: str) -> dict[str, Any]:
    """Describe the explicit run-scoped grants accepted by the browser API."""
    _safe_id(session_id, "session")
    return {"capabilities": list(CAPABILITIES), "current_session_implicit": True,
            "note": "Additional sessions must be supplied in the RunConfig allowlists before a run starts."}

@router.post("/api/sessions/{session_id}/artifacts", status_code=201)
def register_session_artifact(session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Register browser-uploaded base64 attachment bytes without a source path."""
    safe_session = _safe_id(session_id, "session")
    try:
        encoded = str(payload.get("data_base64", ""))
        data = base64.b64decode(encoded, validate=True)
        result = _session_memory_store().register_artifact(
            safe_session, data, str(payload.get("logical_name", "attachment")),
            str(payload.get("mime_type", "application/octet-stream")),
        )
        return result
    except (ValueError, SessionMemoryError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

@router.get("/api/sessions/{session_id}/artifacts")
def list_session_artifacts(session_id: str) -> dict[str, Any]:
    safe_session = _safe_id(session_id, "session")
    manifest = _session_memory_store().get_manifest(safe_session)
    return {"session_id": safe_session, "generation": manifest["generation"], "artifacts": manifest.get("artifacts", [])}

@router.get("/api/sessions/{session_id}/handoffs")
def list_session_handoffs(session_id: str) -> dict[str, Any]:
    safe_session = _safe_id(session_id, "session")
    directory = _session_path(safe_session, safe_session) / "handoffs"
    handoffs = []
    for path in sorted(directory.glob("*.json")) if directory.is_dir() else []:
        item = _session_memory_store().read_handoff(safe_session, path.stem)
        handoffs.append({"handoff_id": item.get("handoff_id"), "source": item.get("source"), "work": item.get("work")})
    return {"handoffs": handoffs}

@router.get("/api/sessions/{session_id}/handoffs/{handoff_id}")
def get_session_handoff(session_id: str, handoff_id: str) -> dict[str, Any]:
    try:
        return _session_memory_store().read_handoff(_safe_id(session_id, "session"), _safe_id(handoff_id, "handoff"))
    except SessionMemoryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

@router.post("/api/sessions/{session_id}/handoffs", status_code=201)
def create_browser_session_handoff(session_id: str, handoff: dict[str, Any]) -> dict[str, Any]:
    try:
        return _session_memory_store().create_handoff(_safe_id(session_id, "session"), handoff)
    except SessionMemoryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

@router.delete("/api/sessions/{session_id}")
def delete_session(session_id: str, request: WorkspaceDeleteRequest) -> dict[str, Any]:
    """Delete one session after confirmation and cooperative run shutdown."""
    return delete_workspace(session_id, request)

__all__ = ["list_workspaces", "list_sessions", "delete_workspace", "get_task_plan", "get_session_plan", "get_session_history", "get_session_archive", "get_session_archive_by_id", "get_session_messages", "get_session_agents", "get_agent_context_graph", "get_agent_context_preview", "_editable_context_store", "inspect_editable_agent_context", "edit_agent_context", "restore_agent_context", "get_session_graph", "_reconcile_graph_view", "get_session_graph_by_id", "get_session_events", "get_session_steers", "get_session_usage", "replace_task_plan", "update_task_plan_status", "update_session_plan_status", "create_workspace", "create_session", "update_session_project_path", "pick_workspace_directory", "open_session_folder", "get_session_memory_capabilities", "register_session_artifact", "list_session_artifacts", "list_session_handoffs", "get_session_handoff", "create_browser_session_handoff", "delete_session", "router"]
