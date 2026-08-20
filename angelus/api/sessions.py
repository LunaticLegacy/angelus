"""Session, workspace, plan, graph, archive, usage and memory routes."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from ..classes import (
    TaskPlanRequest,
    TaskStatusRequest,
    WorkspaceDeleteRequest,
    WorkspaceRequest,
)
from ..history import (
    _agent_context_graph,
    _agent_context_stats,
    _archived_context_page,
    _read_agent_history,
    _session_usage_summary,
)
from ..runtime import _plan_store, _session_memory_store
from ..session_memory import CAPABILITIES, SessionMemoryError
from .. import storage
from ..storage import (
    _deleting_workspaces,
    _persist_json,
    _read_session_event_log,
    _read_workspaces,
    _remove_workspace,
    _safe_id,
    _sessions,
    _sessions_lock,
    _session_event_page,
    _session_id_from_name,
    _session_path,
    _stop_then_remove_workspace,
    _write_workspaces,
)
from .runs import get_run_status

router = APIRouter()



@router.get("/api/workspaces")
def list_workspaces() -> dict[str, list[dict[str, str]]]:
    """List local workspaces available to the browser console."""
    return {"workspaces": _read_workspaces()}

@router.get("/api/sessions")
def list_sessions() -> dict[str, list[dict[str, str]]]:
    """List browser sessions with a compact durable run-status indicator."""
    sessions: list[dict[str, str]] = []
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
        sessions.append({**workspace, "status": indicator})
    return {"sessions": sessions}

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
def get_session_history(workspace_id: str, session_id: str, agent: str = "all") -> dict[str, list[dict[str, Any]]]:
    """Return persisted display turns so a browser refresh restores the chat.

    Args:
        workspace_id: Internal workspace identifier owning the session context.
        session_id: Browser-stable identifier for the current chat.

    Returns:
        Ordered user/assistant display turns, excluding tool result payloads.
    """
    return {"messages": _read_agent_history(workspace_id, session_id, agent)}

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
def get_session_messages(session_id: str, agent: str = "all") -> dict[str, list[dict[str, Any]]]:
    """Return the aggregate or selected Agent transcript for one session."""
    return {"messages": _read_agent_history(session_id, session_id, agent)}

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
        "graph": _agent_context_graph(safe_session, safe_agent),
    }

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
    for event in _read_session_event_log(workspace_id, session_id):
        event_kind = str(event.get("event", ""))
        event_type = str(event.get("type", ""))
        agent = str(event.get("agent", "") or "")
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        task_id = str(data.get("task_id", "") or task_agents.get(agent, ""))
        state = ""
        if event_kind == "error" and (not agent or agent == "coordinator"):
            agent = "coordinator"
            state = "failed"
        elif event_type == "task:dispatched":
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
            state = "completed" if status in {"completed", "complete", "success", "succeeded", "done"} else "failed"
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
        if state and task_id and event_type == "task:dispatched":
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

@router.get("/api/sessions/{session_id}/events")
def get_session_events(
    session_id: str,
    before: int | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    """Return a paginated, newest-first durable trace for one session.

    Args:
        session_id: Browser-visible session identity.
        before: Exclusive chronological event offset from an earlier response;
            omit it to load the newest page.
        limit: Maximum records to return. The server clamps it to ``1..500``.

    Returns:
        Event records, their session-wide total, and a cursor for older events.
    """
    safe_session_id = _safe_id(session_id, "session")
    return _session_event_page(
        safe_session_id,
        safe_session_id,
        before=before,
        limit=limit,
    )

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
    events = _read_session_event_log(safe_session_id, safe_session_id)
    steers = []
    for event in events:
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
    return _session_usage_summary(_read_session_event_log(safe_session_id, safe_session_id))

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
    """Create a local workspace with an isolated context directory."""
    name = request.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Workspace name is required")
    workspace_id = uuid.uuid4().hex
    with _sessions_lock:
        workspaces = _read_workspaces()
        workspace_id = _session_id_from_name(name, {item["id"] for item in workspaces})
        record = {"id": workspace_id, "name": name}
        workspaces.append(record)
        _write_workspaces(workspaces)
    (storage.WORKSPACE_ROOT / workspace_id).mkdir(parents=True, exist_ok=True)
    return record

@router.post("/api/sessions", status_code=201)
def create_session(request: WorkspaceRequest) -> dict[str, str]:
    """Create one browser-visible session and its private workspace path."""
    return create_workspace(request)


@router.post("/api/sessions/{session_id}/open-folder")
def open_session_folder(session_id: str) -> dict[str, str]:
    """Open one session's local workspace directory in the host file manager."""
    safe_session = _safe_id(session_id, "session")
    directory = _session_path(safe_session, safe_session)
    directory.mkdir(parents=True, exist_ok=True)
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

__all__ = ["list_workspaces", "list_sessions", "delete_workspace", "get_task_plan", "get_session_plan", "get_session_history", "get_session_archive", "get_session_archive_by_id", "get_session_messages", "get_session_agents", "get_agent_context_graph", "get_session_graph", "_reconcile_graph_view", "get_session_graph_by_id", "get_session_events", "get_session_steers", "get_session_usage", "replace_task_plan", "update_task_plan_status", "update_session_plan_status", "create_workspace", "create_session", "open_session_folder", "get_session_memory_capabilities", "register_session_artifact", "list_session_artifacts", "list_session_handoffs", "get_session_handoff", "create_browser_session_handoff", "delete_session", "router"]
