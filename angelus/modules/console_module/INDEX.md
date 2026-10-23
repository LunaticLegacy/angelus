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
| [console_state.py](console_state.py#L40) | `_console_lock` | `path: Path` | `threading.RLock` | Return the process-local lock shared by every ConsoleState for a path. |
| [console_state.py](console_state.py#L91) | `TaskPlan.__getitem__` | `index: int` | `PlanItem` | Retain read compatibility with the former flat plan list. |
| [console_state.py](console_state.py#L95) | `TaskPlan.__iter__` | `None` | `Any` | Iterate root tasks for compatibility with legacy callers. |
| [console_state.py](console_state.py#L110) | `ConsoleBlueprint.to_json` | `None` | `dict[str, object]` | Encode the typed blueprint without secrets or runtime objects. |
| [console_state.py](console_state.py#L119) | `ConsoleBlueprint.from_json` | `value: object` | `'ConsoleBlueprint'` | Decode exactly one documented on-disk schema, or fail. |
| [console_state.py](console_state.py#L179) | `ConsoleState._load` | `None` | `ConsoleBlueprint` | Load prior state or initialize an empty blueprint. |
| [console_state.py](console_state.py#L209) | `ConsoleState.transaction` | `None` | `Iterator['ConsoleState']` | Hold one per-Session write transaction across read-modify-write. |
| [console_state.py](console_state.py#L223) | `ConsoleState.save` | `None` | `None` | Atomically commit the current secret-free blueprint. |
| [console_state.py](console_state.py#L231) | `ConsoleState.blueprint` | `None` | `ConsoleBlueprint` | Return an isolated typed snapshot for projection or swarm rebuild. |
| [console_state.py](console_state.py#L239) | `ConsoleState.replace` | `blueprint: ConsoleBlueprint` | `None` | Restore a previously captured blueprint after a failed mutation. |
| [console_state.py](console_state.py#L252) | `ConsoleState.add_worker` | `name: str, system_prompt: str` | `None` | Add a worker after validating its stable identity. |
| [console_state.py](console_state.py#L267) | `ConsoleState.remove_worker` | `name: str` | `None` | Remove a worker and every persisted setting that references it. |
| [console_state.py](console_state.py#L287) | `ConsoleState._nodes` | `None` | `set[str]` | Implement `ConsoleState._nodes`. |
| [console_state.py](console_state.py#L289) | `ConsoleState.add_connection` | `source: str, target: str` | `None` | Add a dependency, rejecting duplicates, self-links, and cycles. |
| [console_state.py](console_state.py#L313) | `ConsoleState.remove_connection` | `source: str, target: str` | `None` | Remove one existing dependency edge. |
| [console_state.py](console_state.py#L328) | `ConsoleState.mapper` | `agent: str, mode: str` | `None` | Store one supported declarative predecessor-output mapper. |
| [console_state.py](console_state.py#L343) | `ConsoleState.router` | `agent: str, targets: list[str]` | `None` | Store a fixed safe router target set for an Agent. |
| [console_state.py](console_state.py#L357) | `ConsoleState.plan` | `agent: str` | `TaskPlan` | Return one Agent's complete typed plan snapshot. |
| [console_state.py](console_state.py#L370) | `ConsoleState.set_plan` | `agent: str, goal: str, summary: str, tasks: list[dict[str, object]]` | `TaskPlan` | Validate and atomically replace one complete recursive plan. |
| [console_state.py](console_state.py#L395) | `ConsoleState.update_task_status` | `agent: str, task_id: str, status: str` | `TaskPlan` | Update one leaf and reconcile all ancestor states. |
| [console_state.py](console_state.py#L430) | `ConsoleState.has_task` | `task_id: str` | `bool` | Return whether any Agent plan contains a task identity. |
| [console_state.py](console_state.py#L435) | `ConsoleState.is_bindable_leaf` | `task_id: str` | `bool` | Return whether an existing task is a leaf in any Agent plan. |
| [console_state.py](console_state.py#L440) | `ConsoleState.bind_execution` | `task_id: str, assignment_id: str` | `None` | Bind a TaskBus assignment to a plan leaf and mark it in progress. |
| [console_state.py](console_state.py#L457) | `ConsoleState.update_assignment_status` | `assignment_id: str, status: str` | `None` | Update only the leaf whose active assignment matches the report. |
| [console_state.py](console_state.py#L495) | `_schema_version` | `document: Mapping[str, object]` | `int` | Return the declared schema version; absence means the v1 layout. |
| [console_state.py](console_state.py#L507) | `_decode_workers` | `value: object` | `dict[str, WorkerBlueprint]` | Decode the worker map, including the role the old decoder dropped. |
| [console_state.py](console_state.py#L528) | `_decode_connections` | `value: object` | `list[ConnectionBlueprint]` | Decode the directed topology edges. |
| [console_state.py](console_state.py#L545) | `_decode_plans` | `value: object` | `dict[str, TaskPlan]` | Decode one task plan per owning Agent. |
| [console_state.py](console_state.py#L554) | `_decode_legacy_plan` | `value: object` | `dict[str, TaskPlan]` | Decode the schema-v1 flat list, preserving each item's owner. |
| [console_state.py](console_state.py#L572) | `_decode_plan` | `value: object, where: str` | `TaskPlan` | Decode one complete per-Agent plan. |
| [console_state.py](console_state.py#L589) | `_decode_item` | `value: object, where: str, legacy: bool` | `PlanItem` | Decode one recursively nested task, validating write-side invariants. |
| [console_state.py](console_state.py#L625) | `_decode_execution` | `value: object, where: str` | `PlanExecution \| None` | Decode the optional TaskBus correlation attached to one task. |
| [console_state.py](console_state.py#L644) | `_normalize_item` | `value: object, seen: set[str]` | `PlanItem` | Implement `_normalize_item`. |
| [console_state.py](console_state.py#L671) | `_derive_status` | `item: PlanItem` | `PlanItem` | Implement `_derive_status`. |
| [console_state.py](console_state.py#L683) | `_find_task` | `items: tuple[PlanItem, ...], task_id: str` | `PlanItem \| None` | Implement `_find_task`. |
| [console_tools.py](console_tools.py#L21) | `_schema` | `*parameters: ToolParameter` | `ToolSchema` | Create a compact first-party tool schema. |
| [console_tools.py](console_tools.py#L46) | `ToolPermissionPolicy.from_profile` | `value: object` | `'ToolPermissionPolicy'` | Decode one persisted profile value without trusting its shape. |
| [console_tools.py](console_tools.py#L69) | `ToolPermissionPolicy.allows` | `category: str, tool: str` | `bool` | Return whether a category and its individual tool are enabled. |
| [console_tools.py](console_tools.py#L81) | `ToolPermissionPolicy.fingerprint` | `None` | `tuple[tuple[str, ...], tuple[str, ...]]` | Return a deterministic value suitable for Agent rebuild identity. |
| [console_tools.py](console_tools.py#L125) | `SessionConsoleTools.build` | `None` | `list[Tool]` | Create the controlled tool set for a coordinator or worker. |
| [console_tools.py](console_tools.py#L208) | `SessionConsoleTools._journal` | `event_type: str, message: str, data: dict[str, object]` | `None` | Append one mutation fact when an execution attempt exists. |
| [console_tools.py](console_tools.py#L220) | `SessionConsoleTools.set_task_plan` | `goal: str, tasks: list[dict[str, object]], summary: str` | `dict[str, object]` | Atomically validate and replace the caller's complete task tree. |
| [console_tools.py](console_tools.py#L226) | `SessionConsoleTools.plan_upsert` | `id: str, status: str, title: str` | `str` | Compatibility adapter used only by pre-registry callers. |
| [console_tools.py](console_tools.py#L235) | `SessionConsoleTools.update_task_status` | `task_id: str, status: str` | `dict[str, object]` | Update one leaf task with optimistic structural invariants. |
| [console_tools.py](console_tools.py#L241) | `SessionConsoleTools.read_task_plan` | `None` | `dict[str, object]` | Return the caller's complete recursive task plan. |
| [console_tools.py](console_tools.py#L245) | `SessionConsoleTools.swarm_connect` | `source: str, target: str` | `str` | Persist and dynamically apply one safe dependency connection. |
| [console_tools.py](console_tools.py#L259) | `SessionConsoleTools.swarm_disconnect` | `source: str, target: str` | `str` | Persist and dynamically remove one dependency connection. |
| [console_tools.py](console_tools.py#L273) | `SessionConsoleTools.swarm_set_mapper` | `agent: str, mode: str` | `str` | Persist and dynamically configure a mapper. |
| [console_tools.py](console_tools.py#L287) | `SessionConsoleTools.swarm_set_router` | `agent: str, targets: list[str]` | `str` | Persist and dynamically configure a fixed router. |
| [console_tools.py](console_tools.py#L301) | `SessionConsoleTools.swarm_add_worker` | `name: str, system_prompt: str` | `str` | Create a profile-inheriting Worker in the live and durable swarm. |
| [console_tools.py](console_tools.py#L319) | `SessionConsoleTools.swarm_remove_worker` | `name: str` | `str` | Remove one Worker from live and durable topology. |
| [console_tools.py](console_tools.py#L335) | `SessionConsoleTools.swarm_info` | `None` | `str` | Return the current live graph and TaskBus state without mutation. |
| [console_tools.py](console_tools.py#L343) | `SessionConsoleTools.dispatch_subagent` | `name: str, system_prompt: str, objective: str, handoff: str, reply_to: str, expected_artifacts: list[str] \| None, plan_task_id: str` | `str` | Create and independently schedule one reporting Worker. |
| [console_tools.py](console_tools.py#L392) | `SessionConsoleTools.dispatch_subagents` | `assignments: list[dict[str, object]]` | `str` | Dispatch a validated independent group of reporting Workers. |
| [console_tools.py](console_tools.py#L421) | `SessionConsoleTools.revive_agent` | `name: str, objective: str, handoff: str, reply_to: str, expected_artifacts: list[str] \| None, plan_task_id: str` | `str` | Assign a new task to one terminal TaskBus Worker. |
| [console_tools.py](console_tools.py#L461) | `SessionConsoleTools.wait_for_reports` | `task_ids: list[str], timeout_seconds: float` | `str` | Wait for bounded structured reports from dispatched Workers. |
| [console_tools.py](console_tools.py#L478) | `SessionConsoleTools._session_id` | `None` | `str` | Return the aggregate's durable execution Session identity. |
| [console_tools.py](console_tools.py#L491) | `SessionConsoleTools._graph` | `None` | `'SwarmGraphService'` | Return the one topology read/write gateway. |
| [console_tools.py](console_tools.py#L504) | `SessionConsoleTools._report_tool` | `name: str, worker: Agent` | `Tool` | Build the terminal structured-report Tool for one dispatched Worker. |
| [console_tools.py](console_tools.py#L554) | `_required_text` | `value: dict[str, object], key: str` | `str` | Read one required non-empty text field from a batch assignment. |
| [console_tools.py](console_tools.py#L573) | `_optional_text` | `value: dict[str, object], key: str` | `str` | Read one optional text field from a batch assignment. |
| [console_tools.py](console_tools.py#L592) | `_string_list` | `value: object` | `list[str]` | Normalize one batch assignment artifact list. |
| [context_provider.py](context_provider.py#L56) | `PlanContextProvider.source_id` | `None` | `str` | Return the stable Composer source identity. |
| [context_provider.py](context_provider.py#L60) | `PlanContextProvider.build_blocks` | `snapshot: ContextSnapshot` | `Sequence[ContextBlock]` | Render the current plan, or nothing while no plan exists. |
| [context_provider.py](context_provider.py#L86) | `PlanContextFactory.build` | `request: ContextProviderRequest` | `Sequence[ContextProvider]` | Return the plan source bound to this Agent's Session. |
| [context_provider.py](context_provider.py#L104) | `plan_context_registration` | `None` | `ContextProviderRegistration` | Return the task-plan source registration for the process registry. |
| [context_provider.py](context_provider.py#L113) | `_render_plan` | `plan: TaskPlan, agent_name: str, limit: int` | `tuple[str, int, bool]` | Render one bounded plan tree as model-readable text. |
| [context_provider.py](context_provider.py#L162) | `_item_line` | `item: PlanItem, depth: int` | `str` | Render one task with its status, identity and bounded description. |
| [context_provider.py](context_provider.py#L173) | `_count` | `items: Sequence[PlanItem]` | `int` | Return the number of tasks in a tree, including every subtask. |
| [context_provider.py](context_provider.py#L178) | `_text` | `value: str` | `str` | Escape text that must not be read as markup. |
| [projection_service/service.py](projection_service/service.py#L78) | `ConsoleProjectionService._session` | `session_id: str` | `Any` | Resolve a Session or translate its absence into a domain lookup. |
| [projection_service/service.py](projection_service/service.py#L83) | `ConsoleProjectionService._state` | `session_id: str` | `Any` | Return the Session-owned typed console state. |
| [projection_service/service.py](projection_service/service.py#L86) | `ConsoleProjectionService._idle` | `session_id: str` | `None` | Reject static graph edits while an attempt is live. |
| [projection_service/service.py](projection_service/service.py#L92) | `ConsoleProjectionService.workflow` | `session_id: str` | `dict[str, object]` | Project the persisted, editable workflow blueprint. |
| [projection_service/service.py](projection_service/service.py#L103) | `ConsoleProjectionService.graph` | `session_id: str, execution_id: str \| None` | `dict[str, object]` | Project one selected/latest execution as the Session execution graph. |
| [projection_service/service.py](projection_service/service.py#L116) | `ConsoleProjectionService.graph_events` | `session_id: str, cursor: int, execution_id: str \| None` | `dict[str, object]` | Return only normalized RunGraph events for one attempt. |
| [projection_service/service.py](projection_service/service.py#L124) | `ConsoleProjectionService.graph_info` | `session_id: str` | `dict[str, object]` | Return compact graph counts and current editability. |
| [projection_service/service.py](projection_service/service.py#L134) | `ConsoleProjectionService._is_idle` | `session_id: str` | `bool` | Return whether static graph changes are currently permitted. |
| [projection_service/service.py](projection_service/service.py#L138) | `ConsoleProjectionService.agents` | `session_id: str` | `dict[str, object]` | Return safe Agent metadata and real context statistics. |
| [projection_service/service.py](projection_service/service.py#L166) | `ConsoleProjectionService._context_stats` | `agent: object` | `dict[str, object]` | Summarize a concrete Agent context without exposing messages. |
| [projection_service/service.py](projection_service/service.py#L175) | `ConsoleProjectionService.usage` | `session_id: str` | `dict[str, object]` | Aggregate five-dimensional token usage across the Session swarm. |
| [projection_service/service.py](projection_service/service.py#L212) | `ConsoleProjectionService._usage_values` | `value: object` | `dict[str, int] \| None` | Normalize one persisted usage mapping without trusting its types. |
| [projection_service/service.py](projection_service/service.py#L226) | `ConsoleProjectionService._add_call_usage` | `target: CallUsage, value: object` | `bool` | Add one normalized usage mapping into a typed accumulator. |
| [projection_service/service.py](projection_service/service.py#L238) | `ConsoleProjectionService._usage_ledger` | `session_id: str` | `SessionUsageLedger \| None` | Rebuild Session usage from durable execution/context state. |
| [projection_service/service.py](projection_service/service.py#L319) | `ConsoleProjectionService.usage_series` | `session_id: str` | `dict[str, object]` | Project per-round usage points, attempts, and compaction markers. |
| [projection_service/service.py](projection_service/service.py#L437) | `ConsoleProjectionService._series_point` | `execution: str, attempt: object, round_idx: int, agent: str, kind: str, timestamp: float \| None` | `dict[str, object]` | Create one empty series point before its journal facts are merged. |
| [projection_service/service.py](projection_service/service.py#L458) | `ConsoleProjectionService._execution_manifest` | `path: Path` | `dict[str, object]` | Read one optional execution manifest without trusting its contents. |
| [projection_service/service.py](projection_service/service.py#L467) | `ConsoleProjectionService._event_timestamp` | `event: dict[str, object]` | `float \| None` | Return one journal event timestamp, rejecting booleans and strings. |
| [projection_service/service.py](projection_service/service.py#L485) | `ConsoleProjectionService._remote_request_index` | `data: dict[str, object]` | `dict[str, object]` | Reduce a remote_request payload to its content-free index. |
| [projection_service/service.py](projection_service/service.py#L508) | `ConsoleProjectionService._llm_request_index` | `data: dict[str, object]` | `dict[str, object]` | Reduce an ``agent:llm_request`` payload to its content-free index. |
| [projection_service/service.py](projection_service/service.py#L534) | `ConsoleProjectionService._event_source` | `event_type: object` | `str` | Classify a journal fact into the frontend's lifecycle source buckets. |
| [projection_service/service.py](projection_service/service.py#L553) | `ConsoleProjectionService.events` | `session_id: str, cursor: int, limit: int` | `dict[str, object]` | Page the live attempt's journal in commit order for the SSE stream. |
| [projection_service/service.py](projection_service/service.py#L581) | `ConsoleProjectionService.event_page` | `session_id: str, execution_id: str \| None, before: int \| None, limit: int` | `dict[str, object]` | Page one durable attempt's journal newest-first, straight from disk. |
| [projection_service/service.py](projection_service/service.py#L611) | `ConsoleProjectionService.event_attempts` | `session_id: str` | `list[dict[str, object]]` | List durable attempts for the Trace selector, newest first. |
| [projection_service/service.py](projection_service/service.py#L635) | `ConsoleProjectionService._event_payload` | `item: dict[str, object]` | `dict[str, object]` | Project one journal record onto the browser event contract. |
| [projection_service/service.py](projection_service/service.py#L666) | `ConsoleProjectionService._execution_root` | `session_id: str` | `Path` | Return the Session's durable execution parent directory. |
| [projection_service/service.py](projection_service/service.py#L670) | `ConsoleProjectionService._attempt_root` | `root: Path, execution_id: str \| None` | `Path \| None` | Resolve one attempt directory, or the newest one when unspecified. |
| [projection_service/service.py](projection_service/service.py#L692) | `ConsoleProjectionService._number` | `value: object` | `float \| None` | Return a float for a JSON number, rejecting booleans and strings. |
| [projection_service/service.py](projection_service/service.py#L696) | `ConsoleProjectionService.ephemeral_cursor` | `session_id: str` | `int` | Implement `ConsoleProjectionService.ephemeral_cursor`. |
| [projection_service/service.py](projection_service/service.py#L701) | `ConsoleProjectionService.ephemeral_events` | `session_id: str, cursor: int` | `dict[str, object]` | Page live deltas, falling back to the write-behind file after restart. |
| [projection_service/service.py](projection_service/service.py#L718) | `ConsoleProjectionService._persisted_stream_events` | `session_id: str, cursor: int` | `list[dict[str, object]]` | Read the newest attempt's write-behind stream without a live attempt. |
| [projection_service/service.py](projection_service/service.py#L751) | `ConsoleProjectionService.add_worker` | `session_id: str, name: str, system_prompt: str` | `dict[str, object]` | Add one worker to an idle Session graph. |
| [projection_service/service.py](projection_service/service.py#L765) | `ConsoleProjectionService.remove_worker` | `session_id: str, name: str` | `dict[str, object]` | Remove one worker from an idle Session graph. |
| [projection_service/service.py](projection_service/service.py#L778) | `ConsoleProjectionService.add_connection` | `session_id: str, source: str, target: str` | `dict[str, object]` | Add one acyclic dependency edge to an idle Session graph. |
| [projection_service/service.py](projection_service/service.py#L792) | `ConsoleProjectionService.remove_connection` | `session_id: str, source: str, target: str` | `dict[str, object]` | Remove one dependency edge from an idle Session graph. |
| [projection_service/service.py](projection_service/service.py#L806) | `ConsoleProjectionService.set_mapper` | `session_id: str, agent: str, mode: str` | `dict[str, object]` | Set a declarative mapper on an idle Session graph. |
| [projection_service/service.py](projection_service/service.py#L820) | `ConsoleProjectionService.set_router` | `session_id: str, agent: str, targets: list[str]` | `dict[str, object]` | Set fixed router targets on an idle Session graph. |
| [projection_service/service.py](projection_service/service.py#L834) | `ConsoleProjectionService.plan` | `session_id: str, agent: str \| None` | `dict[str, object]` | Project durable plan items into JSON-safe API data. |
| [projection_service/service.py](projection_service/service.py#L848) | `ConsoleProjectionService.replace_plan` | `session_id: str, agent: str, goal: str, summary: str, tasks: list[dict[str, object]]` | `dict[str, object]` | Replace one idle Session Agent's complete task plan. |
| [projection_service/service.py](projection_service/service.py#L854) | `ConsoleProjectionService.update_task_status` | `session_id: str, agent: str, task_id: str, status: str` | `dict[str, object]` | Update one leaf task and return the derived plan snapshot. |
| [projection_service/service.py](projection_service/service.py#L860) | `ConsoleProjectionService.context` | `session_id: str, name: str, before: int \| None, limit: int` | `dict[str, object]` | Return persisted linear-context metadata for one valid Agent role. |
| [projection_service/service.py](projection_service/service.py#L903) | `ConsoleProjectionService.archive` | `session_id: str, name: str, before: int \| None, limit: int` | `dict[str, object]` | Return one archive-only page of one Agent's compacted-out context. |
| [projection_service/service.py](projection_service/service.py#L942) | `ConsoleProjectionService._page_tool_results` | `path: Path, entries: Sequence[ContextItem]` | `dict[str, ToolResultRecord]` | Resolve every tool result one context page references. |
| [projection_service/service.py](projection_service/service.py#L974) | `ConsoleProjectionService._entry_card` | `session_id: str, entry: ContextItem, results: dict[str, ToolResultRecord]` | `dict[str, object]` | Project one typed context item into a chat message card. |
| [projection_service/service.py](projection_service/service.py#L1048) | `ConsoleProjectionService.messages` | `session_id: str, name: str \| None, before: int \| None, limit: int` | `dict[str, object]` | Project one Agent's durable context page into chat-message cards. |
| [projection_service/service.py](projection_service/service.py#L1095) | `ConsoleProjectionService._image_previews` | `session_id: str, references: list[dict[str, Any]]` | `list[dict[str, Any]]` | Return only Session-local image URLs, keeping missing refs visible. |
| [projection_service/service.py](projection_service/service.py#L1112) | `ConsoleProjectionService.steering` | `session_id: str, name: str \| None` | `list[dict[str, object]]` | Project durable steering deliveries from the latest attempt journal. |
| [projection_service/service.py](projection_service/service.py#L1127) | `ConsoleProjectionService._journal_signature` | `attempt: object` | `tuple[str, int, str] \| None` | Return the (path, committed byte size, execution id) cache key. |
| [projection_service/service.py](projection_service/service.py#L1138) | `ConsoleProjectionService._cached_steering` | `attempt: object` | `list[dict[str, object]]` | Reduce steering records once per journal state, appending only new lines. |
| [projection_service/service.py](projection_service/service.py#L1192) | `ConsoleProjectionService._reduce_steering_event` | `records: dict[str, dict[str, object]], event: dict[str, object]` | `None` | Fold one journal fact into the durable steering record map. |
| [projection_service/service.py](projection_service/service.py#L1224) | `ConsoleProjectionService._steering_records` | `records: dict[str, dict[str, object]]` | `list[dict[str, object]]` | Return ordered copies so cached records are never mutated by callers. |
| [projection_service/service.py](projection_service/service.py#L1242) | `ConsoleProjectionService.calls` | `session_id: str, name: str, limit: int` | `CallsPayload` | Project every real LLM call made by one Agent from the journal. |
| [projection_service/service.py](projection_service/service.py#L1283) | `ConsoleProjectionService._calls_stats` | `records: list[CallRecord]` | `CallsStats` | Aggregate a filtered call ledger without touching raw prompts. |
| [projection_service/service.py](projection_service/service.py#L1304) | `ConsoleProjectionService._cached_calls` | `attempt: object` | `CallsState` | Reduce the call ledger once per journal state, appending only new lines. |
| [projection_service/service.py](projection_service/service.py#L1356) | `ConsoleProjectionService._primary_call` | `agent: str, round_idx: int, sequence: int, timestamp: JsonValue` | `PrimaryCall` | Create the canonical one-row-per-round primary call record. |
| [projection_service/service.py](projection_service/service.py#L1372) | `ConsoleProjectionService._reduce_calls_event` | `state: CallsState, event: object` | `None` | Fold one journal fact into the per-Agent call ledger. |
| [projection_service/service.py](projection_service/service.py#L1534) | `ConsoleProjectionService._request_config` | `data: dict[str, object]` | `RequestConfig` | Build the run-invariant per-Agent request configuration once. |
| [projection_service/service.py](projection_service/service.py#L1555) | `ConsoleProjectionService._backend_info` | `backend: object` | `BackendInfo` | Reduce a backend identity to the three whitelisted provider keys. |
| [projection_service/service.py](projection_service/service.py#L1567) | `ConsoleProjectionService._call_usage` | `value: object` | `CallUsage \| None` | Reduce one raw usage mapping to fixed, always-emitted counters. |
| [projection_service/service.py](projection_service/service.py#L1578) | `ConsoleProjectionService._tool_names` | `tool_calls: object` | `list[str]` | Reduce a committed tool_calls array to unique, ordered tool names. |
| [projection_service/service.py](projection_service/service.py#L1597) | `ConsoleProjectionService._calls_records` | `state: CallsState` | `list[CallRecord]` | Return every Agent's records in global sequence order. |
| [projection_service/service.py](projection_service/service.py#L1611) | `ConsoleProjectionService._request_messages` | `content: object` | `tuple[list[RequestMessage], int]` | Reduce a request-content preview to capped per-message rows. |
| [projection_service/service.py](projection_service/service.py#L1647) | `ConsoleProjectionService._preview` | `value: object, limit: int` | `ContentPreview \| None` | Cap one content value while reporting its true character count. |
| [projection_service/service.py](projection_service/service.py#L1662) | `ConsoleProjectionService._tool_result_preview` | `value: object` | `ContentPreview \| ToolResultPreview \| None` | Cap a tool result, keeping image counts instead of raw image bytes. |
| [projection_service/service.py](projection_service/service.py#L1675) | `ConsoleProjectionService._tool_calls_content` | `tool_calls: object` | `list[ToolCallContent]` | Reduce committed tool calls to name + capped argument previews. |
| [projection_service/service.py](projection_service/service.py#L1691) | `ConsoleProjectionService._merge_tool_results` | `record: PrimaryCall, tool_calls: object` | `None` | Merge completed tool results into a round row, keyed by call id. |
| [projection_service/service.py](projection_service/service.py#L1712) | `ConsoleProjectionService.context_graph` | `session_id: str, name: str` | `dict[str, object]` | Return the actual GraphContextHandler entity graph projection. |
| [projection_service/service.py](projection_service/service.py#L1748) | `ConsoleProjectionService._persisted_graph_projection` | `session_id: str, name: str` | `ContextGraphProjection` | Decode the committed entity graph for a non-materialised role. |
| [projection_service/service.py](projection_service/service.py#L1782) | `ConsoleProjectionService.compaction_input` | `session_id: str, name: str` | `dict[str, object]` | Reconstruct the next compaction request without provider I/O. |
| [projection_service/service.py](projection_service/service.py#L1821) | `ConsoleProjectionService.request_preview` | `session_id: str, name: str, message: str` | `dict[str, object]` | Compose one possible next Agent request without dispatching it. |
| [projection_service/service.py](projection_service/service.py#L1945) | `ConsoleProjectionService._latest_agent_input` | `session_id: str, name: str` | `str` | Read the newest live user input for one Agent from its journal. |
| [projection_service/service.py](projection_service/service.py#L1966) | `ConsoleProjectionService._detached_preview_agent` | `session_id: str, name: str` | `Any` | Create and hydrate an Agent copy that cannot mutate Session state. |
| [projection_service/service.py](projection_service/service.py#L1986) | `ConsoleProjectionService._agent` | `session_id: str, name: str` | `Any` | Resolve a concrete Agent, allowing unmaterialized persisted roles. |
| [projection_service/service.py](projection_service/service.py#L1997) | `ConsoleProjectionService._context_path` | `session_id: str, name: str` | `Path` | Return the single durable checkpoint path for one valid role. |
| [projection_service/types.py](projection_service/types.py#L236) | `CallsPayload.as_wire` | `None` | `dict[str, JsonValue]` | Serialize to the frontend wire shape with identical keys and order. |
| [tool_provider.py](tool_provider.py#L27) | `ConsoleToolProvider.materialize` | `session: object, policy: ToolPolicy, role: str, agent_name: str \| None` | `list[Tool]` | Build Console Tools authorized for the requested Agent role. |
| [tool_provider.py](tool_provider.py#L49) | `console_tool_registration` | `core: 'AngelusCore'` | `ToolProviderRegistration` | Return Console's complete, single registration with the Tool Registry. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [console_state.py](console_state.py#L32) | `ConsoleDomainError` | `None` | `ValueError` | A safe, user-visible failure caused by a console operation. |
| [console_state.py](console_state.py#L48) | `WorkerBlueprint` | `name: str, system_prompt: str, role: str` | `object` | Secret-free persisted definition of one reusable worker role. |
| [console_state.py](console_state.py#L56) | `ConnectionBlueprint` | `source: str, target: str` | `object` | One directed dependency in the static Session topology. |
| [console_state.py](console_state.py#L63) | `PlanExecution` | `assignment_ids: tuple[str, ...], active_assignment_id: str, updated_at: str` | `object` | Durable correlation between a plan leaf and TaskBus assignments. |
| [console_state.py](console_state.py#L71) | `PlanItem` | `id: str, title: str, description: str, status: str, priority: str, estimated_minutes: float \| None, subtasks: tuple['PlanItem', ...], execution: PlanExecution \| None` | `object` | One recursively nested Agent-authored task. |
| [console_state.py](console_state.py#L84) | `TaskPlan` | `goal: str, summary: str, tasks: tuple[PlanItem, ...], updated_at: str` | `object` | One complete plan owned by a concrete Agent. |
| [console_state.py](console_state.py#L101) | `ConsoleBlueprint` | `workers: dict[str, WorkerBlueprint], connections: list[ConnectionBlueprint], mappers: dict[str, str], routers: dict[str, list[str]], plans: dict[str, TaskPlan], schema_version: int` | `object` | Complete serializable console state owned by one Session. |
| [console_state.py](console_state.py#L167) | `ConsoleState` | `root: Path` | `object` | Atomically persist one Session's typed topology and task plan. |
| [console_tools.py](console_tools.py#L34) | `ToolPermissionPolicy` | `enabled_categories: frozenset[str], enabled_tools: frozenset[str]` | `object` | Validated effective allowlist for the tools this console provides. |
| [console_tools.py](console_tools.py#L90) | `SessionConsoleTools` | `session: 'Session', permissions: ToolPermissionPolicy, worker_factory: WorkerFactory \| None, agent_name: str, swarm_graph: 'SwarmGraphService \| None'` | `object` | Build safe plan and dynamic-topology tools for a single Session. |
| [context_provider.py](context_provider.py#L26) | `PlanContextProvider` | `console: ConsoleState, agent_name: str, max_characters: int` | `object` | Project one Agent's durable task plan into every model request. |
| [context_provider.py](context_provider.py#L83) | `PlanContextFactory` | `None` | `object` | Materialize the task-plan source for one Agent. |
| [projection_service/service.py](projection_service/service.py#L58) | `ConsoleProjectionService` | `core: 'AngelusCore'` | `object` | Provide `ConsoleProjectionService` behavior. |
| [projection_service/types.py](projection_service/types.py#L42) | `ContentPreview` | `text: str, characters: int, truncated: bool` | `object` | One capped content value that still reports its true character count. |
| [projection_service/types.py](projection_service/types.py#L50) | `ToolResultPreview` | `image_count: int` | `ContentPreview` | A tool-result preview that keeps an image count, never image bytes. |
| [projection_service/types.py](projection_service/types.py#L56) | `RequestMessage` | `role: str, text: str, characters: int, truncated: bool` | `object` | One capped planned request message rendered in the ledger. |
| [projection_service/types.py](projection_service/types.py#L65) | `ToolCallContent` | `name: str, args: ContentPreview \| None` | `object` | One tool call's name plus its capped argument preview. |
| [projection_service/types.py](projection_service/types.py#L72) | `ToolResult` | `call_id: str, name: str, ok: JsonValue, duration_ms: JsonValue, result: ContentPreview \| ToolResultPreview \| None` | `object` | One completed tool result keyed by the originating call id. |
| [projection_service/types.py](projection_service/types.py#L82) | `CallUsage` | `input: int, output: int, total: int, cached: int, reasoning: int` | `object` | Token accounting for one call; every key is always emitted. |
| [projection_service/types.py](projection_service/types.py#L92) | `UsageScope` | `all: CallUsage, primary: CallUsage` | `object` | Token totals for one scope: every call, and the request loop alone. |
| [projection_service/types.py](projection_service/types.py#L106) | `SessionUsageLedger` | `lifetime: UsageScope, run: UsageScope \| None, agents: dict[str, CallUsage]` | `object` | Usage rebuilt from journals, split by scope and by call kind. |
| [projection_service/types.py](projection_service/types.py#L120) | `RequestTool` | `name: str, description: ContentPreview \| None` | `object` | One tool schema offered to the model, with a capped description. |
| [projection_service/types.py](projection_service/types.py#L127) | `BackendInfo` | `name: str \| None, provider: str \| None, model: str \| None` | `object` | The provider identity one request was dispatched to. |
| [projection_service/types.py](projection_service/types.py#L135) | `RequestConfig` | `system_prompt: ContentPreview \| None, message: ContentPreview \| None, tools: list[RequestTool], backend: BackendInfo, temperature: JsonValue, max_tokens: JsonValue` | `object` | Run-invariant request material stored once per Agent. |
| [projection_service/types.py](projection_service/types.py#L146) | `PrimaryCall` | `kind: str, agent: str, round: int, request_id: str \| None, model: str, stream: bool, message_count: int, message_roles: dict[str, int], source_ids: list[str], input_characters: int, estimated_input_tokens: int, input_sha256: str, tool_count: int, tool_schema_hashes: list[str], tool_names: list[str], temperature: JsonValue, max_tokens: JsonValue, usage: CallUsage \| None, model_duration_ms: float \| None, round_duration_ms: float \| None, tool_call_count: int \| None, input_message: ContentPreview \| None, request_messages: list[RequestMessage], request_omitted_messages: int, assistant_content: ContentPreview \| None, reasoning_content: ContentPreview \| None, tool_calls: list[ToolCallContent], tool_results: list[ToolResult], retries: int, attempts: int, timestamp: JsonValue, id: str, sequence: int` | `object` | One real, round-based primary LLM call. |
| [projection_service/types.py](projection_service/types.py#L184) | `InternalCall` | `kind: str, agent: str, internal_kind: str, message: str, usage: CallUsage \| None, timestamp: JsonValue, id: str, sequence: int` | `object` | One hidden internal LLM call (for example context compaction). |
| [projection_service/types.py](projection_service/types.py#L200) | `AgentBucket` | `primary: dict[int, PrimaryCall], internal: list[InternalCall], request: RequestConfig \| None` | `object` | Per-Agent accumulator used while folding the durable journal. |
| [projection_service/types.py](projection_service/types.py#L208) | `CallsState` | `agents: dict[str, AgentBucket], sequence: int, cursor: int` | `object` | Incremental fold state keyed by journal byte cursor. |
| [projection_service/types.py](projection_service/types.py#L216) | `CallsStats` | `total: int, primary: int, internal: int, retries: int, input_tokens: int, usage: CallUsage` | `object` | Aggregate counters across one Agent's ledger window. |
| [projection_service/types.py](projection_service/types.py#L227) | `CallsPayload` | `agent: str, calls: list[CallRecord], available_tools: list[str], request_config: RequestConfig \| None, stats: CallsStats, has_more: bool` | `object` | Typed ``/calls`` projection; ``as_wire`` restores the JSON contract. |
| [tool_provider.py](tool_provider.py#L16) | `ConsoleToolProvider` | `core: 'AngelusCore'` | `object` | Materialize the Session-console plan and topology tools. |

<!-- END GENERATED SYMBOL MAP -->
