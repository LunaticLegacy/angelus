"""Local browser UI for configuring and observing a single ``Agent`` run."""

from __future__ import annotations

import json
import os
import queue
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from markdown_it import MarkdownIt

from llmfetcher import Agent, AgentRunStopped
from .classes import (
    ActiveRun,
    BrowserRunControl,
    BrowserSession,
    ConnectorRequest,
    RunConfig,
    RunRequest,
    SteerRequest,
    TaskPlanRequest,
    TaskStatusRequest,
    WorkspaceDeleteRequest,
    WorkspaceRequest,
)
from llmfetcher.events import ExecutionEvent
from llmfetcher.llm_fetcher import LLMBackendConfig, LLMFetcher
from llmfetcher.llm_types import LLMOutput
from llmfetcher.graph_memory import GraphContextHandler
from llmfetcher.tools.shell_tools import create_shell_tools
from llmfetcher.tools.spawn_tools import create_swarm_tools
from llmfetcher.swarm_module.swarm import AgentSwarm
from .task_planning import TaskPlanStore, create_task_planning_tools


PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent
FRONTEND_ROOT = PROJECT_ROOT / "frontend"


def _default_state_root(project_root: Path = PROJECT_ROOT) -> Path:
    """Choose the local Workbench state directory for one source checkout.

    Args:
        project_root: Angelus project root containing the independently owned
            frontend and runtime workspace. Tests may supply a temporary root.

    Returns:
        The project-local ``workspace`` directory for a standalone checkout,
        or the parent superproject's ``workspace`` directory when this exact
        checkout is registered as its ``llmfetcher`` Git submodule.

    Side Effects:
        Reads a parent ``.gitmodules`` file when present. It never creates
        directories or changes Git configuration.
    """
    superproject_root = project_root.parent
    gitmodules_path = superproject_root / ".gitmodules"

    # A submodule checkout should retain the superproject's existing sessions
    # instead of silently creating a second workspace inside the submodule.
    if gitmodules_path.is_file():
        gitmodules = gitmodules_path.read_text(encoding="utf-8", errors="replace")
        if f"path = {project_root.name}" in gitmodules:
            return superproject_root / "workspace"

    return project_root / "workspace"


# Every browser-visible session owns one private directory under ``workspace``.
# An explicit deployment override always takes precedence over checkout layout.
_configured_state_root = os.environ.get("LLMFETCHER_STATE_DIR")
STATE_ROOT = (
    Path(_configured_state_root).resolve()
    if _configured_state_root
    else _default_state_root().resolve()
)
WORKSPACE_ROOT = STATE_ROOT
WORKSPACE_INDEX = STATE_ROOT / "sessions.json"
CONNECTOR_INDEX = STATE_ROOT / "connectors.json"
WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
# Raw HTML remains disabled so model output cannot inject arbitrary browser DOM.
_MARKDOWN = MarkdownIt("commonmark", {"html": False, "linkify": False}).enable("table")


_sessions: dict[tuple[str, str], BrowserSession] = {}
_sessions_lock = threading.Lock()
_deleting_workspaces: set[str] = set()


def _safe_id(value: str, label: str) -> str:
    """Validate IDs before using them in a local storage path."""
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", value):
        raise HTTPException(status_code=400, detail=f"Invalid {label} id")
    return value


def _read_workspaces() -> list[dict[str, str]]:
    """Return the session registry, repairing a missing default session."""
    if not WORKSPACE_INDEX.exists():
        default = [{"id": "default", "name": "default"}]
        WORKSPACE_INDEX.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")
        return default
    try:
        records = json.loads(WORKSPACE_INDEX.read_text(encoding="utf-8"))
        if isinstance(records, list):
            return [item for item in records if isinstance(item, dict) and "id" in item and "name" in item]
    except (OSError, json.JSONDecodeError):
        pass
    return [{"id": "default", "name": "default"}]


