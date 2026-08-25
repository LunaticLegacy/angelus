"""Run control, status and SSE streaming routes."""

from __future__ import annotations

import json
import threading
import time
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import StreamingResponse

from llmfetcher import AgentRunStopped
from llmfetcher.events import ExecutionEvent
from llmfetcher.llm_types import LLMOutput
from llmfetcher.swarm_module import AgentFailure

from ..classes import ActiveRun, BrowserRunControl, RunRequest, SteerRequest
from .. import connectors, runtime, storage
from .. import run_profiles
from ..mcp_registry import resolve_session_servers
from ..history import render_markdown
from ..event_stream import (
    EventBroker,
    historical_event_stream,
    live_event_stream,
    publish_durable_event,
)
from ..provider_adapters import effective_temperature
from ..storage import (
    _append_conversation_turn,
    _deleting_workspaces,
    _get_session,
    _persist_json,
    _project_path,
    _run_state_path,
    _safe_id,
    _session_event_offset_after,
    _session_event_log_size,
    _session_path,
    _sessions_lock,
    _validate_project_path,
)

router = APIRouter()


def _event_resume_offset(
    request: Request,
    workspace_id: str,
    session_id: str,
    *,
    after: int,
    cursor: int | None,
) -> int:
    """Resolve an SSE durable cursor with compatibility precedence.

    Args:
        request: Incoming request that may carry ``Last-Event-ID``.
        workspace_id: Storage partition owning the durable event log.
        session_id: Browser-stable session identity.
        after: Legacy count of already-rendered durable records.
        cursor: Explicit durable byte offset from the browser.

    Returns:
        Valid byte offset no greater than the current event-log size. An
        out-of-range modern cursor restarts safely from zero; otherwise the
        legacy record count is converted by scanning once.
    """
    last_event_id = request.headers.get("last-event-id", "").strip()
    for candidate in (last_event_id, cursor):
        if candidate in (None, ""):
            continue
        try:
            resolved = max(0, int(candidate))
        except (TypeError, ValueError):
            continue
        log_size = _session_event_log_size(workspace_id, session_id)
        return resolved if resolved <= log_size else 0
    return _session_event_offset_after(workspace_id, session_id, after)



