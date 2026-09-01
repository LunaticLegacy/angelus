# tests/ — Phase 1 Regression INDEX

Tests deliberately construct isolated temporary state roots. They never require
real API credentials or mutate the repository's `.angelus-state` directory.

| File | Coverage |
|---|---|
| `test_execution_attempt.py` | Controller stop/force-stop, journal/checkpoint retention, SIGINT and Session-owned executor shutdown. |
| `test_execution_service.py` | Root graph-Agent failure conversion to a failed Session attempt and attempt-scoped hook cleanup. |
| `test_workspace_service.py` | Durable workspace creation, restart rehydration, legacy migration and confirmed deletion. |
| `test_conversation_store.py` | Legacy transcript pagination/projection and root-confined deletion. |
| `test_settings_service.py` | Secret separation, global/Session profile inheritance and coordinator materialization from saved connector state. |
| `test_session_console.py` | Typed console persistence, cycle rejection, controlled plan/topology tools, permission filtering, journal mutation evidence, secret exclusion, and restart-safe persisted Agent context chat projection. |
| `test_paged_context_storage.py` | SQLite context pointer save/load, newest-200 recovery and older-page cursor semantics. |

Run from repository root:

```bash
python -m unittest discover -s tests
node --check frontend/static/app.js
```

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [test_agent_defaults.py](test_agent_defaults.py#L16) | `AgentDefaultTests.test_agents_stream_by_default` | `None` | `None` | The factory opts every Session-created Agent into streaming. |
| [test_conversation_store.py](test_conversation_store.py#L16) | `ConversationStoreTests.test_pages_legacy_conversation_in_chronological_order` | `None` | `None` | The first page is newest but remains ordered for chat rendering. |
| [test_execution_attempt.py](test_execution_attempt.py#L19) | `ExecutionAttemptTests.test_force_stop_is_journaled_and_reaches_stopped` | `None` | `None` | A forced request is one event before the cooperative worker exits. |
| [test_execution_attempt.py](test_execution_attempt.py#L39) | `ExecutionAttemptTests.test_checkpoint_is_retained_when_execution_reaches_terminal_state` | `None` | `None` | Terminal manifest updates preserve the last journal-committed generation. |
| [test_execution_attempt.py](test_execution_attempt.py#L56) | `ExecutionAttemptTests.test_sigint_drain_force_stops_live_attempt_without_signal_handler_io` | `None` | `None` | The signal receiver only marks pending work; drain performs shutdown. |
| [test_execution_attempt.py](test_execution_attempt.py#L70) | `ExecutionAttemptTests.test_host_shutdown_force_stops_live_attempt` | `None` | `None` | An ASGI shutdown hook can persist termination without owning SIGINT. |
| [test_execution_attempt.py](test_execution_attempt.py#L84) | `ExecutionAttemptTests.test_sigint_announces_and_requests_force_stop_before_host_shutdown` | `None` | `None` | SIGINT's immediate phase stops work; host shutdown only awaits it. |
| [test_execution_service.py](test_execution_service.py#L20) | `_FailingSwarm.add_hook` | `hook: object` | `None` | Retain a hook supplied by the execution service. |
| [test_execution_service.py](test_execution_service.py#L31) | `_FailingSwarm.remove_hook` | `hook: object` | `bool` | Remove one retained hook. |
| [test_execution_service.py](test_execution_service.py#L45) | `_FailingSwarm.run` | `_message: str, control: object` | `dict[str, object]` | Return the graph's normal non-fatal root failure marker. |
| [test_execution_service.py](test_execution_service.py#L61) | `ExecutionServiceTests.test_root_agent_failure_marks_attempt_failed_and_removes_hook` | `None` | `None` | A coordinator AgentFailure cannot be recorded as completed output. |
| [test_paged_context_storage.py](test_paged_context_storage.py#L19) | `PagedContextStorageTests.test_save_load_and_page_without_full_context` | `None` | `None` | Store 205 entries then restore and page the newest 200 entries. |
| [test_plugin_manager.py](test_plugin_manager.py#L17) | `PluginManagerTests.test_theme_pack_registers_settings_and_serves_only_whitelisted_css` | `None` | `None` | A theme pack exposes multiple skins without executable entry code. |
| [test_plugin_manager.py](test_plugin_manager.py#L55) | `PluginManagerTests.test_tool_plugin_registers_only_namespaced_provider_after_explicit_load` | `None` | `None` | A tool plugin executes only at load and publishes host namespaced tools. |
| [test_plugin_manager.py](test_plugin_manager.py#L90) | `_json` | `path: Path, value: object` | `None` | Write a test fixture manifest. |
| [test_session_console.py](test_session_console.py#L18) | `_Journal.append` | `event_type: str, data: dict[str, object], **_kwargs: object` | `None` | Implement `_Journal.append`. |
| [test_session_console.py](test_session_console.py#L33) | `_Swarm.dynamic_add_connection` | `source: str, target: str` | `str` | Implement `_Swarm.dynamic_add_connection`. |
| [test_session_console.py](test_session_console.py#L34) | `_Swarm.dynamic_remove_connection` | `source: str, target: str` | `str` | Implement `_Swarm.dynamic_remove_connection`. |
| [test_session_console.py](test_session_console.py#L35) | `_Swarm.dynamic_set_mapper` | `agent: str, mode: str` | `str` | Implement `_Swarm.dynamic_set_mapper`. |
| [test_session_console.py](test_session_console.py#L36) | `_Swarm.dynamic_set_router` | `agent: str, targets: list[str]` | `str` | Implement `_Swarm.dynamic_set_router`. |
| [test_session_console.py](test_session_console.py#L42) | `_PreviewHandler.prepare_tools` | `_tools: object` | `list[object]` | Return an empty schema list for the isolated preview test. |
| [test_session_console.py](test_session_console.py#L57) | `SessionConsoleTests.test_restart_restores_topology_and_rejects_cycle` | `None` | `None` | The persisted blueprint is recovered without a connector or secret. |
| [test_session_console.py](test_session_console.py#L75) | `SessionConsoleTests.test_worker_removal_cleans_router_targets` | `None` | `None` | Removing a worker leaves no invalid persisted router target behind. |
| [test_session_console.py](test_session_console.py#L88) | `SessionConsoleTests.test_plan_and_dynamic_connection_tools_share_one_state_and_journal` | `None` | `None` | Agent tools persist the plan/topology and append no secret-bearing data. |
| [test_session_console.py](test_session_console.py#L106) | `SessionConsoleTests.test_permissions_omit_disabled_tools_from_agent_registration` | `None` | `None` | A persisted false permission removes its Tool before model exposure. |
| [test_session_console.py](test_session_console.py#L117) | `SessionConsoleTests.test_restart_projects_persisted_agent_context_into_chat_messages` | `None` | `None` | The chat endpoint source survives restart without legacy transcripts. |
| [test_session_console.py](test_session_console.py#L137) | `SessionConsoleTests.test_runtime_registry_exposes_and_materializes_project_shell` | `None` | `None` | Shell is both catalog-visible and a real authorized Agent Tool. |
| [test_session_console.py](test_session_console.py#L158) | `SessionConsoleTests.test_detached_previews_restore_context_without_dispatch_or_writes` | `None` | `None` | Both previews compose from checkpoint state without saving the draft. |
| [test_settings_service.py](test_settings_service.py#L16) | `SettingsServiceTests.test_connector_secret_never_appears_in_public_catalog` | `None` | `None` | Connector metadata is readable while its API key stays separate. |
| [test_settings_service.py](test_settings_service.py#L32) | `SettingsServiceTests.test_session_profile_is_session_owned_and_can_restore_inheritance` | `None` | `None` | A full Session override survives global changes until explicitly cleared. |
| [test_settings_service.py](test_settings_service.py#L55) | `SettingsServiceTests.test_saved_connector_materializes_required_coordinator_before_run` | `None` | `None` | Every Session reserves coordinator and builds it from saved profile state. |
| [test_workspace_service.py](test_workspace_service.py#L16) | `WorkspaceServiceTests.test_create_is_durable_and_core_rehydrates_empty_session` | `None` | `None` | A subsequent host sees the workspace and can address its session. |
| [test_workspace_service.py](test_workspace_service.py#L31) | `WorkspaceServiceTests.test_legacy_session_index_is_imported_without_inventing_project_paths` | `None` | `None` | Old session identities remain selectable after the storage redesign. |
| [test_workspace_service.py](test_workspace_service.py#L60) | `WorkspaceServiceTests.test_delete_removes_session_registry_and_durable_state` | `None` | `None` | A confirmed deletion cannot be rehydrated by a later core instance. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [test_agent_defaults.py](test_agent_defaults.py#L13) | `AgentDefaultTests` | `None` | `unittest.TestCase` | Ensure product defaults reach llmfetcher instead of remaining UI-only. |
| [test_conversation_store.py](test_conversation_store.py#L13) | `ConversationStoreTests` | `None` | `unittest.TestCase` | Ensure session selection can recover its historical messages. |
| [test_execution_attempt.py](test_execution_attempt.py#L16) | `ExecutionAttemptTests` | `None` | `unittest.TestCase` | Verify one controller, journal, and committed checkpoint generation. |
| [test_execution_service.py](test_execution_service.py#L13) | `_FailingSwarm` | `None` | `object` | Minimal graph facade that reports an unsuccessful root Agent. |
| [test_execution_service.py](test_execution_service.py#L58) | `ExecutionServiceTests` | `None` | `unittest.TestCase` | Ensure graph-level root failures become terminal attempt failures. |
| [test_paged_context_storage.py](test_paged_context_storage.py#L12) | `_NoopCompactor` | `None` | `object` | Minimal compactor placeholder because this test does not compact. |
| [test_paged_context_storage.py](test_paged_context_storage.py#L16) | `PagedContextStorageTests` | `None` | `unittest.TestCase` | Verify the durable reader returns bounded newest-first windows. |
| [test_plugin_manager.py](test_plugin_manager.py#L14) | `PluginManagerTests` | `None` | `unittest.TestCase` | Assert discovery never executes code and loaded packages stay bounded. |
| [test_session_console.py](test_session_console.py#L15) | `_Journal` | `None` | `object` | Capture secret-free console events emitted by a test tool call. |
| [test_session_console.py](test_session_console.py#L21) | `_Attempt` | `None` | `object` | Minimal attempt façade exposing the journal used by console tools. |
| [test_session_console.py](test_session_console.py#L26) | `_Execution` | `None` | `object` | Minimal execution façade retaining the current attempt. |
| [test_session_console.py](test_session_console.py#L31) | `_Swarm` | `None` | `object` | Minimal dynamic swarm façade used to verify direct dynamic calls. |
| [test_session_console.py](test_session_console.py#L39) | `_PreviewHandler` | `None` | `object` | Minimal provider facade proving request composition performs no I/O. |
| [test_session_console.py](test_session_console.py#L54) | `SessionConsoleTests` | `None` | `unittest.TestCase` | Verify state recovery, validation, and Agent-owned mutation writes. |
| [test_settings_service.py](test_settings_service.py#L13) | `SettingsServiceTests` | `None` | `unittest.TestCase` | Verify the new settings path has one durable authority per concern. |
| [test_workspace_service.py](test_workspace_service.py#L13) | `WorkspaceServiceTests` | `None` | `unittest.TestCase` | Ensure durable workspace records do not create a second session owner. |

<!-- END GENERATED SYMBOL MAP -->
