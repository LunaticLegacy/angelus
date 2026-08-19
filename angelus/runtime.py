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
from llmfetcher.swarm_module.swarm import AgentSwarm
from llmfetcher.tools.shell_tools import create_shell_tools
from llmfetcher.tools.spawn_tools import create_swarm_tools

from .classes import ActiveRun, RunConfig
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
    return {
        "type": event.event_type,
        "source": event.source,
        "agent": event.agent_name,
        "message": event.message,
        "data": event.data,
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
    profile = {
        "schema_version": 1,
        "provider": config.provider.strip(),
        "model": config.model.strip(),
        "api_url": _redacted_api_url(config.api_url),
        "system_prompt_sha256": system_prompt_digest,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "max_rounds": config.max_rounds,
        "max_retries": config.max_retries,
        "max_context_threshold": config.max_context_threshold,
        "enable_shell": config.enable_shell,
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
    backend = LLMBackendConfig(
        name="browser",
        provider=config.provider.strip(),
        model=config.model.strip(),
        api_key=config.api_key,
        api_url=config.api_url.strip() or None,
        timeout=120,
        max_retries=config.max_retries,
    )
    fetcher = LLMFetcher([backend])
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
    agent.add_tools(create_session_memory_tools(
        _session_memory_store(), session_id, _memory_capabilities(config, session_id), uuid.uuid4().hex,
    ))
    return agent

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

def _plan_store(workspace_id: str, session_id: str) -> TaskPlanStore:
    """Return the session-local plan store after validating path components."""
    workspace_id = _safe_id(workspace_id, "workspace")
    session_id = _safe_id(session_id, "session")
    return TaskPlanStore(_session_path(workspace_id, session_id) / "task-plan.json")

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
    # Dynamic workers receive the same frozen session grants as their
    # coordinator.  The closures are run-scoped and do not expose new grants.
    worker_tools.extend(create_session_memory_tools(
        _session_memory_store(), session_id, _memory_capabilities(config, session_id), uuid.uuid4().hex,
    ))
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

__all__ = [
    "_event_payload",
    "_redacted_api_url",
    "_runtime_profile_snapshot",
    "_build_agent",
    "_memory_capabilities",
    "_session_memory_store",
    "_plan_store",
    "_build_swarm",
]
