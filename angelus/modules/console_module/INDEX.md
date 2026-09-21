# console_module/ — Session Console State and Projections INDEX

This module owns the durable, non-secret console projection for one `Session`.
It never creates a second AgentSwarm, executor, or credential store.

| File | Responsibility |
|---|---|
| `console_state.py` | Typed schema-v2 Agent-keyed recursive plans and idle graph blueprint at `console/state.json`; reads schema-v1 flat plans. |
| `projection_service.py` | Projects Session swarm, execution journal, usage, GraphContextHandler state, and durable context cursor pages for APIs; applies idle-only graph edits. |
| `console_tools.py` | Controlled Agent plan and dynamic connection/mapper/router tools that write the same Session state and attempt journal; `ToolPermissionPolicy` omits disabled tools before Agent registration. |
| `tool_provider.py` | Console's single registration and runtime materializer for the unified `ToolRegistry`. |
| `__init__.py` | Public console domain exports. |

## Invariants

- `set_task_plan` atomically replaces a complete recursive tree; only leaves accept direct status changes and every parent status is derived.
- `ConsoleBlueprint` contains Worker identity/instructions and declarative topology only; it contains no API key or connector endpoint.
- A static graph edit is rejected while the owning Session has a live attempt.
- Journal order remains the Trace authority; console endpoints only project it.
- Context is read from the Agent checkpoint even after a process restart. Schema 3 checkpoints query the newest 200 entries then move backward with an exclusive timeline cursor; no projection requires the full transcript.

## Class Map

