# tests/ — Phase 1 Regression INDEX

Tests deliberately construct isolated temporary state roots. They never require
real API credentials or mutate the repository's `.angelus-state` directory.

| File | Coverage |
|---|---|
| `test_execution_attempt.py` | Controller stop/force-stop, journal/checkpoint retention, SIGINT and Session-owned executor shutdown. |
| `test_execution_service.py` | Root graph-Agent failure conversion to a failed Session attempt and attempt-scoped hook cleanup. |
| `test_workspace_service.py` | Durable workspace creation, restart rehydration, legacy migration and confirmed deletion. |
| `test_system_resource_manager.py` | Windows/macOS/Linux system folder-picker dispatch, cancellation, availability, and path validation. |
| `test_conversation_store.py` | Legacy transcript pagination/projection and root-confined deletion. |
| `test_settings_service.py` | Secret separation, global/Session profile inheritance and coordinator materialization from saved connector state. |
| `test_llm_timeout_retry.py` | Provider-neutral timeout classification, causal-chain recognition, configured retries, and streamed partial-output safety. |
| `test_session_console.py` | Typed console persistence, cycle rejection, controlled plan/topology tools, permission filtering, journal mutation evidence, secret exclusion, and restart-safe persisted Agent context chat projection. |
| `test_paged_context_storage.py` | SQLite context pointer save/load, newest-200 recovery and older-page cursor semantics. |
| `test_external_agent_hub.py` | External Agent definition persistence, protocol adapter base, process-candidate discovery boundaries, and Hub route projections. |
| `test_external_agent_hub_read_only_adapters.py` | Coze, OpenCode, and WorkBuddy typed read-only facade adapter tests. |
| `test_codex_app_server_adapter.py` | Constrained Codex App Server stdio handshake and bounded thread discovery. |
| `test_claude_sdk_adapter.py` | Lazy Claude SDK availability and bounded local session discovery. |
| `test_context_package.py` | Strict portable context-package decoding and historical tool-call containment. |
| `test_capability_migrations.py` | Nested-plan migration, MCP secret/binding isolation, context revisions and cross-Session snapshots. |
| `test_plugin_manager.py` | Strict plugin manifest discovery, settings/theme lifecycle, namespaced POFP/GZCTF tool publication, and declarative transient-panel action dispatch. |

Run from repository root:

