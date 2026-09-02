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
| `ExecutionService.start` | Confirm coordinator, subscribe one attempt-scoped journal hook, run the complete AgentSwarm, checkpoint safe graph/context-pointer generations after persisted Agent rounds, and turn a failed coordinator marker into a failed attempt. |
| `ExecutionService.stop` | Apply graceful/forced strategy to same Session controller. |
| `SettingsService.*profile` | Read/replace/clear future-run global or Session profile. |
| `SettingsService.*connector` | CRUD connector and reject deletion while effective profiles reference it. |

Coordinator, workers, and detached request-preview Agents receive the same
effective compaction-output budget, so the inspector displays the exact value
that a future compactor request would use.

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
| [agent_control.py](agent_control.py#L24) | `_CombinedForceEvent.is_set` | `None` | `bool` | Return whether either force-stop source is active. |
| [agent_control.py](agent_control.py#L32) | `_CombinedForceEvent.wait` | `timeout: float \| None` | `bool` | Wait briefly for either force-stop source. |
| [agent_control.py](agent_control.py#L71) | `AgentControlView.should_stop` | `None` | `bool` | Return whether global or local cooperative stop is requested. |
| [agent_control.py](agent_control.py#L80) | `AgentControlView.stop_request` | `None` | `StopRequest \| None` | Return the effective global-or-local stop request for this Agent. |
| [agent_control.py](agent_control.py#L98) | `AgentControlView.drain_steers` | `None` | `list[str]` | Return targeted and broadcast steering messages in FIFO order. |
| [agent_control.py](agent_control.py#L106) | `AgentControlView.steer` | `message: str` | `None` | Queue one Agent-specific steering message. |
| [agent_control.py](agent_control.py#L114) | `AgentControlView.request_stop` | `force: bool, reason: str` | `None` | Request a local cooperative or forceful stop. |
| [agent_control.py](agent_control.py#L123) | `AgentControlView.register_force_canceller` | `cancel: Callable[[StopRequest], None]` | `Callable[[], None]` | Register a resource canceller with both global and local scope. |
| [agent_control.py](agent_control.py#L157) | `SessionRunControl.for_agent` | `agent_id: str` | `AgentControlView` | Return the persistent local control view for one Agent. |
| [agent_control.py](agent_control.py#L174) | `SessionRunControl.should_stop` | `agent_id: str` | `bool` | Return the stop state used by AgentSwarm scheduling. |
| [agent_control.py](agent_control.py#L187) | `SessionRunControl.steer` | `agent_id: str, message: str` | `tuple[str, ...]` | Queue steering for all Agents or one existing Agent. |
| [agent_control.py](agent_control.py#L211) | `SessionRunControl.stop` | `agent_id: str, force: bool, reason: str` | `tuple[str, ...]` | Request stop for all Agents or one active Agent. |
| [agent_control.py](agent_control.py#L235) | `SessionRunControl._drain_broadcast` | `agent_id: str` | `list[str]` | Return unseen broadcast steering messages for one Agent. |
| [execution_service.py](execution_service.py#L32) | `_remove_journal_hook` | `swarm: object, hook: object` | `None` | Best-effort remove an attempt-local hook across supported swarm builds. |
| [execution_service.py](execution_service.py#L82) | `ExecutionService.start` | `session_id: str, message: str` | `ExecutionSnapshot` | Start the configured Session AgentSwarm under a fresh attempt. |
| [execution_service.py](execution_service.py#L169) | `ExecutionService.status` | `session_id: str` | `ExecutionSnapshot` | Return current in-process execution state, or synthetic idle state. |
| [execution_service.py](execution_service.py#L182) | `ExecutionService.stop` | `session_id: str, force: bool, reason: str` | `ExecutionSnapshot` | Request graceful or forced cancellation through the same controller. |
| [execution_service.py](execution_service.py#L194) | `ExecutionService.control` | `session_id: str, agent_id: str, action: str, message: str, reason: str` | `AgentControlReceipt` | Route one typed browser command to all or one active Agent. |
| [execution_service.py](execution_service.py#L246) | `ExecutionService.events` | `session_id: str` | `Iterator[dict[str, Any]]` | Yield durable events from the most recent in-process attempt. |
| [execution_service.py](execution_service.py#L260) | `ExecutionService._require_session` | `session_id: str` | `None` | Raise ``UnknownSession`` before an operation reaches Session state. |
| [session_service.py](session_service.py#L34) | `SessionService.create` | `session_id: str, name: str, project_path: Path` | `Workspace` | Register an empty Session and its durable workspace metadata. |
| [session_service.py](session_service.py#L60) | `SessionService.list` | `None` | `tuple[Workspace, ...]` | List durable workspace records, including sessions configured later. |
| [session_service.py](session_service.py#L68) | `SessionService.ensure_coordinator` | `session_id: str` | `None` | Build or retain the Session's required coordinator from saved profile. |
| [session_service.py](session_service.py#L126) | `SessionService.rebuild_swarm` | `session_id: str` | `None` | Materialize the safe console blueprint into the Session's one swarm. |
| [session_service.py](session_service.py#L154) | `SessionService.create_runtime_worker` | `session_id: str, name: str, system_prompt: str` | `Agent` | Build one worker using the effective Session profile and ToolRegistry. |
| [session_service.py](session_service.py#L198) | `SessionService.preview_agent` | `session_id: str, name: str` | `Agent` | Build one detached Agent for a no-I/O request preview. |
| [session_service.py](session_service.py#L250) | `SessionService.delete` | `session_id: str, confirmation: str, wait_timeout: float` | `Workspace` | Force-stop, durably remove, and unregister one confirmed Session. |
| [settings_service.py](settings_service.py#L32) | `SettingsService.global_profile` | `None` | `dict[str, Any]` | Read future-attempt defaults shared by all Sessions. |
| [settings_service.py](settings_service.py#L40) | `SettingsService.replace_global_profile` | `values: Mapping[str, Any]` | `dict[str, Any]` | Validate connector ownership then atomically replace global defaults. |
| [settings_service.py](settings_service.py#L49) | `SettingsService.session_profile` | `session_id: str` | `dict[str, Any]` | Read effective future-attempt settings for an existing Session. |
| [settings_service.py](settings_service.py#L54) | `SettingsService.replace_session_profile` | `session_id: str, values: Mapping[str, Any]` | `dict[str, Any]` | Store a Session override used only by future execution attempts. |
| [settings_service.py](settings_service.py#L64) | `SettingsService.clear_session_profile` | `session_id: str` | `dict[str, Any]` | Delete a Session override and restore global-default inheritance. |
| [settings_service.py](settings_service.py#L69) | `SettingsService.list_connectors` | `None` | `tuple[dict[str, Any], ...]` | List safe connector projections; secrets never cross this boundary. |
| [settings_service.py](settings_service.py#L73) | `SettingsService.create_connector` | `values: dict[str, Any]` | `dict[str, Any]` | Create one global connector with its optional API key stored separately. |
| [settings_service.py](settings_service.py#L77) | `SettingsService.replace_connector` | `connector_id: str, values: dict[str, Any]` | `dict[str, Any]` | Replace metadata without returning or erasing an omitted API key. |
| [settings_service.py](settings_service.py#L81) | `SettingsService.delete_connector` | `connector_id: str` | `None` | Delete an unreferenced connector or reject with every retaining scope. |
| [settings_service.py](settings_service.py#L94) | `SettingsService._require_session` | `session_id: str` | `None` | Raise ``UnknownSession`` before a Session-scoped settings operation. |
| [settings_service.py](settings_service.py#L99) | `SettingsService._require_connector` | `values: Mapping[str, Any]` | `None` | Reject a non-empty profile connector ID absent from the global store. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [agent_control.py](agent_control.py#L11) | `_CombinedForceEvent` | `global_control: ExecutionController, local_control: ExecutionController` | `object` | Expose the force state of a global and local controller as one event. |
| [agent_control.py](agent_control.py#L56) | `AgentControlView` | `owner: 'SessionRunControl', agent_id: str` | `object` | Duck-typed llmfetcher control view for one concrete Agent. |
| [agent_control.py](agent_control.py#L142) | `SessionRunControl` | `global_control: ExecutionController` | `object` | Route Session-wide and Agent-local controls to active swarm Agents. |
| [agent_control.py](agent_control.py#L252) | `AgentControlReceipt` | `session_id: str, execution_id: str, agent_id: str, action: str, target_agents: tuple[str, ...], queued: bool` | `object` | Acknowledgement for one accepted Agent control command. |
| [execution_service.py](execution_service.py#L17) | `UnknownSession` | `None` | `LookupError` | Raised when a lifecycle request does not name a registered session. |
| [execution_service.py](execution_service.py#L22) | `_JournalBinding` | `attempt: ExecutionAttempt[object] \| None` | `object` | Attempt-scoped target used by a swarm hook before worker scheduling. |
| [execution_service.py](execution_service.py#L65) | `ExecutionService` | `core: 'AngelusCore'` | `object` | Perform Session execution lifecycle use cases without transport code. |
| [session_service.py](session_service.py#L21) | `SessionService` | `core: 'AngelusCore'` | `object` | Create Sessions and materialize their required coordinator when runnable. |
| [settings_service.py](settings_service.py#L14) | `SettingsService` | `core: 'AngelusCore'` | `object` | Apply settings transactions without letting HTTP handlers own policy. |

<!-- END GENERATED SYMBOL MAP -->
