# angelus/classes/ — Data Classes INDEX

Small web-facing Pydantic models and in-memory control-state dataclasses.
Each class has its own module and is re-exported by `__init__.py`.

## Route Map — Leaf Files

| File | Class | Base | Purpose |
|---|---|---|---|
| `run_config.py` | `RunConfig` | `BaseModel` | One run's backend selector/reference plus execution settings: provider, model, optional `connector_id`, direct run-only key/API URL, system prompt, generation/context limits, shell, and Swarm options |
| `run_request.py` | `RunRequest` | `BaseModel` | Incoming run: `session_id`, `workspace_id`, user message, and nested `RunConfig` |
| `connector_request.py` | `ConnectorRequest` | `BaseModel` | Named persisted connector fields only: name, provider, model, API URL, and API key. It deliberately excludes Agent behavior settings; `connectors.py` encrypts the key before disk persistence. |
| `steer_request.py` | `SteerRequest` | `BaseModel` | Mid-run instruction queued for the next safe Agent boundary |
| `compact_request.py` | `CompactRequest` | `BaseModel` | Manual context compaction: target agent name plus the browser run config used to build the compactor |
| `workspace_request.py` | `WorkspaceRequest` | `BaseModel` | Create a user-visible session name bound to an existing project directory |
| `project_path_request.py` | `ProjectPathRequest` | `BaseModel` | Rebind an inactive session to an existing project directory |
| `workspace_delete_request.py` | `WorkspaceDeleteRequest` | `BaseModel` | Explicit confirmation required to delete a workspace/session directory |
| `task_plan_request.py` | `TaskPlanRequest` | `BaseModel` | Complete task-plan replacement: goal, optional summary, and task records |
| `task_status_request.py` | `TaskStatusRequest` | `BaseModel` | Single task status transition |
| `browser_run_control.py` | `BrowserRunControl` | `AgentRunControl` | Thread-safe stop/steer implementation: `stop()` is cooperative; `force_stop()` also exposes the terminal model-I/O cancellation event |
| `active_run.py` | `ActiveRun` | `dataclass` | Live browser-run state: control, event queue, completion signal, optional Swarm, and tracked shell processes; force-stop propagates model cancellation and kills tracked process groups |
| `browser_session.py` | `BrowserSession` | `dataclass` | In-memory per-session concurrency guard: lock plus optional active run |

## Boundaries and Dependencies

- `RunRequest` contains `RunConfig`; neither model is a persisted connector
  record. A saved `connector_id` is resolved server-side, while a direct
  `api_key` is valid only for that request.
- `ConnectorRequest` is stored separately from Agent execution settings. Its
  API key is RSA-encrypted by `connectors.py`; public connector responses omit it
  and instead indicate whether a key exists.
- `ActiveRun` owns `BrowserRunControl`; `BrowserSession` owns the optional
  `ActiveRun`. These are process-memory coordination state, not durable
  session history.
