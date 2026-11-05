# application_module/ — Use-case Service INDEX

Application services coordinate existing owners. They contain no HTTP, browser
or terminal presentation logic.

| File | Responsibility |
|---|---|
| `session_service.py` | Create/list/delete Session + Workspace pairs and materialize coordinator from saved configuration. |
| `execution_service.py` | Start/inspect/stop/replay a Session-owned execution attempt and checkpoint a safe live graph view after every persisted Agent round. |
| `settings_service.py` | Validate connector/profile relationships and perform settings use cases. |

## Function Map

| Source | Function / method | Semantics |
|---|---|---|
| `SessionService.create` | Register Session/execution boundary then durable Workspace, with rollback on catalog failure. |
| `SessionService.ensure_coordinator` | Build/update coordinator from effective Profile and write-only connector secret. |
| `SessionService.rebuild_swarm` | Materialize the typed, secret-free console graph blueprint using the effective Session profile. |
| `ToolRegistry.materialize` | Attach only profile-authorized registered Tools to the coordinator and every restored worker. |
| `SessionService.delete` | Force-stop, remove Angelus state/legacy archive/catalog/aggregate in safe order. |
| `ExecutionService.start` | Confirm coordinator, validate optional targeted Agent, subscribe one attempt-scoped journal hook, run the selected Agent or complete AgentSwarm, checkpoint safe graph/context-pointer generations after persisted Agent rounds, and turn a failed root marker into a failed attempt. |
| `ExecutionService.stop` | Apply graceful/forced strategy to same Session controller. |
| `SettingsService.*profile` | Read/replace/clear future-run global or Session profile. |
| `SettingsService.*connector` | CRUD connector and reject deletion while effective profiles reference it. |

Coordinator, workers, and detached request-preview Agents receive the same
effective compaction-output budget, so the inspector displays the exact value
that a future compactor request would use.
They also receive the same effective `request_timeout_seconds`; changing it
changes coordinator identity and therefore applies on the next materialization.

## Class Map

