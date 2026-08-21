"""Agent and Swarm construction plus run-scoped helpers for the web API."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from llmfetcher import Agent
from llmfetcher.events import ExecutionEvent
from llmfetcher.graph_memory import GraphContextHandler, SemanticGraphWorker
from llmfetcher.llm_fetcher import LLMBackendConfig, LLMFetcher
from llmfetcher.swarm_module import GraphPersistenceError
from llmfetcher.swarm_module.swarm import AgentSwarm
from llmfetcher.tools.shell_tools import create_shell_tools
from llmfetcher.tools.spawn_tools import create_swarm_tools, create_task_report_tool

from .classes import ActiveRun, RunConfig
from .context_editing import ContextEditStore, create_context_editing_tools
from .markdown import render_markdown
from .mcp_tools import create_mcp_tools
from .provider_adapters import create_fetcher, effective_temperature, resolve_provider
from .session_memory import CAPABILITIES, SessionMemoryStore, create_session_memory_tools
from . import storage
from .storage import (
    _append_session_event,
    _context_path,
    _persist_json,
    _safe_id,
    _session_path,
)
from .task_planning import TaskPlanStore, create_task_planning_tools



def _event_payload(event: ExecutionEvent) -> dict[str, Any]:
    """Convert library events to JSON values suitable for Server-Sent Events."""
    data = event.data
    # A completed model round reaches the browser before the durable-history
    # reload.  Render it here with the same raw-HTML-disabled renderer used by
    # history so live Agent replies and reloaded replies never diverge.
    if event.event_type == "agent:round" and isinstance(data, dict):
        data = dict(data)
        content = str(data.get("assistant_content") or "")
        reasoning = str(data.get("reasoning_content") or "")
        data["assistant_content_html"] = render_markdown(content)
        data["reasoning_content_html"] = render_markdown(reasoning)
    return {
        "type": event.event_type,
        "source": event.source,
        "agent": event.agent_name,
        "message": event.message,
        "data": data,
        "timestamp": event.timestamp,
    }

def _redacted_api_url(value: str) -> str:
    """Return an endpoint identity without URL credentials or query secrets."""
    try:
        parsed = urlsplit(value.strip())
        if not parsed.scheme or not parsed.netloc:
            return ""
        host = parsed.hostname or ""
        if parsed.port is not None:
            host = f"{host}:{parsed.port}"
        return urlunsplit((parsed.scheme, host + parsed.path, "", "", ""))
    except ValueError:
        return ""

def _runtime_profile_snapshot(config: RunConfig) -> dict[str, Any]:
    """Build a credential-free, stable description of one run's semantics.

    The browser configuration is otherwise ephemeral.  Keeping this snapshot
    next to the run terminal makes a restored context auditable without ever
    serializing the API key or the full (potentially private) system prompt.
    """
    system_prompt_digest = hashlib.sha256(config.system_prompt.encode("utf-8")).hexdigest()
    _, effective_api_url = resolve_provider(config.provider, config.api_url)
    profile = {
        "schema_version": 1,
        "provider": config.provider.strip(),
        "model": config.model.strip(),
        "api_url": _redacted_api_url(effective_api_url),
        "system_prompt_sha256": system_prompt_digest,
        "temperature": effective_temperature(config.provider, config.temperature),
        "max_tokens": config.max_tokens,
        "max_rounds": config.max_rounds,
        "max_retries": config.max_retries,
        "max_context_threshold": config.max_context_threshold,
        "enable_shell": config.enable_shell,
        "enable_mcp": config.enable_mcp,
        "mcp_servers": sorted(
            (
                {"name": str(server.get("name", "")), "transport": str(server.get("transport", "stdio"))}
                for server in config.mcp_servers
                if isinstance(server, dict)
            ),
            key=lambda server: (server["name"], server["transport"]),
        ),
        "enable_swarm": config.enable_swarm,
        "max_swarm_agents": config.max_swarm_agents,
        "session_memory_allowlists": {
            "search_sessions": sorted(config.session_memory_search_sessions),
            "read_sessions": sorted(config.session_memory_read_sessions),
            "artifact_search_sessions": sorted(config.session_artifact_search_sessions),
            "artifact_open_sessions": sorted(config.session_artifact_open_sessions),
        },
    }
    canonical = json.dumps(profile, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return {**profile, "fingerprint": hashlib.sha256(canonical.encode("utf-8")).hexdigest()}

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
    provider, api_url = resolve_provider(config.provider, config.api_url)
    backend = LLMBackendConfig(
        name="browser",
        provider=provider,
        model=config.model.strip(),
        api_key=config.api_key,
        api_url=api_url or None,
        timeout=120,
        max_retries=config.max_retries,
    )
    fetcher = create_fetcher(backend, config.provider)
    semantic_worker = SemanticGraphWorker(fetcher)
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
            extraction_fetcher=semantic_worker,
            query_fetcher=semantic_worker,
            retrieval_trigger="every_message",
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
    agent.add_tools(_mcp_tools(config, active))
    def _on_plan_changed(event_type: str, plan: dict[str, Any]) -> None:
        _publish_plan_change(
            active, workspace_id, session_id, agent_name, event_type, plan
        )

    agent.add_tools(create_task_planning_tools(
        _plan_store(workspace_id, session_id),
        on_changed=_on_plan_changed,
    ))
    agent.add_tools(create_session_memory_tools(
        _session_memory_store(), session_id, _memory_capabilities(config, session_id), uuid.uuid4().hex,
    ))
    context_path = _context_path(workspace_id, session_id, agent_name)
    agent.add_tools(create_context_editing_tools(
        ContextEditStore(context_path, agent_name),
        persist_context=lambda: agent.context_handler.save(context_path),
        reload_context=lambda: agent.context_handler.load(context_path),
    ))
    return agent


def _mcp_tools(config: RunConfig, active: ActiveRun | None) -> list[Any]:
    """Open one SDK-backed MCP bridge and share it across every run Agent."""
    if not config.enable_mcp:
        return []
    if active is None:
        raise RuntimeError("MCP tools require an active browser run for lifecycle cleanup")
    if active.mcp_bridge is None:
        bridge, tools = create_mcp_tools(config.mcp_servers)
        active.mcp_bridge = bridge
        active.mcp_tools = tools
    return list(active.mcp_tools)

def _memory_capabilities(config: RunConfig, current_session: str) -> dict[str, set[str]]:
    """Freeze the four explicit session grants for one Agent run."""
    fields = {
        "session_memory.search_sessions": config.session_memory_search_sessions,
        "session_memory.read_sessions": config.session_memory_read_sessions,
        "session_artifact.search_sessions": config.session_artifact_search_sessions,
        "session_artifact.open_sessions": config.session_artifact_open_sessions,
    }
    grants: dict[str, set[str]] = {}
    for capability, values in fields.items():
        checked = {current_session}
        for value in values:
            checked.add(_safe_id(value, "session"))
        grants[capability] = checked
    return grants

def _session_memory_store() -> SessionMemoryStore:
    """Create a store whose audit records use the normal durable event log."""
    return SessionMemoryStore(storage.WORKSPACE_ROOT, lambda session, payload: _append_session_event(session, session, payload))

def _publish_plan_change(
    active: ActiveRun | None,
    workspace_id: str,
    session_id: str,
    agent_name: str,
    event_type: str,
    plan: dict[str, Any],
) -> None:
    """Persist and relay one Agent-owned plan mutation to the workbench."""
    payload = {
        "event": "lifecycle",
        **_event_payload(ExecutionEvent(
            source="plan",
            agent_name=agent_name,
            event_type=event_type,
            message=f"{agent_name} plan updated ({plan.get('goal', '')[:80]})",
            data={"plan": plan},
        )),
    }
    _append_session_event(workspace_id, session_id, payload)
    if active is not None:
        active.events.put(payload)


def _plan_store(
    workspace_id: str, session_id: str, agent_name: str = "coordinator"
) -> TaskPlanStore:
    """Return one Agent-owned plan store inside a browser session.

    ``coordinator`` retains the historical ``task-plan.json`` path so existing
    sessions remain readable.  Every subagent receives an isolated sibling
    under ``plans/`` and can therefore never replace the coordinator tree.
    """
    workspace_id = _safe_id(workspace_id, "workspace")
    session_id = _safe_id(session_id, "session")
    agent_name = _safe_id(agent_name, "agent")
    session_dir = _session_path(workspace_id, session_id)
    path = (
        session_dir / "task-plan.json"
        if agent_name == "coordinator"
        else session_dir / "plans" / f"{agent_name}.json"
    )
    return TaskPlanStore(path)


def _swarm_snapshot_path(workspace_id: str, session_id: str) -> Any:
    """Return the private restart-recovery snapshot path for one Swarm.

    Args:
        workspace_id: Internal storage partition owning the session.
        session_id: Browser-stable session identifier.

    Returns:
        Session-owned ``swarm-runtime.json`` path. It is not a browser graph
        view: it contains local worker prompt blueprints but never API keys.
    """
    return _session_path(workspace_id, session_id) / "swarm-runtime.json"


def _worker_tools_for(
    config: RunConfig,
    workspace_id: str,
    session_id: str,
    active: ActiveRun,
    agent_name: str,
) -> list[Any]:
    """Create isolated non-report tools for one dynamically created worker.

    Args:
        config: Current browser execution settings.
        workspace_id: Storage partition owning the run.
        session_id: Browser-stable session identity.
        active: Current process-local lifecycle holder.
        agent_name: New graph-local worker identity.

    Returns:
        Planning, session-memory, optional shell, and MCP tools. The caller
        adds the worker's terminal report tool separately when applicable.
    """
    def on_plan_changed(event_type: str, plan: dict[str, Any]) -> None:
        """Publish mutations to the plan owned by this one worker."""
        _publish_plan_change(active, workspace_id, session_id, agent_name, event_type, plan)

    tools = create_task_planning_tools(
        _plan_store(workspace_id, session_id, agent_name),
        on_changed=on_plan_changed,
    )
    tools.extend(create_session_memory_tools(
        _session_memory_store(), session_id,
        _memory_capabilities(config, session_id), uuid.uuid4().hex,
    ))
    if config.enable_shell:
        tools.extend(create_shell_tools(
            sandbox_cwd=str(_session_path(workspace_id, session_id)),
            register_process=active.register_process,
            unregister_process=active.unregister_process,
            force_stop_event=active.control.force_stopped,
        ))
    tools.extend(_mcp_tools(config, active))
    return tools


def _bind_worker_context_tools(
    workspace_id: str,
    session_id: str,
    agent_name: str,
    worker: Agent,
    tools: list[Any],
) -> list[Any]:
    """Attach live-context edit tools after a dynamic worker is constructed.

    Args:
        workspace_id: Storage partition owning the worker context.
        session_id: Browser-stable session identity.
        agent_name: Newly created graph-local worker identity.
        worker: Live Agent whose context handler must be reloaded after edits.
        tools: Existing worker-local tools created before the Agent existed.

    Returns:
        ``tools`` plus context edit handlers bound to this exact Agent.
    """
    context_path = _context_path(workspace_id, session_id, agent_name)
    return tools + create_context_editing_tools(
        ContextEditStore(context_path, agent_name),
        persist_context=lambda: worker.context_handler.save(context_path),
        reload_context=lambda: worker.context_handler.load(context_path),
    )


def _attach_swarm_runtime_tools(
    swarm: AgentSwarm,
    coordinator: Agent,
    config: RunConfig,
    workspace_id: str,
    session_id: str,
    active: ActiveRun,
) -> None:
    """Install coordinator tools that create future worker Agents in ``swarm``.

    Args:
        swarm: Live or restored graph receiving future topology mutations.
        coordinator: Coordinator Agent already registered in ``swarm``.
        config: Current browser execution settings.
        workspace_id: Storage partition owning the run.
        session_id: Browser-stable session identity.
        active: Process-local run holder captured by tool closures.

    Side Effects:
        Adds dispatch, graph-control, and revival tools to ``coordinator``.
    """
    coordinator.add_tools(create_swarm_tools(
        swarm=swarm,
        llm_fetcher=coordinator.llm_fetcher,
        worker_tool_pool=[],
        worker_tool_factory=lambda agent_name: _worker_tools_for(
            config, workspace_id, session_id, active, agent_name,
        ),
        worker_tool_binder=lambda agent_name, worker, tools: _bind_worker_context_tools(
            workspace_id, session_id, agent_name, worker, tools,
        ),
        coordinator_name="coordinator",
        worker_max_rounds=config.max_rounds,
        worker_max_tokens=config.max_tokens,
        worker_max_context_threshold=config.max_context_threshold,
        context_path_factory=lambda agent_name: _context_path(workspace_id, session_id, agent_name),
    ))


def _attach_swarm_observer(
    swarm: AgentSwarm,
    workspace_id: str,
    session_id: str,
    active: ActiveRun,
) -> None:
    """Persist and stream lifecycle events emitted by a live or restored Swarm.

    Args:
        swarm: Swarm whose hooks should be observed.
        workspace_id: Storage partition owning durable event and graph files.
        session_id: Browser-stable session identity.
        active: Process-local holder whose SSE queue receives the event.
    """
    def capture(event: ExecutionEvent) -> None:
        """Persist one event before waking browser SSE consumers."""
        payload = {"event": "lifecycle", **_event_payload(event)}
        _append_session_event(workspace_id, session_id, payload)
        _persist_json(_session_path(workspace_id, session_id) / "graph-view.json", swarm.view_snapshot())
        active.events.put(payload)

    swarm.add_hook(capture)
    _persist_json(_session_path(workspace_id, session_id) / "graph-view.json", swarm.view_snapshot())


def _synchronize_context_threshold(
    agents: list[Agent],
    max_context_threshold: int,
) -> tuple[str, ...]:
    """Apply the current browser compaction threshold before one run begins.

    Args:
        agents: Live Agent instances participating in the upcoming run.
        max_context_threshold: Browser-selected character threshold to make
            authoritative for their active context files.

    Returns:
        Agent names whose context handler accepted and persisted the value.

    Side Effects:
        Updates each Agent and its persisted context before ``Agent.run``
        reloads that context. This prevents a prior checkpoint's threshold
        from silently overriding a newer setting on retained Swarm workers.
    """
    synchronized: list[str] = []
    for agent in agents:
        setter = getattr(agent, "set_context_threshold", None)
        # Test doubles and third-party Agent-compatible wrappers may predate
        # this optional synchronization method; they remain runnable while
        # first-party Agents always persist the selected threshold.
        if callable(setter) and setter(max_context_threshold, persist=True):
            synchronized.append(getattr(agent, "_agent_name_in_graph", "") or "coordinator")
    return tuple(synchronized)


def _synchronize_swarm_context_threshold(swarm: AgentSwarm, config: RunConfig) -> tuple[str, ...]:
    """Synchronize every currently retained Swarm Agent with ``config``.

    Args:
        swarm: Existing or restored Swarm about to execute a browser turn.
        config: Current request settings containing the authoritative threshold.

    Returns:
        Names of Agents whose context checkpoint was updated.
    """
    agents = [
        swarm.get_agent(str(node.get("id", "")))
        for node in swarm.view_snapshot().get("nodes", [])
        if isinstance(node, dict)
    ]
    return _synchronize_context_threshold(
        [agent for agent in agents if agent is not None],
        config.max_context_threshold,
    )


def _persist_swarm_snapshot(swarm: AgentSwarm, workspace_id: str, session_id: str) -> None:
    """Write a quiescent, credential-free Swarm recovery snapshot.

    Args:
        swarm: Completed Swarm whose TaskBus contains no running task.
        workspace_id: Storage partition owning the session.
        session_id: Browser-stable session identity.

    Raises:
        GraphPersistenceError: If a graph callback cannot be represented as a
            safe declarative or explicitly serialized value.

    Side Effects:
        Replaces ``swarm-runtime.json`` atomically. Dynamic worker prompts are
        retained locally because they are required to recreate their Agents;
        API keys, connector secrets, and endpoint credentials are absent.
    """
    dispatched = set(swarm.dispatched_agent_names())

    def serialize_agent(name: str, agent: Agent) -> dict[str, Any]:
        """Encode only the prompt role necessary to rebuild one Agent."""
        if name == "coordinator":
            return {"kind": "angelus.swarm-agent.v1", "role": "coordinator"}
        return {
            "kind": "angelus.swarm-agent.v1",
            "role": "dispatched" if name in dispatched else "dynamic",
            "system_prompt": agent.system_prompt,
        }

    swarm.save(_swarm_snapshot_path(workspace_id, session_id), agent_serializer=serialize_agent)


def _restore_swarm(
    config: RunConfig,
    workspace_id: str,
    session_id: str,
    active: ActiveRun,
) -> AgentSwarm | None:
    """Rebuild a completed Swarm graph after a backend process restart.

    Args:
        config: Current browser configuration; it supplies ephemeral API keys
            and the backend used for every restored Agent.
        workspace_id: Storage partition owning the recovery snapshot.
        session_id: Browser-stable session identity.
        active: Newly allocated process-local lifecycle holder.

    Returns:
        Reconstructed Swarm, or ``None`` when no compatible quiescent snapshot
        exists. Invalid snapshots are deliberately ignored so a new session
        turn remains available instead of becoming unrecoverable.

    Side Effects:
        Reopens MCP tools as required, restores terminal worker identities and
        TaskBus history, reattaches their report tools, and persists a fresh UI
        graph view. No secret is read from the snapshot.
    """
    snapshot_path = _swarm_snapshot_path(workspace_id, session_id)
    if not snapshot_path.is_file():
        return None

    def resolve_agent(name: str, spec: Any) -> Agent:
        """Create a current-config Agent from one validated local blueprint."""
        if not isinstance(spec, dict) or spec.get("kind") != "angelus.swarm-agent.v1":
            raise GraphPersistenceError(f"Unsupported Angelus Swarm Agent spec for {name!r}")
        role = str(spec.get("role", ""))
        agent = _build_agent(config, workspace_id, session_id, agent_name=name, active=active)
        if role == "coordinator":
            return agent
        if role not in {"dynamic", "dispatched"}:
            raise GraphPersistenceError(f"Unsupported Angelus Swarm Agent role for {name!r}")
        prompt = spec.get("system_prompt")
        if not isinstance(prompt, str) or not prompt:
            raise GraphPersistenceError(f"Missing worker prompt for {name!r}")
        agent.system_prompt = prompt
        return agent

    try:
        swarm = AgentSwarm.load(snapshot_path, agent_resolver=resolve_agent)
    except (GraphPersistenceError, OSError, ValueError):
        return None
    coordinator = swarm.get_agent("coordinator")
    if coordinator is None:
        return None
    _attach_swarm_runtime_tools(swarm, coordinator, config, workspace_id, session_id, active)
    for agent_name in swarm.dispatched_agent_names():
        worker = swarm.get_agent(agent_name)
        if worker is not None:
            worker.add_tools([create_task_report_tool(swarm, agent_name, worker.request_completion)])
    _attach_swarm_observer(swarm, workspace_id, session_id, active)
    return swarm

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
    _attach_swarm_runtime_tools(swarm, coordinator, config, workspace_id, session_id, active)
    _attach_swarm_observer(swarm, workspace_id, session_id, active)
    return swarm

__all__ = [
    "_event_payload",
    "_redacted_api_url",
    "_runtime_profile_snapshot",
    "_build_agent",
    "_memory_capabilities",
    "_session_memory_store",
    "_plan_store",
    "_build_swarm",
    "_synchronize_context_threshold",
    "_synchronize_swarm_context_threshold",
    "_persist_swarm_snapshot",
    "_restore_swarm",
]
