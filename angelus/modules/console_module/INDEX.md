# console_module/ — Session Console State and Projections INDEX

This module owns the durable, non-secret console projection for one `Session`.
It never creates a second AgentSwarm, executor, or credential store.

| File | Responsibility |
|---|---|
| `console_state.py` | Typed, atomically persisted plan and idle graph blueprint at `console/state.json`. |
| `projection_service.py` | Projects Session swarm, execution journal, usage, GraphContextHandler state, and durable context cursor pages for APIs; applies idle-only graph edits. |
| `console_tools.py` | Controlled Agent plan and dynamic connection/mapper/router tools that write the same Session state and attempt journal; `ToolPermissionPolicy` omits disabled tools before Agent registration. |
| `tool_provider.py` | Console's single registration and runtime materializer for the unified `ToolRegistry`. |
| `__init__.py` | Public console domain exports. |

## Invariants

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
| [console_state.py](console_state.py#L51) | `ConsoleBlueprint.to_json` | `None` | `dict[str, object]` | Encode the typed blueprint without secrets or runtime objects. |
| [console_state.py](console_state.py#L60) | `ConsoleBlueprint.from_json` | `value: object` | `'ConsoleBlueprint'` | Decode a tolerant on-disk document, ignoring malformed entries. |
| [console_state.py](console_state.py#L95) | `ConsoleState._load` | `None` | `ConsoleBlueprint` | Load prior state or initialize an empty blueprint. |
| [console_state.py](console_state.py#L100) | `ConsoleState.save` | `None` | `None` | Atomically commit the current secret-free blueprint. |
| [console_state.py](console_state.py#L108) | `ConsoleState.blueprint` | `None` | `ConsoleBlueprint` | Return an isolated typed snapshot for projection or swarm rebuild. |
| [console_state.py](console_state.py#L116) | `ConsoleState.add_worker` | `name: str, system_prompt: str` | `None` | Add a worker after validating its stable identity. |
| [console_state.py](console_state.py#L131) | `ConsoleState.remove_worker` | `name: str` | `None` | Remove a worker and every persisted setting that references it. |
| [console_state.py](console_state.py#L151) | `ConsoleState._nodes` | `None` | `set[str]` | Implement `ConsoleState._nodes`. |
| [console_state.py](console_state.py#L153) | `ConsoleState.add_connection` | `source: str, target: str` | `None` | Add a dependency, rejecting duplicates, self-links, and cycles. |
| [console_state.py](console_state.py#L177) | `ConsoleState.remove_connection` | `source: str, target: str` | `None` | Remove one existing dependency edge. |
| [console_state.py](console_state.py#L192) | `ConsoleState.mapper` | `agent: str, mode: str` | `None` | Store one supported declarative predecessor-output mapper. |
| [console_state.py](console_state.py#L207) | `ConsoleState.router` | `agent: str, targets: list[str]` | `None` | Store a fixed safe router target set for an Agent. |
| [console_state.py](console_state.py#L221) | `ConsoleState.plan` | `agent: str \| None` | `list[PlanItem]` | Return a typed plan snapshot optionally scoped to one Agent. |
| [console_state.py](console_state.py#L232) | `ConsoleState.set_plan` | `items: list[PlanItem]` | `None` | Replace the plan with already-validated Agent-authored items. |
| [console_state.py](console_state.py#L240) | `ConsoleState.upsert_plan_item` | `item: PlanItem` | `None` | Create or replace a durable task-plan item by identity. |
| [console_tools.py](console_tools.py#L16) | `_schema` | `*parameters: ToolParameter` | `ToolSchema` | Create a compact first-party tool schema. |
| [console_tools.py](console_tools.py#L41) | `ToolPermissionPolicy.from_profile` | `value: object` | `'ToolPermissionPolicy'` | Decode one persisted profile value without trusting its shape. |
| [console_tools.py](console_tools.py#L64) | `ToolPermissionPolicy.allows` | `category: str, tool: str` | `bool` | Return whether a category and its individual tool are enabled. |
| [console_tools.py](console_tools.py#L76) | `ToolPermissionPolicy.fingerprint` | `None` | `tuple[tuple[str, ...], tuple[str, ...]]` | Return a deterministic value suitable for Agent rebuild identity. |
| [console_tools.py](console_tools.py#L104) | `SessionConsoleTools.build` | `None` | `list[Tool]` | Create the controlled tool set for a coordinator or worker. |
| [console_tools.py](console_tools.py#L143) | `SessionConsoleTools._journal` | `event_type: str, message: str, data: dict[str, object]` | `None` | Append one mutation fact when an execution attempt exists. |
| [console_tools.py](console_tools.py#L155) | `SessionConsoleTools.plan_upsert` | `id: str, status: str, title: str` | `str` | Persist a task item and record the mutation in the attempt journal. |
| [console_tools.py](console_tools.py#L170) | `SessionConsoleTools.plan_read` | `None` | `list[dict[str, object]]` | Return the currently durable plan to the calling Agent. |
| [console_tools.py](console_tools.py#L178) | `SessionConsoleTools.swarm_connect` | `source: str, target: str` | `str` | Persist and dynamically apply one safe dependency connection. |
| [console_tools.py](console_tools.py#L193) | `SessionConsoleTools.swarm_disconnect` | `source: str, target: str` | `str` | Persist and dynamically remove one dependency connection. |
| [console_tools.py](console_tools.py#L208) | `SessionConsoleTools.swarm_set_mapper` | `agent: str, mode: str` | `str` | Persist and dynamically configure a mapper. |
| [console_tools.py](console_tools.py#L223) | `SessionConsoleTools.swarm_set_router` | `agent: str, targets: list[str]` | `str` | Persist and dynamically configure a fixed router. |
| [projection_service.py](projection_service.py#L27) | `ConsoleProjectionService._session` | `session_id: str` | `Any` | Resolve a Session or translate its absence into a domain lookup. |
| [projection_service.py](projection_service.py#L32) | `ConsoleProjectionService._state` | `session_id: str` | `Any` | Return the Session-owned typed console state. |
| [projection_service.py](projection_service.py#L35) | `ConsoleProjectionService._idle` | `session_id: str` | `None` | Reject static graph edits while an attempt is live. |
| [projection_service.py](projection_service.py#L41) | `ConsoleProjectionService.graph` | `session_id: str` | `dict[str, object]` | Project the real swarm or its typed idle blueprint for the UI. |
| [projection_service.py](projection_service.py#L58) | `ConsoleProjectionService.graph_info` | `session_id: str` | `dict[str, object]` | Return compact graph counts and current editability. |
| [projection_service.py](projection_service.py#L68) | `ConsoleProjectionService._is_idle` | `session_id: str` | `bool` | Return whether static graph changes are currently permitted. |
| [projection_service.py](projection_service.py#L72) | `ConsoleProjectionService.agents` | `session_id: str` | `dict[str, object]` | Return safe Agent metadata and real context statistics. |
| [projection_service.py](projection_service.py#L84) | `ConsoleProjectionService._context_stats` | `agent: object` | `dict[str, object]` | Summarize a concrete Agent context without exposing messages. |
| [projection_service.py](projection_service.py#L93) | `ConsoleProjectionService.usage` | `session_id: str` | `dict[str, object]` | Aggregate five-dimensional token usage across the Session swarm. |
| [projection_service.py](projection_service.py#L104) | `ConsoleProjectionService.events` | `session_id: str, cursor: int, limit: int` | `dict[str, object]` | Page the current attempt's durable journal in commit order. |
| [projection_service.py](projection_service.py#L124) | `ConsoleProjectionService._rebuild_after_edit` | `session_id: str` | `dict[str, object]` | Rebuild the concrete swarm after a persisted static graph change. |
| [projection_service.py](projection_service.py#L136) | `ConsoleProjectionService.add_worker` | `session_id: str, name: str, system_prompt: str` | `dict[str, object]` | Add one worker to an idle Session graph. |
| [projection_service.py](projection_service.py#L151) | `ConsoleProjectionService.remove_worker` | `session_id: str, name: str` | `dict[str, object]` | Remove one worker from an idle Session graph. |
| [projection_service.py](projection_service.py#L165) | `ConsoleProjectionService.add_connection` | `session_id: str, source: str, target: str` | `dict[str, object]` | Add one acyclic dependency edge to an idle Session graph. |
| [projection_service.py](projection_service.py#L180) | `ConsoleProjectionService.remove_connection` | `session_id: str, source: str, target: str` | `dict[str, object]` | Remove one dependency edge from an idle Session graph. |
| [projection_service.py](projection_service.py#L195) | `ConsoleProjectionService.set_mapper` | `session_id: str, agent: str, mode: str` | `dict[str, object]` | Set a declarative mapper on an idle Session graph. |
| [projection_service.py](projection_service.py#L210) | `ConsoleProjectionService.set_router` | `session_id: str, agent: str, targets: list[str]` | `dict[str, object]` | Set fixed router targets on an idle Session graph. |
| [projection_service.py](projection_service.py#L225) | `ConsoleProjectionService.plan` | `session_id: str, agent: str \| None` | `dict[str, object]` | Project durable plan items into JSON-safe API data. |
| [projection_service.py](projection_service.py#L237) | `ConsoleProjectionService.context` | `session_id: str, name: str, before: int \| None, limit: int` | `dict[str, object]` | Return persisted linear-context metadata for one valid Agent role. |
| [projection_service.py](projection_service.py#L260) | `ConsoleProjectionService.messages` | `session_id: str, name: str \| None, before: int \| None, limit: int` | `dict[str, object]` | Project one Agent's durable context page into chat-message cards. |
| [projection_service.py](projection_service.py#L289) | `ConsoleProjectionService.context_graph` | `session_id: str, name: str` | `dict[str, object]` | Return the actual GraphContextHandler entity graph projection. |
| [projection_service.py](projection_service.py#L307) | `ConsoleProjectionService.compaction_input` | `session_id: str, name: str` | `dict[str, object]` | Reconstruct the current compaction input without a remote request. |
| [projection_service.py](projection_service.py#L319) | `ConsoleProjectionService._agent` | `session_id: str, name: str` | `Any` | Resolve a concrete Agent, allowing unmaterialized persisted roles. |
| [projection_service.py](projection_service.py#L330) | `ConsoleProjectionService._context_path` | `session_id: str, name: str` | `Path` | Return the single durable checkpoint path for one valid role. |
| [tool_provider.py](tool_provider.py#L14) | `ConsoleToolProvider.materialize` | `session: object, policy: ToolPolicy, role: str` | `list[Tool]` | Build Console Tools authorized for the requested Agent role. |
| [tool_provider.py](tool_provider.py#L33) | `console_tool_registration` | `None` | `ToolProviderRegistration` | Return Console's complete, single registration with the Tool Registry. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [console_state.py](console_state.py#L13) | `ConsoleDomainError` | `None` | `ValueError` | A safe, user-visible failure caused by a console operation. |
| [console_state.py](console_state.py#L18) | `WorkerBlueprint` | `name: str, system_prompt: str, role: str` | `object` | Secret-free persisted definition of one reusable worker role. |
| [console_state.py](console_state.py#L26) | `ConnectionBlueprint` | `source: str, target: str` | `object` | One directed dependency in the static Session topology. |
| [console_state.py](console_state.py#L33) | `PlanItem` | `id: str, status: str, agent: str, title: str` | `object` | A durable Agent-authored task-plan item. |
| [console_state.py](console_state.py#L42) | `ConsoleBlueprint` | `workers: dict[str, WorkerBlueprint], connections: list[ConnectionBlueprint], mappers: dict[str, str], routers: dict[str, list[str]], plan: list[PlanItem], schema_version: int` | `object` | Complete serializable console state owned by one Session. |
| [console_state.py](console_state.py#L83) | `ConsoleState` | `root: Path` | `object` | Atomically persist one Session's typed topology and task plan. |
| [console_tools.py](console_tools.py#L29) | `ToolPermissionPolicy` | `enabled_categories: frozenset[str], enabled_tools: frozenset[str]` | `object` | Validated effective allowlist for the tools this console provides. |
| [console_tools.py](console_tools.py#L85) | `SessionConsoleTools` | `session: 'Session', permissions: ToolPermissionPolicy` | `object` | Build safe plan and dynamic-topology tools for a single Session. |
| [projection_service.py](projection_service.py#L18) | `ConsoleProjectionService` | `core: 'AngelusCore'` | `object` | Provide `ConsoleProjectionService` behavior. |
| [tool_provider.py](tool_provider.py#L11) | `ConsoleToolProvider` | `None` | `object` | Materialize the Session-console plan and topology tools. |

<!-- END GENERATED SYMBOL MAP -->