```bash
python -m unittest discover -s tests
node --check frontend/static/app.js
```

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [test_agent_control.py](test_agent_control.py#L13) | `AgentControlTests.test_targeted_steer_and_stop_do_not_affect_other_agents` | `None` | `None` | Deliver commands only to the selected Agent control view. |
| [test_agent_control.py](test_agent_control.py#L30) | `AgentControlTests.test_all_scope_broadcasts_and_stops_every_agent` | `None` | `None` | Broadcast steering and global stop to every active Agent view. |
| [test_agent_control.py](test_agent_control.py#L44) | `AgentControlTests.test_all_scope_steer_does_not_reach_agents_created_later` | `None` | `None` | An ALL steer snapshots live Agent views at submission time. |
| [test_agent_control.py](test_agent_control.py#L57) | `AgentControlTests.test_targeted_force_stop_cancels_only_target_resources` | `None` | `None` | Invoke only the selected Agent's registered resource canceller. |
| [test_agent_control.py](test_agent_control.py#L75) | `AgentControlTests.test_effective_stop_request_prefers_force_across_scopes` | `None` | `None` | Expose the force request required by LLMFetcher cancellation checks. |
| [test_agent_defaults.py](test_agent_defaults.py#L16) | `AgentDefaultTests.test_agents_stream_by_default` | `None` | `None` | The factory opts every Session-created Agent into streaming. |
| [test_capability_migrations.py](test_capability_migrations.py#L20) | `CapabilityMigrationTests.test_nested_plan_is_atomic_and_derives_parent_status` | `None` | `None` | Implement `CapabilityMigrationTests.test_nested_plan_is_atomic_and_derives_parent_status`. |
| [test_capability_migrations.py](test_capability_migrations.py#L41) | `CapabilityMigrationTests.test_flat_schema_one_plan_is_migrated_to_coordinator` | `None` | `None` | Implement `CapabilityMigrationTests.test_flat_schema_one_plan_is_migrated_to_coordinator`. |
| [test_capability_migrations.py](test_capability_migrations.py#L47) | `CapabilityMigrationTests.test_context_edit_requires_revision_and_restore_is_forward_only` | `None` | `None` | Implement `CapabilityMigrationTests.test_context_edit_requires_revision_and_restore_is_forward_only`. |
| [test_capability_migrations.py](test_capability_migrations.py#L62) | `CapabilityMigrationTests.test_mcp_secrets_are_not_in_catalog_and_bindings_resolve_by_role` | `None` | `None` | Implement `CapabilityMigrationTests.test_mcp_secrets_are_not_in_catalog_and_bindings_resolve_by_role`. |
| [test_capability_migrations.py](test_capability_migrations.py#L73) | `CapabilityMigrationTests.test_restored_tools_are_registered_and_enabled_by_default` | `None` | `None` | Implement `CapabilityMigrationTests.test_restored_tools_are_registered_and_enabled_by_default`. |
| [test_capability_migrations.py](test_capability_migrations.py#L84) | `CapabilityMigrationTests.test_session_snapshot_reads_current_sqlite_context` | `None` | `None` | Implement `CapabilityMigrationTests.test_session_snapshot_reads_current_sqlite_context`. |
| [test_claude_sdk_adapter.py](test_claude_sdk_adapter.py#L30) | `FakeClaudeDiscovery.availability` | `None` | `ClaudeSdkAvailability` | Report configured local SDK availability. |
| [test_claude_sdk_adapter.py](test_claude_sdk_adapter.py#L38) | `FakeClaudeDiscovery.list_sessions` | `limit: int` | `tuple[ClaudeSdkSessionRecord, ...]` | Return bounded fake session records without executing an Agent. |
| [test_claude_sdk_adapter.py](test_claude_sdk_adapter.py#L53) | `ClaudeSdkAdapterTests.test_unavailable_sdk_reports_safe_health_and_no_sessions` | `None` | `None` | Missing SDK state returns unavailable without any dispatch attempt. |
| [test_claude_sdk_adapter.py](test_claude_sdk_adapter.py#L64) | `ClaudeSdkAdapterTests.test_available_sdk_maps_bounded_session_summaries` | `None` | `None` | Available facade maps SDK records into external session summaries. |
| [test_claude_sdk_adapter.py](test_claude_sdk_adapter.py#L86) | `ClaudeSdkAdapterTests.test_capability_is_read_only_session_discovery` | `None` | `None` | Capability list contains no run, resume, or dispatch declaration. |
| [test_claude_sdk_adapter.py](test_claude_sdk_adapter.py#L98) | `ClaudeSdkAdapterTests.test_context_operations_report_explicit_unsupported_boundary` | `None` | `None` | Transcript operations fail instead of pretending Claude data is empty. |
| [test_codex_app_server_adapter.py](test_codex_app_server_adapter.py#L62) | `FakeCodexTransport.request` | `method: str, params: Mapping[str, object]` | `Mapping[str, object]` | Capture a request and return the configured deterministic result. |
| [test_codex_app_server_adapter.py](test_codex_app_server_adapter.py#L84) | `FakeCodexTransport.notify` | `method: str, params: Mapping[str, object]` | `None` | Capture one notification. |
| [test_codex_app_server_adapter.py](test_codex_app_server_adapter.py#L96) | `FakeCodexTransport.close` | `None` | `None` | Record that the adapter released the fake connection. |
| [test_codex_app_server_adapter.py](test_codex_app_server_adapter.py#L108) | `CodexAppServerAdapterTests.test_health_performs_required_handshake_and_closes_connection` | `None` | `None` | Health sends initialize then initialized without starting a thread. |
| [test_codex_app_server_adapter.py](test_codex_app_server_adapter.py#L125) | `CodexAppServerAdapterTests.test_capabilities_are_hidden_when_handshake_is_unavailable` | `None` | `None` | Unavailable Codex does not advertise inspection capabilities. |
| [test_codex_app_server_adapter.py](test_codex_app_server_adapter.py#L136) | `CodexAppServerAdapterTests.test_discover_sessions_maps_thread_list_without_resuming_threads` | `None` | `None` | Thread summaries map to Hub sessions after the required handshake. |
| [test_codex_app_server_adapter.py](test_codex_app_server_adapter.py#L160) | `CodexAppServerAdapterTests.test_non_stdio_endpoint_is_explicitly_unavailable` | `None` | `None` | The first adapter release does not open experimental remote transports. |
| [test_codex_app_server_adapter.py](test_codex_app_server_adapter.py#L174) | `CodexAppServerAdapterTests.test_read_context_uses_thread_read_without_resuming` | `None` | `None` | Read text items through the documented non-resuming thread endpoint. |
| [test_codex_app_server_adapter.py](test_codex_app_server_adapter.py#L187) | `_definition` | `None` | `ExternalAgentDefinition` | Create the supported local Codex declaration shared by tests. |
| [test_context_package.py](test_context_package.py#L13) | `ContextPackageTests.test_package_decodes_historical_tool_record` | `None` | `None` | Decode a valid package without turning its tool call executable. |
| [test_context_package.py](test_context_package.py#L42) | `ContextPackageTests.test_package_rejects_unknown_or_oversized_message_shape` | `None` | `None` | Reject uncontracted fields instead of forwarding arbitrary JSON. |
| [test_conversation_store.py](test_conversation_store.py#L16) | `ConversationStoreTests.test_pages_legacy_conversation_in_chronological_order` | `None` | `None` | The first page is newest but remains ordered for chat rendering. |
| [test_execution_attempt.py](test_execution_attempt.py#L19) | `ExecutionAttemptTests.test_force_stop_is_journaled_and_reaches_stopped` | `None` | `None` | A forced request is one event before the cooperative worker exits. |
| [test_execution_attempt.py](test_execution_attempt.py#L39) | `ExecutionAttemptTests.test_checkpoint_is_retained_when_execution_reaches_terminal_state` | `None` | `None` | Terminal manifest updates preserve the last journal-committed generation. |
| [test_execution_attempt.py](test_execution_attempt.py#L56) | `ExecutionAttemptTests.test_context_only_checkpoint_does_not_create_a_legacy_graph_file` | `None` | `None` | A non-swarm execution must not touch execution-graph storage. |
| [test_execution_attempt.py](test_execution_attempt.py#L71) | `ExecutionAttemptTests.test_sigint_drain_force_stops_live_attempt_without_signal_handler_io` | `None` | `None` | The signal receiver only marks pending work; drain performs shutdown. |
| [test_execution_attempt.py](test_execution_attempt.py#L85) | `ExecutionAttemptTests.test_host_shutdown_force_stops_live_attempt` | `None` | `None` | An ASGI shutdown hook can persist termination without owning SIGINT. |
| [test_execution_attempt.py](test_execution_attempt.py#L99) | `ExecutionAttemptTests.test_sigint_announces_and_requests_force_stop_before_host_shutdown` | `None` | `None` | SIGINT requests force-stop even when a worker exits immediately. |
| [test_execution_service.py](test_execution_service.py#L22) | `_FailingSwarm.add_hook` | `hook: object` | `None` | Retain a hook supplied by the execution service. |
| [test_execution_service.py](test_execution_service.py#L33) | `_FailingSwarm.remove_hook` | `hook: object` | `bool` | Remove one retained hook. |
| [test_execution_service.py](test_execution_service.py#L47) | `_FailingSwarm.run` | `_message: str, control: object` | `dict[str, object]` | Return the graph's normal non-fatal root failure marker. |
| [test_execution_service.py](test_execution_service.py#L63) | `ExecutionServiceTests.test_root_agent_failure_marks_attempt_failed_and_removes_hook` | `None` | `None` | A coordinator AgentFailure cannot be recorded as completed output. |
| [test_execution_service.py](test_execution_service.py#L83) | `ExecutionServiceTests.test_recovery_starts_a_new_attempt_from_verified_run_graph_checkpoint` | `None` | `None` | Recovery journals its source and never tries to revive old threads. |
| [test_external_agent_hub.py](test_external_agent_hub.py#L28) | `FakeCodexAdapter.kind` | `None` | `str` | Return the protocol kind owned by this fake adapter. |
| [test_external_agent_hub.py](test_external_agent_hub.py#L36) | `FakeCodexAdapter.health` | `definition: ExternalAgentDefinition` | `ExternalAgentHealth` | Return a deterministic healthy projection. |
| [test_external_agent_hub.py](test_external_agent_hub.py#L47) | `FakeCodexAdapter.discover_capabilities` | `definition: ExternalAgentDefinition` | `tuple[ExternalAgentCapability, ...]` | Return one non-executing capability declaration. |
| [test_external_agent_hub.py](test_external_agent_hub.py#L58) | `FakeCodexAdapter.discover_sessions` | `definition: ExternalAgentDefinition, limit: int` | `tuple[ExternalAgentSession, ...]` | Return one bounded remote thread summary. |
| [test_external_agent_hub.py](test_external_agent_hub.py#L97) | `ExternalAgentHubTests.test_store_persists_definitions_and_service_reports_adapter_state` | `None` | `None` | Definitions survive a store reload and use registered adapters. |
| [test_external_agent_hub.py](test_external_agent_hub.py#L118) | `ExternalAgentHubTests.test_unimplemented_adapter_reports_unsupported_without_network_io` | `None` | `None` | Unregistered protocols have explicit non-success health states. |
| [test_external_agent_hub.py](test_external_agent_hub.py#L131) | `ExternalAgentHubTests.test_core_registers_inert_vendor_adapters_without_dispatching_work` | `None` | `None` | Core exposes vendor adapter health without starting a remote run. |
| [test_external_agent_hub.py](test_external_agent_hub.py#L144) | `ExternalAgentHubTests.test_route_functions_project_crud_and_health_without_connector_secrets` | `None` | `None` | Route functions persist metadata and expose no secret field. |
| [test_external_agent_hub.py](test_external_agent_hub.py#L167) | `ExternalAgentHubTests.test_process_discovery_returns_bounded_non_attachable_candidates` | `None` | `None` | Known procfs commands become safe user-confirmed Hub candidates. |
| [test_external_agent_hub.py](test_external_agent_hub.py#L186) | `ExternalAgentHubTests.test_discovery_route_returns_ephemeral_candidate_projections` | `None` | `None` | The discovery route projects candidates without writing Hub state. |
| [test_external_agent_hub_read_only_adapters.py](test_external_agent_hub_read_only_adapters.py#L35) | `FakeReadOnlyFacade.probe` | `definition: ExternalAgentDefinition` | `ExternalAgentProbe` | Return the fixed test probe without performing network I/O. |
| [test_external_agent_hub_read_only_adapters.py](test_external_agent_hub_read_only_adapters.py#L46) | `FakeReadOnlyFacade.discover_sessions` | `definition: ExternalAgentDefinition, limit: int` | `tuple[RemoteSessionSummary, ...]` | Return fixed session data or a controlled transport failure. |
| [test_external_agent_hub_read_only_adapters.py](test_external_agent_hub_read_only_adapters.py#L72) | `ReadOnlyExternalAgentAdapterTests.test_adapters_normalize_their_session_summaries_and_bound_results` | `None` | `None` | Adapters retain remote fields but always bind sessions to the Hub Agent. |
| [test_external_agent_hub_read_only_adapters.py](test_external_agent_hub_read_only_adapters.py#L99) | `ReadOnlyExternalAgentAdapterTests.test_health_is_safe_when_the_injected_transport_is_unavailable` | `None` | `None` | Facade results become unavailable health rather than an adapter crash. |
| [test_external_agent_hub_read_only_adapters.py](test_external_agent_hub_read_only_adapters.py#L111) | `ReadOnlyExternalAgentAdapterTests.test_session_discovery_propagates_safe_transport_errors` | `None` | `None` | A failed discovery is not misreported as a successful empty listing. |
| [test_external_agent_hub_read_only_adapters.py](test_external_agent_hub_read_only_adapters.py#L123) | `ReadOnlyExternalAgentAdapterTests.test_vendor_capabilities_are_declared_without_facade_network_calls` | `None` | `None` | Capability discovery remains deterministic and does not invoke transport. |
| [test_knowledge_tools.py](test_knowledge_tools.py#L16) | `KnowledgeStoreTests.test_upsert_search_read_delete_are_session_local` | `None` | `None` | Implement `KnowledgeStoreTests.test_upsert_search_read_delete_are_session_local`. |
| [test_knowledge_tools.py](test_knowledge_tools.py#L31) | `KnowledgeStoreTests.test_registry_requires_explicit_knowledge_grants` | `None` | `None` | Implement `KnowledgeStoreTests.test_registry_requires_explicit_knowledge_grants`. |
| [test_message_usage_metadata.py](test_message_usage_metadata.py#L22) | `_UsageSwarm.total_usage` | `None` | `dict[str, int]` | Implement `_UsageSwarm.total_usage`. |
| [test_message_usage_metadata.py](test_message_usage_metadata.py#L25) | `_UsageSwarm.agent_usage` | `None` | `dict[str, dict[str, int]]` | Implement `_UsageSwarm.agent_usage`. |
| [test_message_usage_metadata.py](test_message_usage_metadata.py#L32) | `_assistant` | `None` | `LLMOutput` | Return one assistant response with provider-normalised token data. |
| [test_message_usage_metadata.py](test_message_usage_metadata.py#L52) | `MessageUsageMetadataTests.test_sqlite_page_round_trips_usage_and_timing` | `None` | `None` | SQLite payload rows retain per-reply metrics rather than totals. |
| [test_message_usage_metadata.py](test_message_usage_metadata.py#L78) | `MessageUsageMetadataTests.test_legacy_context_without_usage_fields_remains_readable` | `None` | `None` | Old JSON checkpoints get safe empty metadata defaults. |
| [test_message_usage_metadata.py](test_message_usage_metadata.py#L94) | `MessageUsageMetadataTests.test_graph_handler_forwards_usage_metadata_to_its_linear_store` | `None` | `None` | The default graph wrapper must not discard message observability. |
| [test_message_usage_metadata.py](test_message_usage_metadata.py#L115) | `MessageUsageMetadataTests.test_chat_projection_keeps_metadata_across_restart_and_page` | `None` | `None` | History API returns per-message data after Session reconstruction. |
| [test_message_usage_metadata.py](test_message_usage_metadata.py#L142) | `MessageUsageMetadataTests.test_usage_projection_includes_each_agent_not_only_session_total` | `None` | `None` | Usage inspector can distinguish a cache hit made by each Agent. |
| [test_paged_context_storage.py](test_paged_context_storage.py#L19) | `PagedContextStorageTests.test_save_load_and_page_without_full_context` | `None` | `None` | Store 205 entries then restore and page the newest 200 entries. |
| [test_paged_context_storage.py](test_paged_context_storage.py#L47) | `PagedContextStorageTests.test_history_page_includes_compacted_archive_but_agent_load_does_not` | `None` | `None` | Archived rounds remain pageable without becoming active context. |
| [test_plugin_manager.py](test_plugin_manager.py#L17) | `PluginManagerTests.test_theme_pack_registers_settings_and_serves_only_whitelisted_css` | `None` | `None` | A theme pack exposes multiple skins without executable entry code. |
| [test_plugin_manager.py](test_plugin_manager.py#L55) | `PluginManagerTests.test_tool_plugin_registers_only_namespaced_provider_after_explicit_load` | `None` | `None` | A tool plugin executes only at load and publishes host namespaced tools. |
| [test_plugin_manager.py](test_plugin_manager.py#L89) | `PluginManagerTests.test_settings_schema_exposes_user_parameters_to_runtime` | `None` | `None` | Persist declared user parameters and expose them through runtime access. |
| [test_plugin_manager.py](test_plugin_manager.py#L123) | `PluginManagerTests.test_declarative_panel_validates_inputs_and_invokes_registered_action` | `None` | `None` | Render-safe panel declarations dispatch only matching plugin actions. |
| [test_plugin_manager.py](test_plugin_manager.py#L159) | `PluginManagerTests.test_sensitive_panel_field_is_transient_and_settings_remain_secret_free` | `None` | `None` | Allow a password panel field without permitting persisted secrets. |
| [test_plugin_manager.py](test_plugin_manager.py#L192) | `PluginManagerTests.test_gzctf_migration_loads_provider_and_sensitive_login_panel` | `None` | `None` | Load the migrated bundled GZCTF plugin through the v1 runtime. |
| [test_plugin_manager.py](test_plugin_manager.py#L209) | `PluginManagerTests.test_development_packages_are_discovered_and_can_be_loaded` | `None` | `None` | Repository-style development packages remain inert until enabled. |
| [test_plugin_manager.py](test_plugin_manager.py#L239) | `PluginManagerTests.test_repository_plugin_manifests_match_current_contract` | `None` | `None` | Every bundled source plugin is valid and POFP tools can publish. |
| [test_plugin_manager.py](test_plugin_manager.py#L260) | `_json` | `path: Path, value: object` | `None` | Write a test fixture manifest. |
| [test_run_graph_projection.py](test_run_graph_projection.py#L13) | `RunGraphProjectionTests.test_projects_checkpoint_and_journal_into_normalized_states` | `None` | `None` | Implement `RunGraphProjectionTests.test_projects_checkpoint_and_journal_into_normalized_states`. |
| [test_run_graph_projection.py](test_run_graph_projection.py#L48) | `RunGraphProjectionTests.test_live_snapshot_overlays_latest_attempt_without_changing_history_source` | `None` | `None` | Implement `RunGraphProjectionTests.test_live_snapshot_overlays_latest_attempt_without_changing_history_source`. |
| [test_run_graph_projection.py](test_run_graph_projection.py#L64) | `RunGraphProjectionTests.test_recovery_requires_verified_run_graph_checkpoint` | `None` | `None` | Implement `RunGraphProjectionTests.test_recovery_requires_verified_run_graph_checkpoint`. |
| [test_run_graph_projection.py](test_run_graph_projection.py#L97) | `RunGraphProjectionTests.test_events_are_standardized_without_the_raw_journal_envelope` | `None` | `None` | Implement `RunGraphProjectionTests.test_events_are_standardized_without_the_raw_journal_envelope`. |
| [test_session_artifacts.py](test_session_artifacts.py#L16) | `SessionArtifactStoreTests._store` | `root: Path` | `tuple[SessionArtifactStore, SessionExecutor[object]]` | Implement `SessionArtifactStoreTests._store`. |
| [test_session_artifacts.py](test_session_artifacts.py#L24) | `SessionArtifactStoreTests.test_large_result_is_complete_on_disk_and_history_gets_a_reference` | `None` | `None` | Implement `SessionArtifactStoreTests.test_large_result_is_complete_on_disk_and_history_gets_a_reference`. |
| [test_session_artifacts.py](test_session_artifacts.py#L39) | `SessionArtifactStoreTests.test_read_rejects_oversized_range_instead_of_clipping_it` | `None` | `None` | Implement `SessionArtifactStoreTests.test_read_rejects_oversized_range_instead_of_clipping_it`. |
| [test_session_artifacts.py](test_session_artifacts.py#L50) | `SessionArtifactStoreTests.test_ref_cannot_escape_its_session` | `None` | `None` | Implement `SessionArtifactStoreTests.test_ref_cannot_escape_its_session`. |
| [test_session_console.py](test_session_console.py#L19) | `_Journal.append` | `event_type: str, data: dict[str, object], **_kwargs: object` | `None` | Implement `_Journal.append`. |
| [test_session_console.py](test_session_console.py#L34) | `_Swarm.dynamic_add_connection` | `source: str, target: str` | `str` | Implement `_Swarm.dynamic_add_connection`. |
| [test_session_console.py](test_session_console.py#L35) | `_Swarm.dynamic_remove_connection` | `source: str, target: str` | `str` | Implement `_Swarm.dynamic_remove_connection`. |
| [test_session_console.py](test_session_console.py#L36) | `_Swarm.dynamic_set_mapper` | `agent: str, mode: str` | `str` | Implement `_Swarm.dynamic_set_mapper`. |
| [test_session_console.py](test_session_console.py#L37) | `_Swarm.dynamic_set_router` | `agent: str, targets: list[str]` | `str` | Implement `_Swarm.dynamic_set_router`. |
| [test_session_console.py](test_session_console.py#L43) | `_PreviewHandler.prepare_tools` | `_tools: object` | `list[object]` | Return an empty schema list for the isolated preview test. |
| [test_session_console.py](test_session_console.py#L58) | `SessionConsoleTests.test_restart_restores_topology_and_rejects_cycle` | `None` | `None` | The persisted blueprint is recovered without a connector or secret. |
| [test_session_console.py](test_session_console.py#L76) | `SessionConsoleTests.test_worker_removal_cleans_router_targets` | `None` | `None` | Removing a worker leaves no invalid persisted router target behind. |
| [test_session_console.py](test_session_console.py#L89) | `SessionConsoleTests.test_plan_and_dynamic_connection_tools_share_one_state_and_journal` | `None` | `None` | Agent tools persist the plan/topology and append no secret-bearing data. |
| [test_session_console.py](test_session_console.py#L107) | `SessionConsoleTests.test_permissions_omit_disabled_tools_from_agent_registration` | `None` | `None` | A persisted false permission removes its Tool before model exposure. |
| [test_session_console.py](test_session_console.py#L118) | `SessionConsoleTests.test_restart_projects_persisted_agent_context_into_chat_messages` | `None` | `None` | The chat endpoint source survives restart without legacy transcripts. |
| [test_session_console.py](test_session_console.py#L138) | `SessionConsoleTests.test_chat_messages_preserve_per_response_usage_metadata` | `None` | `None` | A saved assistant turn retains its own primary-call observability. |
| [test_session_console.py](test_session_console.py#L172) | `SessionConsoleTests.test_runtime_registry_exposes_and_materializes_project_shell` | `None` | `None` | Shell is both catalog-visible and a real authorized Agent Tool. |
| [test_session_console.py](test_session_console.py#L205) | `SessionConsoleTests.test_steering_projection_rebuilds_recipient_delivery_state` | `None` | `None` | One journaled steering command becomes one durable UI record. |
| [test_session_console.py](test_session_console.py#L234) | `SessionConsoleTests.test_detached_previews_restore_context_without_dispatch_or_writes` | `None` | `None` | Both previews compose from checkpoint state without saving the draft. |
| [test_settings_service.py](test_settings_service.py#L16) | `SettingsServiceTests.test_connector_secret_never_appears_in_public_catalog` | `None` | `None` | Connector metadata is readable while its API key stays separate. |
| [test_settings_service.py](test_settings_service.py#L32) | `SettingsServiceTests.test_session_profile_is_session_owned_and_can_restore_inheritance` | `None` | `None` | A full Session override survives global changes until explicitly cleared. |
| [test_settings_service.py](test_settings_service.py#L55) | `SettingsServiceTests.test_saved_connector_materializes_required_coordinator_before_run` | `None` | `None` | Every Session reserves coordinator and builds it from saved profile state. |
| [test_system_resource_manager.py](test_system_resource_manager.py#L20) | `SystemResourceManagerTests.test_linux_dispatches_to_installed_system_picker` | `None` | `None` | Implement `SystemResourceManagerTests.test_linux_dispatches_to_installed_system_picker`. |
| [test_system_resource_manager.py](test_system_resource_manager.py#L39) | `SystemResourceManagerTests.test_linux_cancel_is_not_an_error` | `None` | `None` | Implement `SystemResourceManagerTests.test_linux_cancel_is_not_an_error`. |
| [test_system_resource_manager.py](test_system_resource_manager.py#L49) | `SystemResourceManagerTests.test_linux_without_system_picker_does_not_fallback_to_web_runtime` | `None` | `None` | Implement `SystemResourceManagerTests.test_linux_without_system_picker_does_not_fallback_to_web_runtime`. |
| [test_system_resource_manager.py](test_system_resource_manager.py#L55) | `SystemResourceManagerTests.test_non_directory_result_is_rejected` | `None` | `None` | Implement `SystemResourceManagerTests.test_non_directory_result_is_rejected`. |
| [test_system_resource_manager.py](test_system_resource_manager.py#L67) | `SystemResourceManagerTests.test_macos_picker_handles_cancel_inside_system_script` | `None` | `None` | Implement `SystemResourceManagerTests.test_macos_picker_handles_cancel_inside_system_script`. |
| [test_system_resource_manager.py](test_system_resource_manager.py#L78) | `SystemResourceManagerTests.test_windows_uses_explorer_shell_com_picker` | `None` | `None` | Implement `SystemResourceManagerTests.test_windows_uses_explorer_shell_com_picker`. |
| [test_tool_result_prompt_budget.py](test_tool_result_prompt_budget.py#L13) | `ToolResultPromptBudgetTests.test_tool_results_are_not_truncated_or_rewritten` | `None` | `None` | Context reconstruction preserves a host-supplied result verbatim. |
| [test_workspace_service.py](test_workspace_service.py#L16) | `WorkspaceServiceTests.test_create_is_durable_and_core_rehydrates_empty_session` | `None` | `None` | A subsequent host sees the workspace and can address its session. |
| [test_workspace_service.py](test_workspace_service.py#L31) | `WorkspaceServiceTests.test_legacy_session_index_is_imported_without_inventing_project_paths` | `None` | `None` | Old session identities remain selectable after the storage redesign. |
| [test_workspace_service.py](test_workspace_service.py#L60) | `WorkspaceServiceTests.test_delete_removes_session_registry_and_durable_state` | `None` | `None` | A confirmed deletion cannot be rehydrated by a later core instance. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [test_agent_control.py](test_agent_control.py#L10) | `AgentControlTests` | `None` | `unittest.TestCase` | Verify scope isolation while preserving Session-wide cancellation. |
| [test_agent_defaults.py](test_agent_defaults.py#L13) | `AgentDefaultTests` | `None` | `unittest.TestCase` | Ensure product defaults reach llmfetcher instead of remaining UI-only. |
| [test_capability_migrations.py](test_capability_migrations.py#L19) | `CapabilityMigrationTests` | `None` | `unittest.TestCase` | Provide `CapabilityMigrationTests` behavior. |
| [test_claude_sdk_adapter.py](test_claude_sdk_adapter.py#L19) | `FakeClaudeDiscovery` | `ready: bool, records: tuple[ClaudeSdkSessionRecord, ...]` | `object` | Injected Claude facade that records read-only discovery calls. |
| [test_claude_sdk_adapter.py](test_claude_sdk_adapter.py#L50) | `ClaudeSdkAdapterTests` | `None` | `unittest.TestCase` | Verify Claude SDK adapter availability and non-executing discovery. |
| [test_codex_app_server_adapter.py](test_codex_app_server_adapter.py#L18) | `RecordedRequest` | `method: str, params: Mapping[str, object]` | `object` | One JSON-RPC request captured by the deterministic test transport. |
| [test_codex_app_server_adapter.py](test_codex_app_server_adapter.py#L31) | `RecordedNotification` | `method: str, params: Mapping[str, object]` | `object` | One JSON-RPC notification captured by the deterministic transport. |
| [test_codex_app_server_adapter.py](test_codex_app_server_adapter.py#L44) | `FakeCodexTransport` | `thread_result: Mapping[str, object], thread_read_result: Mapping[str, object], fail_initialize: bool, requests: list[RecordedRequest], notifications: list[RecordedNotification], closed: bool` | `CodexAppServerTransport` | In-memory App Server transport which never starts a process. |
| [test_codex_app_server_adapter.py](test_codex_app_server_adapter.py#L105) | `CodexAppServerAdapterTests` | `None` | `unittest.TestCase` | Verify the fixed App Server inspection exchange without a Codex binary. |
| [test_context_package.py](test_context_package.py#L10) | `ContextPackageTests` | `None` | `unittest.TestCase` | Verify context exchange input stays bounded and non-executable. |
| [test_conversation_store.py](test_conversation_store.py#L13) | `ConversationStoreTests` | `None` | `unittest.TestCase` | Ensure session selection can recover its historical messages. |
| [test_execution_attempt.py](test_execution_attempt.py#L16) | `ExecutionAttemptTests` | `None` | `unittest.TestCase` | Verify one controller, journal, and committed checkpoint generation. |
| [test_execution_service.py](test_execution_service.py#L15) | `_FailingSwarm` | `None` | `object` | Minimal graph facade that reports an unsuccessful root Agent. |
| [test_execution_service.py](test_execution_service.py#L60) | `ExecutionServiceTests` | `None` | `unittest.TestCase` | Ensure graph-level root failures become terminal attempt failures. |
| [test_external_agent_hub.py](test_external_agent_hub.py#L24) | `FakeCodexAdapter` | `None` | `object` | Deterministic adapter used to verify the Hub base contract. |
| [test_external_agent_hub.py](test_external_agent_hub.py#L74) | `CoreState` | `angelus_core: AngelusCore` | `object` | Minimal FastAPI-like state object for direct route contract tests. |
| [test_external_agent_hub.py](test_external_agent_hub.py#L81) | `ApplicationContext` | `state: CoreState` | `object` | Minimal application object exposing the route's required state field. |
| [test_external_agent_hub.py](test_external_agent_hub.py#L88) | `RequestContext` | `app: ApplicationContext` | `object` | Minimal request object exposing the route's required app property. |
| [test_external_agent_hub.py](test_external_agent_hub.py#L94) | `ExternalAgentHubTests` | `None` | `unittest.TestCase` | Assert persistence, adapter isolation, and HTTP response boundaries. |
| [test_external_agent_hub_read_only_adapters.py](test_external_agent_hub_read_only_adapters.py#L20) | `FakeReadOnlyFacade` | `probe_result: ExternalAgentProbe, session_records: tuple[RemoteSessionSummary, ...], fail_sessions: bool, requested_limits: list[int]` | `object` | Deterministic injected transport implementation for adapter tests. |
| [test_external_agent_hub_read_only_adapters.py](test_external_agent_hub_read_only_adapters.py#L69) | `ReadOnlyExternalAgentAdapterTests` | `None` | `unittest.TestCase` | Assert typed facade boundaries and session normalization for adapters. |
| [test_knowledge_tools.py](test_knowledge_tools.py#L13) | `KnowledgeStoreTests` | `None` | `unittest.TestCase` | Verify durable retrieval stays outside Agent context and task state. |
| [test_message_usage_metadata.py](test_message_usage_metadata.py#L14) | `_NoopCompactor` | `None` | `object` | Offline placeholder; these tests deliberately never compact. |
| [test_message_usage_metadata.py](test_message_usage_metadata.py#L19) | `_UsageSwarm` | `None` | `object` | Minimal aggregate exposing distinct Coordinator/Worker accounting. |
| [test_message_usage_metadata.py](test_message_usage_metadata.py#L49) | `MessageUsageMetadataTests` | `None` | `unittest.TestCase` | Ensure message detail cards survive checkpoint, paging, and restart. |
| [test_paged_context_storage.py](test_paged_context_storage.py#L12) | `_NoopCompactor` | `None` | `object` | Minimal compactor placeholder because this test does not compact. |
| [test_paged_context_storage.py](test_paged_context_storage.py#L16) | `PagedContextStorageTests` | `None` | `unittest.TestCase` | Verify the durable reader returns bounded newest-first windows. |
| [test_plugin_manager.py](test_plugin_manager.py#L14) | `PluginManagerTests` | `None` | `unittest.TestCase` | Assert discovery never executes code and loaded packages stay bounded. |
| [test_run_graph_projection.py](test_run_graph_projection.py#L12) | `RunGraphProjectionTests` | `None` | `unittest.TestCase` | Provide `RunGraphProjectionTests` behavior. |
| [test_session_artifacts.py](test_session_artifacts.py#L13) | `SessionArtifactStoreTests` | `None` | `unittest.TestCase` | Ensure artifact refs replace long history without dropping evidence. |
| [test_session_console.py](test_session_console.py#L16) | `_Journal` | `None` | `object` | Capture secret-free console events emitted by a test tool call. |
| [test_session_console.py](test_session_console.py#L22) | `_Attempt` | `None` | `object` | Minimal attempt façade exposing the journal used by console tools. |
| [test_session_console.py](test_session_console.py#L27) | `_Execution` | `None` | `object` | Minimal execution façade retaining the current attempt. |
| [test_session_console.py](test_session_console.py#L32) | `_Swarm` | `None` | `object` | Minimal dynamic swarm façade used to verify direct dynamic calls. |
| [test_session_console.py](test_session_console.py#L40) | `_PreviewHandler` | `None` | `object` | Minimal provider facade proving request composition performs no I/O. |
| [test_session_console.py](test_session_console.py#L55) | `SessionConsoleTests` | `None` | `unittest.TestCase` | Verify state recovery, validation, and Agent-owned mutation writes. |
| [test_settings_service.py](test_settings_service.py#L13) | `SettingsServiceTests` | `None` | `unittest.TestCase` | Verify the new settings path has one durable authority per concern. |
| [test_system_resource_manager.py](test_system_resource_manager.py#L17) | `SystemResourceManagerTests` | `None` | `unittest.TestCase` | Keep folder selection out of browser and Tauri runtimes. |
| [test_tool_result_prompt_budget.py](test_tool_result_prompt_budget.py#L10) | `ToolResultPromptBudgetTests` | `None` | `unittest.TestCase` | Ensure historical tool output remains cache-stable across rounds. |
| [test_workspace_service.py](test_workspace_service.py#L13) | `WorkspaceServiceTests` | `None` | `unittest.TestCase` | Ensure durable workspace records do not create a second session owner. |

<!-- END GENERATED SYMBOL MAP -->