- Durable transcripts, event ledgers, run profiles, contexts, and plans are
  owned by `storage.py` / `history/` / `runtime.py` / `task_planning.py`, not these data classes.

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [active_run.py](active_run.py#L40) | `ActiveRun.request_mcp_approval` | `server: str, agent: str, capability: str, details: dict[str, Any]` | `dict[str, Any]` | Ask an attached browser to approve one MCP client capability. |
| [active_run.py](active_run.py#L76) | `ActiveRun.resolve_mcp_approval` | `approval_id: str, response: dict[str, Any]` | `dict[str, Any]` | Resolve one pending MCP approval without logging submitted values. |
| [active_run.py](active_run.py#L102) | `ActiveRun.register_process` | `process: Any, agent: str` | `None` | Register a Shell process under its owning Agent. |
| [active_run.py](active_run.py#L112) | `ActiveRun.unregister_process` | `process: Any` | `None` | Forget one completed Shell process. |
| [active_run.py](active_run.py#L121) | `ActiveRun.publish_ephemeral_event` | `payload: dict[str, Any]` | `None` | Queue one live-only browser event without adding it to the audit log. |
| [active_run.py](active_run.py#L130) | `ActiveRun.force_stop` | `agent: str` | `None` | Cancel model/tool I/O for the whole run or one Agent. |
| [active_run.py](active_run.py#L170) | `ActiveRun.reset_for_next_turn` | `durable_offset: int` | `None` | Reuse this completed run holder without replacing its Swarm graph. |
| [browser_run_control.py](browser_run_control.py#L22) | `_CombinedEvent.is_set` | `None` | `bool` | Return whether any constituent terminal event is set. |
| [browser_run_control.py](browser_run_control.py#L26) | `_CombinedEvent.wait` | `timeout: float \| None` | `bool` | Wait up to ``timeout`` seconds for a constituent event. |
| [browser_run_control.py](browser_run_control.py#L50) | `AgentScopedRunControl.should_stop` | `None` | `bool` | Return whether the run or this Agent should stop. |
| [browser_run_control.py](browser_run_control.py#L54) | `AgentScopedRunControl.drain_steers` | `None` | `list[str]` | Deliver session steering only to the coordinator. |
| [browser_run_control.py](browser_run_control.py#L59) | `AgentScopedRunControl.force_stopped` | `None` | `_CombinedEvent` | Return the global-or-local terminal cancellation event. |
| [browser_run_control.py](browser_run_control.py#L81) | `BrowserRunControl.register_agent` | `agent: str` | `None` | Ensure stable stop events exist for ``agent``. |
| [browser_run_control.py](browser_run_control.py#L91) | `BrowserRunControl.known_agents` | `None` | `tuple[str, ...]` | Return registered Agent identifiers in deterministic order. |
| [browser_run_control.py](browser_run_control.py#L96) | `BrowserRunControl._agent_force_event` | `agent: str` | `threading.Event` | Return the stable terminal event for ``agent``. |
| [browser_run_control.py](browser_run_control.py#L101) | `BrowserRunControl.for_agent` | `agent: str` | `AgentScopedRunControl` | Return a control view combining global and ``agent`` state. |
| [browser_run_control.py](browser_run_control.py#L113) | `BrowserRunControl.should_stop` | `agent: str` | `bool` | Return whether global or selected-Agent cooperative stop is set. |
| [browser_run_control.py](browser_run_control.py#L120) | `BrowserRunControl.drain_steers` | `None` | `list[str]` | Drain all unapplied session-level steering messages. |
| [browser_run_control.py](browser_run_control.py#L129) | `BrowserRunControl.stop` | `agent: str` | `None` | Request cooperative stop for the whole run or one Agent. |
| [browser_run_control.py](browser_run_control.py#L141) | `BrowserRunControl.force_stop` | `agent: str` | `None` | Request terminal stop for the whole run or one Agent. |
| [browser_run_control.py](browser_run_control.py#L155) | `BrowserRunControl.reset` | `None` | `None` | Clear terminal controls before the same session begins another run. |
| [browser_run_control.py](browser_run_control.py#L179) | `BrowserRunControl.force_stopped` | `None` | `threading.Event` | Return the run-wide terminal cancellation event. |
| [browser_run_control.py](browser_run_control.py#L183) | `BrowserRunControl.steer` | `message: str` | `None` | Queue a session-level coordinator steering message. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [active_run.py](active_run.py#L17) | `ActiveRun` | `control: BrowserRunControl, event_broker: EventBroker, done: threading.Event, swarm: AgentSwarm \| None, mcp_bridge: Any \| None, mcp_tools: list[Any], mcp_servers: list[dict[str, Any]], processes: dict[Any, str], processes_lock: threading.Lock, mcp_sampling_handler: Any \| None, mcp_approval_condition: threading.Condition, mcp_approvals: dict[str, dict[str, Any]], mcp_remembered_approvals: set[tuple[str, str]]` | `object` | Live work and its multi-subscriber broker, owned by one session. |
| [browser_run_control.py](browser_run_control.py#L11) | `_CombinedEvent` | `*events: threading.Event` | `object` | Expose the union of global and Agent-local terminal stop events. |
| [browser_run_control.py](browser_run_control.py#L34) | `AgentScopedRunControl` | `owner: 'BrowserRunControl', agent: str` | `AgentRunControl` | Project one Agent's stop state from a run-level registry. |
| [browser_run_control.py](browser_run_control.py#L64) | `BrowserRunControl` | `None` | `AgentRunControl` | Thread-safe browser controls with cooperative and terminal stop modes. |
| [browser_session.py](browser_session.py#L10) | `BrowserSession` | `lock: threading.Lock, active: ActiveRun \| None` | `object` | In-memory state that prevents concurrent runs in the same chat. |
| [compact_request.py](compact_request.py#L6) | `CompactRequest` | `agent: str, config: RunConfig` | `BaseModel` | Manual context-compaction request for one Agent. |
| [connector_request.py](connector_request.py#L4) | `ConnectorRequest` | `name: str, provider: str, model: str, api_key: str, api_url: str` | `BaseModel` | A named, persisted backend connection configuration. |
| [project_path_request.py](project_path_request.py#L6) | `ProjectPathRequest` | `project_path: str` | `BaseModel` | Absolute existing project directory selected by the local user. |
| [run_config.py](run_config.py#L4) | `RunConfig` | `provider: str, model: str, api_key: str, connector_id: str, api_url: str, system_prompt: str, temperature: float, max_tokens: int, max_rounds: int, max_retries: int, max_context_threshold: int, enable_shell: bool, enable_swarm: bool, max_swarm_agents: int, session_memory_search_sessions: list[str], session_memory_read_sessions: list[str], session_artifact_search_sessions: list[str], session_artifact_open_sessions: list[str]` | `BaseModel` | Settings used to create the backend and Agent for a browser session. |
| [run_request.py](run_request.py#L6) | `RunRequest` | `session_id: str, workspace_id: str, message: str, config: RunConfig` | `BaseModel` | A message and its non-persisted browser-side configuration. |
| [steer_request.py](steer_request.py#L4) | `SteerRequest` | `message: str` | `BaseModel` | One instruction added at the next safe agent boundary. |
| [task_plan_request.py](task_plan_request.py#L6) | `TaskPlanRequest` | `goal: str, summary: str, tasks: list[dict[str, Any]]` | `BaseModel` | Entire user task plan supplied by the browser or Agent planning tool. |
| [task_status_request.py](task_status_request.py#L4) | `TaskStatusRequest` | `status: str` | `BaseModel` | One user-requested planning status transition. |
| [workspace_delete_request.py](workspace_delete_request.py#L4) | `WorkspaceDeleteRequest` | `confirmation: str` | `BaseModel` | Explicit second confirmation required before deleting a workspace. |
| [workspace_request.py](workspace_request.py#L4) | `WorkspaceRequest` | `name: str, project_path: str` | `BaseModel` | A local session name and its explicitly selected existing project. |

<!-- END GENERATED SYMBOL MAP -->