| Source | Class | Semantics |
|---|---|---|
| `console_state.py` | `ConsoleState` | Atomic owner of one Session's typed console blueprint. |
| `console_state.py` | `ConsoleBlueprint`, `WorkerBlueprint`, `ConnectionBlueprint`, `PlanItem` | Explicit durable domain records. |
| `projection_service.py` | `ConsoleProjectionService` | Session-only read/edit boundary for the HTTP adapter. |
| `console_tools.py` | `SessionConsoleTools`, `ToolPermissionPolicy` | Tool factory scoped to one Session aggregate plus the typed category-and-tool allowlist that controls model exposure. |

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [console_state.py](console_state.py#L63) | `TaskPlan.__getitem__` | `index: int` | `PlanItem` | Retain read compatibility with the former flat plan list. |
| [console_state.py](console_state.py#L67) | `TaskPlan.__iter__` | `None` | `Any` | Iterate root tasks for compatibility with legacy callers. |
| [console_state.py](console_state.py#L82) | `ConsoleBlueprint.to_json` | `None` | `dict[str, object]` | Encode the typed blueprint without secrets or runtime objects. |
| [console_state.py](console_state.py#L91) | `ConsoleBlueprint.from_json` | `value: object` | `'ConsoleBlueprint'` | Decode a tolerant on-disk document, ignoring malformed entries. |
| [console_state.py](console_state.py#L143) | `ConsoleState._load` | `None` | `ConsoleBlueprint` | Load prior state or initialize an empty blueprint. |
| [console_state.py](console_state.py#L148) | `ConsoleState.save` | `None` | `None` | Atomically commit the current secret-free blueprint. |
| [console_state.py](console_state.py#L156) | `ConsoleState.blueprint` | `None` | `ConsoleBlueprint` | Return an isolated typed snapshot for projection or swarm rebuild. |
| [console_state.py](console_state.py#L164) | `ConsoleState.add_worker` | `name: str, system_prompt: str` | `None` | Add a worker after validating its stable identity. |
| [console_state.py](console_state.py#L179) | `ConsoleState.remove_worker` | `name: str` | `None` | Remove a worker and every persisted setting that references it. |
| [console_state.py](console_state.py#L199) | `ConsoleState._nodes` | `None` | `set[str]` | Implement `ConsoleState._nodes`. |
| [console_state.py](console_state.py#L201) | `ConsoleState.add_connection` | `source: str, target: str` | `None` | Add a dependency, rejecting duplicates, self-links, and cycles. |
| [console_state.py](console_state.py#L225) | `ConsoleState.remove_connection` | `source: str, target: str` | `None` | Remove one existing dependency edge. |
| [console_state.py](console_state.py#L240) | `ConsoleState.mapper` | `agent: str, mode: str` | `None` | Store one supported declarative predecessor-output mapper. |
| [console_state.py](console_state.py#L255) | `ConsoleState.router` | `agent: str, targets: list[str]` | `None` | Store a fixed safe router target set for an Agent. |
| [console_state.py](console_state.py#L269) | `ConsoleState.plan` | `agent: str` | `TaskPlan` | Return one Agent's complete typed plan snapshot. |
| [console_state.py](console_state.py#L282) | `ConsoleState.set_plan` | `agent: str, goal: str, summary: str, tasks: list[dict[str, object]]` | `TaskPlan` | Validate and atomically replace one complete recursive plan. |
| [console_state.py](console_state.py#L307) | `ConsoleState.update_task_status` | `agent: str, task_id: str, status: str` | `TaskPlan` | Update one leaf and reconcile all ancestor states. |
| [console_state.py](console_state.py#L342) | `ConsoleState.has_task` | `task_id: str` | `bool` | Return whether any Agent plan contains a task identity. |
| [console_state.py](console_state.py#L347) | `ConsoleState.is_bindable_leaf` | `task_id: str` | `bool` | Return whether an existing task is a leaf in any Agent plan. |
| [console_state.py](console_state.py#L352) | `ConsoleState.bind_execution` | `task_id: str, assignment_id: str` | `None` | Bind a TaskBus assignment to a plan leaf and mark it in progress. |
| [console_state.py](console_state.py#L369) | `ConsoleState.update_assignment_status` | `assignment_id: str, status: str` | `None` | Update only the leaf whose active assignment matches the report. |
| [console_state.py](console_state.py#L391) | `_decode_item` | `value: object` | `PlanItem \| None` | Implement `_decode_item`. |
| [console_state.py](console_state.py#L408) | `_decode_plan` | `value: dict[str, object]` | `TaskPlan` | Implement `_decode_plan`. |
| [console_state.py](console_state.py#L414) | `_normalize_item` | `value: object, seen: set[str]` | `PlanItem` | Implement `_normalize_item`. |
| [console_state.py](console_state.py#L441) | `_derive_status` | `item: PlanItem` | `PlanItem` | Implement `_derive_status`. |
| [console_state.py](console_state.py#L453) | `_find_task` | `items: tuple[PlanItem, ...], task_id: str` | `PlanItem \| None` | Implement `_find_task`. |
| [console_tools.py](console_tools.py#L20) | `_schema` | `*parameters: ToolParameter` | `ToolSchema` | Create a compact first-party tool schema. |
| [console_tools.py](console_tools.py#L45) | `ToolPermissionPolicy.from_profile` | `value: object` | `'ToolPermissionPolicy'` | Decode one persisted profile value without trusting its shape. |
| [console_tools.py](console_tools.py#L68) | `ToolPermissionPolicy.allows` | `category: str, tool: str` | `bool` | Return whether a category and its individual tool are enabled. |
| [console_tools.py](console_tools.py#L80) | `ToolPermissionPolicy.fingerprint` | `None` | `tuple[tuple[str, ...], tuple[str, ...]]` | Return a deterministic value suitable for Agent rebuild identity. |
| [console_tools.py](console_tools.py#L112) | `SessionConsoleTools.build` | `None` | `list[Tool]` | Create the controlled tool set for a coordinator or worker. |
| [console_tools.py](console_tools.py#L195) | `SessionConsoleTools._journal` | `event_type: str, message: str, data: dict[str, object]` | `None` | Append one mutation fact when an execution attempt exists. |
| [console_tools.py](console_tools.py#L207) | `SessionConsoleTools.set_task_plan` | `goal: str, tasks: list[dict[str, object]], summary: str` | `dict[str, object]` | Atomically validate and replace the caller's complete task tree. |
| [console_tools.py](console_tools.py#L213) | `SessionConsoleTools.plan_upsert` | `id: str, status: str, title: str` | `str` | Compatibility adapter used only by pre-registry callers. |
| [console_tools.py](console_tools.py#L222) | `SessionConsoleTools.update_task_status` | `task_id: str, status: str` | `dict[str, object]` | Update one leaf task with optimistic structural invariants. |
| [console_tools.py](console_tools.py#L228) | `SessionConsoleTools.read_task_plan` | `None` | `dict[str, object]` | Return the caller's complete recursive task plan. |
| [console_tools.py](console_tools.py#L232) | `SessionConsoleTools.swarm_connect` | `source: str, target: str` | `str` | Persist and dynamically apply one safe dependency connection. |
| [console_tools.py](console_tools.py#L247) | `SessionConsoleTools.swarm_disconnect` | `source: str, target: str` | `str` | Persist and dynamically remove one dependency connection. |
| [console_tools.py](console_tools.py#L262) | `SessionConsoleTools.swarm_set_mapper` | `agent: str, mode: str` | `str` | Persist and dynamically configure a mapper. |
| [console_tools.py](console_tools.py#L277) | `SessionConsoleTools.swarm_set_router` | `agent: str, targets: list[str]` | `str` | Persist and dynamically configure a fixed router. |
| [console_tools.py](console_tools.py#L292) | `SessionConsoleTools.swarm_add_worker` | `name: str, system_prompt: str` | `str` | Create a profile-inheriting Worker in the live and durable swarm. |
| [console_tools.py](console_tools.py#L319) | `SessionConsoleTools.swarm_remove_worker` | `name: str` | `str` | Remove one Worker from live and durable topology. |
| [console_tools.py](console_tools.py#L340) | `SessionConsoleTools.swarm_info` | `None` | `str` | Return the current live graph and TaskBus state without mutation. |
| [console_tools.py](console_tools.py#L348) | `SessionConsoleTools.dispatch_subagent` | `name: str, system_prompt: str, objective: str, handoff: str, reply_to: str, expected_artifacts: list[str] \| None, plan_task_id: str` | `str` | Create and independently schedule one reporting Worker. |
| [console_tools.py](console_tools.py#L399) | `SessionConsoleTools.dispatch_subagents` | `assignments: list[dict[str, object]]` | `str` | Dispatch a validated independent group of reporting Workers. |
| [console_tools.py](console_tools.py#L428) | `SessionConsoleTools.revive_agent` | `name: str, objective: str, handoff: str, reply_to: str, expected_artifacts: list[str] \| None, plan_task_id: str` | `str` | Assign a new task to one terminal TaskBus Worker. |
| [console_tools.py](console_tools.py#L468) | `SessionConsoleTools.wait_for_reports` | `task_ids: list[str], timeout_seconds: float` | `str` | Wait for bounded structured reports from dispatched Workers. |
| [console_tools.py](console_tools.py#L485) | `SessionConsoleTools._session_id` | `None` | `str` | Return the aggregate's durable execution Session identity. |
| [console_tools.py](console_tools.py#L500) | `SessionConsoleTools._report_tool` | `name: str, worker: Agent` | `Tool` | Build the terminal structured-report Tool for one dispatched Worker. |
| [console_tools.py](console_tools.py#L550) | `_required_text` | `value: dict[str, object], key: str` | `str` | Read one required non-empty text field from a batch assignment. |
| [console_tools.py](console_tools.py#L569) | `_optional_text` | `value: dict[str, object], key: str` | `str` | Read one optional text field from a batch assignment. |
| [console_tools.py](console_tools.py#L588) | `_string_list` | `value: object` | `list[str]` | Normalize one batch assignment artifact list. |
| [projection_service.py](projection_service.py#L200) | `CallsPayload.as_wire` | `None` | `dict[str, JsonValue]` | Serialize to the frontend wire shape with identical keys and order. |
| [projection_service.py](projection_service.py#L237) | `ConsoleProjectionService._session` | `session_id: str` | `Any` | Resolve a Session or translate its absence into a domain lookup. |
| [projection_service.py](projection_service.py#L242) | `ConsoleProjectionService._state` | `session_id: str` | `Any` | Return the Session-owned typed console state. |
| [projection_service.py](projection_service.py#L245) | `ConsoleProjectionService._idle` | `session_id: str` | `None` | Reject static graph edits while an attempt is live. |
| [projection_service.py](projection_service.py#L251) | `ConsoleProjectionService.workflow` | `session_id: str` | `dict[str, object]` | Project the persisted, editable workflow blueprint. |
| [projection_service.py](projection_service.py#L280) | `ConsoleProjectionService.graph` | `session_id: str, execution_id: str \| None` | `dict[str, object]` | Project one selected/latest execution as the Session execution graph. |
| [projection_service.py](projection_service.py#L297) | `ConsoleProjectionService.graph_events` | `session_id: str, cursor: int, execution_id: str \| None` | `dict[str, object]` | Return only normalized RunGraph events for one attempt. |
| [projection_service.py](projection_service.py#L305) | `ConsoleProjectionService.graph_info` | `session_id: str` | `dict[str, object]` | Return compact graph counts and current editability. |
| [projection_service.py](projection_service.py#L315) | `ConsoleProjectionService._is_idle` | `session_id: str` | `bool` | Return whether static graph changes are currently permitted. |
| [projection_service.py](projection_service.py#L319) | `ConsoleProjectionService.agents` | `session_id: str` | `dict[str, object]` | Return safe Agent metadata and real context statistics. |
| [projection_service.py](projection_service.py#L343) | `ConsoleProjectionService._context_stats` | `agent: object` | `dict[str, object]` | Summarize a concrete Agent context without exposing messages. |
| [projection_service.py](projection_service.py#L352) | `ConsoleProjectionService.usage` | `session_id: str` | `dict[str, object]` | Aggregate five-dimensional token usage across the Session swarm. |
| [projection_service.py](projection_service.py#L382) | `ConsoleProjectionService._remote_request_index` | `data: dict[str, object]` | `dict[str, object]` | Reduce a remote_request payload to its content-free index. |
| [projection_service.py](projection_service.py#L405) | `ConsoleProjectionService._llm_request_index` | `data: dict[str, object]` | `dict[str, object]` | Reduce an ``agent:llm_request`` payload to its content-free index. |
| [projection_service.py](projection_service.py#L431) | `ConsoleProjectionService._event_source` | `event_type: object` | `str` | Classify a journal fact into the frontend's lifecycle source buckets. |
| [projection_service.py](projection_service.py#L450) | `ConsoleProjectionService.events` | `session_id: str, cursor: int, limit: int` | `dict[str, object]` | Page the current attempt's durable journal in commit order. |
| [projection_service.py](projection_service.py#L484) | `ConsoleProjectionService._rebuild_after_edit` | `session_id: str` | `dict[str, object]` | Rebuild the concrete swarm after a persisted static graph change. |
| [projection_service.py](projection_service.py#L496) | `ConsoleProjectionService.add_worker` | `session_id: str, name: str, system_prompt: str` | `dict[str, object]` | Add one worker to an idle Session graph. |
| [projection_service.py](projection_service.py#L511) | `ConsoleProjectionService.remove_worker` | `session_id: str, name: str` | `dict[str, object]` | Remove one worker from an idle Session graph. |
| [projection_service.py](projection_service.py#L525) | `ConsoleProjectionService.add_connection` | `session_id: str, source: str, target: str` | `dict[str, object]` | Add one acyclic dependency edge to an idle Session graph. |
| [projection_service.py](projection_service.py#L540) | `ConsoleProjectionService.remove_connection` | `session_id: str, source: str, target: str` | `dict[str, object]` | Remove one dependency edge from an idle Session graph. |
| [projection_service.py](projection_service.py#L555) | `ConsoleProjectionService.set_mapper` | `session_id: str, agent: str, mode: str` | `dict[str, object]` | Set a declarative mapper on an idle Session graph. |
| [projection_service.py](projection_service.py#L570) | `ConsoleProjectionService.set_router` | `session_id: str, agent: str, targets: list[str]` | `dict[str, object]` | Set fixed router targets on an idle Session graph. |
| [projection_service.py](projection_service.py#L585) | `ConsoleProjectionService.plan` | `session_id: str, agent: str \| None` | `dict[str, object]` | Project durable plan items into JSON-safe API data. |
| [projection_service.py](projection_service.py#L599) | `ConsoleProjectionService.context` | `session_id: str, name: str, before: int \| None, limit: int` | `dict[str, object]` | Return persisted linear-context metadata for one valid Agent role. |
| [projection_service.py](projection_service.py#L624) | `ConsoleProjectionService.messages` | `session_id: str, name: str \| None, before: int \| None, limit: int` | `dict[str, object]` | Project one Agent's durable context page into chat-message cards. |
| [projection_service.py](projection_service.py#L685) | `ConsoleProjectionService._image_previews` | `session_id: str, references: list[dict[str, Any]]` | `list[dict[str, Any]]` | Return only Session-local image URLs, keeping missing refs visible. |
| [projection_service.py](projection_service.py#L702) | `ConsoleProjectionService.steering` | `session_id: str, name: str \| None` | `list[dict[str, object]]` | Project durable steering deliveries from the latest attempt journal. |
| [projection_service.py](projection_service.py#L717) | `ConsoleProjectionService._journal_signature` | `attempt: object` | `tuple[str, int, str] \| None` | Return the (path, committed byte size, execution id) cache key. |
| [projection_service.py](projection_service.py#L728) | `ConsoleProjectionService._cached_steering` | `attempt: object` | `list[dict[str, object]]` | Reduce steering records once per journal state, appending only new lines. |
| [projection_service.py](projection_service.py#L782) | `ConsoleProjectionService._reduce_steering_event` | `records: dict[str, dict[str, object]], event: dict[str, object]` | `None` | Fold one journal fact into the durable steering record map. |
| [projection_service.py](projection_service.py#L814) | `ConsoleProjectionService._steering_records` | `records: dict[str, dict[str, object]]` | `list[dict[str, object]]` | Return ordered copies so cached records are never mutated by callers. |
| [projection_service.py](projection_service.py#L832) | `ConsoleProjectionService.calls` | `session_id: str, name: str, limit: int` | `CallsPayload` | Project every real LLM call made by one Agent from the journal. |
| [projection_service.py](projection_service.py#L873) | `ConsoleProjectionService._calls_stats` | `records: list[CallRecord]` | `CallsStats` | Aggregate a filtered call ledger without touching raw prompts. |
| [projection_service.py](projection_service.py#L894) | `ConsoleProjectionService._cached_calls` | `attempt: object` | `CallsState` | Reduce the call ledger once per journal state, appending only new lines. |
| [projection_service.py](projection_service.py#L946) | `ConsoleProjectionService._primary_call` | `agent: str, round_idx: int, sequence: int, timestamp: JsonValue` | `PrimaryCall` | Create the canonical one-row-per-round primary call record. |
| [projection_service.py](projection_service.py#L962) | `ConsoleProjectionService._reduce_calls_event` | `state: CallsState, event: object` | `None` | Fold one journal fact into the per-Agent call ledger. |
| [projection_service.py](projection_service.py#L1124) | `ConsoleProjectionService._request_config` | `data: dict[str, object]` | `RequestConfig` | Build the run-invariant per-Agent request configuration once. |
| [projection_service.py](projection_service.py#L1145) | `ConsoleProjectionService._backend_info` | `backend: object` | `BackendInfo` | Reduce a backend identity to the three whitelisted provider keys. |
| [projection_service.py](projection_service.py#L1157) | `ConsoleProjectionService._call_usage` | `value: object` | `CallUsage \| None` | Reduce one raw usage mapping to fixed, always-emitted counters. |
| [projection_service.py](projection_service.py#L1168) | `ConsoleProjectionService._tool_names` | `tool_calls: object` | `list[str]` | Reduce a committed tool_calls array to unique, ordered tool names. |
| [projection_service.py](projection_service.py#L1187) | `ConsoleProjectionService._calls_records` | `state: CallsState` | `list[CallRecord]` | Return every Agent's records in global sequence order. |
| [projection_service.py](projection_service.py#L1201) | `ConsoleProjectionService._request_messages` | `content: object` | `tuple[list[RequestMessage], int]` | Reduce a request-content preview to capped per-message rows. |
| [projection_service.py](projection_service.py#L1237) | `ConsoleProjectionService._preview` | `value: object, limit: int` | `ContentPreview \| None` | Cap one content value while reporting its true character count. |
| [projection_service.py](projection_service.py#L1252) | `ConsoleProjectionService._tool_result_preview` | `value: object` | `ContentPreview \| ToolResultPreview \| None` | Cap a tool result, keeping image counts instead of raw image bytes. |
| [projection_service.py](projection_service.py#L1265) | `ConsoleProjectionService._tool_calls_content` | `tool_calls: object` | `list[ToolCallContent]` | Reduce committed tool calls to name + capped argument previews. |
| [projection_service.py](projection_service.py#L1281) | `ConsoleProjectionService._merge_tool_results` | `record: PrimaryCall, tool_calls: object` | `None` | Merge completed tool results into a round row, keyed by call id. |
| [projection_service.py](projection_service.py#L1302) | `ConsoleProjectionService.context_graph` | `session_id: str, name: str` | `dict[str, object]` | Return the actual GraphContextHandler entity graph projection. |
| [projection_service.py](projection_service.py#L1320) | `ConsoleProjectionService.compaction_input` | `session_id: str, name: str` | `dict[str, object]` | Reconstruct the next compaction request without provider I/O. |
| [projection_service.py](projection_service.py#L1362) | `ConsoleProjectionService.request_preview` | `session_id: str, name: str, message: str` | `dict[str, object]` | Compose one possible next Agent request without dispatching it. |
| [projection_service.py](projection_service.py#L1405) | `ConsoleProjectionService._detached_preview_agent` | `session_id: str, name: str` | `Any` | Create and hydrate an Agent copy that cannot mutate Session state. |
| [projection_service.py](projection_service.py#L1425) | `ConsoleProjectionService._agent` | `session_id: str, name: str` | `Any` | Resolve a concrete Agent, allowing unmaterialized persisted roles. |
| [projection_service.py](projection_service.py#L1436) | `ConsoleProjectionService._context_path` | `session_id: str, name: str` | `Path` | Return the single durable checkpoint path for one valid role. |
| [tool_provider.py](tool_provider.py#L27) | `ConsoleToolProvider.materialize` | `session: object, policy: ToolPolicy, role: str, agent_name: str \| None` | `list[Tool]` | Build Console Tools authorized for the requested Agent role. |
| [tool_provider.py](tool_provider.py#L48) | `console_tool_registration` | `core: 'AngelusCore'` | `ToolProviderRegistration` | Return Console's complete, single registration with the Tool Registry. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [console_state.py](console_state.py#L15) | `ConsoleDomainError` | `None` | `ValueError` | A safe, user-visible failure caused by a console operation. |
| [console_state.py](console_state.py#L20) | `WorkerBlueprint` | `name: str, system_prompt: str, role: str` | `object` | Secret-free persisted definition of one reusable worker role. |
| [console_state.py](console_state.py#L28) | `ConnectionBlueprint` | `source: str, target: str` | `object` | One directed dependency in the static Session topology. |
| [console_state.py](console_state.py#L35) | `PlanExecution` | `assignment_ids: tuple[str, ...], active_assignment_id: str, updated_at: str` | `object` | Durable correlation between a plan leaf and TaskBus assignments. |
| [console_state.py](console_state.py#L43) | `PlanItem` | `id: str, title: str, description: str, status: str, priority: str, estimated_minutes: float \| None, subtasks: tuple['PlanItem', ...], execution: PlanExecution \| None` | `object` | One recursively nested Agent-authored task. |
| [console_state.py](console_state.py#L56) | `TaskPlan` | `goal: str, summary: str, tasks: tuple[PlanItem, ...], updated_at: str` | `object` | One complete plan owned by a concrete Agent. |
| [console_state.py](console_state.py#L73) | `ConsoleBlueprint` | `workers: dict[str, WorkerBlueprint], connections: list[ConnectionBlueprint], mappers: dict[str, str], routers: dict[str, list[str]], plans: dict[str, TaskPlan], schema_version: int` | `object` | Complete serializable console state owned by one Session. |
| [console_state.py](console_state.py#L131) | `ConsoleState` | `root: Path` | `object` | Atomically persist one Session's typed topology and task plan. |
| [console_tools.py](console_tools.py#L33) | `ToolPermissionPolicy` | `enabled_categories: frozenset[str], enabled_tools: frozenset[str]` | `object` | Validated effective allowlist for the tools this console provides. |
| [console_tools.py](console_tools.py#L89) | `SessionConsoleTools` | `session: 'Session', permissions: ToolPermissionPolicy, worker_factory: WorkerFactory \| None, agent_name: str` | `object` | Build safe plan and dynamic-topology tools for a single Session. |
| [projection_service.py](projection_service.py#L34) | `ContentPreview` | `text: str, characters: int, truncated: bool` | `object` | One capped content value that still reports its true character count. |
| [projection_service.py](projection_service.py#L42) | `ToolResultPreview` | `image_count: int` | `ContentPreview` | A tool-result preview that keeps an image count, never image bytes. |
| [projection_service.py](projection_service.py#L48) | `RequestMessage` | `role: str, text: str, characters: int, truncated: bool` | `object` | One capped planned request message rendered in the ledger. |
| [projection_service.py](projection_service.py#L57) | `ToolCallContent` | `name: str, args: ContentPreview \| None` | `object` | One tool call's name plus its capped argument preview. |
| [projection_service.py](projection_service.py#L64) | `ToolResult` | `call_id: str, name: str, ok: JsonValue, duration_ms: JsonValue, result: ContentPreview \| ToolResultPreview \| None` | `object` | One completed tool result keyed by the originating call id. |
| [projection_service.py](projection_service.py#L74) | `CallUsage` | `input: int, output: int, total: int, cached: int, reasoning: int` | `object` | Token accounting for one call; every key is always emitted. |
| [projection_service.py](projection_service.py#L84) | `RequestTool` | `name: str, description: ContentPreview \| None` | `object` | One tool schema offered to the model, with a capped description. |
| [projection_service.py](projection_service.py#L91) | `BackendInfo` | `name: str \| None, provider: str \| None, model: str \| None` | `object` | The provider identity one request was dispatched to. |
| [projection_service.py](projection_service.py#L99) | `RequestConfig` | `system_prompt: ContentPreview \| None, message: ContentPreview \| None, tools: list[RequestTool], backend: BackendInfo, temperature: JsonValue, max_tokens: JsonValue` | `object` | Run-invariant request material stored once per Agent. |
| [projection_service.py](projection_service.py#L110) | `PrimaryCall` | `kind: str, agent: str, round: int, request_id: str \| None, model: str, stream: bool, message_count: int, message_roles: dict[str, int], source_ids: list[str], input_characters: int, estimated_input_tokens: int, input_sha256: str, tool_count: int, tool_schema_hashes: list[str], tool_names: list[str], temperature: JsonValue, max_tokens: JsonValue, usage: CallUsage \| None, model_duration_ms: float \| None, round_duration_ms: float \| None, tool_call_count: int \| None, input_message: ContentPreview \| None, request_messages: list[RequestMessage], request_omitted_messages: int, assistant_content: ContentPreview \| None, reasoning_content: ContentPreview \| None, tool_calls: list[ToolCallContent], tool_results: list[ToolResult], retries: int, attempts: int, timestamp: JsonValue, id: str, sequence: int` | `object` | One real, round-based primary LLM call. |
| [projection_service.py](projection_service.py#L148) | `InternalCall` | `kind: str, agent: str, internal_kind: str, message: str, usage: CallUsage \| None, timestamp: JsonValue, id: str, sequence: int` | `object` | One hidden internal LLM call (for example context compaction). |
| [projection_service.py](projection_service.py#L164) | `AgentBucket` | `primary: dict[int, PrimaryCall], internal: list[InternalCall], request: RequestConfig \| None` | `object` | Per-Agent accumulator used while folding the durable journal. |
| [projection_service.py](projection_service.py#L172) | `CallsState` | `agents: dict[str, AgentBucket], sequence: int, cursor: int` | `object` | Incremental fold state keyed by journal byte cursor. |
| [projection_service.py](projection_service.py#L180) | `CallsStats` | `total: int, primary: int, internal: int, retries: int, input_tokens: int, usage: CallUsage` | `object` | Aggregate counters across one Agent's ledger window. |
| [projection_service.py](projection_service.py#L191) | `CallsPayload` | `agent: str, calls: list[CallRecord], available_tools: list[str], request_config: RequestConfig \| None, stats: CallsStats, has_more: bool` | `object` | Typed ``/calls`` projection; ``as_wire`` restores the JSON contract. |
| [projection_service.py](projection_service.py#L217) | `ConsoleProjectionService` | `core: 'AngelusCore'` | `object` | Provide `ConsoleProjectionService` behavior. |
| [tool_provider.py](tool_provider.py#L16) | `ConsoleToolProvider` | `core: 'AngelusCore'` | `object` | Materialize the Session-console plan and topology tools. |

<!-- END GENERATED SYMBOL MAP -->
