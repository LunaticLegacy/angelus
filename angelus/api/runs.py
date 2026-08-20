"""Run control, status and SSE streaming routes."""

from __future__ import annotations

import json
import queue
import threading
import time
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from llmfetcher import AgentRunStopped
from llmfetcher.events import ExecutionEvent
from llmfetcher.llm_types import LLMOutput
from llmfetcher.swarm_module import AgentFailure

from ..classes import ActiveRun, BrowserRunControl, RunRequest, SteerRequest
from .. import connectors, runtime, storage
from ..history import render_markdown
from ..storage import (
    _append_conversation_turn,
    _append_session_event,
    _deleting_workspaces,
    _get_session,
    _persist_json,
    _read_session_event_log,
    _run_state_path,
    _safe_id,
    _session_path,
    _sessions_lock,
)

router = APIRouter()



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
    with _sessions_lock:
        if workspace_id in _deleting_workspaces:
            raise HTTPException(status_code=409, detail="Workspace is being deleted")
    config = connectors._resolve_connector_key(request.config)
    if not config.model.strip():
        raise HTTPException(status_code=422, detail="Model is required")
    session = _get_session(workspace_id, session_id)
    with session.lock:
        if session.active and not session.active.done.is_set():
            raise HTTPException(status_code=409, detail="This chat already has an active run")
        active = ActiveRun(control=BrowserRunControl())
        session.active = active
    started_at = time.time()
    runtime_profile = runtime._runtime_profile_snapshot(config)
    _persist_json(_run_state_path(workspace_id, session_id), {
        "status": "running", "run_id": session_id, "started_at": started_at,
        "runtime_profile": runtime_profile,
    })
    _append_conversation_turn(workspace_id, session_id, {
        "role": "user", "content": request.message, "reasoning": "", "tools": [],
    })
    _append_session_event(workspace_id, session_id, {
        "event": "run_started",
        "run_id": session_id,
        "timestamp": started_at,
        "message": request.message,
        "runtime_profile": runtime_profile,
    })

    def execute() -> None:
        started = time.time()
        terminal_status = "completed"
        error_message = ""
        try:
            if config.enable_swarm:
                swarm = runtime._build_swarm(config, workspace_id, session_id, active)
                active.swarm = swarm
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
                def capture(event: ExecutionEvent) -> None:
                    """Durably relay one named single-Agent event to the browser.

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
                    _append_session_event(workspace_id, session_id, payload)
                    active.events.put(payload)
                agent.add_hook(capture)
                output = agent.run(
                    request.message,
                    temperature=config.temperature,
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
            _append_session_event(workspace_id, session_id, result_payload)
            active.events.put(result_payload)
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
            _append_session_event(workspace_id, session_id, stopped_payload)
            active.events.put(stopped_payload)
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
            _append_session_event(workspace_id, session_id, error_payload)
            active.events.put(error_payload)
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
                        _append_session_event(workspace_id, session_id, error_payload)
                        active.events.put(error_payload)
            active.done.set()
            run_state = {
                "status": terminal_status, "run_id": session_id,
                "started_at": started_at, "finished_at": time.time(),
                "runtime_profile": runtime_profile,
            }
            if error_message:
                run_state["error"] = error_message
            _persist_json(_run_state_path(workspace_id, session_id), run_state)
            done_payload = {"event": "done", "timestamp": time.time()}
            _append_session_event(workspace_id, session_id, done_payload)
            active.events.put(done_payload)

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
def stream_events(workspace_id: str, session_id: str, after: int = 0) -> StreamingResponse:
    """Stream durable session events after a chronological log offset.

    Args:
        workspace_id: Browser session storage partition.
        session_id: Browser-visible session identity.
        after: Number of already-rendered event-log records. New connections
            replay only later records, so a refresh cannot lose events that an
            earlier SSE consumer removed from its in-memory queue.

    Returns:
        An SSE response that tails ``events.ndjson`` until the active run ends.
    """
    workspace_id = _safe_id(workspace_id, "workspace")
    session_id = _safe_id(session_id, "session")
    session = _get_session(workspace_id, session_id)
    active = session.active
    if active is None:
        # No live worker (e.g. the run finished between a status check and the
        # SSE reconnect): replay the durable tail once and close instead of
        # letting the browser retry a 404 connection forever.
        def replay_historical():
            events = _read_session_event_log(workspace_id, session_id)
            for index, payload in enumerate(events):
                if index >= max(0, after):
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        return StreamingResponse(
            replay_historical(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    def generate():
        next_index = max(0, after)
        while True:
            events = _read_session_event_log(workspace_id, session_id)
            while next_index < len(events):
                payload = events[next_index]
                next_index += 1
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            if active.done.is_set():
                while True:
                    try:
                        active.events.get_nowait()
                    except queue.Empty:
                        break
                break
            # The queue remains a local wake-up/compatibility buffer. Drain it
            # after reading the durable log so abandoned SSE clients cannot
            # retain an unbounded copy of events.
            while True:
                try:
                    active.events.get_nowait()
                except queue.Empty:
                    break
            yield ": keepalive\n\n"
            time.sleep(0.25)

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

@router.post("/api/workspaces/{workspace_id}/runs/{session_id}/stop")
def stop_run(workspace_id: str, session_id: str) -> dict[str, bool]:
    """Request a stop at the next completed model-and-tool boundary."""
    session = _get_session(_safe_id(workspace_id, "workspace"), _safe_id(session_id, "session"))
    if not session.active or session.active.done.is_set():
        raise HTTPException(status_code=409, detail="No active run")
    session.active.control.stop()
    if session.active.swarm is not None:
        session.active.swarm.request_shutdown()
    return {"ok": True}

@router.post("/api/workspaces/{workspace_id}/runs/{session_id}/force-stop")
def force_stop_run(workspace_id: str, session_id: str) -> dict[str, bool]:
    """Interrupt an in-flight model request and kill registered tool processes."""
    session = _get_session(_safe_id(workspace_id, "workspace"), _safe_id(session_id, "session"))
    if not session.active or session.active.done.is_set():
        raise HTTPException(status_code=409, detail="No active run")
    session.active.force_stop()
    if session.active.swarm is not None:
        session.active.swarm.request_shutdown()
    _persist_json(_run_state_path(workspace_id, session_id), {
        "status": "force_stopping", "run_id": session_id,
        "requested_at": time.time(),
    })
    return {"ok": True}

@router.post("/api/workspaces/{workspace_id}/runs/{session_id}/steer")
def steer_run(workspace_id: str, session_id: str, request: SteerRequest) -> dict[str, bool]:
    """Queue a steering message that Agent.run applies at a safe boundary."""
    session = _get_session(_safe_id(workspace_id, "workspace"), _safe_id(session_id, "session"))
    if not session.active or session.active.done.is_set():
        raise HTTPException(status_code=409, detail="No active run")
    session.active.control.steer(request.message)
    return {"ok": True}

__all__ = ["start_run", "get_run_status", "stream_events", "stop_run", "force_stop_run", "steer_run", "router"]