| Source | Class | Semantics |
|---|---|---|
| `session_service.py` | `SessionService` | Session/workspace lifecycle and coordinator materialization. |
| `execution_service.py` | `ExecutionService` | Session execution lifecycle facade. |
| `settings_service.py` | `SettingsService` | Cross-store settings transaction boundary. |
| `execution_service.py` | `UnknownSession` | Uniform missing-Session use-case error. |

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [agent_control.py](agent_control.py#L15) | `SteeringInstruction.__new__` | `message: str, steer_id: str` | `'SteeringInstruction'` | Implement `SteeringInstruction.__new__`. |
| [agent_control.py](agent_control.py#L42) | `_CombinedForceEvent.is_set` | `None` | `bool` | Return whether either force-stop source is active. |
| [agent_control.py](agent_control.py#L50) | `_CombinedForceEvent.wait` | `timeout: float \| None` | `bool` | Wait briefly for either force-stop source. |
| [agent_control.py](agent_control.py#L89) | `AgentControlView.should_stop` | `None` | `bool` | Return whether global or local cooperative stop is requested. |
| [agent_control.py](agent_control.py#L98) | `AgentControlView.stop_request` | `None` | `StopRequest \| None` | Return the effective global-or-local stop request for this Agent. |
| [agent_control.py](agent_control.py#L116) | `AgentControlView.drain_steers` | `None` | `list[str]` | Return pending steering messages in FIFO order. |
| [agent_control.py](agent_control.py#L124) | `AgentControlView.steer` | `message: str, steer_id: str` | `None` | Queue one Agent-specific steering message. |
| [agent_control.py](agent_control.py#L132) | `AgentControlView.request_stop` | `force: bool, reason: str` | `None` | Request a local cooperative or forceful stop. |
| [agent_control.py](agent_control.py#L141) | `AgentControlView.register_force_canceller` | `cancel: Callable[[StopRequest], None]` | `Callable[[], None]` | Register a resource canceller with both global and local scope. |
| [agent_control.py](agent_control.py#L173) | `SessionRunControl.for_agent` | `agent_id: str` | `AgentControlView` | Return the persistent local control view for one Agent. |
| [agent_control.py](agent_control.py#L189) | `SessionRunControl.forget_agent` | `agent_id: str` | `None` | Drop one Agent's control view after it leaves the live graph. |
| [agent_control.py](agent_control.py#L201) | `SessionRunControl.should_stop` | `agent_id: str` | `bool` | Return the stop state used by AgentSwarm scheduling. |
| [agent_control.py](agent_control.py#L214) | `SessionRunControl.steer` | `agent_id: str, message: str` | `SteeringSubmission` | Queue steering for all Agents or one existing Agent. |
| [agent_control.py](agent_control.py#L242) | `SessionRunControl.stop` | `agent_id: str, force: bool, reason: str` | `tuple[str, ...]` | Request stop for all Agents or one active Agent. |
| [context_provider.py](context_provider.py#L36) | `WorkspaceContextProvider.source_id` | `None` | `str` | Return the stable Composer source identity. |
| [context_provider.py](context_provider.py#L40) | `WorkspaceContextProvider.build_blocks` | `snapshot: ContextSnapshot` | `Sequence[ContextBlock]` | Build the durable workspace description for the next request. |
| [context_provider.py](context_provider.py#L65) | `WorkspaceContextFactory.build` | `request: ContextProviderRequest` | `Sequence[ContextProvider]` | Return the workspace description bound to this Agent. |
| [context_provider.py](context_provider.py#L81) | `workspace_context_registration` | `None` | `ContextProviderRegistration` | Return the workspace source registration for the process registry. |
| [execution_service.py](execution_service.py#L36) | `_remove_journal_hook` | `swarm: object, hook: object` | `None` | Best-effort remove an attempt-local hook across supported swarm builds. |
| [execution_service.py](execution_service.py#L86) | `ExecutionService.start` | `session_id: str, message: str, recovery: dict[str, object] \| None, images: list[dict[str, Any]] \| None, target_agent: str \| None, connector_id: str \| None` | `ExecutionSnapshot` | Start the configured Session AgentSwarm under a fresh attempt. |
| [execution_service.py](execution_service.py#L268) | `ExecutionService._validate_images` | `session: Any, images: list[dict[str, Any]]` | `list[dict[str, Any]]` | Resolve ownership and metadata before an execution can start. |
| [execution_service.py](execution_service.py#L297) | `ExecutionService.recover` | `session_id: str, execution_id: str \| None` | `ExecutionSnapshot` | Start a safe, guided continuation from a verified RunGraph checkpoint. |
| [execution_service.py](execution_service.py#L331) | `ExecutionService.status` | `session_id: str` | `ExecutionSnapshot` | Return current in-process execution state, or synthetic idle state. |
| [execution_service.py](execution_service.py#L344) | `ExecutionService.stop` | `session_id: str, force: bool, reason: str` | `ExecutionSnapshot` | Request graceful or forced cancellation through the same controller. |
| [execution_service.py](execution_service.py#L364) | `ExecutionService.control` | `session_id: str, agent_id: str, action: str, message: str, reason: str` | `AgentControlReceipt` | Route one typed browser command to all or one active Agent. |
| [execution_service.py](execution_service.py#L423) | `ExecutionService.events` | `session_id: str` | `Iterator[dict[str, Any]]` | Yield durable events from the most recent in-process attempt. |
| [execution_service.py](execution_service.py#L437) | `ExecutionService._require_session` | `session_id: str` | `None` | Raise ``UnknownSession`` before an operation reaches Session state. |
| [session_service.py](session_service.py#L36) | `SessionService._context_providers` | `session_id: str, session: 'Session', workspace: Workspace, policy: ToolPolicy, role: str, agent_name: str` | `tuple[ContextProvider, ...]` | Materialize every module and plugin source for one Agent. |
| [session_service.py](session_service.py#L67) | `SessionService.create` | `session_id: str, name: str, project_path: Path \| None` | `Workspace` | Register an empty Session and its durable workspace metadata. |
| [session_service.py](session_service.py#L99) | `SessionService.list` | `None` | `tuple[Workspace, ...]` | List durable workspace records, including sessions configured later. |
| [session_service.py](session_service.py#L107) | `SessionService.ensure_coordinator` | `session_id: str, connector_id: str \| None` | `None` | Build or retain the Session's required coordinator from saved profile. |
| [session_service.py](session_service.py#L198) | `SessionService.compact` | `session_id: str, agent_name: str, on_event: Callable[[str, str, dict], None] \| None` | `Agent` | Compact one existing Session Agent through its configured fetcher. |
| [session_service.py](session_service.py#L236) | `SessionService.rebuild_swarm` | `session_id: str` | `None` | Materialize the safe console blueprint into the Session's one swarm. |
| [session_service.py](session_service.py#L266) | `SessionService.create_runtime_worker` | `session_id: str, name: str, system_prompt: str, connector_id: str \| None` | `Agent` | Build one worker using the effective Session profile and ToolRegistry. |
| [session_service.py](session_service.py#L325) | `SessionService.preview_agent` | `session_id: str, name: str, connector_id: str \| None` | `Agent` | Build one detached Agent for a no-I/O request preview. |
| [session_service.py](session_service.py#L393) | `SessionService._resolved_api_url` | `profile: dict[str, object], connector_id: str` | `str` | Resolve a profile endpoint, falling back to connector metadata. |
| [session_service.py](session_service.py#L401) | `SessionService._agent_budget` | `profile: dict[str, object], name: str` | `tuple[int, int, int]` | Resolve one Agent's optional execution overrides from the profile. |
| [session_service.py](session_service.py#L413) | `SessionService._resolve_connector_id` | `session_id: str, connector_id: str \| None, profile: dict[str, object]` | `str` | Resolve a per-run connector, then optional Session default. |
| [session_service.py](session_service.py#L426) | `SessionService.delete` | `session_id: str, confirmation: str, wait_timeout: float` | `Workspace` | Force-stop, durably remove, and unregister one confirmed Session. |
| [settings_service.py](settings_service.py#L34) | `SettingsService.global_profile` | `None` | `dict[str, Any]` | Read future-attempt defaults shared by all Sessions. |
| [settings_service.py](settings_service.py#L42) | `SettingsService.replace_global_profile` | `values: Mapping[str, Any]` | `dict[str, Any]` | Atomically replace global Session behavior defaults. |
| [settings_service.py](settings_service.py#L50) | `SettingsService.session_profile` | `session_id: str` | `dict[str, Any]` | Read effective future-attempt settings for an existing Session. |
| [settings_service.py](settings_service.py#L55) | `SettingsService.replace_session_profile` | `session_id: str, values: Mapping[str, Any]` | `dict[str, Any]` | Store a Session behavior override used only by future attempts. |
| [settings_service.py](settings_service.py#L64) | `SettingsService.clear_session_profile` | `session_id: str` | `dict[str, Any]` | Delete a Session override and restore global-default inheritance. |
| [settings_service.py](settings_service.py#L69) | `SettingsService.list_connectors` | `None` | `'tuple[ConnectorView, ...]'` | List safe connector projections; secrets never cross this boundary. |
| [settings_service.py](settings_service.py#L73) | `SettingsService.create_connector` | `values: Mapping[str, object]` | `'ConnectorView'` | Create one global connector with its optional API key stored separately. |
| [settings_service.py](settings_service.py#L77) | `SettingsService.replace_connector` | `connector_id: str, values: Mapping[str, object]` | `'ConnectorView'` | Replace metadata without returning or erasing an omitted API key. |
| [settings_service.py](settings_service.py#L83) | `SettingsService.session_preferences` | `session_id: str` | `'SessionPreference'` | Implement `SettingsService.session_preferences`. |
| [settings_service.py](settings_service.py#L87) | `SettingsService.set_default_connector` | `session_id: str, connector_id: str \| None` | `'SessionPreference'` | Implement `SettingsService.set_default_connector`. |
| [settings_service.py](settings_service.py#L96) | `SettingsService.delete_connector` | `connector_id: str` | `None` | Delete metadata and clear optional Session convenience defaults. |
| [settings_service.py](settings_service.py#L101) | `SettingsService._require_session` | `session_id: str` | `None` | Raise ``UnknownSession`` before a Session-scoped settings operation. |
| [swarm_graph_service.py](swarm_graph_service.py#L31) | `_rollback_failures` | `console: ConsoleState, previous: ConsoleBlueprint, cleanup: Callable[[], object] \| None` | `list[BaseException]` | Attempt every rollback action and return failures for aggregation. |
| [swarm_graph_service.py](swarm_graph_service.py#L83) | `SwarmGraphService.snapshot` | `session_id: str, execution_id: str \| None` | `dict[str, object]` | Return the one canonical swarm execution graph snapshot. |
| [swarm_graph_service.py](swarm_graph_service.py#L131) | `SwarmGraphService.live_view` | `session_id: str, execution_id: str \| None` | `SwarmViewSnapshot \| None` | Return the typed live view for an active Session attempt. |
| [swarm_graph_service.py](swarm_graph_service.py#L155) | `SwarmGraphService._live_view` | `session: 'Session', execution_id: str \| None` | `SwarmViewSnapshot \| None` | Read one live snapshot, or ``None`` when the attempt is not live. |
| [swarm_graph_service.py](swarm_graph_service.py#L170) | `SwarmGraphService.topology` | `session_id: str` | `dict[str, object]` | Return the editable static topology derived from :meth:`snapshot`. |
| [swarm_graph_service.py](swarm_graph_service.py#L195) | `SwarmGraphService.materialize` | `session_id: str` | `None` | Rebuild the live swarm from the durable blueprint. |
| [swarm_graph_service.py](swarm_graph_service.py#L213) | `SwarmGraphService.control_nodes` | `session_id: str` | `list[dict[str, object]]` | Return agent nodes used to pre-register control views. |
| [swarm_graph_service.py](swarm_graph_service.py#L250) | `SwarmGraphService.add_agent` | `session_id: str, name: str, system_prompt: str` | `SwarmGraphResult` | Add one worker to the durable and live graph through one path. |
| [swarm_graph_service.py](swarm_graph_service.py#L299) | `SwarmGraphService.remove_agent` | `session_id: str, name: str` | `SwarmGraphResult` | Remove one worker from the durable and live graph through one path. |
| [swarm_graph_service.py](swarm_graph_service.py#L347) | `SwarmGraphService.dispatch_agent` | `session_id: str, name: str, system_prompt: str, dispatch: Callable[[object], object]` | `SwarmGraphResult` | Create one Worker and dispatch its first task through one path. |
| [swarm_graph_service.py](swarm_graph_service.py#L402) | `SwarmGraphService.add_connection` | `session_id: str, source: str, target: str` | `SwarmGraphResult` | Add one acyclic dependency edge through one path. |
| [swarm_graph_service.py](swarm_graph_service.py#L425) | `SwarmGraphService.remove_connection` | `session_id: str, source: str, target: str` | `SwarmGraphResult` | Remove one dependency edge through one path. |
| [swarm_graph_service.py](swarm_graph_service.py#L448) | `SwarmGraphService.set_mapper` | `session_id: str, agent: str, mode: str` | `SwarmGraphResult` | Set one declarative mapper through one path. |
| [swarm_graph_service.py](swarm_graph_service.py#L471) | `SwarmGraphService.set_router` | `session_id: str, agent: str, targets: list[str]` | `SwarmGraphResult` | Set one fixed router target list through one path. |
| [swarm_graph_service.py](swarm_graph_service.py#L494) | `SwarmGraphService._mutate` | `session_id: str, mutate: Callable[[ConsoleState], None], apply_live: Callable[[object], str], status: str` | `SwarmGraphResult` | Apply one persisted topology mutation and mirror it to a live swarm. |
| [swarm_graph_service.py](swarm_graph_service.py#L534) | `SwarmGraphService._decorate` | `graph: dict[str, object], blueprint: object, live: bool` | `None` | Attach roles, mappers, routers, revision and the data source. |
| [swarm_graph_service.py](swarm_graph_service.py#L592) | `SwarmGraphService._session` | `session_id: str` | `'Session'` | Resolve one Session without hiding an unknown identity. |
| [swarm_graph_service.py](swarm_graph_service.py#L607) | `SwarmGraphService._is_live` | `session: 'Session'` | `bool` | Return whether the Session has an active execution attempt. |
| [swarm_graph_service.py](swarm_graph_service.py#L620) | `SwarmGraphService._require_console` | `session: 'Session'` | `ConsoleState` | Require the durable console state used by every topology mutation. |
| [swarm_graph_service.py](swarm_graph_service.py#L637) | `SwarmGraphService._require_live_swarm` | `session: 'Session'` | `object` | Require a materialized live swarm for an active mutation. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [agent_control.py](agent_control.py#L12) | `SteeringInstruction` | `None` | `str` | A model-visible steering string with a durable delivery identity. |
| [agent_control.py](agent_control.py#L22) | `SteeringSubmission` | `steer_id: str, target_agents: tuple[str, ...]` | `object` | One queued steering command and its fixed recipient snapshot. |
| [agent_control.py](agent_control.py#L29) | `_CombinedForceEvent` | `global_control: ExecutionController, local_control: ExecutionController` | `object` | Expose the force state of a global and local controller as one event. |
| [agent_control.py](agent_control.py#L74) | `AgentControlView` | `owner: 'SessionRunControl', agent_id: str` | `object` | Duck-typed llmfetcher control view for one concrete Agent. |
| [agent_control.py](agent_control.py#L160) | `SessionRunControl` | `global_control: ExecutionController` | `object` | Route Session-wide and Agent-local controls to active swarm Agents. |
| [agent_control.py](agent_control.py#L267) | `AgentControlReceipt` | `session_id: str, execution_id: str, agent_id: str, action: str, target_agents: tuple[str, ...], queued: bool, steer_id: str \| None` | `object` | Acknowledgement for one accepted Agent control command. |
| [context_provider.py](context_provider.py#L18) | `WorkspaceContextProvider` | `project_path: Path \| None, state_path: Path, agent_name: str` | `object` | Expose the bound project and Angelus state directories to an Agent. |
| [context_provider.py](context_provider.py#L62) | `WorkspaceContextFactory` | `None` | `object` | Materialize the workspace source for one Agent. |
| [execution_service.py](execution_service.py#L21) | `UnknownSession` | `None` | `LookupError` | Raised when a lifecycle request does not name a registered session. |
| [execution_service.py](execution_service.py#L26) | `_JournalBinding` | `attempt: ExecutionAttempt[object] \| None` | `object` | Attempt-scoped target used by a swarm hook before worker scheduling. |
| [execution_service.py](execution_service.py#L69) | `ExecutionService` | `core: 'AngelusCore'` | `object` | Perform Session execution lifecycle use cases without transport code. |
| [session_service.py](session_service.py#L23) | `SessionService` | `core: 'AngelusCore'` | `object` | Create Sessions and materialize their required coordinator when runnable. |
| [settings_service.py](settings_service.py#L16) | `SettingsService` | `core: 'AngelusCore'` | `object` | Apply settings transactions without letting HTTP handlers own policy. |
| [swarm_graph_service.py](swarm_graph_service.py#L51) | `SwarmGraphResult` | `status: str, snapshot: dict[str, object], payload: object \| None` | `object` | Outcome of one topology mutation plus the canonical graph snapshot. |
| [swarm_graph_service.py](swarm_graph_service.py#L65) | `SwarmGraphService` | `core: 'AngelusCore'` | `object` | Read and mutate one Session's swarm execution graph through one path. |

<!-- END GENERATED SYMBOL MAP -->