@router.post("/api/runs")
def start_run(request: RunRequest) -> dict[str, str]:
    """Start one Agent or Swarm in a session-owned worker thread.

    Args:
        request: Browser message, session identity, and ephemeral model/run
            configuration.

    Returns:
        Run and workspace identifiers used by status, control, and SSE routes.

    Raises:
        HTTPException: If the session is unavailable, already running, or has
            no model configured.

    Side Effects:
        Persists the user turn, run state, event trace, Agent contexts, final
        graph task terminals, and any completed assistant result.
    """
    session_id = _safe_id(request.session_id, "session")
    workspace_id = _safe_id(request.workspace_id, "workspace")
    if not storage._workspace_exists(workspace_id):
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        _validate_project_path(str(_project_path(workspace_id, session_id)))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="The selected project directory is unavailable") from exc
    with _sessions_lock:
        if workspace_id in _deleting_workspaces:
            raise HTTPException(status_code=409, detail="Workspace is being deleted")
    # Profile data is server-owned.  The request's configuration remains a
    # compatibility fallback only for old clients that have not selected a
    # persisted profile yet; a saved Agent profile always wins at this run
    # boundary and stays frozen in the resulting runtime snapshot.
    saved_config, _sources = run_profiles.resolve_profile(workspace_id, "coordinator")
    config = saved_config if saved_config.model.strip() or saved_config.connector_id else request.config
    config = connectors._resolve_connector_key(config)
    # Shell and Swarm belong to the unified permission panel.  Keep legacy
    # persisted booleans compatible, but make an explicitly enabled category
    # sufficient for all newly edited profiles.
    config = config.model_copy(update={
        "enable_shell": config.enable_shell or runtime._category_permitted(config, "shell"),
        "enable_swarm": config.enable_swarm or runtime._category_permitted(config, "swarm"),
    })
    if not config.model.strip():
        raise HTTPException(
            status_code=422,
            detail="尚未配置可用模型。请打开设置 → 连接器，选择或新建连接器后再运行。",
        )
    session = _get_session(workspace_id, session_id)
    event_log_size = _session_event_log_size(workspace_id, session_id)
    with session.lock:
        if session.active and not session.active.done.is_set():
            raise HTTPException(status_code=409, detail="This chat already has an active run")
        if (
            config.enable_swarm
            and session.active
            and session.active.swarm is not None
            and not session.active.mcp_servers
        ):
            # Keep the in-process execution graph and every Agent instance
            # alive between user turns. Tool closures retain this ActiveRun,
            # so reset it in place rather than replacing its identity.
            active = session.active
            active.reset_for_next_turn(event_log_size)
        else:
            active = ActiveRun(
                control=BrowserRunControl(),
                event_broker=EventBroker(durable_offset=event_log_size),
            )
            # A restarted backend has no in-memory BrowserSession. Recreate a
            # completed Swarm from its credential-free local blueprint before
            # falling back to a brand-new graph on the first resumed turn.
            if config.enable_swarm:
                active.swarm = runtime._restore_swarm(
                    config, workspace_id, session_id, active,
                )
        # MCP configuration is resolved exclusively from the global registry
        # and this session's authorization policy at the run boundary.
        active.mcp_servers = resolve_session_servers(
            session_id, _project_path(workspace_id, session_id)
        )
        session.active = active
    started_at = time.time()
    runtime_profile = runtime._runtime_profile_snapshot(config, active.mcp_servers)
    _persist_json(_run_state_path(workspace_id, session_id), {
        "status": "running", "run_id": session_id, "started_at": started_at,
        "runtime_profile": runtime_profile,
    })
    _append_conversation_turn(workspace_id, session_id, {
        "role": "user", "content": request.message, "reasoning": "", "tools": [],
    })
    publish_durable_event(active, workspace_id, session_id, {
        "event": "run_started",
        "run_id": session_id,
        "timestamp": started_at,
        "message": request.message,
        "runtime_profile": runtime_profile,
    })

    def execute() -> None:
        """Run the configured Agent graph and persist one terminal outcome."""
        started = time.time()
        terminal_status = "completed"
        error_message = ""
        try:
            if config.enable_swarm:
                # A completed Swarm remains owned by this in-process session.
                # Build it only for the first Swarm turn; rebuilding here would
                # discard the retained worker instances just selected above.
                swarm = active.swarm
                if swarm is None:
                    swarm = runtime._build_swarm(config, workspace_id, session_id, active)
                    active.swarm = swarm
                # Settings are browser-local drafts until this boundary. Keep
                # the selected threshold in memory so each Agent reapplies it
                # after loading its checkpoint during ``swarm.run``.
                runtime._synchronize_swarm_context_threshold(swarm, config)
                outputs = swarm.run(request.message, control=active.control)
                output = outputs.get("coordinator")
                if not isinstance(output, LLMOutput):
                    if isinstance(output, AgentFailure) and output.exception is not None:
                        raise output.exception
                    detail = getattr(output, "exception", repr(output))
                    raise RuntimeError(
                        "Coordinator did not produce a language-model output as: "
                        f"{detail}"
                    )
                _persist_json(_session_path(workspace_id, session_id) / "graph-view.json", swarm.view_snapshot())
                # Aggregate token usage across every executed agent
                # (coordinator + workers), each of which already includes
                # its own internal compaction / graph-memory LLM calls.
                usage = swarm.total_usage()
            else:
                agent = runtime._build_agent(config, workspace_id, session_id, active=active)
                # Single-Agent sessions load their checkpoint inside ``run``;
                # the in-memory selection is reapplied immediately afterward.
                runtime._synchronize_context_threshold(
                    [agent], config.max_context_threshold,
                )
                def capture(event: ExecutionEvent) -> None:
                    """Relay one named single-Agent event to the browser.

                    Library-created single Agents do not assign an event name,
                    so this adapter supplies the browser-visible coordinator
                    identity required to group lifecycle records.
                    """
                    # ``_event_payload`` belongs to the runtime module.  Use
                    # the module-qualified helper here: this router imports
                    # ``runtime`` rather than its private helpers, and an
                    # unresolved name would otherwise be swallowed by the
                    # Agent hook dispatcher, silently dropping all lifecycle
                    # (including tool) events.
                    payload = {"event": "lifecycle", **runtime._event_payload(event)}
                    payload["agent"] = payload["agent"] or "coordinator"
                    if event.event_type == "agent:stream_delta":
                        active.publish_ephemeral_event(payload)
                        return
                    publish_durable_event(active, workspace_id, session_id, payload)
                agent.add_hook(capture)
                output = agent.run(
                    request.message,
                    temperature=effective_temperature(config.provider, config.temperature),
                    control=active.control,
                )
                usage = {
                    "input": getattr(agent.usage, "input_tokens", 0) or 0,
                    "output": getattr(agent.usage, "output_tokens", 0) or 0,
                    "total": getattr(agent.usage, "total_tokens", 0) or 0,
                    "cached": getattr(agent.usage, "cached_tokens", 0) or 0,
                    "reasoning": getattr(agent.usage, "reasoning_tokens", 0) or 0,
                }
            result_payload = {
                "event": "result",
                "content": output.content,
                "content_html": render_markdown(output.content),
                "reasoning": output.reasoning_content,
                "reasoning_html": render_markdown(output.reasoning_content),
                "provider": output.provider,
                "model": output.model,
                "usage": usage,
                "duration_ms": round((time.time() - started) * 1000),
            }
            _append_conversation_turn(workspace_id, session_id, {
                "role": "assistant",
                "content": output.content,
                "reasoning": output.reasoning_content,
                "tools": [],
            })
            publish_durable_event(active, workspace_id, session_id, result_payload)
        except AgentRunStopped as exc:
            terminal_status = "stopped"
            # The Agent saves only completed boundaries before raising. Mirror
            # that result in the browser transcript so history and LLM context
            # include the same last turn after either stop operation.
            output = exc.last_output
            if output is not None and not config.enable_swarm:
                _append_conversation_turn(workspace_id, session_id, {
                    "role": "assistant",
                    "content": output.content,
                    "reasoning": output.reasoning_content,
                    "tools": [],
                })
            stopped_payload = {
                "event": "stopped",
                "message": "Run stopped after the current step.",
                "timestamp": time.time(),
            }
            publish_durable_event(active, workspace_id, session_id, stopped_payload)
        except Exception as exc:
            terminal_status = "error"
            error_message = f"{type(exc).__name__}: {exc}"
            error_payload = {
                "event": "error",
                "message": error_message,
                "timestamp": time.time(),
            }
            # Persist terminal failures before notifying SSE clients so a
            # browser refresh can explain a run that is no longer live.
            publish_durable_event(active, workspace_id, session_id, error_payload)
        finally:
            if active.mcp_bridge is not None:
                try:
                    active.mcp_bridge.close()
                except Exception:
                    pass
            if active.swarm is not None:
                try:
                    # Close and persist every dynamic task before publishing
                    # the run terminal so refreshes cannot observe stale work.
                    active.swarm.finalize_tasks()
                    _persist_json(
                        _session_path(workspace_id, session_id) / "graph-view.json",
                        active.swarm.view_snapshot(),
                    )
                    runtime._persist_swarm_snapshot(
                        active.swarm, workspace_id, session_id,
                    )
                except Exception as exc:
                    cleanup_error = f"{type(exc).__name__}: {exc}"
                    if terminal_status == "completed":
                        terminal_status = "error"
                        error_message = cleanup_error
                        error_payload = {
                            "event": "error",
                            "message": cleanup_error,
                            "timestamp": time.time(),
                        }
                        publish_durable_event(active, workspace_id, session_id, error_payload)
            run_state = {
                "status": terminal_status, "run_id": session_id,
                "started_at": started_at, "finished_at": time.time(),
                "runtime_profile": runtime_profile,
            }
            if error_message:
                run_state["error"] = error_message
            try:
                _persist_json(_run_state_path(workspace_id, session_id), run_state)
                done_payload = {"event": "done", "timestamp": time.time()}
                publish_durable_event(active, workspace_id, session_id, done_payload)
            finally:
                # Even a terminal metadata I/O failure must release status,
                # deletion, and SSE waiters instead of orphaning a live run.
                active.event_broker.close()
                active.done.set()

    threading.Thread(target=execute, name=f"llmfetcher-{session_id}", daemon=True).start()
    return {"run_id": session_id, "workspace_id": workspace_id}