def _write_workspaces(workspaces: list[dict[str, str]]) -> None:
    """Atomically replace the small local workspace registry."""
    temporary = WORKSPACE_INDEX.with_suffix(".tmp")
    temporary.write_text(json.dumps(workspaces, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(WORKSPACE_INDEX)


def _conversation_path(workspace_id: str, session_id: str) -> Path:
    """Return the authoritative display transcript for one session.

    Args:
        workspace_id: Session directory identity retained by legacy callers.
        session_id: Browser-visible session identity; it must equal
            ``workspace_id`` in the one-session-one-directory layout.

    Returns:
        JSON file containing only display-safe user and assistant turns.
    """
    return _session_path(workspace_id, session_id) / "conversation.json"


def _run_state_path(workspace_id: str, session_id: str) -> Path:
    """Return the durable browser-facing state file for one Agent run."""
    return _session_path(workspace_id, session_id) / "run-state.json"


def _write_conversation(workspace_id: str, session_id: str, messages: list[dict[str, Any]]) -> None:
    """Atomically replace a session's canonical browser transcript.

    Args:
        workspace_id: Session directory identity.
        session_id: Browser-visible session identity.
        messages: Ordered display-safe user and assistant message records.
    """
    _persist_json(_conversation_path(workspace_id, session_id), {"messages": messages})


def _append_conversation_turn(workspace_id: str, session_id: str, turn: dict[str, Any]) -> None:
    """Append one display turn so refresh never depends on Agent context.

    Args:
        workspace_id: Session directory identity.
        session_id: Browser-visible session identity.
        turn: User or assistant message fields safe for browser restoration.
    """
    path = _conversation_path(workspace_id, session_id)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        messages = payload.get("messages", []) if isinstance(payload, dict) else []
    except (OSError, json.JSONDecodeError):
        messages = []
    messages.append(turn)
    _write_conversation(workspace_id, session_id, messages)


def _workspace_exists(workspace_id: str) -> bool:
    """Return whether a workspace is registered locally."""
    return any(item["id"] == workspace_id for item in _read_workspaces())


def _session_id_from_name(name: str, existing: set[str]) -> str:
    """Build a stable directory-safe session ID from a user display name.

    Args:
        name: User supplied session display name.
        existing: IDs already reserved in the session registry.

    Returns:
        Lowercase ASCII slug when possible, or a generated ID for names that
        cannot be represented safely. A numeric suffix resolves collisions.
    """
    base = re.sub(r"[^a-zA-Z0-9_-]+", "-", name.strip()).strip("-_").lower()
    if not base:
        base = f"session-{uuid.uuid4().hex[:12]}"
    candidate = base[:80]
    suffix = 2
    while candidate in existing:
        ending = f"-{suffix}"
        candidate = f"{base[:80 - len(ending)]}{ending}"
        suffix += 1
    return candidate


def _remove_workspace(workspace_id: str) -> None:
    """Remove a stopped workspace directory and its local registry entry.

    Args:
        workspace_id: Validated workspace ID scheduled for deletion.

    Side Effects:
        Deletes only ``WORKSPACE_ROOT / workspace_id`` and removes matching
        in-memory sessions and the persisted workspace record.
    """
    workspace_path = WORKSPACE_ROOT / workspace_id
    try:
        shutil.rmtree(workspace_path, ignore_errors=False)
    finally:
        with _sessions_lock:
            records = [item for item in _read_workspaces() if item["id"] != workspace_id]
            _write_workspaces(records)
            for key in [key for key in _sessions if key[0] == workspace_id]:
                del _sessions[key]
            _deleting_workspaces.discard(workspace_id)


def _stop_then_remove_workspace(workspace_id: str, active_runs: list[ActiveRun]) -> None:
    """Wait for active work to reach safe stop boundaries before deletion.

    Args:
        workspace_id: Validated workspace ID reserved for deletion.
        active_runs: Runs that were active when deletion was confirmed.

    Side Effects:
        Requests cooperative stops, waits for all runs to finish, then invokes
        :func:`_remove_workspace` in a daemon worker thread.
    """
    for active in active_runs:
        active.control.stop()
    for active in active_runs:
        active.done.wait()
    _remove_workspace(workspace_id)


def _read_connectors() -> list[dict[str, Any]]:
    """Load saved connector records, treating a missing store as empty.

    Returns:
        JSON-compatible connector records ordered by creation time.
    """
    if not CONNECTOR_INDEX.exists():
        return []
    try:
        records = json.loads(CONNECTOR_INDEX.read_text(encoding="utf-8"))
        return records if isinstance(records, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _write_connectors(connectors: list[dict[str, Any]]) -> None:
    """Atomically persist connectors in a current-user-readable JSON file.

    Args:
        connectors: Complete connector collection replacing the prior store.

    Side Effects:
        Creates or replaces ``CONNECTOR_INDEX`` and attempts to set mode 0600
        before the atomic replacement.
    """
    temporary = CONNECTOR_INDEX.with_suffix(".tmp")
    temporary.write_text(json.dumps(connectors, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        temporary.chmod(0o600)
    except OSError:
        pass
    temporary.replace(CONNECTOR_INDEX)


def _get_session(workspace_id: str, session_id: str) -> BrowserSession:
    """Get or create the in-memory holder for a validated browser session."""
    with _sessions_lock:
        return _sessions.setdefault((workspace_id, session_id), BrowserSession())


def _event_payload(event: ExecutionEvent) -> dict[str, Any]:
    """Convert library events to JSON values suitable for Server-Sent Events."""
    return {
        "type": event.event_type,
        "source": event.source,
        "agent": event.agent_name,
        "message": event.message,
        "data": event.data,
        "timestamp": event.timestamp,
    }


def render_markdown(text: str) -> str:
    """Convert trusted-to-render model Markdown into safe display HTML.

    Args:
        text: Raw assistant or reasoning text received from an LLM backend.

    Returns:
        HTML generated by ``markdown-it-py`` with raw HTML and linkification
        disabled. The caller may insert this value into the console message UI.
    """
    return _MARKDOWN.render(text)


def _session_path(workspace_id: str, session_id: str) -> Path:
    """Return the private on-disk directory that owns one browser session.

    Args:
        workspace_id: Validated internal storage partition ID.
        session_id: Validated browser-stable chat ID.

    Returns:
        Directory containing agent contexts, graph views, task plans, and the
        append-only execution event log. It is never returned as a UI label.
    """
    workspace_id = _safe_id(workspace_id, "workspace")
    session_id = _safe_id(session_id, "session")
    # The browser passes the selected session in both legacy fields. Older
    # callers can still provide a distinct second value; the first field is
    # the authoritative session-directory identity during the transition.
    path = WORKSPACE_ROOT / workspace_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _build_agent(config: RunConfig, workspace_id: str, session_id: str, *, agent_name: str = "coordinator", active: ActiveRun | None = None) -> Agent:
    """Create one session-owned Agent from current UI settings.

    Args:
        config: Browser supplied backend and execution configuration.
        workspace_id: Internal partition that owns the browser session.
        session_id: Browser-stable chat identifier.
        agent_name: Graph-local identity used to isolate this Agent's context.

    Returns:
        Configured Agent with planning and optional shell tools. Credentials
        remain in memory and are never written to the session directory.
    """
    backend = LLMBackendConfig(
        name="browser",
        provider=config.provider.strip(),
        model=config.model.strip(),
        api_key=config.api_key,
        api_url=config.api_url.strip() or None,
        timeout=120,
        max_retries=0,
    )
    fetcher = LLMFetcher([backend])
    agent = Agent(
        llm_fetcher=fetcher,
        system_prompt=(config.system_prompt + "\n\nFor a multi-step user goal, first call set_task_plan with an actionable nested plan. Keep task status current with update_task_status as work progresses."),
        # Keep browser-selected compaction behavior consistent for the
        # coordinator and every subsequently created session Agent.
        max_context_threshold=config.max_context_threshold,
        context_path=_context_path(workspace_id, session_id, agent_name),
        default_max_rounds=config.max_rounds,
        default_max_tokens=config.max_tokens,
        # Graph long-term memory: entity/relation graph persisted alongside
        # the linear context file (``<context>.graph.json``), reusing the
        # same LLM for extraction/query fallback and compaction.
        context_handler=GraphContextHandler(
            compacting_fetcher=fetcher,
            max_context_threshold=config.max_context_threshold,
        ),
    )
    if config.enable_shell:
        agent.add_tools(create_shell_tools(
            sandbox_cwd=str(_session_path(workspace_id, session_id)),
            register_process=active.register_process if active else None,
            unregister_process=active.unregister_process if active else None,
            force_stop_event=active.control.force_stopped if active else None,
        ))
    def _on_plan_changed(event_type: str, plan: dict[str, Any]) -> None:
        if active is not None:
            active.events.put({
                "event": "lifecycle",
                **_event_payload(ExecutionEvent(
                    source="plan", agent_name=agent_name,
                    event_type=event_type,
                    message=f"Plan updated ({plan.get('goal', '')[:80]})",
                    data={"plan": plan},
                )),
            })

    agent.add_tools(create_task_planning_tools(
        _plan_store(workspace_id, session_id),
        on_changed=_on_plan_changed,
    ))
    return agent


def _plan_store(workspace_id: str, session_id: str) -> TaskPlanStore:
    """Return the session-local plan store after validating path components."""
    workspace_id = _safe_id(workspace_id, "workspace")
    session_id = _safe_id(session_id, "session")
    return TaskPlanStore(_session_path(workspace_id, session_id) / "task-plan.json")


def _context_path(workspace_id: str, session_id: str, agent_name: str = "coordinator") -> Path:
    """Return the validated JSON context path for one browser session.

    Args:
        workspace_id: Internal workspace identifier owning session files.
        session_id: Browser-stable session identifier.

    Returns:
        Session-local context path owned by the named Agent. Its parent
        directory is created so ``Agent.run()`` can persist history after a
        successful response.

    Side Effects:
        Creates the session's ``contexts`` directory when it does not exist.
    """
    workspace_id = _safe_id(workspace_id, "workspace")
    session_id = _safe_id(session_id, "session")
    agent_name = _safe_id(agent_name, "agent")
    # Agent context persistence does not create parent directories itself.
    context_path = _session_path(workspace_id, session_id) / "contexts" / f"{agent_name}.json"
    context_path.parent.mkdir(parents=True, exist_ok=True)
    return context_path


def _persist_json(path: Path, payload: dict[str, Any]) -> None:
    """Atomically persist JSON runtime metadata for refresh and restart recovery.

    Args:
        path: Session-owned destination file.
        payload: JSON-compatible metadata replacing the prior snapshot.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # Worker hooks can snapshot concurrently; unique siblings avoid one hook
    # replacing another hook's temporary file before its atomic rename.
    temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    temporary.replace(path)


def _append_session_event(workspace_id: str, session_id: str, payload: dict[str, Any]) -> None:
    """Append one serialized runtime event to the session's durable trace.

    Args:
        workspace_id: Internal partition owning the session.
        session_id: Browser-stable session identity.
        payload: SSE-compatible event payload. Non-JSON exception data is
            rendered with ``str`` so observability cannot break execution.
    """
    event_path = _session_path(workspace_id, session_id) / "events.ndjson"
    with event_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


def _read_session_event_log(workspace_id: str, session_id: str) -> list[dict[str, Any]]:
    """Read valid durable events for one browser session in write order.

    Args:
        workspace_id: Session storage partition that owns ``events.ndjson``.
        session_id: Browser-visible session identity within that partition.

    Returns:
        JSON object records in chronological order. Malformed or partial lines
        are ignored so a concurrent append never breaks historical inspection.
    """
    event_path = _session_path(workspace_id, session_id) / "events.ndjson"
    try:
        lines = event_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    events: list[dict[str, Any]] = []
    for line in lines:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def _session_event_page(
    workspace_id: str,
    session_id: str,
    *,
    before: int | None,
    limit: int,
) -> dict[str, Any]:
    """Return a reverse-chronological page from a session's durable trace.

    Args:
        workspace_id: Session storage partition that owns the event log.
        session_id: Browser-visible session identity.
        before: Exclusive chronological offset for older-event pagination;
            ``None`` starts from the newest stored event.
        limit: Requested maximum number of records. Values are clamped to
            ``1..500`` to keep the inspector responsive.

    Returns:
        A mapping containing newest-first ``events``, the total event count,
        and ``next_before`` for the next older page or ``None`` at the start.
    """
    events = _read_session_event_log(workspace_id, session_id)
    page_limit = max(1, min(limit, 500))
    end = len(events) if before is None else max(0, min(before, len(events)))
    start = max(0, end - page_limit)
    # Reverse only the selected slice so the UI can prepend live events while
    # appending older history without reordering either group.
    return {
        "events": list(reversed(events[start:end])),
        "total": len(events),
        "next_before": start if start else None,
    }


def _empty_usage() -> dict[str, int]:
    """Return the complete token-usage shape used by session aggregations."""
    return {"input": 0, "output": 0, "total": 0, "cached": 0, "reasoning": 0}


def _session_usage_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate completed model-round token usage for a browser session.

    Args:
        events: Chronological or reverse-chronological durable event records.
            Only lifecycle records of type ``agent:round`` contribute usage.

    Returns:
        A mapping with session-wide ``usage`` and per-agent usage records.

    ``agent:round`` carries a per-round delta as ``round_usage`` as well as a
    cumulative value. Summing the delta keeps multiple runs and worker Agents
    accurate without double-counting earlier rounds.
    """
    total = _empty_usage()
    by_agent: dict[str, dict[str, int]] = {}
    for event in events:
        if event.get("event") != "lifecycle" or event.get("type") != "agent:round":
            continue
        agent = str(event.get("agent") or "unknown")
        data = event.get("data")
        round_usage = data.get("round_usage") if isinstance(data, dict) else None
        if not isinstance(round_usage, dict):
            continue
        agent_usage = by_agent.setdefault(agent, _empty_usage())
        for key in total:
            value = round_usage.get(key, 0)
            if isinstance(value, (int, float)):
                tokens = max(0, int(value))
                total[key] += tokens
                agent_usage[key] += tokens
    agents = [
        {"id": agent, "usage": usage}
        for agent, usage in sorted(by_agent.items(), key=lambda item: (-item[1]["total"], item[0]))
    ]
    return {"usage": total, "agents": agents}


def _history_context_paths(workspace_id: str, session_id: str) -> list[Path]:
    """Return current and legacy context locations in restoration priority.

    Args:
        workspace_id: Internal partition that owned the historical chat.
        session_id: Browser-stable identifier for that chat.

    Returns:
        Ordered paths beginning with the current coordinator context, followed
        by pre-session-directory workspace and application-wide legacy files.
        This is read-only compatibility; newly created runs write only the
        first path.
    """
    workspace_id = _safe_id(workspace_id, "workspace")
    session_id = _safe_id(session_id, "session")
    return [
        _context_path(workspace_id, session_id),
        WORKSPACE_ROOT / workspace_id / f"{session_id}.json",
    ]


def _read_session_history(workspace_id: str, session_id: str) -> list[dict[str, Any]]:
    """Read display-safe user and assistant turns from persisted context.

    Args:
        workspace_id: Internal workspace identifier owning the context file.
        session_id: Browser-stable session identifier.

    Returns:
        Ordered chat turns. Assistant tool call names, arguments, and bounded
        persisted results are included for inspection; compacted internal
        context is excluded.
    """
    raw: dict[str, Any] | None = None
    try:
        candidate = json.loads(_conversation_path(workspace_id, session_id).read_text(encoding="utf-8"))
        if isinstance(candidate, dict):
            raw = candidate
    except (OSError, json.JSONDecodeError):
        pass
    # This fallback only supports pre-migration installations. New sessions
    # always use conversation.json and therefore have one unambiguous source.
    if raw is None:
        for context_path in _history_context_paths(workspace_id, session_id):
            try:
                candidate = json.loads(context_path.read_text(encoding="utf-8"))
                if isinstance(candidate, dict):
                    raw = candidate
                    break
            except (OSError, json.JSONDecodeError):
                continue
    if raw is None:
        return []
    messages = raw.get("messages", [])
    history: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict) or message.get("role") not in {"user", "assistant"}:
            continue
        content = str(message.get("content", ""))
        reasoning = str(message.get("reasoning", message.get("content_reasoning", "")))
        if not content and not reasoning:
            continue
        tool_calls = []
        for item in message.get("tool_calls", []):
            if not isinstance(item, dict) or not isinstance(item.get("call"), dict):
                continue
            call = item["call"]
            tool_calls.append({
                "name": str(call.get("name", "unknown")),
                "arguments": call.get("arguments", {}),
                "result": str(item.get("result", "")),
            })
        turn: dict[str, Any] = {"role": message["role"], "content": content, "reasoning": reasoning, "tools": tool_calls}
        if message["role"] == "assistant":
            turn["content_html"] = render_markdown(content)
            turn["reasoning_html"] = render_markdown(reasoning)
        history.append(turn)
    return history


def _build_swarm(config: RunConfig, workspace_id: str, session_id: str, active: ActiveRun) -> AgentSwarm:
    """Build a coordinator-led swarm bound to one private session directory.

    Args:
        config: Browser backend and execution settings.
        workspace_id: Internal storage partition owning the session.
        session_id: Browser-stable chat identifier.
        active: Live run holder that receives graph and Agent events.

    Returns:
        An ``AgentSwarm`` whose coordinator can dispatch independent workers
        through ``dispatch_subagent(s)`` and wait for structured reports.

    Side Effects:
        Adds graph and coordinator hooks that persist an event log and replace
        ``graph-view.json`` after topology changes.
    """
    coordinator = _build_agent(config, workspace_id, session_id, active=active)
    swarm = AgentSwarm(max_concurrency_agents=config.max_swarm_agents)
    swarm.add_agent("coordinator", coordinator)
    worker_tools = create_task_planning_tools(_plan_store(workspace_id, session_id))
    if config.enable_shell:
        worker_tools.extend(create_shell_tools(
            sandbox_cwd=str(_session_path(workspace_id, session_id)),
            register_process=active.register_process,
            unregister_process=active.unregister_process,
            force_stop_event=active.control.force_stopped,
        ))
    coordinator.add_tools(create_swarm_tools(
        swarm=swarm,
        llm_fetcher=coordinator.llm_fetcher,
        worker_tool_pool=worker_tools,
        coordinator_name="coordinator",
        worker_max_rounds=config.max_rounds,
        worker_max_tokens=config.max_tokens,
        worker_max_context_threshold=config.max_context_threshold,
        context_path_factory=lambda agent_name: _context_path(workspace_id, session_id, agent_name),
    ))

    def capture(event: ExecutionEvent) -> None:
        """Persist and relay one graph or coordinator event without blocking execution."""
        payload = {"event": "lifecycle", **_event_payload(event)}
        _append_session_event(workspace_id, session_id, payload)
        _persist_json(_session_path(workspace_id, session_id) / "graph-view.json", swarm.view_snapshot())
        active.events.put(payload)

    swarm.add_hook(capture)
    _persist_json(_session_path(workspace_id, session_id) / "graph-view.json", swarm.view_snapshot())
    return swarm


def _turns_from_legacy_context(path: Path) -> list[dict[str, Any]]:
    """Extract browser-safe transcript turns from one old Agent context file.

    Args:
        path: JSON context produced by a legacy ``ContextHandler``.

    Returns:
        Ordered user and assistant turns, or an empty list when the file is
        unreadable or does not contain display messages.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    turns: list[dict[str, Any]] = []
    for message in raw.get("messages", []) if isinstance(raw, dict) else []:
        if not isinstance(message, dict) or message.get("role") not in {"user", "assistant"}:
            continue
        tools = [
            {"name": str(item.get("call", {}).get("name", "unknown")), "arguments": item.get("call", {}).get("arguments", {}), "result": str(item.get("result", ""))}
            for item in message.get("tool_calls", [])
            if isinstance(item, dict) and isinstance(item.get("call"), dict)
        ]
        turns.append({"role": message["role"], "content": str(message.get("content", "")), "reasoning": str(message.get("content_reasoning", "")), "tools": tools})
    return turns


def _turns_from_event_log(path: Path) -> list[dict[str, Any]]:
    """Recover a minimal chat transcript from durable swarm event records.

    Args:
        path: NDJSON event log belonging to a session without Agent context.

    Returns:
        User graph-start messages and final result messages in log order.
    """
    turns: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return turns
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("event") == "lifecycle" and event.get("type") == "graph:start":
            turns.append({"role": "user", "content": str(event.get("message", "")), "reasoning": "", "tools": []})
        elif event.get("event") == "result":
            turns.append({"role": "assistant", "content": str(event.get("content", "")), "reasoning": str(event.get("reasoning", "")), "tools": []})
    return turns


def migrate_legacy_state() -> None:
    """Migrate all `.llmfetcher` data into independent `workspace` sessions.

    The migration runs once when the new registry is absent. Each legacy
    workspace becomes one session directory named after its display name;
    all nested artifacts are copied, newest conflicting context is selected,
    and the original tree is moved into a dated migration backup only after
    the new registry and session transcripts have been written.
    """
    legacy_root = PROJECT_ROOT / ".llmfetcher"
    if WORKSPACE_INDEX.exists() or not legacy_root.is_dir():
        return
    try:
        legacy_records = json.loads((legacy_root / "workspaces.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        legacy_records = []
    records: list[dict[str, str]] = []
    used: set[str] = set()
    for item in legacy_records if isinstance(legacy_records, list) else []:
        if not isinstance(item, dict) or not item.get("id") or not item.get("name"):
            continue
        source = legacy_root / "workspaces" / str(item["id"])
        is_default = str(item["id"]) == "default"
        session_id = "default" if is_default else _session_id_from_name(str(item["name"]), used)
        display_name = "default" if is_default else str(item["name"])
        used.add(session_id)
        target = STATE_ROOT / session_id
        target.mkdir(parents=True, exist_ok=True)
        # Copy nested session artifacts first; reports and logs are preserved verbatim.
        for nested in (source / "sessions").glob("*") if (source / "sessions").is_dir() else []:
            if nested.is_dir():
                shutil.copytree(nested, target, dirs_exist_ok=True)
        contexts = sorted(source.glob("*.json"), key=lambda candidate: candidate.stat().st_mtime, reverse=True) if source.is_dir() else []
        contexts = [candidate for candidate in contexts if not candidate.name.endswith(".plan.json")]
        turns: list[dict[str, Any]] = []
        if contexts:
            context_target = target / "contexts" / "coordinator.json"
            context_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(contexts[0], context_target)
            turns = _turns_from_legacy_context(contexts[0])
        plan_files = sorted(source.glob("*.plan.json"), key=lambda candidate: candidate.stat().st_mtime, reverse=True) if source.is_dir() else []
        if plan_files and not (target / "task-plan.json").exists():
            shutil.copy2(plan_files[0], target / "task-plan.json")
        if not turns:
            turns = _turns_from_event_log(target / "events.ndjson")
        _persist_json(target / "conversation.json", {"messages": turns})
        _persist_json(target / "metadata.json", {"id": session_id, "name": display_name, "legacy_workspace_id": str(item["id"])})
        records.append({"id": session_id, "name": display_name})
    # Preserve historical global contexts as their own recoverable sessions.
    global_contexts = legacy_root / "sessions"
    for context in global_contexts.glob("*.json") if global_contexts.is_dir() else []:
        session_id = _session_id_from_name(f"legacy-{context.stem}", used)
        used.add(session_id)
        target = STATE_ROOT / session_id
        (target / "contexts").mkdir(parents=True, exist_ok=True)
        shutil.copy2(context, target / "contexts" / "coordinator.json")
        _persist_json(target / "conversation.json", {"messages": _turns_from_legacy_context(context)})
        _persist_json(target / "metadata.json", {"id": session_id, "name": session_id, "legacy_global_session_id": context.stem})
        records.append({"id": session_id, "name": session_id})
    if (legacy_root / "connectors.json").exists():
        shutil.copy2(legacy_root / "connectors.json", CONNECTOR_INDEX)
    _write_workspaces(records or [{"id": "default", "name": "default"}])
    backup = STATE_ROOT / f"migration-backup-{int(time.time())}"
    shutil.move(str(legacy_root), str(backup))


migrate_legacy_state()


app = FastAPI(title="llmfetcher Console", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=FRONTEND_ROOT / "static"), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    """Serve the standalone chat console."""
    return FileResponse(FRONTEND_ROOT / "templates" / "index.html")


@app.get("/api/providers")
def providers() -> dict[str, list[str]]:
    """Expose the providers currently registered by the library."""
    return {"providers": list(LLMFetcher.list_available_backend_providers())}


@app.get("/api/connectors")
def list_connectors() -> dict[str, list[dict[str, Any]]]:
    """List locally persisted connector settings, including saved API keys."""
    return {"connectors": _read_connectors()}


@app.post("/api/connectors", status_code=201)
def create_connector(request: ConnectorRequest) -> dict[str, Any]:
    """Persist a named connection and return its complete local record.

    Args:
        request: Provider, model, credential and runtime defaults to store.

    Returns:
        New connector record with its generated stable ID.
    """
    record = {"id": uuid.uuid4().hex, **request.model_dump()}
    with _sessions_lock:
        connectors = _read_connectors()
        connectors.append(record)
        _write_connectors(connectors)
    return record


@app.put("/api/connectors/{connector_id}")
def update_connector(connector_id: str, request: ConnectorRequest) -> dict[str, Any]:
    """Replace one connector's persisted settings while retaining its ID.

    Args:
        connector_id: Stable connector identifier returned by creation.
        request: Entire replacement connector configuration.

    Returns:
        Updated connector record.

    Raises:
        HTTPException: If the connector identifier does not exist.
    """
    connector_id = _safe_id(connector_id, "connector")
    replacement = {"id": connector_id, **request.model_dump()}
    with _sessions_lock:
        connectors = _read_connectors()
        for index, connector in enumerate(connectors):
            if connector.get("id") == connector_id:
                connectors[index] = replacement
                _write_connectors(connectors)
                return replacement
    raise HTTPException(status_code=404, detail="Connector not found")


@app.delete("/api/connectors/{connector_id}", status_code=204)
def delete_connector(connector_id: str) -> None:
    """Delete one persisted connector and its locally stored credential.

    Args:
        connector_id: Stable connector identifier returned by creation.

    Raises:
        HTTPException: If no connector uses ``connector_id``.
    """
    connector_id = _safe_id(connector_id, "connector")
    with _sessions_lock:
        connectors = _read_connectors()
        remaining = [item for item in connectors if item.get("id") != connector_id]
        if len(remaining) == len(connectors):
            raise HTTPException(status_code=404, detail="Connector not found")
        _write_connectors(remaining)


@app.get("/api/workspaces")
def list_workspaces() -> dict[str, list[dict[str, str]]]:
    """List local workspaces available to the browser console."""
    return {"workspaces": _read_workspaces()}


@app.get("/api/sessions")
def list_sessions() -> dict[str, list[dict[str, str]]]:
    """List browser-visible sessions backed by independent workspace paths."""
    return {"sessions": _read_workspaces()}


@app.delete("/api/workspaces/{workspace_id}")
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


@app.get("/api/workspaces/{workspace_id}/sessions/{session_id}/plan")
def get_task_plan(workspace_id: str, session_id: str) -> dict[str, Any]:
    """Return the current persisted task plan for one browser session."""
    return _plan_store(workspace_id, session_id).read()


@app.get("/api/sessions/{session_id}/plan")
def get_session_plan(session_id: str) -> dict[str, Any]:
    """Return the task plan for one independent browser session."""
    return _plan_store(session_id, session_id).read()


@app.get("/api/workspaces/{workspace_id}/sessions/{session_id}/messages")
def get_session_history(workspace_id: str, session_id: str, agent: str = "all") -> dict[str, list[dict[str, Any]]]:
    """Return persisted display turns so a browser refresh restores the chat.

    Args:
        workspace_id: Internal workspace identifier owning the session context.
        session_id: Browser-stable identifier for the current chat.

    Returns:
        Ordered user/assistant display turns, excluding tool result payloads.
    """
    return {"messages": _read_agent_history(workspace_id, session_id, agent)}


def _read_agent_history(workspace_id: str, session_id: str, agent_name: str) -> list[dict[str, Any]]:
    """Read one Agent's complete display transcript from durable events.

    Args:
        workspace_id: Internal storage partition owning the session.
        session_id: Browser-stable identifier for the current chat.
        agent_name: Selected graph Agent, or ``all`` for the canonical chat.

    Returns:
        Chronological user prompts and detailed Agent turns. Event history is
        preferred because an Agent context may discard old turns during
        compaction; legacy contexts remain a fallback for older sessions.
    """
    if agent_name in {"", "all"}:
        return _read_session_history(workspace_id, session_id)
    agent_name = _safe_id(agent_name, "agent")
    turns = _agent_turns_from_events(workspace_id, session_id, agent_name)
    if turns:
        return turns
    context_path = _session_path(workspace_id, session_id) / "contexts" / f"{agent_name}.json"
    turns = _turns_from_legacy_context(context_path)
    for turn in turns:
        if turn.get("role") == "assistant":
            turn["content_html"] = render_markdown(str(turn.get("content", "")))
            turn["reasoning_html"] = render_markdown(str(turn.get("reasoning", "")))
    return turns


def _agent_turns_from_events(
    workspace_id: str,
    session_id: str,
    agent_name: str,
) -> list[dict[str, Any]]:
    """Reconstruct an Agent transcript from the append-only lifecycle log.

    Args:
        workspace_id: Internal storage partition owning ``events.ndjson``.
        session_id: Browser-stable identifier for the current chat.
        agent_name: Graph Agent whose model rounds should be included.

    Returns:
        Chronological user prompts and assistant rounds with rendered Markdown
        and completed tool evidence. A coordinator result identical to its
        final model round is emitted only once.
    """
    turns: list[dict[str, Any]] = []
    completed_tools: dict[tuple[str, int], list[dict[str, Any]]] = {}
    last_assistant: tuple[str, str] | None = None
    # One round-identity tracker per Agent, reset at its ``agent:start``.
    # The graph used to relay each Agent event through two hook paths, so the
    # durable log may contain an immediate second copy of every round.  A round
    # that exactly repeats the previous (agent, round, content, reasoning) is
    # that duplicate, not a real new model step.
    last_round: dict[str, tuple[int, str, str]] = {}

    for event in _read_session_event_log(workspace_id, session_id):
        event_kind = str(event.get("event", ""))
        event_type = str(event.get("type", ""))
        event_agent = str(event.get("agent") or "coordinator")
        data = event.get("data") if isinstance(event.get("data"), dict) else {}

        # Agent starts delimit one run boundary for round deduplication.
        # Coordinator starts also delimit real browser submissions; showing
        # those in every Agent filter preserves the user-side conversation.
        if event_kind == "lifecycle" and event_type == "agent:start":
            last_round.pop(event_agent, None)
            if event_agent != "coordinator":
                continue
            content = str(event.get("message", ""))
            if content:
                turns.append({"role": "user", "content": content, "reasoning": "", "tools": []})
            last_assistant = None
            continue

        # Tool completion precedes its matching model-round event, allowing
        # the detailed message to carry both request arguments and results.
        if event_kind == "lifecycle" and event_type == "agent:tools_completed":
            round_number = data.get("round")
            if event_agent == agent_name and isinstance(round_number, int):
                completed_tools[(event_agent, round_number)] = _display_tools_from_event(data)
            continue
        if event_kind == "lifecycle" and event_type == "agent:round" and event_agent == agent_name:
            content = str(data.get("assistant_content", ""))
            reasoning = str(data.get("reasoning_content", ""))
            tools = completed_tools.pop((event_agent, data.get("round")), [])
            if not content and not reasoning and not tools:
                continue
            round_number = data.get("round")
            previous_round = last_round.get(event_agent)
            if (
                isinstance(round_number, int)
                and previous_round is not None
                and previous_round == (round_number, content, reasoning)
            ):
                # Immediate duplicate copy of the same round (legacy double-write).
                continue
            turn = {"role": "assistant", "content": content, "reasoning": reasoning, "tools": tools}
            turn["content_html"] = render_markdown(content)
            turn["reasoning_html"] = render_markdown(reasoning)
            turns.append(turn)
            last_assistant = (content, reasoning)
            if isinstance(round_number, int):
                last_round[event_agent] = (round_number, content, reasoning)
            continue

        # The top-level result repeats the coordinator's final model round in
        # normal runs, but remains necessary for old or partial event logs.
        if event_kind == "result" and agent_name == "coordinator":
            content = str(event.get("content", ""))
            reasoning = str(event.get("reasoning", ""))
            if (not content and not reasoning) or last_assistant == (content, reasoning):
                continue
            turn = {"role": "assistant", "content": content, "reasoning": reasoning, "tools": []}
            turn["content_html"] = render_markdown(content)
            turn["reasoning_html"] = render_markdown(reasoning)
            turns.append(turn)
            last_assistant = (content, reasoning)
    return turns


def _display_tools_from_event(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize completed lifecycle tool calls for browser display.

    Args:
        data: ``agent:tools_completed`` event data.

    Returns:
        Safe tool name, argument, and persisted result mappings in call order.
    """
    tools: list[dict[str, Any]] = []
    for item in data.get("tool_calls", []):
        if not isinstance(item, dict):
            continue
        tools.append({
            "name": str(item.get("name", "unknown")),
            "arguments": item.get("args", {}),
            "result": str(item.get("result", "")),
        })
    return tools


@app.get("/api/sessions/{session_id}/messages")
def get_session_messages(session_id: str, agent: str = "all") -> dict[str, list[dict[str, Any]]]:
    """Return the aggregate or selected Agent transcript for one session."""
    return {"messages": _read_agent_history(session_id, session_id, agent)}


def _agent_context_stats(session_id: str, agent_name: str) -> dict[str, Any]:
    """Return current context-length statistics for one Agent.

    Reads the Agent's persisted linear-context JSON
    (``contexts/<agent>.json``) and summarizes the retained conversation:
    message count, estimated character size of retained messages, the
    compacted abstract size (when compaction already ran), the compaction
    threshold, and the estimated ratio of current size to that threshold.

    Args:
        session_id: Browser-stable session identity.
        agent_name: Graph Agent whose context file is read.

    Returns:
        Dict with ``messages``, ``characters``, ``abstract_characters``,
        ``compacted``, ``threshold``, ``round`` and ``ratio`` keys. Missing
        or malformed context files yield all-zero defaults so the UI can
        render an empty state instead of failing.
    """
    stats = {
        "messages": 0,
        "characters": 0,
        "abstract_characters": 0,
        "compacted": False,
        "threshold": 0,
        "round": 0,
        "ratio": 0.0,
    }
    try:
        safe_session = _safe_id(session_id, "session")
        safe_agent = _safe_id(agent_name, "agent")
        path = _session_path(safe_session, safe_session) / "contexts" / f"{safe_agent}.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return stats

    if not isinstance(raw, dict):
        return stats

    messages = raw.get("messages", [])
    if isinstance(messages, list):
        stats["messages"] = len(messages)
        stats["characters"] = sum(
            len(json.dumps(msg, ensure_ascii=False, default=str))
            for msg in messages
            if isinstance(msg, dict)
        )

    abstract = raw.get("abstract")
    if isinstance(abstract, dict):
        stats["compacted"] = True
        stats["abstract_characters"] = len(
            json.dumps(abstract, ensure_ascii=False, default=str)
        )

    threshold = raw.get("compress_threshold")
    if isinstance(threshold, (int, float)) and threshold > 0:
        stats["threshold"] = int(threshold)

    round_value = raw.get("round")
    if isinstance(round_value, (int, float)) and not isinstance(round_value, bool):
        stats["round"] = int(round_value)

    # Estimated ratio of retained context to the compaction threshold.
    total_chars = stats["characters"] + stats["abstract_characters"]
    if stats["threshold"] > 0:
        stats["ratio"] = round(min(1.0, total_chars / stats["threshold"]), 4)

    return stats


@app.get("/api/sessions/{session_id}/agents")
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


@app.get("/api/workspaces/{workspace_id}/sessions/{session_id}/graph")
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


@app.get("/api/sessions/{session_id}/graph")
def get_session_graph_by_id(session_id: str) -> dict[str, Any]:
    """Return a session's safe persisted execution-graph view."""
    return get_session_graph(session_id, session_id)


@app.get("/api/sessions/{session_id}/events")
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


@app.get("/api/sessions/{session_id}/steers")
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


@app.get("/api/sessions/{session_id}/steers")
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


@app.get("/api/sessions/{session_id}/usage")
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


@app.put("/api/workspaces/{workspace_id}/sessions/{session_id}/plan")
def replace_task_plan(workspace_id: str, session_id: str, request: TaskPlanRequest) -> dict[str, Any]:
    """Allow a user to replace their supervised task plan from the UI."""
    try:
        return _plan_store(workspace_id, session_id).replace(goal=request.goal, summary=request.summary, tasks=request.tasks)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.patch("/api/workspaces/{workspace_id}/sessions/{session_id}/plan/tasks/{task_id}")
def update_task_plan_status(workspace_id: str, session_id: str, task_id: str, request: TaskStatusRequest) -> dict[str, Any]:
    """Persist a status change made by a task-block control in the UI."""
    try:
        return _plan_store(workspace_id, session_id).update_status(task_id, request.status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.patch("/api/sessions/{session_id}/plan/tasks/{task_id}")
def update_session_plan_status(session_id: str, task_id: str, request: TaskStatusRequest) -> dict[str, Any]:
    """Persist one task-status transition within an independent session."""
    try:
        return _plan_store(session_id, session_id).update_status(task_id, request.status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/workspaces", status_code=201)
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
    (WORKSPACE_ROOT / workspace_id).mkdir(parents=True, exist_ok=True)
    return record


@app.post("/api/sessions", status_code=201)
def create_session(request: WorkspaceRequest) -> dict[str, str]:
    """Create one browser-visible session and its private workspace path."""
    return create_workspace(request)


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str, request: WorkspaceDeleteRequest) -> dict[str, Any]:
    """Delete one session after confirmation and cooperative run shutdown."""
    return delete_workspace(session_id, request)


@app.post("/api/runs")
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
    if not _workspace_exists(workspace_id):
        raise HTTPException(status_code=404, detail="Workspace not found")
    with _sessions_lock:
        if workspace_id in _deleting_workspaces:
            raise HTTPException(status_code=409, detail="Workspace is being deleted")
    if not request.config.model.strip():
        raise HTTPException(status_code=422, detail="Model is required")
    session = _get_session(workspace_id, session_id)
    with session.lock:
        if session.active and not session.active.done.is_set():
            raise HTTPException(status_code=409, detail="This chat already has an active run")
        active = ActiveRun(control=BrowserRunControl())
        session.active = active
    started_at = time.time()
    _persist_json(_run_state_path(workspace_id, session_id), {
        "status": "running", "run_id": session_id, "started_at": started_at,
    })
    _append_conversation_turn(workspace_id, session_id, {
        "role": "user", "content": request.message, "reasoning": "", "tools": [],
    })

    def execute() -> None:
        started = time.time()
        terminal_status = "completed"
        error_message = ""
        try:
            if request.config.enable_swarm:
                swarm = _build_swarm(request.config, workspace_id, session_id, active)
                active.swarm = swarm
                outputs = swarm.run(request.message, control=active.control)
                output = outputs.get("coordinator")
                if not isinstance(output, LLMOutput):
                    raise RuntimeError("Coordinator did not produce a language-model output")
                _persist_json(_session_path(workspace_id, session_id) / "graph-view.json", swarm.view_snapshot())
                # Aggregate token usage across every executed agent
                # (coordinator + workers), each of which already includes
                # its own internal compaction / graph-memory LLM calls.
                usage = swarm.total_usage()
            else:
                agent = _build_agent(request.config, workspace_id, session_id, active=active)
                def capture(event: ExecutionEvent) -> None:
                    """Durably relay one named single-Agent event to the browser.

                    Library-created single Agents do not assign an event name,
                    so this adapter supplies the browser-visible coordinator
                    identity required to group lifecycle records.
                    """
                    payload = {"event": "lifecycle", **_event_payload(event)}
                    payload["agent"] = payload["agent"] or "coordinator"
                    _append_session_event(workspace_id, session_id, payload)
                    active.events.put(payload)
                agent.add_hook(capture)
                output = agent.run(
                    request.message,
                    temperature=request.config.temperature,
                    control=active.control,
                )
                usage = {
                    "input": agent.usage.input_tokens,
                    "output": agent.usage.output_tokens,
                    "total": agent.usage.total_tokens,
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
            if output is not None and not request.config.enable_swarm:
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
            }
            if error_message:
                run_state["error"] = error_message
            _persist_json(_run_state_path(workspace_id, session_id), run_state)
            done_payload = {"event": "done", "timestamp": time.time()}
            _append_session_event(workspace_id, session_id, done_payload)
            active.events.put(done_payload)

    threading.Thread(target=execute, name=f"llmfetcher-{session_id}", daemon=True).start()
    return {"run_id": session_id, "workspace_id": workspace_id}


@app.get("/api/workspaces/{workspace_id}/runs/{session_id}/status")
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


@app.get("/api/workspaces/{workspace_id}/runs/{session_id}/events")
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
        raise HTTPException(status_code=404, detail="No active run")

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


@app.post("/api/workspaces/{workspace_id}/runs/{session_id}/stop")
def stop_run(workspace_id: str, session_id: str) -> dict[str, bool]:
    """Request a stop at the next completed model-and-tool boundary."""
    session = _get_session(_safe_id(workspace_id, "workspace"), _safe_id(session_id, "session"))
    if not session.active or session.active.done.is_set():
        raise HTTPException(status_code=409, detail="No active run")
    session.active.control.stop()
    if session.active.swarm is not None:
        session.active.swarm.request_shutdown()
    return {"ok": True}


@app.post("/api/workspaces/{workspace_id}/runs/{session_id}/force-stop")
def force_stop_run(workspace_id: str, session_id: str) -> dict[str, bool]:
    """Immediately stop the Agent and terminate registered tool processes."""
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


@app.post("/api/workspaces/{workspace_id}/runs/{session_id}/steer")
def steer_run(workspace_id: str, session_id: str, request: SteerRequest) -> dict[str, bool]:
    """Queue a steering message that Agent.run applies at a safe boundary."""
    session = _get_session(_safe_id(workspace_id, "workspace"), _safe_id(session_id, "session"))
    if not session.active or session.active.done.is_set():
        raise HTTPException(status_code=409, detail="No active run")
    session.active.control.steer(request.message)
    return {"ok": True}


def main() -> None:
    """Run the local console with ``llmfetcher-web``."""
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8765)
