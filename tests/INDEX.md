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
| `test_image_attachments.py` | Image store decode/MIME/dimension/animation bounds, symlink-safe confined import, content-integrity and Session HTTP upload/download isolation. |
| `test_image_tool_provider.py` | `view_image` authorization/roles, native `ImageToolResult` reference, confined project import and byte isolation. |
| `test_native_vision_payload.py` | End-to-end native vision payload: real Session attachment store resolver drives real OpenAI/Anthropic handlers into a fake SDK transport, proving wire bytes exist only at dispatch and request snapshots/text-only turns stay byte-free. |
| `test_plugin_manager.py` | Strict plugin manifest discovery, settings/theme lifecycle, namespaced POFP/GZCTF tool publication, and declarative transient-panel action dispatch. |

Run from repository root:

```bash
python -m pytest tests -v          # canonical CI runner (unittest- and pytest-style)
python -m unittest discover -s tests
node --check frontend/static/app.js
```

> 测试约定：`tests/` 同时接受 unittest 风格（`unittest.TestCase`，被 `unittest discover` 与
> `pytest` 共同收集）与 pytest 风格（模块级 `def test_*` + fixture）。注意 **pytest 风格文件
> 不会被 `unittest discover` 收集**，因此 CI 以 `python -m pytest tests -v` 为准；若只跑
> `unittest discover` 会出现静默漏测。新增测试优先使用 `unittest.TestCase`，以便两种入口都能执行。

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
| [test_execution_service.py](test_execution_service.py#L32) | `_FailingSwarm.add_hook` | `hook: object` | `None` | Retain a hook supplied by the execution service. |
| [test_execution_service.py](test_execution_service.py#L43) | `_FailingSwarm.remove_hook` | `hook: object` | `bool` | Remove one retained hook. |
| [test_execution_service.py](test_execution_service.py#L57) | `_FailingSwarm.run` | `_message: str, control: object` | `dict[str, object]` | Return the graph's normal non-fatal root failure marker. |
| [test_execution_service.py](test_execution_service.py#L73) | `ExecutionServiceTests.test_root_agent_failure_marks_attempt_failed_and_removes_hook` | `None` | `None` | A coordinator AgentFailure cannot be recorded as completed output. |
| [test_execution_service.py](test_execution_service.py#L93) | `ExecutionServiceTests.test_recovery_starts_a_new_attempt_from_verified_run_graph_checkpoint` | `None` | `None` | Recovery journals its source and never tries to revive old threads. |
| [test_execution_service.py](test_execution_service.py#L147) | `_RecordingSwarm.add_hook` | `hook: object` | `None` | Retain a hook supplied by the execution service. |
| [test_execution_service.py](test_execution_service.py#L158) | `_RecordingSwarm.remove_hook` | `hook: object` | `bool` | Remove one retained hook. |
| [test_execution_service.py](test_execution_service.py#L172) | `_RecordingSwarm.view_snapshot` | `None` | `dict[str, object]` | Return a minimal live topology for control pre-registration. |
| [test_execution_service.py](test_execution_service.py#L180) | `_RecordingSwarm.run` | `message: object, control: object` | `dict[str, object]` | Record the exact initial input handed to the graph. |
| [test_execution_service.py](test_execution_service.py#L197) | `_PreviewHandler.prepare_tools` | `_tools: object` | `list[object]` | Return an empty schema list for the isolated preview test. |
| [test_execution_service.py](test_execution_service.py#L209) | `_png` | `None` | `bytes` | Return one small valid PNG payload. |
| [test_execution_service.py](test_execution_service.py#L223) | `ExecutionImageWiringTests._session` | `directory: str` | `tuple[AngelusCore, object]` | Create a runnable-shaped Session without building a real coordinator. |
| [test_execution_service.py](test_execution_service.py#L241) | `ExecutionImageWiringTests.test_start_validates_store_refs_and_passes_user_message` | `None` | `None` | Validated references reach the swarm as one UserMessage, not a dict. |
| [test_execution_service.py](test_execution_service.py#L272) | `ExecutionImageWiringTests.test_image_only_turn_is_accepted_and_blank_text_is_rejected` | `None` | `None` | An image-only turn runs; blank text without images stays invalid. |
| [test_execution_service.py](test_execution_service.py#L291) | `ExecutionImageWiringTests.test_start_rejects_refs_outside_the_session_store` | `None` | `None` | Unknown, mismatched, and over-budget references fail before dispatch. |
| [test_execution_service.py](test_execution_service.py#L315) | `ExecutionImageWiringTests.test_coordinator_fetcher_resolves_session_attachment` | `None` | `None` | The real Agent factory binds the Session store as its image resolver. |
| [test_execution_service.py](test_execution_service.py#L352) | `ControlImageRejectionTests.test_image_steering_is_rejected_before_execution_lookup` | `None` | `None` | A non-empty images field returns 422 even with no live execution. |
| [test_execution_service.py](test_execution_service.py#L396) | `_BlockingSwarm.add_hook` | `hook: object` | `None` | Retain the attempt journal hook supplied by the service. |
| [test_execution_service.py](test_execution_service.py#L407) | `_BlockingSwarm.remove_hook` | `hook: object` | `bool` | Remove one retained hook. |
| [test_execution_service.py](test_execution_service.py#L421) | `_BlockingSwarm.view_snapshot` | `None` | `dict[str, object]` | Return a minimal live topology for control pre-registration. |
| [test_execution_service.py](test_execution_service.py#L429) | `_BlockingSwarm.run` | `_message: object, control: object` | `dict[str, object]` | Signal entry and block until the test releases the attempt. |
| [test_execution_service.py](test_execution_service.py#L447) | `RuntimeAgentDirtyTests._session` | `directory: str` | `tuple[AngelusCore, object]` | Create a runnable-shaped Session without building a real coordinator. |
| [test_execution_service.py](test_execution_service.py#L465) | `RuntimeAgentDirtyTests.test_graceful_stop_keeps_runtime_agents_reusable` | `None` | `None` | A graceful stop leaves the cached coordinator valid for reuse. |
| [test_execution_service.py](test_execution_service.py#L474) | `RuntimeAgentDirtyTests.test_forced_stop_marks_runtime_agents_dirty` | `None` | `None` | A forced stop invalidates cached Agents so clients are rebuilt. |
| [test_execution_service.py](test_execution_service.py#L483) | `RuntimeAgentDirtyTests.test_control_marks_runtime_agents_dirty_only_when_forced` | `None` | `None` | Browser control invalidates Agents only for ``force_stop``. |
| [test_execution_service.py](test_execution_service.py#L507) | `RuntimeAgentDirtyTests.test_ensure_coordinator_rebuilds_dirty_agents_for_same_profile` | `None` | `None` | A dirty flag defeats an unchanged fingerprint and resets on rebuild. |
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
| [test_image_attachments.py](test_image_attachments.py#L20) | `image_bytes` | `fmt: Any, size: Any` | `Any` | Implement `image_bytes`. |
| [test_image_attachments.py](test_image_attachments.py#L27) | `ImageAttachmentStoreTests.setUp` | `None` | `Any` | Implement `ImageAttachmentStoreTests.setUp`. |
| [test_image_attachments.py](test_image_attachments.py#L30) | `ImageAttachmentStoreTests.tearDown` | `None` | `Any` | Implement `ImageAttachmentStoreTests.tearDown`. |
| [test_image_attachments.py](test_image_attachments.py#L33) | `ImageAttachmentStoreTests.test_actual_format_persisted_and_resolved` | `None` | `Any` | Implement `ImageAttachmentStoreTests.test_actual_format_persisted_and_resolved`. |
| [test_image_attachments.py](test_image_attachments.py#L54) | `ImageAttachmentStoreTests.test_rejects_invalid_oversized_animated_and_unsupported` | `None` | `Any` | Implement `ImageAttachmentStoreTests.test_rejects_invalid_oversized_animated_and_unsupported`. |
| [test_image_attachments.py](test_image_attachments.py#L74) | `ImageAttachmentStoreTests.test_confinement_symlinks_integrity_and_count` | `None` | `Any` | Implement `ImageAttachmentStoreTests.test_confinement_symlinks_integrity_and_count`. |
| [test_image_attachments.py](test_image_attachments.py#L104) | `ImageAttachmentStoreTests.test_http_upload_download_bounds_and_session_isolation` | `None` | `Any` | Implement `ImageAttachmentStoreTests.test_http_upload_download_bounds_and_session_isolation`. |
| [test_image_tool_provider.py](test_image_tool_provider.py#L23) | `image_bytes` | `fmt: Any, size: Any` | `Any` | Implement `image_bytes`. |
| [test_image_tool_provider.py](test_image_tool_provider.py#L29) | `build` | `tmp_path: Any, project_path: Any` | `Any` | Implement `build`. |
| [test_image_tool_provider.py](test_image_tool_provider.py#L44) | `ImageToolProviderTests.setUp` | `None` | `Any` | Implement `ImageToolProviderTests.setUp`. |
| [test_image_tool_provider.py](test_image_tool_provider.py#L47) | `ImageToolProviderTests.tearDown` | `None` | `Any` | Implement `ImageToolProviderTests.tearDown`. |
| [test_image_tool_provider.py](test_image_tool_provider.py#L50) | `ImageToolProviderTests.test_materialize_requires_grant_and_authorized_role` | `None` | `Any` | Implement `ImageToolProviderTests.test_materialize_requires_grant_and_authorized_role`. |
| [test_image_tool_provider.py](test_image_tool_provider.py#L60) | `ImageToolProviderTests.test_materialize_requires_session_storage` | `None` | `Any` | Implement `ImageToolProviderTests.test_materialize_requires_session_storage`. |
| [test_image_tool_provider.py](test_image_tool_provider.py#L68) | `ImageToolProviderTests.test_view_image_by_attachment_id_returns_native_reference` | `None` | `Any` | Implement `ImageToolProviderTests.test_view_image_by_attachment_id_returns_native_reference`. |
| [test_image_tool_provider.py](test_image_tool_provider.py#L84) | `ImageToolProviderTests.test_view_image_imports_confined_project_file` | `None` | `Any` | Implement `ImageToolProviderTests.test_view_image_imports_confined_project_file`. |
| [test_image_tool_provider.py](test_image_tool_provider.py#L100) | `ImageToolProviderTests.test_view_image_requires_exactly_one_source` | `None` | `Any` | Implement `ImageToolProviderTests.test_view_image_requires_exactly_one_source`. |
| [test_image_tool_provider.py](test_image_tool_provider.py#L109) | `ImageToolProviderTests.test_view_image_requires_project_for_path` | `None` | `Any` | Implement `ImageToolProviderTests.test_view_image_requires_project_for_path`. |
| [test_image_tool_provider.py](test_image_tool_provider.py#L115) | `ImageToolProviderTests.test_registration_contract_exposes_vision_tool` | `None` | `Any` | Implement `ImageToolProviderTests.test_registration_contract_exposes_vision_tool`. |
| [test_knowledge_tools.py](test_knowledge_tools.py#L16) | `KnowledgeStoreTests.test_upsert_search_read_delete_are_session_local` | `None` | `None` | Implement `KnowledgeStoreTests.test_upsert_search_read_delete_are_session_local`. |
| [test_knowledge_tools.py](test_knowledge_tools.py#L31) | `KnowledgeStoreTests.test_registry_requires_explicit_knowledge_grants` | `None` | `None` | Implement `KnowledgeStoreTests.test_registry_requires_explicit_knowledge_grants`. |
| [test_llm_timeout_retry.py](test_llm_timeout_retry.py#L16) | `_Handler.prepare_tools` | `tools: object` | `object` | Implement `_Handler.prepare_tools`. |
| [test_llm_timeout_retry.py](test_llm_timeout_retry.py#L19) | `_Handler.create_completion` | `**_kwargs: object` | `object` | Implement `_Handler.create_completion`. |
| [test_llm_timeout_retry.py](test_llm_timeout_retry.py#L25) | `_Handler.normalize_completion_response` | `_raw: object` | `LLMOutput` | Implement `_Handler.normalize_completion_response`. |
| [test_llm_timeout_retry.py](test_llm_timeout_retry.py#L28) | `_Handler.abort_active_request` | `None` | `int` | Implement `_Handler.abort_active_request`. |
| [test_llm_timeout_retry.py](test_llm_timeout_retry.py#L37) | `_StreamingHandler.create_completion` | `**_kwargs: object` | `object` | Implement `_StreamingHandler.create_completion`. |
| [test_llm_timeout_retry.py](test_llm_timeout_retry.py#L41) | `_StreamingHandler.iter_stream_text` | `_raw: object, **_kwargs: object` | `Any` | Implement `_StreamingHandler.iter_stream_text`. |
| [test_llm_timeout_retry.py](test_llm_timeout_retry.py#L49) | `_fetcher` | `handler: _Handler, retries: int` | `LLMFetcher` | Implement `_fetcher`. |
| [test_llm_timeout_retry.py](test_llm_timeout_retry.py#L61) | `TimeoutRetryTests.test_timed_out_wording_uses_configured_retry_budget` | `None` | `None` | Implement `TimeoutRetryTests.test_timed_out_wording_uses_configured_retry_budget`. |
| [test_llm_timeout_retry.py](test_llm_timeout_retry.py#L71) | `TimeoutRetryTests.test_timeout_in_causal_chain_is_retryable` | `None` | `None` | Implement `TimeoutRetryTests.test_timeout_in_causal_chain_is_retryable`. |
| [test_llm_timeout_retry.py](test_llm_timeout_retry.py#L81) | `TimeoutRetryTests.test_ordinary_provider_failure_is_not_retried` | `None` | `None` | Implement `TimeoutRetryTests.test_ordinary_provider_failure_is_not_retried`. |
| [test_llm_timeout_retry.py](test_llm_timeout_retry.py#L89) | `TimeoutRetryTests.test_stream_retries_only_before_first_delta` | `None` | `None` | Implement `TimeoutRetryTests.test_stream_retries_only_before_first_delta`. |
| [test_message_usage_metadata.py](test_message_usage_metadata.py#L22) | `_UsageSwarm.total_usage` | `None` | `dict[str, int]` | Implement `_UsageSwarm.total_usage`. |
| [test_message_usage_metadata.py](test_message_usage_metadata.py#L25) | `_UsageSwarm.agent_usage` | `None` | `dict[str, dict[str, int]]` | Implement `_UsageSwarm.agent_usage`. |
| [test_message_usage_metadata.py](test_message_usage_metadata.py#L32) | `_assistant` | `None` | `LLMOutput` | Return one assistant response with provider-normalised token data. |
| [test_message_usage_metadata.py](test_message_usage_metadata.py#L52) | `MessageUsageMetadataTests.test_sqlite_page_round_trips_usage_and_timing` | `None` | `None` | SQLite payload rows retain per-reply metrics rather than totals. |
| [test_message_usage_metadata.py](test_message_usage_metadata.py#L78) | `MessageUsageMetadataTests.test_legacy_context_without_usage_fields_remains_readable` | `None` | `None` | Old JSON checkpoints get safe empty metadata defaults. |
| [test_message_usage_metadata.py](test_message_usage_metadata.py#L94) | `MessageUsageMetadataTests.test_graph_handler_forwards_usage_metadata_to_its_linear_store` | `None` | `None` | The default graph wrapper must not discard message observability. |
| [test_message_usage_metadata.py](test_message_usage_metadata.py#L115) | `MessageUsageMetadataTests.test_chat_projection_keeps_metadata_across_restart_and_page` | `None` | `None` | History API returns per-message data after Session reconstruction. |
| [test_message_usage_metadata.py](test_message_usage_metadata.py#L142) | `MessageUsageMetadataTests.test_usage_projection_includes_each_agent_not_only_session_total` | `None` | `None` | Usage inspector can distinguish a cache hit made by each Agent. |
| [test_native_vision_payload.py](test_native_vision_payload.py#L27) | `_png` | `None` | `bytes` | Return one small valid PNG payload. |
| [test_native_vision_payload.py](test_native_vision_payload.py#L41) | `NativeVisionPayloadTests._session` | `directory: str` | `tuple[AngelusCore, object]` | Create a Session owning a real attachment store. |
| [test_native_vision_payload.py](test_native_vision_payload.py#L56) | `NativeVisionPayloadTests._handler` | `provider: str, resolver: Any` | `Any` | Build a real provider handler with a fake SDK client. |
| [test_native_vision_payload.py](test_native_vision_payload.py#L72) | `NativeVisionPayloadTests._messages` | `metadata: dict, text: str` | `tuple[list, dict]` | Assemble one user turn referencing an already-stored attachment. |
| [test_native_vision_payload.py](test_native_vision_payload.py#L87) | `NativeVisionPayloadTests.test_openai_wire_carries_durable_bytes` | `None` | `None` | OpenAI receives a base64 data URL built from the stored bytes. |
| [test_native_vision_payload.py](test_native_vision_payload.py#L111) | `NativeVisionPayloadTests.test_anthropic_wire_carries_durable_bytes` | `None` | `None` | Anthropic receives a native base64 image source block. |
| [test_native_vision_payload.py](test_native_vision_payload.py#L131) | `NativeVisionPayloadTests.test_request_snapshot_stays_byte_free` | `None` | `None` | The prepared request snapshot keeps references and never bytes. |
| [test_native_vision_payload.py](test_native_vision_payload.py#L149) | `NativeVisionPayloadTests.test_text_only_turn_never_resolves_bytes` | `None` | `None` | A text-only turn keeps a plain string content and calls no resolver. |
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
| [test_run_graph_projection.py](test_run_graph_projection.py#L15) | `RunGraphProjectionTests.test_projects_checkpoint_and_journal_into_normalized_states` | `None` | `None` | Implement `RunGraphProjectionTests.test_projects_checkpoint_and_journal_into_normalized_states`. |
| [test_run_graph_projection.py](test_run_graph_projection.py#L50) | `RunGraphProjectionTests.test_live_snapshot_overlays_latest_attempt_without_changing_history_source` | `None` | `None` | Implement `RunGraphProjectionTests.test_live_snapshot_overlays_latest_attempt_without_changing_history_source`. |
| [test_run_graph_projection.py](test_run_graph_projection.py#L66) | `RunGraphProjectionTests.test_recovery_requires_verified_run_graph_checkpoint` | `None` | `None` | Implement `RunGraphProjectionTests.test_recovery_requires_verified_run_graph_checkpoint`. |
| [test_run_graph_projection.py](test_run_graph_projection.py#L99) | `RunGraphProjectionTests.test_events_are_standardized_without_the_raw_journal_envelope` | `None` | `None` | Implement `RunGraphProjectionTests.test_events_are_standardized_without_the_raw_journal_envelope`. |
| [test_run_graph_projection.py](test_run_graph_projection.py#L128) | `RunGraphCheckpointReplayTests._write_attempt` | `root: Path, events: list[dict[str, object]], checkpoint: dict[str, object] \| None, execution_id: str` | `Path` | Implement `RunGraphCheckpointReplayTests._write_attempt`. |
| [test_run_graph_projection.py](test_run_graph_projection.py#L143) | `RunGraphCheckpointReplayTests._reference` | `events: list[dict[str, object]], execution_id: str` | `dict[str, object]` | Implement `RunGraphCheckpointReplayTests._reference`. |
| [test_run_graph_projection.py](test_run_graph_projection.py#L150) | `RunGraphCheckpointReplayTests._facts` | `None` | `list[dict[str, object]]` | Implement `RunGraphCheckpointReplayTests._facts`. |
| [test_run_graph_projection.py](test_run_graph_projection.py#L162) | `RunGraphCheckpointReplayTests.test_project_resumes_tail_from_cursor_without_skipping_interleaved_facts` | `None` | `None` | Implement `RunGraphCheckpointReplayTests.test_project_resumes_tail_from_cursor_without_skipping_interleaved_facts`. |
| [test_run_graph_projection.py](test_run_graph_projection.py#L177) | `RunGraphCheckpointReplayTests.test_events_replays_from_start_when_cursor_precedes_checkpoint` | `None` | `None` | Implement `RunGraphCheckpointReplayTests.test_events_replays_from_start_when_cursor_precedes_checkpoint`. |
| [test_run_graph_projection.py](test_run_graph_projection.py#L193) | `RunGraphCheckpointReplayTests.test_journal_reader_skips_checkpointed_prefix_without_parsing` | `None` | `None` | Implement `RunGraphCheckpointReplayTests.test_journal_reader_skips_checkpointed_prefix_without_parsing`. |
| [test_session_artifacts.py](test_session_artifacts.py#L16) | `SessionArtifactStoreTests._store` | `root: Path` | `tuple[SessionArtifactStore, SessionExecutor[object]]` | Implement `SessionArtifactStoreTests._store`. |
| [test_session_artifacts.py](test_session_artifacts.py#L24) | `SessionArtifactStoreTests.test_large_result_is_complete_on_disk_and_history_gets_a_reference` | `None` | `None` | Implement `SessionArtifactStoreTests.test_large_result_is_complete_on_disk_and_history_gets_a_reference`. |
| [test_session_artifacts.py](test_session_artifacts.py#L39) | `SessionArtifactStoreTests.test_read_rejects_oversized_range_instead_of_clipping_it` | `None` | `None` | Implement `SessionArtifactStoreTests.test_read_rejects_oversized_range_instead_of_clipping_it`. |
| [test_session_artifacts.py](test_session_artifacts.py#L50) | `SessionArtifactStoreTests.test_ref_cannot_escape_its_session` | `None` | `None` | Implement `SessionArtifactStoreTests.test_ref_cannot_escape_its_session`. |
| [test_session_console.py](test_session_console.py#L33) | `_Journal.append` | `event_type: str, data: dict[str, object], **_kwargs: object` | `None` | Implement `_Journal.append`. |
| [test_session_console.py](test_session_console.py#L48) | `_Swarm.dynamic_add_connection` | `source: str, target: str` | `str` | Implement `_Swarm.dynamic_add_connection`. |
| [test_session_console.py](test_session_console.py#L49) | `_Swarm.dynamic_remove_connection` | `source: str, target: str` | `str` | Implement `_Swarm.dynamic_remove_connection`. |
| [test_session_console.py](test_session_console.py#L50) | `_Swarm.dynamic_set_mapper` | `agent: str, mode: str` | `str` | Implement `_Swarm.dynamic_set_mapper`. |
| [test_session_console.py](test_session_console.py#L51) | `_Swarm.dynamic_set_router` | `agent: str, targets: list[str]` | `str` | Implement `_Swarm.dynamic_set_router`. |
| [test_session_console.py](test_session_console.py#L57) | `_PreviewHandler.prepare_tools` | `_tools: object` | `list[object]` | Return an empty schema list for the isolated preview test. |
| [test_session_console.py](test_session_console.py#L72) | `SessionConsoleTests.test_restart_restores_topology_and_rejects_cycle` | `None` | `None` | The persisted blueprint is recovered without a connector or secret. |
| [test_session_console.py](test_session_console.py#L90) | `SessionConsoleTests.test_worker_removal_cleans_router_targets` | `None` | `None` | Removing a worker leaves no invalid persisted router target behind. |
| [test_session_console.py](test_session_console.py#L103) | `SessionConsoleTests.test_plan_and_dynamic_connection_tools_share_one_state_and_journal` | `None` | `None` | Agent tools persist the plan/topology and append no secret-bearing data. |
| [test_session_console.py](test_session_console.py#L121) | `SessionConsoleTests.test_permissions_omit_disabled_tools_from_agent_registration` | `None` | `None` | A persisted false permission removes its Tool before model exposure. |
| [test_session_console.py](test_session_console.py#L132) | `SessionConsoleTests.test_restart_projects_persisted_agent_context_into_chat_messages` | `None` | `None` | The chat endpoint source survives restart without legacy transcripts. |
| [test_session_console.py](test_session_console.py#L152) | `SessionConsoleTests.test_chat_messages_preserve_per_response_usage_metadata` | `None` | `None` | A saved assistant turn retains its own primary-call observability. |
| [test_session_console.py](test_session_console.py#L186) | `SessionConsoleTests.test_chat_messages_project_full_tool_payloads` | `None` | `None` | The chat view restores each tool call's full arguments and result. |
| [test_session_console.py](test_session_console.py#L226) | `SessionConsoleTests.test_runtime_registry_exposes_and_materializes_project_shell` | `None` | `None` | Shell is both catalog-visible and a real authorized Agent Tool. |
| [test_session_console.py](test_session_console.py#L259) | `SessionConsoleTests.test_steering_projection_rebuilds_recipient_delivery_state` | `None` | `None` | One journaled steering command becomes one durable UI record. |
| [test_session_console.py](test_session_console.py#L288) | `SessionConsoleTests.test_detached_previews_restore_context_without_dispatch_or_writes` | `None` | `None` | Both previews compose from checkpoint state without saving the draft. |
| [test_session_console.py](test_session_console.py#L327) | `_first_stream_chunk` | `response: object` | `str` | Return only the first SSE chunk so a running stream can be inspected. |
| [test_session_console.py](test_session_console.py#L348) | `GraphEventStreamTests._core_with_completed_attempt` | `root: Path` | `AngelusCore` | Build one Session whose terminal attempt has durable journal facts. |
| [test_session_console.py](test_session_console.py#L361) | `GraphEventStreamTests.test_graph_events_sse_frames_use_real_newlines` | `None` | `None` | Raw HTTP bytes are id/data frames separated by real blank lines. |
| [test_session_console.py](test_session_console.py#L384) | `GraphEventStreamTests.test_keep_alive_frame_uses_real_newlines_while_running` | `None` | `None` | An idle poll while the attempt runs emits a real newline keep-alive. |
| [test_session_console.py](test_session_console.py#L433) | `JournalProjectionCacheTests._service` | `root: Path` | `tuple[ConsoleProjectionService, ExecutionJournal]` | Implement `JournalProjectionCacheTests._service`. |
| [test_session_console.py](test_session_console.py#L438) | `JournalProjectionCacheTests.test_steering_projection_reads_only_appended_journal_bytes` | `None` | `None` | Implement `JournalProjectionCacheTests.test_steering_projection_reads_only_appended_journal_bytes`. |
| [test_session_console.py](test_session_console.py#L466) | `JournalProjectionCacheTests.test_steering_cache_discards_prefix_when_journal_shrinks` | `None` | `None` | Implement `JournalProjectionCacheTests.test_steering_cache_discards_prefix_when_journal_shrinks`. |
| [test_session_console.py](test_session_console.py#L484) | `JournalProjectionCacheTests.test_events_page_streams_from_cursor_with_bounded_lookahead` | `None` | `None` | Implement `JournalProjectionCacheTests.test_events_page_streams_from_cursor_with_bounded_lookahead`. |
| [test_session_console.py](test_session_console.py#L514) | `JournalProjectionCacheTests.test_events_strip_legacy_remote_request_bodies` | `None` | `None` | A legacy journal body is reduced to its content-free index on read. |
| [test_session_console.py](test_session_console.py#L548) | `JournalProjectionCacheTests.test_events_leave_non_request_events_intact` | `None` | `None` | Sanitizing remote requests must not rewrite other journal facts. |
| [test_session_console.py](test_session_console.py#L556) | `JournalProjectionCacheTests.test_events_classify_plan_and_graph_sources_for_frontend_reloads` | `None` | `None` | Plan mutations must carry source=="plan" so the panel auto-reloads. |
| [test_session_console.py](test_session_console.py#L581) | `JournalProjectionCacheTests.test_events_reduce_llm_request_to_a_content_free_index` | `None` | `None` | A live llm_request keeps only round/sampling/backend/tool names. |
| [test_session_console.py](test_session_console.py#L615) | `JournalProjectionCacheTests.test_events_strip_new_format_request_content` | `None` | `None` | A new-format ``request_content`` sibling never reaches the trace page. |
| [test_session_console.py](test_session_console.py#L666) | `CallLedgerProjectionTests._service` | `root: Path` | `tuple[ConsoleProjectionService, ExecutionJournal]` | Implement `CallLedgerProjectionTests._service`. |
| [test_session_console.py](test_session_console.py#L671) | `CallLedgerProjectionTests._request` | `**overrides: object` | `dict[str, object]` | Implement `CallLedgerProjectionTests._request`. |
| [test_session_console.py](test_session_console.py#L682) | `CallLedgerProjectionTests.test_calls_project_attempts_usage_and_internal_entries` | `None` | `None` | Implement `CallLedgerProjectionTests.test_calls_project_attempts_usage_and_internal_entries`. |
| [test_session_console.py](test_session_console.py#L741) | `CallLedgerProjectionTests.test_calls_window_bounds_and_reports_more` | `None` | `None` | Implement `CallLedgerProjectionTests.test_calls_window_bounds_and_reports_more`. |
| [test_session_console.py](test_session_console.py#L758) | `CallLedgerProjectionTests.test_calls_cache_reads_only_appended_journal_bytes` | `None` | `None` | Implement `CallLedgerProjectionTests.test_calls_cache_reads_only_appended_journal_bytes`. |
| [test_session_console.py](test_session_console.py#L774) | `CallLedgerProjectionTests.test_calls_cache_discards_prefix_when_journal_shrinks` | `None` | `None` | Implement `CallLedgerProjectionTests.test_calls_cache_discards_prefix_when_journal_shrinks`. |
| [test_session_console.py](test_session_console.py#L788) | `CallLedgerProjectionTests.test_calls_copies_isolate_cached_records_from_caller_mutation` | `None` | `None` | Implement `CallLedgerProjectionTests.test_calls_copies_isolate_cached_records_from_caller_mutation`. |
| [test_session_console.py](test_session_console.py#L804) | `CallLedgerProjectionTests.test_calls_ignore_legacy_prompt_and_tool_bodies` | `None` | `None` | The ledger projects index keys only, even from a legacy full body. |
| [test_session_console.py](test_session_console.py#L829) | `CallLedgerProjectionTests.test_ledger_projects_per_round_content_from_new_events` | `None` | `None` | New-format events, and only those, supply per-round input/output. |
| [test_session_console.py](test_session_console.py#L878) | `CallLedgerProjectionTests.test_ledger_preview_is_capped_at_2000_characters` | `None` | `None` | One oversized value is truncated but reports its true size. |
| [test_session_console.py](test_session_console.py#L904) | `CallLedgerProjectionTests.test_ledger_copies_isolate_new_content_from_caller_mutation` | `None` | `None` | Mutating a returned per-round content row cannot poison the cache. |
| [test_session_console.py](test_session_console.py#L929) | `CallLedgerProjectionTests.test_legacy_remote_request_yields_no_ledger_content` | `None` | `None` | A legacy request body supplies index keys only, never content. |
| [test_session_console.py](test_session_console.py#L956) | `CallLedgerProjectionTests.test_ledger_projects_request_messages_from_new_events` | `None` | `None` | The new ``request_content`` sibling, and only it, supplies the input. |
| [test_session_console.py](test_session_console.py#L991) | `CallLedgerProjectionTests.test_ledger_request_messages_are_capped_at_2000_characters` | `None` | `None` | One oversized projected request message reports its true size. |
| [test_session_console.py](test_session_console.py#L1011) | `CallLedgerProjectionTests.test_legacy_remote_request_yields_no_request_messages` | `None` | `None` | A legacy body never populates the new per-round request_messages. |
| [test_session_console.py](test_session_console.py#L1030) | `CallLedgerProjectionTests.test_request_messages_copies_isolate_from_caller_mutation` | `None` | `None` | Mutating a returned request_messages row cannot poison the cache. |
| [test_session_console.py](test_session_console.py#L1051) | `CallLedgerProjectionTests.test_calls_returns_typed_records_for_read_only_access` | `None` | `None` | ``calls`` yields typed dataclasses; callers only read their fields. |
| [test_session_console.py](test_session_console.py#L1126) | `FrontendContextLoadTests._read` | `relative: str` | `str` | Implement `FrontendContextLoadTests._read`. |
| [test_session_console.py](test_session_console.py#L1130) | `FrontendContextLoadTests.test_initial_message_page_is_bounded_below_server_cap` | `None` | `None` | Implement `FrontendContextLoadTests.test_initial_message_page_is_bounded_below_server_cap`. |
| [test_session_console.py](test_session_console.py#L1137) | `FrontendContextLoadTests.test_context_dialog_tabs_hydrate_lazily` | `None` | `None` | Implement `FrontendContextLoadTests.test_context_dialog_tabs_hydrate_lazily`. |
| [test_session_console.py](test_session_console.py#L1148) | `FrontendContextLoadTests.test_per_round_tool_chips_render_in_the_calls_tab_only` | `None` | `None` | Implement `FrontendContextLoadTests.test_per_round_tool_chips_render_in_the_calls_tab_only`. |
| [test_session_console.py](test_session_console.py#L1188) | `FrontendContextLoadTests.test_chat_view_renders_tool_payloads` | `None` | `None` | Implement `FrontendContextLoadTests.test_chat_view_renders_tool_payloads`. |
| [test_session_console.py](test_session_console.py#L1203) | `FrontendContextLoadTests.test_chat_view_cache_buster_is_bumped` | `None` | `None` | Implement `FrontendContextLoadTests.test_chat_view_cache_buster_is_bumped`. |
| [test_session_console.py](test_session_console.py#L1209) | `FrontendContextLoadTests.test_static_cache_buster_is_bumped` | `None` | `None` | Implement `FrontendContextLoadTests.test_static_cache_buster_is_bumped`. |
| [test_session_console.py](test_session_console.py#L1216) | `FrontendContextLoadTests.test_plan_mutations_trigger_a_plan_reload` | `None` | `None` | ``plan:*`` lifecycle facts must schedule the debounced plan reload. |
| [test_session_console.py](test_session_console.py#L1232) | `FrontendContextLoadTests.test_legacy_chat_handler_also_reloads_on_plan_mutations` | `None` | `None` | The legacy chat.js handler must mirror the plan-prefix guard. |
| [test_session_console.py](test_session_console.py#L1243) | `FrontendContextLoadTests.test_round_content_renders_readable_request_messages` | `None` | `None` | The per-round input block renders the literal model:/messages: layout. |
| [test_session_console.py](test_session_console.py#L1260) | `FrontendContextLoadTests.test_calls_tab_is_wired_to_the_journal_ledger` | `None` | `None` | Implement `FrontendContextLoadTests.test_calls_tab_is_wired_to_the_journal_ledger`. |
| [test_settings_service.py](test_settings_service.py#L16) | `SettingsServiceTests.test_connector_secret_never_appears_in_public_catalog` | `None` | `None` | Connector metadata is readable while its API key stays separate. |
| [test_settings_service.py](test_settings_service.py#L32) | `SettingsServiceTests.test_session_profile_is_session_owned_and_can_restore_inheritance` | `None` | `None` | A full Session override survives global changes until explicitly cleared. |
| [test_settings_service.py](test_settings_service.py#L55) | `SettingsServiceTests.test_saved_connector_materializes_required_coordinator_before_run` | `None` | `None` | Every Session reserves coordinator and builds it from saved profile state. |
| [test_settings_service.py](test_settings_service.py#L90) | `SettingsServiceTests.test_request_timeout_defaults_and_rejects_invalid_values` | `None` | `None` | Implement `SettingsServiceTests.test_request_timeout_defaults_and_rejects_invalid_values`. |
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
| [test_execution_service.py](test_execution_service.py#L25) | `_FailingSwarm` | `None` | `object` | Minimal graph facade that reports an unsuccessful root Agent. |
| [test_execution_service.py](test_execution_service.py#L70) | `ExecutionServiceTests` | `None` | `unittest.TestCase` | Ensure graph-level root failures become terminal attempt failures. |
| [test_execution_service.py](test_execution_service.py#L139) | `_RecordingSwarm` | `None` | `object` | Swarm facade that captures the validated initial user input. |
| [test_execution_service.py](test_execution_service.py#L194) | `_PreviewHandler` | `None` | `object` | Minimal provider facade proving request composition performs no I/O. |
| [test_execution_service.py](test_execution_service.py#L220) | `ExecutionImageWiringTests` | `None` | `unittest.TestCase` | Native image references flow from the Session store into providers. |
| [test_execution_service.py](test_execution_service.py#L349) | `ControlImageRejectionTests` | `None` | `unittest.TestCase` | Steering stays text-only; attached images fail loudly, never silently. |
| [test_execution_service.py](test_execution_service.py#L387) | `_BlockingSwarm` | `None` | `object` | Swarm facade that holds an attempt open until the test releases it. |
| [test_execution_service.py](test_execution_service.py#L444) | `RuntimeAgentDirtyTests` | `None` | `unittest.TestCase` | Forced stops invalidate cached runtime Agents; graceful stops do not. |
| [test_external_agent_hub.py](test_external_agent_hub.py#L24) | `FakeCodexAdapter` | `None` | `object` | Deterministic adapter used to verify the Hub base contract. |
| [test_external_agent_hub.py](test_external_agent_hub.py#L74) | `CoreState` | `angelus_core: AngelusCore` | `object` | Minimal FastAPI-like state object for direct route contract tests. |
| [test_external_agent_hub.py](test_external_agent_hub.py#L81) | `ApplicationContext` | `state: CoreState` | `object` | Minimal application object exposing the route's required state field. |
| [test_external_agent_hub.py](test_external_agent_hub.py#L88) | `RequestContext` | `app: ApplicationContext` | `object` | Minimal request object exposing the route's required app property. |
| [test_external_agent_hub.py](test_external_agent_hub.py#L94) | `ExternalAgentHubTests` | `None` | `unittest.TestCase` | Assert persistence, adapter isolation, and HTTP response boundaries. |
| [test_external_agent_hub_read_only_adapters.py](test_external_agent_hub_read_only_adapters.py#L20) | `FakeReadOnlyFacade` | `probe_result: ExternalAgentProbe, session_records: tuple[RemoteSessionSummary, ...], fail_sessions: bool, requested_limits: list[int]` | `object` | Deterministic injected transport implementation for adapter tests. |
| [test_external_agent_hub_read_only_adapters.py](test_external_agent_hub_read_only_adapters.py#L69) | `ReadOnlyExternalAgentAdapterTests` | `None` | `unittest.TestCase` | Assert typed facade boundaries and session normalization for adapters. |
| [test_image_attachments.py](test_image_attachments.py#L26) | `ImageAttachmentStoreTests` | `None` | `unittest.TestCase` | Provide `ImageAttachmentStoreTests` behavior. |
| [test_image_tool_provider.py](test_image_tool_provider.py#L43) | `ImageToolProviderTests` | `None` | `unittest.TestCase` | Provide `ImageToolProviderTests` behavior. |
| [test_knowledge_tools.py](test_knowledge_tools.py#L13) | `KnowledgeStoreTests` | `None` | `unittest.TestCase` | Verify durable retrieval stays outside Agent context and task state. |
| [test_llm_timeout_retry.py](test_llm_timeout_retry.py#L11) | `_Handler` | `failures: list[Exception]` | `object` | Provide `_Handler` behavior. |
| [test_llm_timeout_retry.py](test_llm_timeout_retry.py#L32) | `_StreamingHandler` | `failures: list[Exception], fail_after_delta: bool` | `_Handler` | Provide `_StreamingHandler` behavior. |
| [test_llm_timeout_retry.py](test_llm_timeout_retry.py#L60) | `TimeoutRetryTests` | `None` | `unittest.TestCase` | Provide `TimeoutRetryTests` behavior. |
| [test_message_usage_metadata.py](test_message_usage_metadata.py#L14) | `_NoopCompactor` | `None` | `object` | Offline placeholder; these tests deliberately never compact. |
| [test_message_usage_metadata.py](test_message_usage_metadata.py#L19) | `_UsageSwarm` | `None` | `object` | Minimal aggregate exposing distinct Coordinator/Worker accounting. |
| [test_message_usage_metadata.py](test_message_usage_metadata.py#L49) | `MessageUsageMetadataTests` | `None` | `unittest.TestCase` | Ensure message detail cards survive checkpoint, paging, and restart. |
| [test_native_vision_payload.py](test_native_vision_payload.py#L38) | `NativeVisionPayloadTests` | `None` | `unittest.TestCase` | Provider wire conversion happens from durable references, not history. |
| [test_paged_context_storage.py](test_paged_context_storage.py#L12) | `_NoopCompactor` | `None` | `object` | Minimal compactor placeholder because this test does not compact. |
| [test_paged_context_storage.py](test_paged_context_storage.py#L16) | `PagedContextStorageTests` | `None` | `unittest.TestCase` | Verify the durable reader returns bounded newest-first windows. |
| [test_plugin_manager.py](test_plugin_manager.py#L14) | `PluginManagerTests` | `None` | `unittest.TestCase` | Assert discovery never executes code and loaded packages stay bounded. |
| [test_run_graph_projection.py](test_run_graph_projection.py#L14) | `RunGraphProjectionTests` | `None` | `unittest.TestCase` | Provide `RunGraphProjectionTests` behavior. |
| [test_run_graph_projection.py](test_run_graph_projection.py#L118) | `RunGraphCheckpointReplayTests` | `None` | `unittest.TestCase` | Bounded replay must resume from the checkpoint cursor exactly. |
| [test_session_artifacts.py](test_session_artifacts.py#L13) | `SessionArtifactStoreTests` | `None` | `unittest.TestCase` | Ensure artifact refs replace long history without dropping evidence. |
| [test_session_console.py](test_session_console.py#L30) | `_Journal` | `None` | `object` | Capture secret-free console events emitted by a test tool call. |
| [test_session_console.py](test_session_console.py#L36) | `_Attempt` | `None` | `object` | Minimal attempt façade exposing the journal used by console tools. |
| [test_session_console.py](test_session_console.py#L41) | `_Execution` | `None` | `object` | Minimal execution façade retaining the current attempt. |
| [test_session_console.py](test_session_console.py#L46) | `_Swarm` | `None` | `object` | Minimal dynamic swarm façade used to verify direct dynamic calls. |
| [test_session_console.py](test_session_console.py#L54) | `_PreviewHandler` | `None` | `object` | Minimal provider facade proving request composition performs no I/O. |
| [test_session_console.py](test_session_console.py#L69) | `SessionConsoleTests` | `None` | `unittest.TestCase` | Verify state recovery, validation, and Agent-owned mutation writes. |
| [test_session_console.py](test_session_console.py#L341) | `GraphEventStreamTests` | `None` | `unittest.TestCase` | The run-graph SSE route must emit spec-framed real newlines. |
| [test_session_console.py](test_session_console.py#L401) | `_FakeAttempt` | `journal: ExecutionJournal` | `object` | Minimal attempt façade exposing a real append-only journal. |
| [test_session_console.py](test_session_console.py#L409) | `_FakeExecution` | `attempt: _FakeAttempt` | `object` | Minimal execution façade retaining the current attempt. |
| [test_session_console.py](test_session_console.py#L416) | `_FakeSession` | `attempt: _FakeAttempt` | `object` | Minimal session façade exposing only the execution attempt. |
| [test_session_console.py](test_session_console.py#L423) | `_FakeCore` | `session: _FakeSession` | `object` | Minimal composition root whose session lookup returns one fake. |
| [test_session_console.py](test_session_console.py#L430) | `JournalProjectionCacheTests` | `None` | `unittest.TestCase` | Per-request projections must read only the un-consumed journal tail. |
| [test_session_console.py](test_session_console.py#L647) | `_LedgerSession` | `attempt: _FakeAttempt` | `object` | Minimal Session façade carrying one attempt plus persisted role metadata. |
| [test_session_console.py](test_session_console.py#L656) | `_LedgerCore` | `session: _LedgerSession` | `object` | Minimal composition root exposing one durable Session lookup. |
| [test_session_console.py](test_session_console.py#L663) | `CallLedgerProjectionTests` | `None` | `unittest.TestCase` | The journal-derived call ledger must expose real calls without prompts. |
| [test_session_console.py](test_session_console.py#L1123) | `FrontendContextLoadTests` | `None` | `unittest.TestCase` | Static guards for the payload and lazy-tab frontend regressions. |
| [test_settings_service.py](test_settings_service.py#L13) | `SettingsServiceTests` | `None` | `unittest.TestCase` | Verify the new settings path has one durable authority per concern. |
| [test_system_resource_manager.py](test_system_resource_manager.py#L17) | `SystemResourceManagerTests` | `None` | `unittest.TestCase` | Keep folder selection out of browser and Tauri runtimes. |
| [test_tool_result_prompt_budget.py](test_tool_result_prompt_budget.py#L10) | `ToolResultPromptBudgetTests` | `None` | `unittest.TestCase` | Ensure historical tool output remains cache-stable across rounds. |
| [test_workspace_service.py](test_workspace_service.py#L13) | `WorkspaceServiceTests` | `None` | `unittest.TestCase` | Ensure durable workspace records do not create a second session owner. |

<!-- END GENERATED SYMBOL MAP -->