@router.get("/api/workspaces/{workspace_id}/runs/{session_id}/status")
def get_run_status(workspace_id: str, session_id: str) -> dict[str, Any]:
    """Return durable run state and diagnose a worker lost after a restart.

    Args:
        workspace_id: Browser session storage partition.
        session_id: Browser-visible session identity.

    Returns:
        Current-process activity, terminal status, timings, and an optional
        human-readable error. A durable ``running`` or ``force_stopping``
        record with no live worker is converted to ``interrupted`` so a
        refreshed browser never silently presents an orphaned run as idle.
    """
    workspace_id = _safe_id(workspace_id, "workspace")
    session_id = _safe_id(session_id, "session")
    session = _get_session(workspace_id, session_id)
    active = session.active is not None and not session.active.done.is_set()
    try:
        payload = json.loads(_run_state_path(workspace_id, session_id).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    status = str(payload.get("status", "idle"))
    error_message = str(payload.get("error", ""))
    if not active and status in {"running", "force_stopping"}:
        error_message = (
            "执行工作线程已不在当前服务进程中；任务可能因服务重启或进程中断而停止。"
        )
        # Record the diagnosis once so every later refresh reports the same
        # recoverable failure rather than appearing to run forever.
        payload = {
            **payload,
            "status": "interrupted",
            "finished_at": time.time(),
            "error": error_message,
        }
        _persist_json(_run_state_path(workspace_id, session_id), payload)
        status = "interrupted"
    return {
        "active": active,
        "status": "running" if active else status,
        "run_id": session_id if active else payload.get("run_id"),
        "started_at": payload.get("started_at"),
        "finished_at": payload.get("finished_at"),
        "error": error_message or None,
    }

@router.get("/api/workspaces/{workspace_id}/runs/{session_id}/events")
def stream_events(
    workspace_id: str,
    session_id: str,
    request: Request,
    after: int = 0,
    cursor: int | None = None,
) -> StreamingResponse:
    """Stream durable session events after a chronological log offset.

    Args:
        workspace_id: Browser session storage partition.
        session_id: Browser-visible session identity.
        request: Incoming request whose ``Last-Event-ID`` resumes a live SSE.
        after: Number of already-rendered event-log records. New connections
            replay only later records, so a refresh cannot lose events that an
            earlier SSE consumer removed from its in-memory queue.
        cursor: Preferred durable byte offset for explicit browser reconnects.

    Returns:
        An SSE response that replays durable history once, then consumes the
        process-local broadcast ring until the active run ends.
    """
    workspace_id = _safe_id(workspace_id, "workspace")
    session_id = _safe_id(session_id, "session")
    session = _get_session(workspace_id, session_id)
    active = session.active

    resume_offset = _event_resume_offset(
        request,
        workspace_id,
        session_id,
        after=after,
        cursor=cursor,
    )

    if active is None:
        # No live worker (e.g. the run finished between a status check and the
        # SSE reconnect): replay the durable tail once and close instead of
        # letting the browser retry a 404 connection forever.
        return StreamingResponse(
            historical_event_stream(
                workspace_id, session_id, resume_offset,
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    return StreamingResponse(
        live_event_stream(
            workspace_id, session_id, active, resume_offset,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )

def _control_target(active: ActiveRun, requested: Any) -> tuple[str, dict[str, str]]:
    """Validate one control target and snapshot current Agent states.

    Args:
        active: Live run that owns the control registry and optional Swarm.
        requested: JSON body containing an optional ``agent`` field.

    Returns:
        Normalized target and current per-Agent canonical states.

    Raises:
        HTTPException: If a concrete Agent does not exist in this run.
    """
    target = str(requested.get("agent", "all") if isinstance(requested, dict) else "all").strip() or "all"
    states: dict[str, str] = {}
    if active.swarm is not None:
        snapshot = active.swarm.view_snapshot()
        states = {
            str(node["id"]): str(snapshot.get("node_states", {}).get(node["id"], {}).get("state", "queued"))
            for node in snapshot.get("nodes", [])
            if node.get("kind") == "agent"
        }
    else:
        states = {"coordinator": "running"}
    if target != "all" and target not in states:
        raise HTTPException(status_code=404, detail=f"Unknown Agent: {target}")
    if target != "all" and states.get(target) in {"completed", "failed", "interrupted", "cancelled"}:
        raise HTTPException(status_code=409, detail=f"Agent {target!r} is already terminal")
    return target, states


@router.post("/api/workspaces/{workspace_id}/runs/{session_id}/stop")
def stop_run(
    workspace_id: str,
    session_id: str,
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    """Request a cooperative stop for all work or one selected Agent.

    Args:
        workspace_id: Browser storage partition.
        session_id: Active run identifier.
        payload: JSON object whose ``agent`` defaults to ``all``.
    """
    session = _get_session(_safe_id(workspace_id, "workspace"), _safe_id(session_id, "session"))
    if not session.active or session.active.done.is_set():
        raise HTTPException(status_code=409, detail="No active run")
    target, states = _control_target(session.active, payload)
    session.active.control.stop(target)
    if target == "all" and session.active.swarm is not None:
        session.active.swarm.request_shutdown()
    return {"ok": True, "accepted": True, "target": target, "agent_states": states}

@router.post("/api/workspaces/{workspace_id}/runs/{session_id}/force-stop")
def force_stop_run(
    workspace_id: str,
    session_id: str,
    payload: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any]:
    """Force-stop model and tool I/O for all work or one Agent.

    Args:
        workspace_id: Browser storage partition.
        session_id: Active run identifier.
        payload: JSON object whose ``agent`` defaults to ``all``.
    """
    session = _get_session(_safe_id(workspace_id, "workspace"), _safe_id(session_id, "session"))
    if not session.active or session.active.done.is_set():
        raise HTTPException(status_code=409, detail="No active run")
    target, states = _control_target(session.active, payload)
    session.active.force_stop(target)
    if target == "all" and session.active.swarm is not None:
        session.active.swarm.request_shutdown()
    if target == "all":
        _persist_json(_run_state_path(workspace_id, session_id), {
            "status": "force_stopping", "run_id": session_id,
            "requested_at": time.time(),
        })
    return {"ok": True, "accepted": True, "target": target, "agent_states": states}

@router.post("/api/workspaces/{workspace_id}/runs/{session_id}/steer")
def steer_run(workspace_id: str, session_id: str, request: SteerRequest) -> dict[str, bool]:
    """Queue a steering message that Agent.run applies at a safe boundary."""
    session = _get_session(_safe_id(workspace_id, "workspace"), _safe_id(session_id, "session"))
    if not session.active or session.active.done.is_set():
        raise HTTPException(status_code=409, detail="No active run")
    session.active.control.steer(request.message)
    return {"ok": True}


@router.post("/api/workspaces/{workspace_id}/runs/{session_id}/mcp-approvals/{approval_id}")
def resolve_mcp_approval(
    workspace_id: str,
    session_id: str,
    approval_id: str,
    payload: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Resolve sampling or elicitation without logging submitted values.

    Args:
        workspace_id: Browser storage partition.
        session_id: Active run identifier.
        approval_id: Opaque pending approval identifier from SSE.
        payload: ``decision``, optional ``remember``, and elicitation content.
    """
    safe_workspace = _safe_id(workspace_id, "workspace")
    safe_session = _safe_id(session_id, "session")
    session = _get_session(safe_workspace, safe_session)
    if not session.active or session.active.done.is_set():
        raise HTTPException(status_code=409, detail="No active run")
    if payload.get("decision") not in {"allow", "reject"}:
        raise HTTPException(status_code=422, detail="decision must be allow or reject")
    try:
        audit = session.active.resolve_mcp_approval(approval_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="MCP approval not found") from exc
    publish_durable_event(session.active, safe_workspace, safe_session, {
        "event": "mcp_approval_resolved", "timestamp": time.time(), **audit,
    })
    return {"ok": True, **audit}

__all__ = ["start_run", "get_run_status", "stream_events", "stop_run", "force_stop_run", "steer_run", "resolve_mcp_approval", "router"]
