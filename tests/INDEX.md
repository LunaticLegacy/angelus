# tests/ — Test Suite INDEX

`unittest`-based regression suite covering persistence, graph context, web API,
swarm, TLB-RAG, and utilities.

## Route Map — Leaf Files

| File | What It Tests |
|------|---------------|
| `test_active_run_reuse.py` | 同进程多轮复用 ActiveRun/Swarm 时保留控制对象身份并清理逐轮状态 |
| `test_agent_stop_persistence.py` | Cooperative-stop persistence, force-stop interruption of in-flight model requests, and cancellation-without-retry regression coverage |
| `test_agent_turns_from_events.py` | `_agent_turns_from_events()` reconstructs conversation turns from event log |
| `test_archive_retrieval.py` | Bounded lexical retrieval over compacted raw archive records |
| `test_compact.py` | Manual context-compaction endpoint, staged events, and failure handling |
| `test_connector_store.py` | Connector CRUD, API-key encryption/redaction, and authoritative server-side backend resolution |
| `test_cli_state_dir.py` | CLI `--state-dir` 对新旧状态根环境变量的同步与导入顺序 |
| `test_context_archive_api.py` | Archived raw-context API pagination and provenance fields |
| `test_context_editing.py` | Agent 活动上下文的检查、版本化编辑、审计、冲突检测和前向恢复 |
| `test_context_stats.py` | 统一上下文长度估算、远程请求统计和检查器响应契约 |
| `test_execution_graph_persistence.py` | ExecutionGraph persistence and recovery |
| `test_graph_builder.py` | Entity/relation extraction and graph ingestion |
| `test_graph_handler.py` | Hybrid linear/graph handler, compaction, and archive evidence injection |
| `test_graph_retriever.py` | Graph retrieval scoring, expansion, and rendering |
| `test_graph_semantic.py` | Stateless semantic graph worker and reranking boundary |
| `test_graph_store.py` | Graph storage, relations, communities, and persistence |
| `test_plugin_api.py` | Plugin REST/static bridge, public response redaction, route isolation, and asset traversal protection |
| `test_plugin_autoreload.py` | 开发模式插件自动重载的指纹、去抖、失败隔离和生产禁用边界 |
| `test_plugin_bootstrap.py` | Packaged starter plugins copy once into the persistent directory beside `workspace/` without overwriting users |
| `test_desktop_packaging.py` | Keeps the Windows MSI version numeric while the public release remains Alpha. |
| `test_workspace_opening.py` | Current-workspace button opens the selected session directory through the host file manager. |
| `test_plugin_manager.py` | Plugin discovery, lifecycle, registration, enable/disable state, and failure isolation |
| `test_plugin_registry.py` | Plugin path resolution, manifest validation, and atomic `plugins.json` registry operations |
| `test_provider_adapters.py` | Kimi Code discovery, OpenAI-compatible backend resolution, manual-compaction parity, and credential-safe provenance |
| `test_mcp_tools.py` | Official MCP SDK stdio discovery, native tool bridging, schema preservation, invocation, and safe environment configuration |
| `test_retrieved_context.py` | RetrievedContextHandler: TLB-RAG memory injection |
| `test_run_profile_persistence.py` | Credential-free runtime profile and durable event persistence |
| `test_run_profiles.py` | Persistent global defaults, per-Agent inheritance/restore, credential exclusion, and two-level tool permission gates |
| `test_session_history.py` | Session history rebuild from events and legacy context files |
| `test_session_memory.py` | Explicit cross-session memory/artifact grants and snapshot evidence boundaries |
| `test_session_steers.py` | Durable retrieval and ordering of applied steering instructions |
| `test_session_observability.py` | Session event logging, SSE streaming |
| `test_shell_tools.py` | Shell tool execution, sandboxing |
| `test_state_root.py` | `_default_state_root()`: workspace directory resolution |
| `test_sse_stream.py` | Durable SSE replay and live event-stream behavior |
| `test_swarm_failure_isolation.py` | Worker failure isolation and coordinator reporting |
| `test_swarm_restart_recovery.py` | Swarm 终态快照、进程重启恢复、worker 复活与凭据边界 |
| `test_task_planning.py` | TaskPlanStore: JSON plan CRUD plus coordinator/worker plan-path isolation |
| `test_tlb_rag.py` | TLB-RAG handler: traversal, cache, retrieval |
| `test_tlb_reliability.py` | TLB-RAG reliability: edge cases, error handling |
| `test_web_markdown.py` | `render_markdown()`: CommonMark rendering |
| `test_workbench_assets.py` | Active Workbench script/template DOM, left settings navigation, selectable session-memory grants, and settings API consistency |
| `test_spike_product_adapters.py` | Claude Code / Codex 外部产品适配 Spike 的解析、快照和增量读取 |
| `test_webapp_context_threshold.py` | Webapp context-threshold and browser retry-count configuration |
| `test_workspace_deletion.py` | Workspace deletion: cleanup, active run handling |

## Intent Routing

- **Agent tests** → `test_active_run_reuse.py`, `test_agent_stop_persistence.py`, `test_agent_turns_from_events.py`
- **Web/API tests** → `test_compact.py`, `test_connector_store.py`, `test_provider_adapters.py`, `test_sse_stream.py`, `test_web_markdown.py`, `test_webapp_context_threshold.py`, `test_workspace_deletion.py`, `test_workspace_opening.py`
- **Context tests** → `test_archive_retrieval.py`, `test_context_archive_api.py`, `test_context_editing.py`, `test_context_stats.py`, `test_graph_handler.py`, `test_retrieved_context.py`, `test_session_history.py`, `test_session_memory.py`
- **Plugin / MCP tests** → `test_plugin_api.py`, `test_plugin_autoreload.py`, `test_plugin_bootstrap.py`, `test_plugin_manager.py`, `test_plugin_registry.py`, `test_mcp_tools.py`
- **Swarm tests** → `test_execution_graph_persistence.py`, `test_swarm_failure_isolation.py`, `test_swarm_restart_recovery.py`
- **TLB-RAG tests** → `test_tlb_rag.py`, `test_tlb_reliability.py`
- **Other** → `test_cli_state_dir.py`, `test_desktop_packaging.py`, `test_session_observability.py`, `test_shell_tools.py`, `test_spike_product_adapters.py`, `test_state_root.py`, `test_task_planning.py`, `test_workbench_assets.py`

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [test_active_run_reuse.py](test_active_run_reuse.py#L13) | `ActiveRunReuseTests.test_reset_for_next_turn_preserves_control_identity_and_clears_state` | `None` | `None` | Reuse must not invalidate tool closures holding ``force_stopped``. |
| [test_active_run_reuse.py](test_active_run_reuse.py#L33) | `ActiveRunReuseTests.test_reset_rejects_a_still_running_holder` | `None` | `None` | An in-flight run cannot be reset into a competing execution turn. |
| [test_active_run_reuse.py](test_active_run_reuse.py#L39) | `ActiveRunReuseTests.test_stream_fragment_is_marked_live_only` | `None` | `None` | Keep provider deltas out of the durable-event persistence path. |
| [test_agent_stop_persistence.py](test_agent_stop_persistence.py#L26) | `_CompletedBoundaryFetcher.fetch` | `**_: object` | `LLMOutput` | Return the response that must survive a subsequent stop request. |
| [test_agent_stop_persistence.py](test_agent_stop_persistence.py#L39) | `_StopAfterBoundary.should_stop` | `None` | `bool` | Return ``True`` after the first response and tool batch complete. |
| [test_agent_stop_persistence.py](test_agent_stop_persistence.py#L43) | `_StopAfterBoundary.drain_steers` | `None` | `list[str]` | Return no steering messages for this focused stop-path test. |
| [test_agent_stop_persistence.py](test_agent_stop_persistence.py#L60) | `_SecondRoundFailureFetcher.fetch` | `**_: object` | `LLMOutput` | Implement `_SecondRoundFailureFetcher.fetch`. |
| [test_agent_stop_persistence.py](test_agent_stop_persistence.py#L78) | `_SteerOnce.should_stop` | `None` | `bool` | Implement `_SteerOnce.should_stop`. |
| [test_agent_stop_persistence.py](test_agent_stop_persistence.py#L81) | `_SteerOnce.drain_steers` | `None` | `list[str]` | Implement `_SteerOnce.drain_steers`. |
| [test_agent_stop_persistence.py](test_agent_stop_persistence.py#L102) | `_BlockingFetcher.fetch` | `**_: object` | `LLMOutput` | Wait like a provider request whose transport is still open. |
| [test_agent_stop_persistence.py](test_agent_stop_persistence.py#L113) | `_BlockingFetcher.abort_active_requests` | `None` | `int` | Record the terminal transport-close request from the Agent. |
| [test_agent_stop_persistence.py](test_agent_stop_persistence.py#L125) | `_ForceStopDuringRequest.should_stop` | `None` | `bool` | Keep the ordinary cooperative stop path inactive for this test. |
| [test_agent_stop_persistence.py](test_agent_stop_persistence.py#L129) | `_ForceStopDuringRequest.drain_steers` | `None` | `list[str]` | Return no steering messages while the request is blocked. |
| [test_agent_stop_persistence.py](test_agent_stop_persistence.py#L141) | `_CancellingHandler.abort_active_request` | `None` | `bool` | Report a closed transport without requiring a provider SDK. |
| [test_agent_stop_persistence.py](test_agent_stop_persistence.py#L145) | `_CancellingHandler.prepare_tools` | `_tools: object` | `None` | Return no provider tool schema in this retry-only test. |
| [test_agent_stop_persistence.py](test_agent_stop_persistence.py#L149) | `_CancellingHandler.create_completion` | `**_: object` | `object` | Set cancellation, then fail as a client-close normally would. |
| [test_agent_stop_persistence.py](test_agent_stop_persistence.py#L155) | `_CancellingHandler.normalize_completion_response` | `_raw: object` | `LLMOutput` | Cancelled transport must not return a response in this test. |
| [test_agent_stop_persistence.py](test_agent_stop_persistence.py#L163) | `AgentStopPersistenceTests.test_stopped_agent_saves_completed_context_and_exposes_output` | `None` | `None` | Persist the completed user/assistant turn before reporting a stop. |
| [test_agent_stop_persistence.py](test_agent_stop_persistence.py#L186) | `AgentStopPersistenceTests.test_completed_boundary_is_saved_before_a_later_model_failure` | `None` | `None` | A run error must not discard an earlier completed response. |
| [test_agent_stop_persistence.py](test_agent_stop_persistence.py#L205) | `AgentStopPersistenceTests.test_force_stop_interrupts_an_inflight_model_request` | `None` | `None` | End the Agent immediately and ask its fetcher to close transport. |
| [test_agent_stop_persistence.py](test_agent_stop_persistence.py#L234) | `AgentStopPersistenceTests.test_force_stop_never_retries_after_transport_close` | `None` | `None` | Terminal cancellation wins over a close-induced timeout error. |
| [test_agent_turns_from_events.py](test_agent_turns_from_events.py#L15) | `AgentTurnsFromEventsTests.setUp` | `None` | `Any` | Implement `AgentTurnsFromEventsTests.setUp`. |
| [test_agent_turns_from_events.py](test_agent_turns_from_events.py#L22) | `AgentTurnsFromEventsTests.tearDown` | `None` | `Any` | Implement `AgentTurnsFromEventsTests.tearDown`. |
| [test_agent_turns_from_events.py](test_agent_turns_from_events.py#L25) | `AgentTurnsFromEventsTests._write_events` | `events: list[dict]` | `None` | Write events to a temp events.ndjson. |
| [test_agent_turns_from_events.py](test_agent_turns_from_events.py#L32) | `AgentTurnsFromEventsTests._read_turns` | `agent_name: str` | `list[dict]` | Read turns using the same session path logic. |
| [test_agent_turns_from_events.py](test_agent_turns_from_events.py#L39) | `AgentTurnsFromEventsTests.test_single_round_no_duplicates` | `None` | `Any` | One user message + one coordinator agent:round should produce 2 turns. |
| [test_agent_turns_from_events.py](test_agent_turns_from_events.py#L58) | `AgentTurnsFromEventsTests.test_run_started_and_steer_are_durable_transcript_turns` | `None` | `Any` | New browser sessions rebuild user, steer, and result from events. |
| [test_agent_turns_from_events.py](test_agent_turns_from_events.py#L78) | `AgentTurnsFromEventsTests.test_two_rounds_no_duplicates` | `None` | `Any` | Two user questions + two coordinator responses → 4 turns. |
| [test_agent_turns_from_events.py](test_agent_turns_from_events.py#L104) | `AgentTurnsFromEventsTests.test_duplicate_agent_round_events_are_deduplicated` | `None` | `Any` | An immediate second copy of the same round must not duplicate turns. |
| [test_agent_turns_from_events.py](test_agent_turns_from_events.py#L133) | `AgentTurnsFromEventsTests.test_worker_duplicate_rounds_are_deduplicated_per_agent` | `None` | `Any` | Worker double-writes collapse while distinct workers stay separate. |
| [test_agent_turns_from_events.py](test_agent_turns_from_events.py#L160) | `AgentTurnsFromEventsTests.test_non_coordinator_agent_only_gets_its_own_rounds` | `None` | `Any` | A sub-agent 'worker-1' sees coordinator user messages + its own rounds. |
| [test_agent_turns_from_events.py](test_agent_turns_from_events.py#L185) | `AgentTurnsFromEventsTests.test_agent_turns_page_returns_newest_limit_and_next_before` | `None` | `Any` | Pagination returns the newest page with an exclusive next cursor. |
| [test_agent_turns_from_events.py](test_agent_turns_from_events.py#L216) | `AgentTurnsFromEventsTests.test_agent_turns_page_clamps_limit_and_handles_empty` | `None` | `Any` | Limit is clamped to 1..500 and empty logs fall back cleanly. |
| [test_archive_retrieval.py](test_archive_retrieval.py#L15) | `ArchiveRetrievalTests.test_returns_ranked_evidence_with_source_timeline` | `None` | `None` | Implement `ArchiveRetrievalTests.test_returns_ranked_evidence_with_source_timeline`. |
| [test_archive_retrieval.py](test_archive_retrieval.py#L30) | `ArchiveRetrievalTests.test_tool_output_is_searchable_but_returned_evidence_is_bounded` | `None` | `None` | Implement `ArchiveRetrievalTests.test_tool_output_is_searchable_but_returned_evidence_is_bounded`. |
| [test_archive_retrieval.py](test_archive_retrieval.py#L53) | `ArchiveRetrievalTests.test_cjk_terms_match_and_limits_are_enforced` | `None` | `None` | Implement `ArchiveRetrievalTests.test_cjk_terms_match_and_limits_are_enforced`. |
| [test_archive_retrieval.py](test_archive_retrieval.py#L69) | `ArchiveRetrievalTests.test_empty_query_and_invalid_bounds_do_not_create_unbounded_results` | `None` | `None` | Implement `ArchiveRetrievalTests.test_empty_query_and_invalid_bounds_do_not_create_unbounded_results`. |
| [test_cli_state_dir.py](test_cli_state_dir.py#L13) | `test_cli_state_dir_synchronizes_plugin_and_registry_roots` | `None` | `None` | ``--state-dir`` must give the CLI one application root for both stores. |
| [test_cli_state_dir.py](test_cli_state_dir.py#L25) | `test_cli_state_dir_leaves_environment_untouched_when_omitted` | `None` | `None` | The source-checkout default remains available without an explicit flag. |
| [test_compact.py](test_compact.py#L23) | `FakeFetcher.fetch` | `**kwargs: object` | `LLMOutput` | Implement `FakeFetcher.fetch`. |
| [test_compact.py](test_compact.py#L33) | `_seed_context` | `directory: Path, messages: list[dict] \| None` | `Path` | Write a linear-context file for the coordinator agent. |
| [test_compact.py](test_compact.py#L52) | `_register_session` | `None` | `tuple[object, str]` | Register the demo session under a temporary state root. |
| [test_compact.py](test_compact.py#L63) | `_body` | `api_key: str` | `dict` | Implement `_body`. |
| [test_compact.py](test_compact.py#L78) | `TestCompact.test_rejects_active_run` | `None` | `None` | Compaction must not race a running session's context writes. |
| [test_compact.py](test_compact.py#L93) | `TestCompact.test_streams_stages_and_compacts` | `monkeypatch: Any` | `None` | A successful compaction streams loading/saving/done stages. |
| [test_compact.py](test_compact.py#L122) | `TestCompact.test_failure_leaves_context_untouched` | `monkeypatch: Any` | `None` | An unparseable compaction reply must not modify the context file. |
| [test_compact.py](test_compact.py#L148) | `TestCompact.test_no_messages_reports_done_without_llm` | `monkeypatch: Any` | `None` | An empty context short-circuits without calling the model. |
| [test_connector_store.py](test_connector_store.py#L12) | `test_connector_store_round_trip` | `None` | `None` | Persist multiple connector records without touching the real local store. |
| [test_connector_store.py](test_connector_store.py#L37) | `test_blank_connector_update_keeps_saved_key_and_response_is_redacted` | `None` | `None` | A selected connector must remain usable without sending its key back. |
| [test_context_archive_api.py](test_context_archive_api.py#L15) | `ContextArchiveApiTests.test_agent_context_graph_is_bounded_and_exposes_only_visible_relations` | `None` | `None` | The graph inspector receives a safe per-Agent persisted snapshot. |
| [test_context_archive_api.py](test_context_archive_api.py#L47) | `ContextArchiveApiTests.test_agent_context_graph_is_empty_when_companion_file_is_missing` | `None` | `None` | Old linear-only contexts remain inspectable without an API error. |
| [test_context_archive_api.py](test_context_archive_api.py#L60) | `ContextArchiveApiTests.test_archive_page_exposes_raw_evidence_and_timeline_with_pagination` | `None` | `None` | Implement `ContextArchiveApiTests.test_archive_page_exposes_raw_evidence_and_timeline_with_pagination`. |
| [test_context_archive_api.py](test_context_archive_api.py#L86) | `ContextArchiveApiTests.test_active_context_preview_matches_model_message_shape` | `None` | `None` | The viewer receives the full persisted prompt in send order. |
| [test_context_archive_api.py](test_context_archive_api.py#L116) | `ContextArchiveApiTests.test_context_preview_uses_latest_captured_remote_request` | `None` | `None` | Prefer the actual credential-free request snapshot over a rebuild. |
| [test_context_archive_api.py](test_context_archive_api.py#L148) | `ContextArchiveApiTests.test_archive_page_is_empty_for_legacy_or_malformed_contexts` | `None` | `None` | Implement `ContextArchiveApiTests.test_archive_page_is_empty_for_legacy_or_malformed_contexts`. |
| [test_context_archive_api.py](test_context_archive_api.py#L169) | `_seed_linear_context` | `directory: Path, agent: str, messages: list[dict] \| None, threshold: int, round_: int` | `Path` | Write a linear-context checkpoint for one Agent under a temp root. |
| [test_context_archive_api.py](test_context_archive_api.py#L197) | `CompactionInputPreviewApiTests.test_compaction_input_preview_matches_compactor_transcript` | `None` | `None` | The endpoint returns the bounded transcript plus budget metadata. |
| [test_context_archive_api.py](test_context_archive_api.py#L222) | `CompactionInputPreviewApiTests.test_compaction_input_preview_omits_oldest_entries_when_over_budget` | `None` | `None` | Newest-first retention must match the compactor's omitted prefix. |
| [test_context_archive_api.py](test_context_archive_api.py#L260) | `CompactionInputPreviewApiTests.test_compaction_input_preview_is_empty_for_missing_agent` | `None` | `None` | An Agent without a persisted checkpoint renders an empty state. |
| [test_context_archive_api.py](test_context_archive_api.py#L278) | `CompactionInputPreviewApiTests.test_compaction_input_preview_is_empty_for_malformed_context` | `None` | `None` | A corrupt checkpoint must not crash the read-only preview. |
| [test_context_archive_api.py](test_context_archive_api.py#L297) | `CompactionInputPreviewApiTests.test_compaction_input_preview_rejects_aggregate_agent` | `None` | `None` | The aggregate ``all`` filter is not a single Agent checkpoint. |
| [test_context_archive_api.py](test_context_archive_api.py#L311) | `CompactionInputPreviewApiTests.test_compaction_input_preview_rejects_invalid_ids` | `None` | `None` | Unsafe identifiers are rejected before any file access. |
| [test_context_editing.py](test_context_editing.py#L22) | `ContextEditingTests._store` | `directory: str` | `ContextEditStore` | Create an editable checkpoint with two timeline-stable messages. |
| [test_context_editing.py](test_context_editing.py#L42) | `ContextEditingTests.test_first_edit_saves_baseline_and_restore_is_forward_only` | `None` | `None` | A first edit can always recover its pristine legacy checkpoint. |
| [test_context_editing.py](test_context_editing.py#L74) | `ContextEditingTests.test_stale_revision_and_unknown_record_are_rejected` | `None` | `None` | Optimistic revision checks prevent silent concurrent overwrites. |
| [test_context_editing.py](test_context_editing.py#L100) | `ContextEditingTests.test_context_edit_marks_existing_entity_graph_stale` | `None` | `None` | The graph API never presents entities derived from pre-edit text. |
| [test_context_editing.py](test_context_editing.py#L129) | `ContextEditingTests.test_browser_api_and_live_tool_share_the_same_revision_protocol` | `None` | `None` | HTTP and Agent handlers both enforce the public dataclass schema. |
| [test_context_stats.py](test_context_stats.py#L41) | `_json_length` | `value: object` | `int` | Reference serializer matching the spec's unique character basis. |
| [test_context_stats.py](test_context_stats.py#L49) | `ContextLengthStatsTests.test_empty_list_is_all_zeros` | `None` | `None` | Implement `ContextLengthStatsTests.test_empty_list_is_all_zeros`. |
| [test_context_stats.py](test_context_stats.py#L59) | `ContextLengthStatsTests.test_empty_list_with_empty_tools_is_all_zeros` | `None` | `None` | Implement `ContextLengthStatsTests.test_empty_list_with_empty_tools_is_all_zeros`. |
| [test_context_stats.py](test_context_stats.py#L69) | `ContextLengthStatsTests.test_plain_messages_are_measured_and_tokens_derived` | `None` | `None` | Implement `ContextLengthStatsTests.test_plain_messages_are_measured_and_tokens_derived`. |
| [test_context_stats.py](test_context_stats.py#L86) | `ContextLengthStatsTests.test_tool_schemas_are_counted_separately` | `None` | `None` | Implement `ContextLengthStatsTests.test_tool_schemas_are_counted_separately`. |
| [test_context_stats.py](test_context_stats.py#L105) | `ContextLengthStatsTests.test_non_dict_entries_are_skipped_defensively` | `None` | `None` | Implement `ContextLengthStatsTests.test_non_dict_entries_are_skipped_defensively`. |
| [test_context_stats.py](test_context_stats.py#L128) | `ContextLengthStatsTests.test_result_is_a_frozen_dataclass_with_full_fields` | `None` | `None` | Implement `ContextLengthStatsTests.test_result_is_a_frozen_dataclass_with_full_fields`. |
| [test_context_stats.py](test_context_stats.py#L157) | `AgentContextStatsTests._assert_all_spec_keys_present` | `stats: dict` | `None` | Implement `AgentContextStatsTests._assert_all_spec_keys_present`. |
| [test_context_stats.py](test_context_stats.py#L160) | `AgentContextStatsTests.test_missing_context_yields_all_zero_spec_defaults` | `None` | `None` | Implement `AgentContextStatsTests.test_missing_context_yields_all_zero_spec_defaults`. |
| [test_context_stats.py](test_context_stats.py#L179) | `AgentContextStatsTests.test_context_stats_include_estimated_tokens_and_keep_legacy_keys` | `None` | `None` | Implement `AgentContextStatsTests.test_context_stats_include_estimated_tokens_and_keep_legacy_keys`. |
| [test_context_stats.py](test_context_stats.py#L210) | `AgentContextStatsTests.test_context_stats_preserve_compaction_and_ratio_fields` | `None` | `None` | Implement `AgentContextStatsTests.test_context_stats_preserve_compaction_and_ratio_fields`. |
| [test_context_stats.py](test_context_stats.py#L255) | `AgentContextPreviewStatsTests.test_remote_request_stats_dataclass_fields_are_complete` | `None` | `None` | Implement `AgentContextPreviewStatsTests.test_remote_request_stats_dataclass_fields_are_complete`. |
| [test_context_stats.py](test_context_stats.py#L260) | `AgentContextPreviewStatsTests.test_preview_stats_match_estimate_context_length` | `None` | `None` | Implement `AgentContextPreviewStatsTests.test_preview_stats_match_estimate_context_length`. |
| [test_context_stats.py](test_context_stats.py#L298) | `AgentContextPreviewStatsTests.test_preview_without_remote_request_has_no_stats` | `None` | `None` | Implement `AgentContextPreviewStatsTests.test_preview_without_remote_request_has_no_stats`. |
| [test_desktop_packaging.py](test_desktop_packaging.py#L11) | `test_windows_msi_uses_a_numeric_wix_version_for_preview_releases` | `None` | `None` | WiX must not derive an MSI version from the textual `-preview` suffix. |
| [test_desktop_packaging.py](test_desktop_packaging.py#L20) | `test_preview_release_metadata_and_trigger_stay_aligned` | `None` | `None` | Keep package formats and the desktop release tag on one preview release. |
| [test_event_broker.py](test_event_broker.py#L11) | `test_two_subscribers_receive_the_same_event` | `None` | `None` | Independent cursors observe one publication without competing. |
| [test_event_broker.py](test_event_broker.py#L33) | `test_overflow_reports_gap_and_durable_watermark` | `None` | `None` | A slow cursor receives an explicit disk-recovery boundary. |
| [test_event_broker.py](test_event_broker.py#L47) | `test_idle_wait_does_not_wake_until_timeout` | `None` | `None` | An idle broker waits instead of producing a polling tick. |
| [test_execution_graph_persistence.py](test_execution_graph_persistence.py#L14) | `_agent` | `prompt: str` | `Agent` | Build a tool-free Agent suitable for default persistence tests. |
| [test_execution_graph_persistence.py](test_execution_graph_persistence.py#L32) | `ExecutionGraphPersistenceTests.test_save_and_load_restores_agents_edges_and_callbacks` | `None` | `None` | Restore a graph with mapper/router callbacks through a registry. |
| [test_execution_graph_persistence.py](test_execution_graph_persistence.py#L61) | `ExecutionGraphPersistenceTests.test_callbacks_require_explicit_registry` | `None` | `None` | Reject implicit serialization of arbitrary executable callbacks. |
| [test_external_agent_provider_settings.py](test_external_agent_provider_settings.py#L11) | `test_only_opencode_accepts_a_browser_configured_endpoint` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Any` | `None` | Reject endpoint data for CLI-backed Providers before private state is written. |
| [test_external_agent_provider_settings.py](test_external_agent_provider_settings.py#L27) | `test_opencode_persists_its_loopback_endpoint` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Any` | `None` | Persist a selected OpenCode endpoint without exposing any credential field. |
| [test_external_codex_provider.py](test_external_codex_provider.py#L20) | `_FakeRuntime.call` | `factory: Any` | `Any` | Invoke the factory with a fake async client and record its request. |
| [test_external_codex_provider.py](test_external_codex_provider.py#L40) | `_FakeRuntime.close` | `None` | `None` | Match the real runtime cleanup surface. |
| [test_external_codex_provider.py](test_external_codex_provider.py#L44) | `test_codex_provider_maps_fixed_contract_actions_to_safe_rpc_payloads` | `None` | `None` | Discovery/start/send/steer use fixed methods rather than passthrough JSON. |
| [test_external_codex_provider.py](test_external_codex_provider.py#L65) | `test_codex_provider_rejects_steering_a_turn_it_does_not_own` | `None` | `None` | A random thread cannot be controlled without Angelus-observed turn state. |
| [test_external_codex_provider.py](test_external_codex_provider.py#L77) | `test_codex_client_initializes_once_before_thread_requests` | `None` | `None` | Issue Codex's ordered handshake before a normal App Server request. |
| [test_graph_builder.py](test_graph_builder.py#L21) | `_FakeFetcher.fetch` | `msg: Any, system_prompt: Any, temperature: Any, max_tokens: Any, context_handler: Any, backend_name: Any, tools: Any` | `Any` | Implement `_FakeFetcher.fetch`. |
| [test_graph_builder.py](test_graph_builder.py#L32) | `_msg` | `role: str, content: str, timeline: int` | `LLMContext` | Implement `_msg`. |
| [test_graph_builder.py](test_graph_builder.py#L37) | `BuilderLlmTests.test_llm_extraction_upserts` | `None` | `Any` | Implement `BuilderLlmTests.test_llm_extraction_upserts`. |
| [test_graph_builder.py](test_graph_builder.py#L61) | `BuilderLlmTests.test_llm_failure_falls_back_to_regex` | `None` | `Any` | Implement `BuilderLlmTests.test_llm_failure_falls_back_to_regex`. |
| [test_graph_builder.py](test_graph_builder.py#L72) | `BuilderLlmTests.test_no_fetcher_uses_regex_only` | `None` | `Any` | Implement `BuilderLlmTests.test_no_fetcher_uses_regex_only`. |
| [test_graph_builder.py](test_graph_builder.py#L84) | `BuilderLlmTests.test_empty_messages_noop` | `None` | `Any` | Implement `BuilderLlmTests.test_empty_messages_noop`. |
| [test_graph_builder.py](test_graph_builder.py#L91) | `BuilderTimelineTests.test_first_last_seen_updated` | `None` | `Any` | Implement `BuilderTimelineTests.test_first_last_seen_updated`. |
| [test_graph_builder.py](test_graph_builder.py#L102) | `BuilderTimelineTests.test_evidence_timeline_recorded` | `None` | `Any` | Implement `BuilderTimelineTests.test_evidence_timeline_recorded`. |
| [test_graph_builder.py](test_graph_builder.py#L119) | `RegexExtractionTests.test_file_function_hashtag` | `None` | `Any` | Implement `RegexExtractionTests.test_file_function_hashtag`. |
| [test_graph_builder.py](test_graph_builder.py#L130) | `RegexExtractionTests.test_relations_empty` | `None` | `Any` | Implement `RegexExtractionTests.test_relations_empty`. |
| [test_graph_builder.py](test_graph_builder.py#L136) | `StatsTests.test_stats_str` | `None` | `Any` | Implement `StatsTests.test_stats_str`. |
| [test_graph_edit_api.py](test_graph_edit_api.py#L16) | `_install_live_swarm` | `session_id: str` | `None` | Register a session holder with a live coordinator-led Swarm. |
| [test_graph_edit_api.py](test_graph_edit_api.py#L34) | `GraphEditApiTests.setUp` | `None` | `None` | Implement `GraphEditApiTests.setUp`. |
| [test_graph_edit_api.py](test_graph_edit_api.py#L39) | `GraphEditApiTests.tearDown` | `None` | `None` | Implement `GraphEditApiTests.tearDown`. |
| [test_graph_edit_api.py](test_graph_edit_api.py#L46) | `GraphEditApiTests._expect_http` | `status_code: int, call: Any` | `None` | Implement `GraphEditApiTests._expect_http`. |
| [test_graph_edit_api.py](test_graph_edit_api.py#L51) | `GraphEditApiTests.test_mutations_reject_sessions_without_a_live_swarm` | `None` | `None` | Every mutation requires an active Swarm; absent/done holders 409. |
| [test_graph_edit_api.py](test_graph_edit_api.py#L67) | `GraphEditApiTests.test_happy_path_mutates_topology_and_persists_view_and_events` | `None` | `None` | Add/connect/mapper/router/remove round-trips through the live graph. |
| [test_graph_edit_api.py](test_graph_edit_api.py#L128) | `GraphEditApiTests.test_duplicate_agent_and_unknown_targets_are_rejected` | `None` | `None` | Duplicate names, unknown nodes, and bad mapper modes return 409. |
| [test_graph_edit_api.py](test_graph_edit_api.py#L160) | `GraphEditApiTests.test_coordinator_is_protected_and_names_are_validated` | `None` | `None` | Removing the coordinator is a 400; unsafe names are rejected. |
| [test_graph_handler.py](test_graph_handler.py#L25) | `_RecordingCompactor.fetch` | `msg: Any, system_prompt: Any, temperature: Any, max_tokens: Any, context_handler: Any, backend_name: Any, tools: Any` | `Any` | Implement `_RecordingCompactor.fetch`. |
| [test_graph_handler.py](test_graph_handler.py#L44) | `_FakeExtractionFetcher.fetch` | `msg: Any, system_prompt: Any, temperature: Any, max_tokens: Any, context_handler: Any, backend_name: Any, tools: Any` | `Any` | Implement `_FakeExtractionFetcher.fetch`. |
| [test_graph_handler.py](test_graph_handler.py#L58) | `_FakeQueryFetcher.fetch` | `msg: Any, system_prompt: Any, temperature: Any, max_tokens: Any, context_handler: Any, backend_name: Any, tools: Any` | `Any` | Implement `_FakeQueryFetcher.fetch`. |
| [test_graph_handler.py](test_graph_handler.py#L65) | `_chain_store` | `names: Any` | `GraphStore` | A->B->C->D import chain of file entities. |
| [test_graph_handler.py](test_graph_handler.py#L78) | `_assistant` | `content: str, **kwargs: Any` | `LLMOutput` | Implement `_assistant`. |
| [test_graph_handler.py](test_graph_handler.py#L84) | `InitTests.test_defaults` | `None` | `Any` | Implement `InitTests.test_defaults`. |
| [test_graph_handler.py](test_graph_handler.py#L96) | `InitTests.test_keyword_only_constructor` | `None` | `Any` | Implement `InitTests.test_keyword_only_constructor`. |
| [test_graph_handler.py](test_graph_handler.py#L102) | `RetrievalTriggerTests.test_first_message_retrieval_injects_graph_memory` | `None` | `Any` | Implement `RetrievalTriggerTests.test_first_message_retrieval_injects_graph_memory`. |
| [test_graph_handler.py](test_graph_handler.py#L115) | `RetrievalTriggerTests.test_first_message_retrieves_only_once` | `None` | `Any` | Implement `RetrievalTriggerTests.test_first_message_retrieves_only_once`. |
| [test_graph_handler.py](test_graph_handler.py#L134) | `RetrievalTriggerTests.test_every_message_trigger_retrieves_each_user_message` | `None` | `Any` | Implement `RetrievalTriggerTests.test_every_message_trigger_retrieves_each_user_message`. |
| [test_graph_handler.py](test_graph_handler.py#L154) | `RetrievalTriggerTests.test_manual_trigger_requires_explicit_retrieve` | `None` | `Any` | Implement `RetrievalTriggerTests.test_manual_trigger_requires_explicit_retrieve`. |
| [test_graph_handler.py](test_graph_handler.py#L173) | `RetrievalTriggerTests.test_auto_trigger_reretrieves_after_compaction` | `None` | `Any` | Implement `RetrievalTriggerTests.test_auto_trigger_reretrieves_after_compaction`. |
| [test_graph_handler.py](test_graph_handler.py#L193) | `RetrievalTriggerTests.test_auto_retrieval_injects_bounded_raw_archive_evidence` | `None` | `Any` | Compacted source turns remain retrievable, rather than deleted. |
| [test_graph_handler.py](test_graph_handler.py#L211) | `RetrievalTriggerTests.test_auto_no_reretrieval_without_compaction` | `None` | `Any` | Implement `RetrievalTriggerTests.test_auto_no_reretrieval_without_compaction`. |
| [test_graph_handler.py](test_graph_handler.py#L230) | `RetrievalTriggerTests.test_empty_graph_no_injection` | `None` | `Any` | Implement `RetrievalTriggerTests.test_empty_graph_no_injection`. |
| [test_graph_handler.py](test_graph_handler.py#L240) | `GraphUpdateTests.test_flush_after_graph_update_every_messages` | `None` | `Any` | Implement `GraphUpdateTests.test_flush_after_graph_update_every_messages`. |
| [test_graph_handler.py](test_graph_handler.py#L253) | `GraphUpdateTests.test_no_flush_before_threshold` | `None` | `Any` | Implement `GraphUpdateTests.test_no_flush_before_threshold`. |
| [test_graph_handler.py](test_graph_handler.py#L263) | `GraphUpdateTests.test_compaction_forces_flush` | `None` | `Any` | Implement `GraphUpdateTests.test_compaction_forces_flush`. |
| [test_graph_handler.py](test_graph_handler.py#L277) | `GraphUpdateTests.test_flush_uses_extraction_fetcher` | `None` | `Any` | Implement `GraphUpdateTests.test_flush_uses_extraction_fetcher`. |
| [test_graph_handler.py](test_graph_handler.py#L300) | `GraphUpdateTests.test_pending_timelines_match_linear_rounds` | `None` | `Any` | Implement `GraphUpdateTests.test_pending_timelines_match_linear_rounds`. |
| [test_graph_handler.py](test_graph_handler.py#L316) | `BuildMessageTests.test_graph_block_first_then_history` | `None` | `Any` | Implement `BuildMessageTests.test_graph_block_first_then_history`. |
| [test_graph_handler.py](test_graph_handler.py#L330) | `BuildMessageTests.test_graph_block_before_compacted_abstract` | `None` | `Any` | Implement `BuildMessageTests.test_graph_block_before_compacted_abstract`. |
| [test_graph_handler.py](test_graph_handler.py#L344) | `BuildMessageTests.test_tool_results_forwarded_to_linear` | `None` | `Any` | Implement `BuildMessageTests.test_tool_results_forwarded_to_linear`. |
| [test_graph_handler.py](test_graph_handler.py#L359) | `PersistenceTests.test_save_flushes_pending_messages_before_persisting_graph` | `None` | `Any` | Implement `PersistenceTests.test_save_flushes_pending_messages_before_persisting_graph`. |
| [test_graph_handler.py](test_graph_handler.py#L378) | `PersistenceTests.test_save_load_roundtrip` | `None` | `Any` | Implement `PersistenceTests.test_save_load_roundtrip`. |
| [test_graph_handler.py](test_graph_handler.py#L405) | `PersistenceTests.test_load_without_graph_file_resets_store` | `None` | `Any` | Implement `PersistenceTests.test_load_without_graph_file_resets_store`. |
| [test_graph_handler.py](test_graph_handler.py#L425) | `PersistenceTests.test_load_missing_files_returns_false` | `None` | `Any` | Implement `PersistenceTests.test_load_missing_files_returns_false`. |
| [test_graph_handler.py](test_graph_handler.py#L430) | `PersistenceTests.test_load_sets_compaction_generation_from_abstract` | `None` | `Any` | Implement `PersistenceTests.test_load_sets_compaction_generation_from_abstract`. |
| [test_graph_handler.py](test_graph_handler.py#L450) | `ClearTests.test_clear_context_keeps_long_term_graph` | `None` | `Any` | Implement `ClearTests.test_clear_context_keeps_long_term_graph`. |
| [test_graph_handler.py](test_graph_handler.py#L472) | `RetrieveApiTests.test_retrieve_uses_current_timeline` | `None` | `Any` | Implement `RetrieveApiTests.test_retrieve_uses_current_timeline`. |
| [test_graph_handler.py](test_graph_handler.py#L485) | `RetrieveApiTests.test_query_fetcher_used_for_seed_extraction` | `None` | `Any` | Implement `RetrieveApiTests.test_query_fetcher_used_for_seed_extraction`. |
| [test_graph_handler.py](test_graph_handler.py#L499) | `RetrieveApiTests.test_retriever_config_applied` | `None` | `Any` | Implement `RetrieveApiTests.test_retriever_config_applied`. |
| [test_graph_retriever.py](test_graph_retriever.py#L26) | `_FakeFetcher.fetch` | `msg: Any, system_prompt: Any, temperature: Any, max_tokens: Any, context_handler: Any, backend_name: Any, tools: Any` | `Any` | Implement `_FakeFetcher.fetch`. |
| [test_graph_retriever.py](test_graph_retriever.py#L40) | `_chain_graph` | `names: Any` | `GraphStore` | A->B->C->D import chain of file entities. |
| [test_graph_retriever.py](test_graph_retriever.py#L54) | `RetrievalConfigTests.test_weights_normalize` | `None` | `Any` | Implement `RetrievalConfigTests.test_weights_normalize`. |
| [test_graph_retriever.py](test_graph_retriever.py#L59) | `RetrievalConfigTests.test_default_weights` | `None` | `Any` | Implement `RetrievalConfigTests.test_default_weights`. |
| [test_graph_retriever.py](test_graph_retriever.py#L64) | `RetrievalConfigTests.test_all_zero_fallback` | `None` | `Any` | Implement `RetrievalConfigTests.test_all_zero_fallback`. |
| [test_graph_retriever.py](test_graph_retriever.py#L71) | `SeedExtractionTests.test_regex_fallback_no_fetcher` | `None` | `Any` | Implement `SeedExtractionTests.test_regex_fallback_no_fetcher`. |
| [test_graph_retriever.py](test_graph_retriever.py#L79) | `SeedExtractionTests.test_llm_fetcher_used` | `None` | `Any` | Implement `SeedExtractionTests.test_llm_fetcher_used`. |
| [test_graph_retriever.py](test_graph_retriever.py#L91) | `SeedExtractionTests.test_llm_failure_falls_back_to_regex` | `None` | `Any` | Implement `SeedExtractionTests.test_llm_failure_falls_back_to_regex`. |
| [test_graph_retriever.py](test_graph_retriever.py#L99) | `SeedExtractionTests.test_unresolved_seed_skipped` | `None` | `Any` | Implement `SeedExtractionTests.test_unresolved_seed_skipped`. |
| [test_graph_retriever.py](test_graph_retriever.py#L111) | `FusionTests.test_ppr_diffusion_monotonic_chain` | `None` | `Any` | Implement `FusionTests.test_ppr_diffusion_monotonic_chain`. |
| [test_graph_retriever.py](test_graph_retriever.py#L126) | `FusionTests.test_time_channel_recency` | `None` | `Any` | Implement `FusionTests.test_time_channel_recency`. |
| [test_graph_retriever.py](test_graph_retriever.py#L136) | `FusionTests.test_keyword_exact_match_ranks_first` | `None` | `Any` | Implement `FusionTests.test_keyword_exact_match_ranks_first`. |
| [test_graph_retriever.py](test_graph_retriever.py#L144) | `FusionTests.test_embedding_vector_channel` | `None` | `Any` | Implement `FusionTests.test_embedding_vector_channel`. |
| [test_graph_retriever.py](test_graph_retriever.py#L157) | `FusionTests.test_top_k_limit` | `None` | `Any` | Implement `FusionTests.test_top_k_limit`. |
| [test_graph_retriever.py](test_graph_retriever.py#L163) | `FusionTests.test_min_score_filter` | `None` | `Any` | Implement `FusionTests.test_min_score_filter`. |
| [test_graph_retriever.py](test_graph_retriever.py#L171) | `ExpansionTests.test_one_hop_neighbors_and_relations` | `None` | `Any` | Implement `ExpansionTests.test_one_hop_neighbors_and_relations`. |
| [test_graph_retriever.py](test_graph_retriever.py#L190) | `ExpansionTests.test_neighbor_ids_populated` | `None` | `Any` | Implement `ExpansionTests.test_neighbor_ids_populated`. |
| [test_graph_retriever.py](test_graph_retriever.py#L202) | `CommunityTests.test_cached_community_summaries_selected` | `None` | `Any` | Implement `CommunityTests.test_cached_community_summaries_selected`. |
| [test_graph_retriever.py](test_graph_retriever.py#L221) | `CommunityTests.test_on_demand_community_detection` | `None` | `Any` | Implement `CommunityTests.test_on_demand_community_detection`. |
| [test_graph_retriever.py](test_graph_retriever.py#L228) | `CommunityTests.test_communities_disabled` | `None` | `Any` | Implement `CommunityTests.test_communities_disabled`. |
| [test_graph_retriever.py](test_graph_retriever.py#L238) | `RenderTests.test_rendered_block_format` | `None` | `Any` | Implement `RenderTests.test_rendered_block_format`. |
| [test_graph_retriever.py](test_graph_retriever.py#L252) | `RenderTests.test_standalone_render` | `None` | `Any` | Implement `RenderTests.test_standalone_render`. |
| [test_graph_retriever.py](test_graph_retriever.py#L272) | `EmptyGraphTests.test_empty_graph` | `None` | `Any` | Implement `EmptyGraphTests.test_empty_graph`. |
| [test_graph_retriever.py](test_graph_retriever.py#L278) | `EmptyGraphTests.test_blank_query` | `None` | `Any` | Implement `EmptyGraphTests.test_blank_query`. |
| [test_graph_retriever.py](test_graph_retriever.py#L286) | `SerializationTests.test_result_roundtrip` | `None` | `Any` | Implement `SerializationTests.test_result_roundtrip`. |
| [test_graph_semantic.py](test_graph_semantic.py#L19) | `_RecordingFetcher.fetch` | `**kwargs: Any` | `Any` | Implement `_RecordingFetcher.fetch`. |
| [test_graph_semantic.py](test_graph_semantic.py#L28) | `SemanticGraphWorkerTests.test_worker_always_removes_history_and_tools` | `None` | `Any` | Implement `SemanticGraphWorkerTests.test_worker_always_removes_history_and_tools`. |
| [test_graph_semantic.py](test_graph_semantic.py#L41) | `SemanticGraphWorkerTests.test_rerank_uses_only_valid_candidate_ids` | `None` | `Any` | Implement `SemanticGraphWorkerTests.test_rerank_uses_only_valid_candidate_ids`. |
| [test_graph_semantic.py](test_graph_semantic.py#L57) | `SemanticGraphWorkerTests.test_worker_drives_relation_extraction_without_agent_context` | `None` | `Any` | Implement `SemanticGraphWorkerTests.test_worker_drives_relation_extraction_without_agent_context`. |
| [test_graph_semantic.py](test_graph_semantic.py#L74) | `SemanticRerankIntegrationTests.test_valid_rerank_reorders_fused_hits_and_keeps_omitted_candidates` | `None` | `Any` | Implement `SemanticRerankIntegrationTests.test_valid_rerank_reorders_fused_hits_and_keeps_omitted_candidates`. |
| [test_graph_semantic.py](test_graph_semantic.py#L86) | `SemanticRerankIntegrationTests.test_invalid_rerank_keeps_deterministic_order` | `None` | `Any` | Implement `SemanticRerankIntegrationTests.test_invalid_rerank_keeps_deterministic_order`. |
| [test_graph_store.py](test_graph_store.py#L18) | `NormalizeTests.test_casefold_and_space` | `None` | `Any` | Implement `NormalizeTests.test_casefold_and_space`. |
| [test_graph_store.py](test_graph_store.py#L24) | `NormalizeTests.test_type_prefix_avoids_collision` | `None` | `Any` | Implement `NormalizeTests.test_type_prefix_avoids_collision`. |
| [test_graph_store.py](test_graph_store.py#L29) | `NormalizeTests.test_unicode_nfkc` | `None` | `Any` | Implement `NormalizeTests.test_unicode_nfkc`. |
| [test_graph_store.py](test_graph_store.py#L34) | `UpsertEntityTests.setUp` | `None` | `Any` | Implement `UpsertEntityTests.setUp`. |
| [test_graph_store.py](test_graph_store.py#L37) | `UpsertEntityTests.test_insert_and_merge` | `None` | `Any` | Implement `UpsertEntityTests.test_insert_and_merge`. |
| [test_graph_store.py](test_graph_store.py#L46) | `UpsertEntityTests.test_alias_merge` | `None` | `Any` | Implement `UpsertEntityTests.test_alias_merge`. |
| [test_graph_store.py](test_graph_store.py#L53) | `UpsertEntityTests.test_find_by_name` | `None` | `Any` | Implement `UpsertEntityTests.test_find_by_name`. |
| [test_graph_store.py](test_graph_store.py#L58) | `UpsertEntityTests.test_substring_fallback` | `None` | `Any` | Implement `UpsertEntityTests.test_substring_fallback`. |
| [test_graph_store.py](test_graph_store.py#L65) | `RelationTests.setUp` | `None` | `Any` | Implement `RelationTests.setUp`. |
| [test_graph_store.py](test_graph_store.py#L71) | `RelationTests.test_upsert_aggregates` | `None` | `Any` | Implement `RelationTests.test_upsert_aggregates`. |
| [test_graph_store.py](test_graph_store.py#L79) | `RelationTests.test_distinct_relations_kept` | `None` | `Any` | Implement `RelationTests.test_distinct_relations_kept`. |
| [test_graph_store.py](test_graph_store.py#L84) | `RelationTests.test_missing_endpoint_returns_none` | `None` | `Any` | Implement `RelationTests.test_missing_endpoint_returns_none`. |
| [test_graph_store.py](test_graph_store.py#L87) | `RelationTests.test_neighbors_hops` | `None` | `Any` | Implement `RelationTests.test_neighbors_hops`. |
| [test_graph_store.py](test_graph_store.py#L94) | `RelationTests.test_invalidate` | `None` | `Any` | Implement `RelationTests.test_invalidate`. |
| [test_graph_store.py](test_graph_store.py#L101) | `PPRTests.test_pagerank_seed_dominates` | `None` | `Any` | Implement `PPRTests.test_pagerank_seed_dominates`. |
| [test_graph_store.py](test_graph_store.py#L116) | `PPRTests.test_pagerank_isolated` | `None` | `Any` | Implement `PPRTests.test_pagerank_isolated`. |
| [test_graph_store.py](test_graph_store.py#L121) | `CommunityTests.test_louvain_two_clusters` | `None` | `Any` | Implement `CommunityTests.test_louvain_two_clusters`. |
| [test_graph_store.py](test_graph_store.py#L138) | `TimeDecayTests.test_decay_monotonic` | `None` | `Any` | Implement `TimeDecayTests.test_decay_monotonic`. |
| [test_graph_store.py](test_graph_store.py#L142) | `TimeDecayTests.test_decay_range` | `None` | `Any` | Implement `TimeDecayTests.test_decay_range`. |
| [test_graph_store.py](test_graph_store.py#L147) | `SerializationTests.test_roundtrip` | `None` | `Any` | Implement `SerializationTests.test_roundtrip`. |
| [test_graph_store.py](test_graph_store.py#L161) | `SerializationTests.test_save_load` | `None` | `Any` | Implement `SerializationTests.test_save_load`. |
| [test_graph_store.py](test_graph_store.py#L174) | `SerializationTests.test_save_failure_keeps_previous_file_and_removes_temporary_file` | `None` | `Any` | Implement `SerializationTests.test_save_failure_keeps_previous_file_and_removes_temporary_file`. |
| [test_mcp_registry.py](test_mcp_registry.py#L13) | `test_registry_encrypts_credentials_and_public_view_is_masked` | `tmp_path: Path, monkeypatch: pytest.MonkeyPatch` | `None` | Never persist or return static headers, env values, or bearer tokens. |
| [test_mcp_registry.py](test_mcp_registry.py#L38) | `test_registry_rejects_legacy_sse_and_forbidden_templates` | `None` | `None` | Allow project expansion only in controlled stdio args and cwd. |
| [test_mcp_registry.py](test_mcp_registry.py#L46) | `test_run_config_rejects_removed_raw_mcp_fields` | `None` | `None` | Force browser clients to use server-side session bindings. |
| [test_mcp_tools.py](test_mcp_tools.py#L53) | `test_stdio_mcp_tools_are_discovered_and_called_without_shell` | `tmp_path: Path` | `None` | Reuse one real stdio process across discovery and repeated tool calls. |
| [test_mcp_tools.py](test_mcp_tools.py#L77) | `test_mcp_rejects_inline_secret_values` | `None` | `None` | Implement `test_mcp_rejects_inline_secret_values`. |
| [test_mcp_tools.py](test_mcp_tools.py#L87) | `test_stdio_mcp_reconnects_only_for_the_call_after_a_disconnect` | `tmp_path: Path` | `None` | Do not replay a failed call; reconnect the server on its next call. |
| [test_mcp_tools.py](test_mcp_tools.py#L109) | `test_desktop_sidecar_collects_official_mcp_client_runtime` | `None` | `None` | Implement `test_desktop_sidecar_collects_official_mcp_client_runtime`. |
| [test_mcp_tools.py](test_mcp_tools.py#L118) | `test_desktop_sidecar_build_uses_a_cross_platform_non_shell_launcher` | `None` | `None` | Implement `test_desktop_sidecar_build_uses_a_cross_platform_non_shell_launcher`. |
| [test_plugin_api.py](test_plugin_api.py#L66) | `_manifest` | `name: str, **overrides: Any` | `dict` | Implement `_manifest`. |
| [test_plugin_api.py](test_plugin_api.py#L79) | `_write_plugin` | `base: Path, name: str, assets: tuple[str, ...]` | `Path` | Implement `_write_plugin`. |
| [test_plugin_api.py](test_plugin_api.py#L99) | `_add_registry_record` | `registry: Any, name: str, enabled: bool, permissions: list[str] \| None` | `dict` | Implement `_add_registry_record`. |
| [test_plugin_api.py](test_plugin_api.py#L116) | `_build_app` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *plugin_names: str` | `tuple[TestClient, PluginManager, dict[str, dict]]` | One enabled plugin per name; returns (client, manager, records). |
| [test_plugin_api.py](test_plugin_api.py#L144) | `_purge_plugin_namespace` | `None` | `Any` | Implement `_purge_plugin_namespace`. |
| [test_plugin_api.py](test_plugin_api.py#L159) | `test_list_exposes_exactly_appendix_d_fields` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_list_exposes_exactly_appendix_d_fields`. |
| [test_plugin_api.py](test_plugin_api.py#L186) | `test_list_excludes_disabled_and_inactive_plugins` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_list_excludes_disabled_and_inactive_plugins`. |
| [test_plugin_api.py](test_plugin_api.py#L207) | `test_detail_adds_permissions_granted` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_detail_adds_permissions_granted`. |
| [test_plugin_api.py](test_plugin_api.py#L221) | `test_detail_unknown_id_404` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_detail_unknown_id_404`. |
| [test_plugin_api.py](test_plugin_api.py#L229) | `test_detail_disabled_plugin_404` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_detail_disabled_plugin_404`. |
| [test_plugin_api.py](test_plugin_api.py#L239) | `test_status_includes_disabled_and_active_plugin_lifecycle` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_status_includes_disabled_and_active_plugin_lifecycle`. |
| [test_plugin_api.py](test_plugin_api.py#L257) | `test_workbench_can_register_a_discovered_plugin_without_executing_it` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | The UI may adopt only manager-discovered local directories. |
| [test_plugin_api.py](test_plugin_api.py#L281) | `test_workbench_can_load_and_unload_plugin_with_permission_confirmation` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Lifecycle controls mount fresh routes and remove them on unload. |
| [test_plugin_api.py](test_plugin_api.py#L324) | `test_plugin_settings_are_persisted_without_exposing_them_in_listing` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_plugin_settings_are_persisted_without_exposing_them_in_listing`. |
| [test_plugin_api.py](test_plugin_api.py#L342) | `test_plugin_settings_reject_credential_shaped_keys` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_plugin_settings_reject_credential_shaped_keys`. |
| [test_plugin_api.py](test_plugin_api.py#L360) | `test_static_asset_served_from_whitelist` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_static_asset_served_from_whitelist`. |
| [test_plugin_api.py](test_plugin_api.py#L375) | `test_static_traversal_attempts_404` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_static_traversal_attempts_404`. |
| [test_plugin_api.py](test_plugin_api.py#L391) | `test_static_existing_but_not_whitelisted_404` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_static_existing_but_not_whitelisted_404`. |
| [test_plugin_api.py](test_plugin_api.py#L401) | `test_static_symlink_escape_404` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_static_symlink_escape_404`. |
| [test_plugin_api.py](test_plugin_api.py#L422) | `test_static_disabled_plugin_404` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_static_disabled_plugin_404`. |
| [test_plugin_api.py](test_plugin_api.py#L437) | `test_plugin_route_isolated_to_its_prefix` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_plugin_route_isolated_to_its_prefix`. |
| [test_plugin_api.py](test_plugin_api.py#L455) | `test_disabled_plugin_routes_not_mounted` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_disabled_plugin_routes_not_mounted`. |
| [test_plugin_api.py](test_plugin_api.py#L474) | `test_rescan_discovers_and_loads_newly_added_plugin` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_rescan_discovers_and_loads_newly_added_plugin`. |
| [test_plugin_api.py](test_plugin_api.py#L498) | `test_rescan_removes_plugin_whose_dir_was_deleted` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_rescan_removes_plugin_whose_dir_was_deleted`. |
| [test_plugin_api.py](test_plugin_api.py#L517) | `test_rescan_noop_returns_empty_summary` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_rescan_noop_returns_empty_summary`. |
| [test_plugin_api.py](test_plugin_api.py#L528) | `test_rescan_never_imports_unregistered_plugin` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_rescan_never_imports_unregistered_plugin`. |
| [test_plugin_autoreload.py](test_plugin_autoreload.py#L32) | `_clear_env` | `monkeypatch: pytest.MonkeyPatch` | `None` | Implement `_clear_env`. |
| [test_plugin_autoreload.py](test_plugin_autoreload.py#L36) | `test_disabled_by_default` | `monkeypatch: pytest.MonkeyPatch` | `None` | Implement `test_disabled_by_default`. |
| [test_plugin_autoreload.py](test_plugin_autoreload.py#L43) | `test_enabled_truthy_values` | `monkeypatch: pytest.MonkeyPatch, value: str` | `None` | Implement `test_enabled_truthy_values`. |
| [test_plugin_autoreload.py](test_plugin_autoreload.py#L49) | `test_disabled_falsey_values` | `monkeypatch: pytest.MonkeyPatch, value: str` | `None` | Implement `test_disabled_falsey_values`. |
| [test_plugin_autoreload.py](test_plugin_autoreload.py#L54) | `test_watcher_polls_rescan_and_stops` | `monkeypatch: pytest.MonkeyPatch` | `None` | Implement `test_watcher_polls_rescan_and_stops`. |
| [test_plugin_autoreload.py](test_plugin_autoreload.py#L75) | `test_watcher_survives_rescan_failure` | `monkeypatch: pytest.MonkeyPatch` | `None` | Implement `test_watcher_survives_rescan_failure`. |
| [test_plugin_autoreload.py](test_plugin_autoreload.py#L92) | `test_start_is_idempotent` | `monkeypatch: pytest.MonkeyPatch` | `None` | Implement `test_start_is_idempotent`. |
| [test_plugin_autoreload.py](test_plugin_autoreload.py#L104) | `test_default_interval_is_positive` | `None` | `None` | Implement `test_default_interval_is_positive`. |
| [test_plugin_bootstrap.py](test_plugin_bootstrap.py#L11) | `_bundle_plugin` | `root: Path, name: str` | `Path` | Implement `_bundle_plugin`. |
| [test_plugin_bootstrap.py](test_plugin_bootstrap.py#L22) | `test_bundled_plugins_are_copied_next_to_workspace_once` | `monkeypatch: Any, tmp_path: Path` | `None` | Implement `test_bundled_plugins_are_copied_next_to_workspace_once`. |
| [test_plugin_bootstrap.py](test_plugin_bootstrap.py#L45) | `test_source_run_without_bundle_is_a_noop` | `monkeypatch: Any, tmp_path: Path` | `None` | Implement `test_source_run_without_bundle_is_a_noop`. |
| [test_plugin_bootstrap.py](test_plugin_bootstrap.py#L50) | `test_packaged_build_includes_starter_plugins` | `None` | `None` | Implement `test_packaged_build_includes_starter_plugins`. |
| [test_plugin_manager.py](test_plugin_manager.py#L40) | `_manifest` | `name: str, **overrides: Any` | `dict` | Implement `_manifest`. |
| [test_plugin_manager.py](test_plugin_manager.py#L52) | `_write_plugin` | `base: Path, name: str, main_src: str, manifest: dict \| None` | `Path` | Implement `_write_plugin`. |
| [test_plugin_manager.py](test_plugin_manager.py#L65) | `_make_manager` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `Any` | A PluginManager over temp tiers with the registry index redirected. |
| [test_plugin_manager.py](test_plugin_manager.py#L76) | `_add_registry_record` | `registry: Any, name: str, enabled: bool, permissions: list[str] \| None` | `dict` | Implement `_add_registry_record`. |
| [test_plugin_manager.py](test_plugin_manager.py#L213) | `_FakeHookHost.add_hook` | `hook: Any` | `None` | Implement `_FakeHookHost.add_hook`. |
| [test_plugin_manager.py](test_plugin_manager.py#L217) | `_FakeHookHost.remove_hook` | `hook: Any` | `None` | Implement `_FakeHookHost.remove_hook`. |
| [test_plugin_manager.py](test_plugin_manager.py#L221) | `_FakeHookHost.emit` | `event_type: str, **kwargs: Any` | `None` | Implement `_FakeHookHost.emit`. |
| [test_plugin_manager.py](test_plugin_manager.py#L236) | `_purge_plugin_namespace` | `None` | `Any` | Drop the runtime ``angelus_plugins`` namespace after every test. |
| [test_plugin_manager.py](test_plugin_manager.py#L257) | `test_discover_scans_two_tiers` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_discover_scans_two_tiers`. |
| [test_plugin_manager.py](test_plugin_manager.py#L271) | `test_workspace_tier_shadows_global_tier` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_workspace_tier_shadows_global_tier`. |
| [test_plugin_manager.py](test_plugin_manager.py#L285) | `test_invalid_manifest_marks_error_and_load_raises` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_invalid_manifest_marks_error_and_load_raises`. |
| [test_plugin_manager.py](test_plugin_manager.py#L304) | `test_unknown_plugin_load_raises` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_unknown_plugin_load_raises`. |
| [test_plugin_manager.py](test_plugin_manager.py#L310) | `test_discover_preserves_lifecycle_across_rediscovery` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_discover_preserves_lifecycle_across_rediscovery`. |
| [test_plugin_manager.py](test_plugin_manager.py#L329) | `test_load_publishes_all_four_registration_kinds` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_load_publishes_all_four_registration_kinds`. |
| [test_plugin_manager.py](test_plugin_manager.py#L364) | `test_namespaced_import_keeps_plugin_modules_isolated` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_namespaced_import_keeps_plugin_modules_isolated`. |
| [test_plugin_manager.py](test_plugin_manager.py#L380) | `test_duplicate_load_does_not_re_setup` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_duplicate_load_does_not_re_setup`. |
| [test_plugin_manager.py](test_plugin_manager.py#L397) | `test_reload_tears_down_and_re_setups` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_reload_tears_down_and_re_setups`. |
| [test_plugin_manager.py](test_plugin_manager.py#L422) | `test_setup_failure_blocks_without_raising` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_setup_failure_blocks_without_raising`. |
| [test_plugin_manager.py](test_plugin_manager.py#L440) | `test_hook_outside_whitelist_blocks_plugin` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_hook_outside_whitelist_blocks_plugin`. |
| [test_plugin_manager.py](test_plugin_manager.py#L453) | `test_teardown_is_idempotent_and_unpublishes` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_teardown_is_idempotent_and_unpublishes`. |
| [test_plugin_manager.py](test_plugin_manager.py#L474) | `test_teardown_purges_plugin_modules` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_teardown_purges_plugin_modules`. |
| [test_plugin_manager.py](test_plugin_manager.py#L493) | `test_load_all_loads_only_registry_enabled` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_load_all_loads_only_registry_enabled`. |
| [test_plugin_manager.py](test_plugin_manager.py#L511) | `test_enable_persists_grants_and_loads` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_enable_persists_grants_and_loads`. |
| [test_plugin_manager.py](test_plugin_manager.py#L526) | `test_enable_without_registry_record_raises` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_enable_without_registry_record_raises`. |
| [test_plugin_manager.py](test_plugin_manager.py#L536) | `test_disable_tears_down_and_persists` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_disable_tears_down_and_persists`. |
| [test_plugin_manager.py](test_plugin_manager.py#L552) | `test_get_status_reports_lifecycle` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_get_status_reports_lifecycle`. |
| [test_plugin_manager.py](test_plugin_manager.py#L584) | `test_failing_hook_is_isolated_and_other_hooks_still_run` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_failing_hook_is_isolated_and_other_hooks_still_run`. |
| [test_plugin_manager.py](test_plugin_manager.py#L610) | `test_example_tool_end_to_end_chain` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_example_tool_end_to_end_chain`. |
| [test_plugin_manager.py](test_plugin_manager.py#L671) | `test_rescan_discovers_and_loads_newly_added_plugin_dir` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_rescan_discovers_and_loads_newly_added_plugin_dir`. |
| [test_plugin_manager.py](test_plugin_manager.py#L693) | `test_rescan_tears_down_plugin_whose_dir_was_removed` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_rescan_tears_down_plugin_whose_dir_was_removed`. |
| [test_plugin_manager.py](test_plugin_manager.py#L714) | `test_rescan_never_imports_unregistered_plugin` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_rescan_never_imports_unregistered_plugin`. |
| [test_plugin_manager.py](test_plugin_manager.py#L732) | `test_rescan_is_idempotent_noop` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Implement `test_rescan_is_idempotent_noop`. |
| [test_plugin_registry.py](test_plugin_registry.py#L25) | `test_plugin_dir_is_parallel_to_workspace` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Plugins resolve beside, rather than inside, the state-root workspace. |
| [test_plugin_registry.py](test_plugin_registry.py#L35) | `test_plugin_dir_explicit_state_root` | `tmp_path: Path` | `None` | Explicit state_root avoids touching the real STATE_ROOT. |
| [test_plugin_registry.py](test_plugin_registry.py#L40) | `test_plugin_dir_env_override` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | ANGELUS_PLUGIN_DIR replaces the application plugin directory. |
| [test_plugin_registry.py](test_plugin_registry.py#L47) | `test_legacy_path_aliases_resolve_to_application_directory` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Older callers cannot accidentally restore a workspace-local directory. |
| [test_plugin_registry.py](test_plugin_registry.py#L59) | `test_ensure_plugin_dir_creates_application_directory` | `tmp_path: Path` | `None` | ensure_plugin_dirs creates the persistent sibling directory. |
| [test_plugin_registry.py](test_plugin_registry.py#L71) | `_valid_manifest` | `None` | `dict` | Implement `_valid_manifest`. |
| [test_plugin_registry.py](test_plugin_registry.py#L93) | `test_valid_manifest_passes` | `None` | `None` | A manifest matching appendix A validates with zero errors. |
| [test_plugin_registry.py](test_plugin_registry.py#L98) | `test_missing_required_fields_report_field_level_errors` | `None` | `None` | Missing name/version/entry each produce their own field error. |
| [test_plugin_registry.py](test_plugin_registry.py#L115) | `test_invalid_permissions_report_field_level_errors` | `None` | `None` | Bad action and missing scope are reported per permission index. |
| [test_plugin_registry.py](test_plugin_registry.py#L130) | `test_unknown_top_level_field_is_rejected` | `None` | `None` | additionalProperties=false: unknown fields are field-level errors. |
| [test_plugin_registry.py](test_plugin_registry.py#L139) | `test_api_version_must_be_one` | `None` | `None` | api_version is a const; anything else is rejected on its field. |
| [test_plugin_registry.py](test_plugin_registry.py#L148) | `test_invalid_name_and_version_patterns` | `None` | `None` | name/version patterns are enforced field-wise. |
| [test_plugin_registry.py](test_plugin_registry.py#L159) | `test_non_object_manifest_is_rejected` | `None` | `None` | Root must be a JSON object. |
| [test_plugin_registry.py](test_plugin_registry.py#L165) | `test_load_manifest_returns_validated_manifest` | `tmp_path: Path` | `None` | load_manifest reads, parses and validates a manifest file. |
| [test_plugin_registry.py](test_plugin_registry.py#L176) | `test_load_manifest_reports_missing_file` | `tmp_path: Path` | `None` | A missing manifest file yields a structured root-level error. |
| [test_plugin_registry.py](test_plugin_registry.py#L183) | `test_load_manifest_reports_invalid_json` | `tmp_path: Path` | `None` | Unparsable JSON yields a structured root-level error. |
| [test_plugin_registry.py](test_plugin_registry.py#L199) | `_patch_registry` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `Path` | Point the registry at a temp file and return its path. |
| [test_plugin_registry.py](test_plugin_registry.py#L206) | `test_empty_registry_read_contract` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | A missing registry file reads back as the canonical empty document. |
| [test_plugin_registry.py](test_plugin_registry.py#L214) | `test_add_and_read_plugin_round_trip` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | add_plugin persists a record that list_plugins/get_plugin can read. |
| [test_plugin_registry.py](test_plugin_registry.py#L236) | `test_atomic_write_leaves_no_tmp_residue` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Writes use .tmp+replace(); no .tmp sibling survives. |
| [test_plugin_registry.py](test_plugin_registry.py#L250) | `test_corrupt_registry_reads_as_empty` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Corrupt JSON degrades to the empty registry instead of raising. |
| [test_plugin_registry.py](test_plugin_registry.py#L258) | `test_set_enabled_writes_permissions_granted_on_first_enable` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | First enable persists install-time granted permissions. |
| [test_plugin_registry.py](test_plugin_registry.py#L275) | `test_set_enabled_does_not_overwrite_existing_grants` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | Later enables keep previously granted permissions untouched. |
| [test_plugin_registry.py](test_plugin_registry.py#L289) | `test_grant_permissions_merges_uniquely` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | grant_permissions appends unique action:scope strings. |
| [test_plugin_registry.py](test_plugin_registry.py#L306) | `test_update_and_remove_plugin` | `monkeypatch: pytest.MonkeyPatch, tmp_path: Path` | `None` | update_plugin applies changes; remove_plugin deletes the record. |
| [test_project_directories.py](test_project_directories.py#L17) | `isolated_state` | `tmp_path: Path` | `Any` | Redirect the mutable session registry and state root for one test. |
| [test_project_directories.py](test_project_directories.py#L37) | `test_new_session_binds_existing_project_but_deletes_only_state` | `isolated_state: Path, tmp_path: Path` | `None` | Registry deletion must never remove files from the selected project. |
| [test_project_directories.py](test_project_directories.py#L63) | `test_legacy_session_uses_internal_directory_as_project` | `isolated_state: Path` | `None` | Records created before project binding preserve their original cwd. |
| [test_project_directories.py](test_project_directories.py#L75) | `test_inactive_legacy_session_can_rebind_to_an_existing_project` | `isolated_state: Path, tmp_path: Path` | `None` | A legacy fallback remains usable until the user explicitly replaces it. |
| [test_project_directories.py](test_project_directories.py#L93) | `test_active_session_cannot_change_project_directory` | `isolated_state: Path, tmp_path: Path` | `None` | A running Agent must not have its working directory changed mid-turn. |
| [test_project_directories.py](test_project_directories.py#L114) | `test_project_path_rejects_relative_or_missing_directories` | `value: str` | `None` | A prompt string cannot substitute for a real existing project root. |
| [test_project_directories.py](test_project_directories.py#L120) | `test_agent_shell_and_prompt_use_registered_project` | `isolated_state: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch` | `None` | The backend-enforced Shell cwd and explanatory prompt use one path. |
| [test_project_directories.py](test_project_directories.py#L141) | `test_native_picker_returns_canonical_path_or_cancellation` | `tmp_path: Path, monkeypatch: pytest.MonkeyPatch` | `None` | The loopback picker distinguishes a selected folder from cancellation. |
| [test_project_directories.py](test_project_directories.py#L165) | `test_native_picker_rejects_remote_clients` | `None` | `None` | A network client cannot make the backend open host GUI windows. |
| [test_provider_adapters.py](test_provider_adapters.py#L22) | `test_kimi_code_resolves_to_openai_compatible_backend_and_official_endpoint` | `None` | `None` | Kimi Code needs no fake LLMFetcher backend provider. |
| [test_provider_adapters.py](test_provider_adapters.py#L31) | `test_kimi_adapter_is_used_by_agent_and_manual_compaction` | `None` | `None` | Every browser-created model request shares the same adapter. |
| [test_provider_adapters.py](test_provider_adapters.py#L44) | `test_kimi_fetcher_forces_the_only_supported_temperature_everywhere` | `None` | `None` | Internal graph/compaction fetches cannot leak a non-Kimi temperature. |
| [test_provider_adapters.py](test_provider_adapters.py#L60) | `test_kimi_adapter_is_visible_and_profiled_without_exposing_credentials` | `None` | `None` | The UI can discover Kimi while persisted run provenance remains safe. |
| [test_retrieved_context.py](test_retrieved_context.py#L18) | `RetrievedContextHandlerTests.test_extract_json_from_fenced_block` | `None` | `None` | Implement `RetrievedContextHandlerTests.test_extract_json_from_fenced_block`. |
| [test_retrieved_context.py](test_retrieved_context.py#L22) | `RetrievedContextHandlerTests.test_extract_json_nested_braces` | `None` | `None` | Implement `RetrievedContextHandlerTests.test_extract_json_nested_braces`. |
| [test_retrieved_context.py](test_retrieved_context.py#L28) | `RetrievedContextHandlerTests.test_extract_json_raises_on_no_braces` | `None` | `None` | Implement `RetrievedContextHandlerTests.test_extract_json_raises_on_no_braces`. |
| [test_retrieved_context.py](test_retrieved_context.py#L34) | `RetrievedContextHandlerTests.test_parse_session_file_with_frontmatter` | `None` | `None` | Implement `RetrievedContextHandlerTests.test_parse_session_file_with_frontmatter`. |
| [test_retrieved_context.py](test_retrieved_context.py#L60) | `RetrievedContextHandlerTests.test_parse_session_file_missing_file_returns_none` | `None` | `None` | Implement `RetrievedContextHandlerTests.test_parse_session_file_missing_file_returns_none`. |
| [test_retrieved_context.py](test_retrieved_context.py#L66) | `RetrievedContextHandlerTests.test_parse_session_file_no_frontmatter` | `None` | `None` | Implement `RetrievedContextHandlerTests.test_parse_session_file_no_frontmatter`. |
| [test_retrieved_context.py](test_retrieved_context.py#L75) | `RetrievedContextHandlerTests.test_messages_to_text_renders_user_and_assistant` | `None` | `None` | Implement `RetrievedContextHandlerTests.test_messages_to_text_renders_user_and_assistant`. |
| [test_retrieved_context.py](test_retrieved_context.py#L96) | `RetrievedContextHandlerTests.test_messages_to_text_skips_retrieved_system_messages` | `None` | `None` | Implement `RetrievedContextHandlerTests.test_messages_to_text_skips_retrieved_system_messages`. |
| [test_retrieved_context.py](test_retrieved_context.py#L115) | `RetrievedContextHandlerTests.test_slugify_converts_to_lowercase_hyphenated` | `None` | `None` | Implement `RetrievedContextHandlerTests.test_slugify_converts_to_lowercase_hyphenated`. |
| [test_retrieved_context.py](test_retrieved_context.py#L121) | `RetrievedContextHandlerTests.test_slugify_handles_special_characters` | `None` | `None` | Implement `RetrievedContextHandlerTests.test_slugify_handles_special_characters`. |
| [test_retrieved_context.py](test_retrieved_context.py#L127) | `RetrievedContextHandlerTests.test_slugify_truncates_long_titles` | `None` | `None` | Implement `RetrievedContextHandlerTests.test_slugify_truncates_long_titles`. |
| [test_retrieved_context.py](test_retrieved_context.py#L134) | `RetrievedContextHandlerTests.test_update_index_creates_new_index_file` | `None` | `None` | Implement `RetrievedContextHandlerTests.test_update_index_creates_new_index_file`. |
| [test_retrieved_context.py](test_retrieved_context.py#L147) | `RetrievedContextHandlerTests.test_update_index_appends_to_existing` | `None` | `None` | Implement `RetrievedContextHandlerTests.test_update_index_appends_to_existing`. |
| [test_retrieved_context.py](test_retrieved_context.py#L165) | `RetrievedContextHandlerTests.test_update_index_replaces_existing_entry` | `None` | `None` | Implement `RetrievedContextHandlerTests.test_update_index_replaces_existing_entry`. |
| [test_retrieved_context.py](test_retrieved_context.py#L186) | `RetrievedContextHandlerTests.test_retrieval_first_message_trigger` | `None` | `None` | Implement `RetrievedContextHandlerTests.test_retrieval_first_message_trigger`. |
| [test_retrieved_context.py](test_retrieved_context.py#L196) | `RetrievedContextHandlerTests.test_retrieval_manual_never_triggers` | `None` | `None` | Implement `RetrievedContextHandlerTests.test_retrieval_manual_never_triggers`. |
| [test_retrieved_context.py](test_retrieved_context.py#L203) | `RetrievedContextHandlerTests.test_retrieval_second_message_does_not_trigger` | `None` | `None` | Implement `RetrievedContextHandlerTests.test_retrieval_second_message_does_not_trigger`. |
| [test_retrieved_context.py](test_retrieved_context.py#L218) | `RetrievedContextHandlerTests.test_create_save_tool_returns_valid_tool` | `None` | `None` | Implement `RetrievedContextHandlerTests.test_create_save_tool_returns_valid_tool`. |
| [test_retrieved_context.py](test_retrieved_context.py#L233) | `RetrievedContextHandlerTests.test_build_messages_injects_retrieved_as_user_role` | `None` | `None` | Implement `RetrievedContextHandlerTests.test_build_messages_injects_retrieved_as_user_role`. |
| [test_retrieved_context.py](test_retrieved_context.py#L256) | `RetrievedContextHandlerTests.test_build_messages_no_retrieved_just_linear` | `None` | `None` | Implement `RetrievedContextHandlerTests.test_build_messages_no_retrieved_just_linear`. |
| [test_retrieved_context.py](test_retrieved_context.py#L269) | `_FakeLinear.build_messages` | `None` | `list[dict[str, str]]` | Implement `_FakeLinear.build_messages`. |
| [test_run_profile_persistence.py](test_run_profile_persistence.py#L25) | `_CompletedAgent.add_hook` | `_hook: object` | `None` | Implement `_CompletedAgent.add_hook`. |
| [test_run_profile_persistence.py](test_run_profile_persistence.py#L28) | `_CompletedAgent.run` | `_message: str, **_kwargs: object` | `LLMOutput` | Implement `_CompletedAgent.run`. |
| [test_run_profile_persistence.py](test_run_profile_persistence.py#L35) | `_ToolLifecycleAgent.add_hook` | `hook: object` | `None` | Implement `_ToolLifecycleAgent.add_hook`. |
| [test_run_profile_persistence.py](test_run_profile_persistence.py#L38) | `_ToolLifecycleAgent.run` | `message: str, **kwargs: object` | `LLMOutput` | Implement `_ToolLifecycleAgent.run`. |
| [test_run_profile_persistence.py](test_run_profile_persistence.py#L52) | `_CompletedSwarm.run` | `_message: str, **_kwargs: object` | `dict[str, LLMOutput]` | Return the coordinator result expected by the browser run route. |
| [test_run_profile_persistence.py](test_run_profile_persistence.py#L60) | `_CompletedSwarm.total_usage` | `None` | `dict[str, int]` | Provide the aggregate usage shape persisted by ``start_run``. |
| [test_run_profile_persistence.py](test_run_profile_persistence.py#L64) | `_CompletedSwarm.finalize_tasks` | `None` | `None` | Match the terminal-cleanup method invoked by the run route. |
| [test_run_profile_persistence.py](test_run_profile_persistence.py#L67) | `_CompletedSwarm.view_snapshot` | `None` | `dict[str, list[object]]` | Return the empty graph shape sufficient for persistence assertions. |
| [test_run_profile_persistence.py](test_run_profile_persistence.py#L78) | `_ImmediateThread.start` | `None` | `None` | Implement `_ImmediateThread.start`. |
| [test_run_profile_persistence.py](test_run_profile_persistence.py#L85) | `RunProfilePersistenceTests.test_runtime_profile_is_stable_and_never_serializes_credentials` | `None` | `None` | A resumed-session diagnosis needs semantics, but not API secrets. |
| [test_run_profile_persistence.py](test_run_profile_persistence.py#L108) | `RunProfilePersistenceTests.test_concurrent_event_appends_remain_complete_json_records` | `None` | `None` | Swarm worker hooks must not interleave their NDJSON records. |
| [test_run_profile_persistence.py](test_run_profile_persistence.py#L132) | `RunProfilePersistenceTests.test_start_run_persists_profile_in_state_and_event_log` | `None` | `None` | Run provenance survives both the active and terminal state rewrite. |
| [test_run_profile_persistence.py](test_run_profile_persistence.py#L168) | `RunProfilePersistenceTests.test_start_run_persists_single_agent_tool_lifecycle_event` | `None` | `None` | Single-Agent hooks must survive serialization into the durable Trace. |
| [test_run_profile_persistence.py](test_run_profile_persistence.py#L200) | `RunProfilePersistenceTests.test_start_run_reuses_completed_swarm_without_rebuilding_agents` | `None` | `None` | A second Swarm turn must run the retained graph instead of replacing it. |
| [test_scoped_run_control.py](test_scoped_run_control.py#L20) | `_BlockingAgent.run` | `message: str, max_rounds: int \| None, control: Any` | `Any` | Wait for release, then honor the supplied cooperative control. |
| [test_scoped_run_control.py](test_scoped_run_control.py#L30) | `test_agent_stop_is_isolated_until_global_stop` | `None` | `None` | Stop one Worker without changing another Worker or the whole run. |
| [test_scoped_run_control.py](test_scoped_run_control.py#L43) | `test_agent_force_stop_sets_only_its_combined_terminal_event` | `None` | `None` | Targeted force-stop leaves independent model cancellation events clear. |
| [test_scoped_run_control.py](test_scoped_run_control.py#L56) | `test_global_stop_reaches_existing_and_future_agent_views` | `None` | `None` | Global control applies to already registered and later scheduled Agents. |
| [test_scoped_run_control.py](test_scoped_run_control.py#L67) | `test_graph_does_not_submit_a_targeted_queued_agent` | `None` | `None` | Cancel queued work while an independent running Agent still completes. |
| [test_scoped_run_control.py](test_scoped_run_control.py#L91) | `test_graph_isolates_a_running_agent_stop` | `None` | `None` | Let an independent Worker finish after its peer stops at a boundary. |
| [test_scoped_run_control.py](test_scoped_run_control.py#L113) | `test_mcp_approval_rejects_without_browser_and_returns_submitted_fields` | `None` | `None` | Fail closed without SSE and avoid retaining elicited values afterward. |
| [test_session_history.py](test_session_history.py#L10) | `test_session_history_returns_display_turns_and_bounded_tool_results` | `None` | `None` | Restore user/assistant text together with persisted tool audit data. |
| [test_session_history.py](test_session_history.py#L30) | `test_session_history_recovers_legacy_structured_tool_result` | `None` | `None` | Legacy ``str(dict)`` tool results must hydrate as structured browser data. |
| [test_session_history.py](test_session_history.py#L52) | `test_event_history_keeps_raw_stdout_as_text` | `None` | `None` | A bracketed stdout line must not be misclassified as structured JSON. |
| [test_session_history.py](test_session_history.py#L60) | `test_context_path_creates_agent_context_directory` | `None` | `None` | Provision the parent directory required for Agent context persistence. |
| [test_session_history.py](test_session_history.py#L73) | `test_session_history_falls_back_to_pre_session_directory_context` | `None` | `None` | Restore chats written before per-Agent session directories existed. |
| [test_session_history.py](test_session_history.py#L91) | `test_agent_history_rebuilds_all_runs_and_completed_tools_from_events` | `None` | `None` | Keep every browser prompt after Agent context compaction. |
| [test_session_history.py](test_session_history.py#L130) | `test_aggregate_history_prefers_durable_events_and_restores_steer` | `None` | `None` | The aggregate chat uses its append-only log, not a stale transcript. |
| [test_session_history.py](test_session_history.py#L160) | `test_agent_history_uses_context_when_no_durable_events_exist` | `None` | `None` | Retain compatibility with Agent contexts created before event logs. |
| [test_session_memory.py](test_session_memory.py#L9) | `_tool` | `tools: Any, name: Any` | `Any` | Implement `_tool`. |
| [test_session_memory.py](test_session_memory.py#L13) | `test_cross_session_grants_and_snapshot_evidence` | `tmp_path: Path` | `None` | Implement `test_cross_session_grants_and_snapshot_evidence`. |
| [test_session_memory.py](test_session_memory.py#L33) | `test_artifact_snapshot_and_immutable_handoff` | `tmp_path: Path` | `None` | Implement `test_artifact_snapshot_and_immutable_handoff`. |
| [test_session_observability.py](test_session_observability.py#L16) | `SessionObservabilityTests.test_session_list_exposes_four_state_indicator` | `None` | `None` | Sidebar status is a compact projection of each durable run state. |
| [test_session_observability.py](test_session_observability.py#L48) | `SessionObservabilityTests.test_event_page_is_newest_first_and_usage_uses_round_deltas` | `None` | `None` | Keep historical trace order and avoid cumulative-usage double counts. |
| [test_session_observability.py](test_session_observability.py#L80) | `SessionObservabilityTests.test_event_cursor_pages_backwards_and_skips_incomplete_tail` | `None` | `None` | Trace cursors cover old records while SSE resumes at a complete line. |
| [test_session_observability.py](test_session_observability.py#L110) | `SessionObservabilityTests.test_usage_prefers_canonical_per_call_ledger` | `None` | `None` | The display-only round payload must not double-count ledger calls. |
| [test_session_observability.py](test_session_observability.py#L129) | `SessionObservabilityTests.test_usage_run_tracks_current_lifecycle_and_excludes_steers` | `None` | `None` | The "本次" (run) tile counts the latest run and drops steer work. |
| [test_session_observability.py](test_session_observability.py#L172) | `SessionObservabilityTests.test_orphaned_running_state_becomes_persisted_interruption` | `None` | `None` | Expose a restart-lost worker as a durable, explainable terminal state. |
| [test_session_observability.py](test_session_observability.py#L202) | `SessionObservabilityTests.test_graph_read_reconciles_legacy_states_and_dispatch_edges` | `None` | `None` | Project an old failed graph into precise task and node terminals. |
| [test_session_steers.py](test_session_steers.py#L16) | `SessionSteersTests.test_get_session_steers_returns_applied_instructions_in_order` | `None` | `None` | Reconstruct steer history from the durable append-only event log. |
| [test_session_steers.py](test_session_steers.py#L42) | `SessionSteersTests.test_get_session_steers_ignores_non_steer_and_malformed_events` | `None` | `None` | Skip lifecycle records without an applied-steering payload. |
| [test_shell_tools.py](test_shell_tools.py#L8) | `test_shell_tool_runs_with_popen_pipes` | `None` | `None` | The shell handler must use Popen-compatible stdout/stderr arguments. |
| [test_spike_product_adapters.py](test_spike_product_adapters.py#L42) | `_write` | `tmp_path: Path, lines: list[dict]` | `Path` | Implement `_write`. |
| [test_spike_product_adapters.py](test_spike_product_adapters.py#L48) | `test_claude_adapter_normalizes_user_and_tool_use` | `tmp_path: Any` | `None` | Implement `test_claude_adapter_normalizes_user_and_tool_use`. |
| [test_spike_product_adapters.py](test_spike_product_adapters.py#L60) | `test_codex_adapter_normalizes_tool_round_trip` | `tmp_path: Any` | `None` | Implement `test_codex_adapter_normalizes_tool_round_trip`. |
| [test_spike_product_adapters.py](test_spike_product_adapters.py#L72) | `test_codex_developer_message_is_meta_not_user` | `tmp_path: Any` | `None` | Implement `test_codex_developer_message_is_meta_not_user`. |
| [test_sse_serialization.py](test_sse_serialization.py#L14) | `test_encode_sse_event_normalizes_nested_exception_values` | `None` | `None` | Keep SSE subscribers alive when a live error is an exception instance. |
| [test_sse_stream.py](test_sse_stream.py#L28) | `_seed_events` | `count: int` | `None` | Implement `_seed_events`. |
| [test_sse_stream.py](test_sse_stream.py#L35) | `_payloads` | `chunks: list[str]` | `list[dict]` | Decode data records while ignoring SSE IDs and keepalive comments. |
| [test_sse_stream.py](test_sse_stream.py#L48) | `TestSseStream.test_after_offset_skips_replayed_history` | `None` | `None` | A refresh that already rendered N events must not receive them again. |
| [test_sse_stream.py](test_sse_stream.py#L92) | `TestSseStream.test_no_active_run_replays_tail_and_closes` | `None` | `None` | A finished run must not leave the browser retrying a 404 forever. |
| [test_sse_stream.py](test_sse_stream.py#L107) | `TestSseStream.test_resume_cursor_precedence_and_legacy_count` | `None` | `None` | Last-Event-ID wins over cursor, which wins over legacy after. |
| [test_sse_stream.py](test_sse_stream.py#L133) | `TestSseStream.test_idle_keepalive_does_not_reread_event_log` | `None` | `None` | Idle live connections perform one handoff read, not timed polling. |
| [test_sse_stream.py](test_sse_stream.py#L166) | `_CompactionFetcher.fetch` | `**kwargs: Any` | `Any` | Implement `_CompactionFetcher.fetch`. |
| [test_sse_stream.py](test_sse_stream.py#L185) | `TestCompactionLifecycleStream.test_compaction_events_persist_and_replay_over_sse` | `None` | `None` | A tiny threshold triggers compaction whose events land in events.ndjson. |
| [test_state_root.py](test_state_root.py#L13) | `StateRootTests.test_standalone_project_uses_its_own_workspace` | `None` | `None` | A normal LLMFetcher checkout keeps runtime state in-project. |
| [test_state_root.py](test_state_root.py#L24) | `StateRootTests.test_angelus_submodule_uses_the_superproject_workspace` | `None` | `None` | A registered submodule must recover Angelus sessions by default. |
| [test_swarm_failure_isolation.py](test_swarm_failure_isolation.py#L31) | `_StubAgent.run` | `message: str, max_rounds: int \| None, control: Any` | `Any` | Implement `_StubAgent.run`. |
| [test_swarm_failure_isolation.py](test_swarm_failure_isolation.py#L40) | `SwarmFailureIsolationTests.test_static_graph_failure_is_isolated_and_downstream_skipped` | `None` | `None` | A failing Agent does not cancel siblings; its dependents are skipped. |
| [test_swarm_failure_isolation.py](test_swarm_failure_isolation.py#L63) | `SwarmFailureIsolationTests.test_dispatched_worker_failure_report_reaches_coordinator` | `None` | `None` | A crashing dispatched worker still delivers a failed TaskReport. |
| [test_swarm_restart_recovery.py](test_swarm_restart_recovery.py#L19) | `SwarmRestartRecoveryTests.test_restore_rebuilds_worker_and_task_bus_after_process_restart` | `None` | `None` | A new ``ActiveRun`` restores terminal-ready Swarm topology from disk. |
| [test_swarm_restart_recovery.py](test_swarm_restart_recovery.py#L61) | `SwarmRestartRecoveryTests.test_current_threshold_updates_memory_without_pre_run_checkpoint_write` | `None` | `None` | A new setting must not serialize a fresh handler over old context. |
| [test_task_planning.py](test_task_planning.py#L10) | `test_task_plan_round_trip_and_recursive_status_update` | `None` | `None` | Store nested tasks and update a leaf without losing its plan tree. |
| [test_task_planning.py](test_task_planning.py#L25) | `test_parent_status_is_derived_and_bound_execution_updates_its_ancestors` | `None` | `None` | A Swarm-bound leaf controls derived parent status without false completion. |
| [test_task_planning.py](test_task_planning.py#L51) | `test_stale_execution_event_cannot_replace_revived_assignment` | `None` | `None` | An older worker assignment cannot overwrite the active revived task. |
| [test_task_planning.py](test_task_planning.py#L64) | `test_model_task_id_alias_is_preserved_for_later_swarm_binding` | `None` | `None` | Accept the common tool-argument spelling instead of generating a UUID. |
| [test_task_planning.py](test_task_planning.py#L75) | `test_agent_plan_stores_are_isolated_and_keep_legacy_coordinator_path` | `monkeypatch: Any, tmp_path: Path` | `None` | A worker can replace only its own plan, never the coordinator plan. |
| [test_tlb_rag.py](test_tlb_rag.py#L22) | `PathSafetyTests.setUp` | `None` | `Any` | Implement `PathSafetyTests.setUp`. |
| [test_tlb_rag.py](test_tlb_rag.py#L31) | `PathSafetyTests.tearDown` | `None` | `Any` | Implement `PathSafetyTests.tearDown`. |
| [test_tlb_rag.py](test_tlb_rag.py#L34) | `PathSafetyTests.test_allows_file_inside_root` | `None` | `Any` | Implement `PathSafetyTests.test_allows_file_inside_root`. |
| [test_tlb_rag.py](test_tlb_rag.py#L38) | `PathSafetyTests.test_rejects_sibling_directory_same_prefix` | `None` | `Any` | Implement `PathSafetyTests.test_rejects_sibling_directory_same_prefix`. |
| [test_tlb_rag.py](test_tlb_rag.py#L42) | `PathSafetyTests.test_rejects_parent_traversal` | `None` | `Any` | Implement `PathSafetyTests.test_rejects_parent_traversal`. |
| [test_tlb_rag.py](test_tlb_rag.py#L46) | `PathSafetyTests.test_rejects_absolute_path_outside_root` | `None` | `Any` | Implement `PathSafetyTests.test_rejects_absolute_path_outside_root`. |
| [test_tlb_rag.py](test_tlb_rag.py#L50) | `PathSafetyTests.test_symlink_escape_blocked` | `None` | `Any` | Implement `PathSafetyTests.test_symlink_escape_blocked`. |
| [test_tlb_rag.py](test_tlb_rag.py#L57) | `PathSafetyTests.test_read_file_tool_uses_resolve_inside_root` | `None` | `Any` | Implement `PathSafetyTests.test_read_file_tool_uses_resolve_inside_root`. |
| [test_tlb_rag.py](test_tlb_rag.py#L67) | `ReadTraceTests.setUp` | `None` | `Any` | Implement `ReadTraceTests.setUp`. |
| [test_tlb_rag.py](test_tlb_rag.py#L74) | `ReadTraceTests.tearDown` | `None` | `Any` | Implement `ReadTraceTests.tearDown`. |
| [test_tlb_rag.py](test_tlb_rag.py#L77) | `ReadTraceTests.test_trace_records_successful_reads` | `None` | `Any` | Implement `ReadTraceTests.test_trace_records_successful_reads`. |
| [test_tlb_rag.py](test_tlb_rag.py#L89) | `ReadTraceTests.test_trace_records_failed_reads` | `None` | `Any` | Implement `ReadTraceTests.test_trace_records_failed_reads`. |
| [test_tlb_rag.py](test_tlb_rag.py#L101) | `JSONParseTests.test_braces_in_string_values` | `None` | `Any` | Implement `JSONParseTests.test_braces_in_string_values`. |
| [test_tlb_rag.py](test_tlb_rag.py#L107) | `JSONParseTests.test_nested_json_object` | `None` | `Any` | Implement `JSONParseTests.test_nested_json_object`. |
| [test_tlb_rag.py](test_tlb_rag.py#L113) | `JSONParseTests.test_fenced_block` | `None` | `Any` | Implement `JSONParseTests.test_fenced_block`. |
| [test_tlb_rag.py](test_tlb_rag.py#L119) | `JSONParseTests.test_raises_on_no_json` | `None` | `Any` | Implement `JSONParseTests.test_raises_on_no_json`. |
| [test_tlb_rag.py](test_tlb_rag.py#L123) | `JSONParseTests.test_validate_rejects_invalid_status` | `None` | `Any` | Implement `JSONParseTests.test_validate_rejects_invalid_status`. |
| [test_tlb_rag.py](test_tlb_rag.py#L127) | `JSONParseTests.test_validate_accepts_valid_result` | `None` | `Any` | Implement `JSONParseTests.test_validate_accepts_valid_result`. |
| [test_tlb_rag.py](test_tlb_rag.py#L139) | `JSONParseTests.test_validate_rejects_non_bool_tlb_hit` | `None` | `Any` | Implement `JSONParseTests.test_validate_rejects_non_bool_tlb_hit`. |
| [test_tlb_rag.py](test_tlb_rag.py#L143) | `JSONParseTests.test_validate_rejects_non_list_leaf_files` | `None` | `Any` | Implement `JSONParseTests.test_validate_rejects_non_list_leaf_files`. |
| [test_tlb_rag.py](test_tlb_rag.py#L151) | `QueryKeyTests.test_identical_queries_produce_same_key` | `None` | `Any` | Implement `QueryKeyTests.test_identical_queries_produce_same_key`. |
| [test_tlb_rag.py](test_tlb_rag.py#L156) | `QueryKeyTests.test_unicode_normalization` | `None` | `Any` | Implement `QueryKeyTests.test_unicode_normalization`. |
| [test_tlb_rag.py](test_tlb_rag.py#L161) | `QueryKeyTests.test_case_insensitive` | `None` | `Any` | Implement `QueryKeyTests.test_case_insensitive`. |
| [test_tlb_rag.py](test_tlb_rag.py#L171) | `TLBRAGHandlerCacheTests.setUp` | `None` | `Any` | Implement `TLBRAGHandlerCacheTests.setUp`. |
| [test_tlb_rag.py](test_tlb_rag.py#L178) | `TLBRAGHandlerCacheTests.tearDown` | `None` | `Any` | Implement `TLBRAGHandlerCacheTests.tearDown`. |
| [test_tlb_rag.py](test_tlb_rag.py#L181) | `TLBRAGHandlerCacheTests.test_put_and_validate_cache_entry` | `None` | `Any` | Implement `TLBRAGHandlerCacheTests.test_put_and_validate_cache_entry`. |
| [test_tlb_rag.py](test_tlb_rag.py#L191) | `TLBRAGHandlerCacheTests.test_cache_invalidated_when_file_modified` | `None` | `Any` | Implement `TLBRAGHandlerCacheTests.test_cache_invalidated_when_file_modified`. |
| [test_tlb_rag.py](test_tlb_rag.py#L204) | `TLBRAGHandlerCacheTests.test_public_cache_api_no_direct_dict_access_needed` | `None` | `Any` | Implement `TLBRAGHandlerCacheTests.test_public_cache_api_no_direct_dict_access_needed`. |
| [test_tlb_rag.py](test_tlb_rag.py#L211) | `TLBRAGHandlerCacheTests.test_clear_cache` | `None` | `Any` | Implement `TLBRAGHandlerCacheTests.test_clear_cache`. |
| [test_tlb_rag.py](test_tlb_rag.py#L220) | `_fake_fetcher` | `None` | `Any` | Return a minimal fetcher stub for TLBRAGHandler init (doesn't call fetch). |
| [test_tlb_reliability.py](test_tlb_reliability.py#L24) | `PathSafetyExtendedTests.setUp` | `None` | `Any` | Implement `PathSafetyExtendedTests.setUp`. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L29) | `PathSafetyExtendedTests.tearDown` | `None` | `Any` | Implement `PathSafetyExtendedTests.tearDown`. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L32) | `PathSafetyExtendedTests.test_relative_path_allowed` | `None` | `Any` | Implement `PathSafetyExtendedTests.test_relative_path_allowed`. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L38) | `PathSafetyExtendedTests.test_absolute_path_rejection` | `None` | `Any` | Implement `PathSafetyExtendedTests.test_absolute_path_rejection`. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L42) | `PathSafetyExtendedTests.test_symlink_to_outside_root` | `None` | `Any` | Implement `PathSafetyExtendedTests.test_symlink_to_outside_root`. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L54) | `WorkerLifecycleTests.setUp` | `None` | `Any` | Implement `WorkerLifecycleTests.setUp`. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L60) | `WorkerLifecycleTests.tearDown` | `None` | `Any` | Implement `WorkerLifecycleTests.tearDown`. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L63) | `WorkerLifecycleTests.test_worker_exception_clears_context` | `None` | `Any` | Worker.run exception should not leave context residue. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L86) | `TLBCacheTests.setUp` | `None` | `Any` | Implement `TLBCacheTests.setUp`. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L93) | `TLBCacheTests.tearDown` | `None` | `Any` | Implement `TLBCacheTests.tearDown`. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L96) | `TLBCacheTests.test_cache_entry_put_and_get` | `None` | `Any` | Implement `TLBCacheTests.test_cache_entry_put_and_get`. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L103) | `TLBCacheTests.test_cache_invalidation_on_content_change` | `None` | `Any` | Implement `TLBCacheTests.test_cache_invalidation_on_content_change`. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L110) | `TLBCacheTests.test_cache_invalidation_on_file_deletion` | `None` | `Any` | Implement `TLBCacheTests.test_cache_invalidation_on_file_deletion`. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L117) | `TLBCacheTests.test_public_cache_api` | `None` | `Any` | Implement `TLBCacheTests.test_public_cache_api`. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L123) | `TLBCacheTests.test_clear_cache_returns_count` | `None` | `Any` | Implement `TLBCacheTests.test_clear_cache_returns_count`. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L129) | `TLBCacheTests.test_reject_external_path_in_put` | `None` | `Any` | Implement `TLBCacheTests.test_reject_external_path_in_put`. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L139) | `ReadTraceExtendedTests.setUp` | `None` | `Any` | Implement `ReadTraceExtendedTests.setUp`. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L146) | `ReadTraceExtendedTests.tearDown` | `None` | `Any` | Implement `ReadTraceExtendedTests.tearDown`. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L149) | `ReadTraceExtendedTests.test_trace_index_vs_leaf_detection` | `None` | `Any` | Implement `ReadTraceExtendedTests.test_trace_index_vs_leaf_detection`. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L156) | `ReadTraceExtendedTests.test_trace_hashes_differ_for_different_content` | `None` | `Any` | Implement `ReadTraceExtendedTests.test_trace_hashes_differ_for_different_content`. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L164) | `ReadTraceExtendedTests.test_visited_indexes_from_trace` | `None` | `Any` | P0-D: visited_indexes must come from real trace, not model. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L181) | `ReadTraceExtendedTests.test_unread_leaf_rejected` | `None` | `Any` | P0-D: model reports a leaf that was never actually read. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L200) | `RetrievedContextHandlerReliabilityTests.setUp` | `None` | `Any` | Implement `RetrievedContextHandlerReliabilityTests.setUp`. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L206) | `RetrievedContextHandlerReliabilityTests.tearDown` | `None` | `Any` | Implement `RetrievedContextHandlerReliabilityTests.tearDown`. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L209) | `RetrievedContextHandlerReliabilityTests._make_handler` | `**kw: Any` | `Any` | Implement `RetrievedContextHandlerReliabilityTests._make_handler`. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L215) | `RetrievedContextHandlerReliabilityTests.test_clear_context_resets_all_state` | `None` | `Any` | P0-J. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L226) | `RetrievedContextHandlerReliabilityTests.test_clear_context_preserves_tlb_cache` | `None` | `Any` | P0-J: cross-session TLB cache survives clear_context. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L235) | `RetrievedContextHandlerReliabilityTests.test_retrieved_memory_role_is_not_system` | `None` | `Any` | P0-I. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L246) | `RetrievedContextHandlerReliabilityTests.test_archive_scope_auto_defaults_to_project` | `None` | `Any` | P0-N. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L255) | `RetrievedContextHandlerReliabilityTests.test_archive_scope_none_skips` | `None` | `Any` | Implement `RetrievedContextHandlerReliabilityTests.test_archive_scope_none_skips`. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L259) | `RetrievedContextHandlerReliabilityTests.test_classification_rejects_absolute_path` | `None` | `Any` | P0-P: Guard forces safe fallback for absolute paths. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L271) | `RetrievedContextHandlerReliabilityTests.test_reject_classification_with_parent_traversal` | `None` | `Any` | P0-P: model returns path with '..'. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L280) | `RetrievedContextHandlerReliabilityTests.test_project_user_dedup` | `None` | `Any` | P0-H: same file in project and user does not duplicate. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L297) | `RetrievedContextHandlerReliabilityTests.test_messages_to_text_skips_retrieved` | `None` | `Any` | Implement `RetrievedContextHandlerReliabilityTests.test_messages_to_text_skips_retrieved`. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L305) | `RetrievedContextHandlerReliabilityTests.test_slugify_various` | `None` | `Any` | Implement `RetrievedContextHandlerReliabilityTests.test_slugify_various`. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L312) | `_FakeLinear.build_messages` | `None` | `Any` | Implement `_FakeLinear.build_messages`. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L316) | `_fake_fetcher` | `None` | `Any` | Return a minimal fetcher stub for TLBRAGHandler init (doesn't call fetch). |
| [test_tlb_reliability.py](test_tlb_reliability.py#L321) | `_fake_fetcher_for_retrieve` | `None` | `Any` | Return a fetcher that can create a minimal Agent for retrieve(). |
| [test_tlb_reliability.py](test_tlb_reliability.py#L344) | `_fake_fetcher_returning` | `data: dict` | `Any` | Return a fake fetcher that responds with given JSON. |
| [test_transcript_projection.py](test_transcript_projection.py#L16) | `TranscriptProjectionTests.setUp` | `None` | `None` | Create one isolated session directory for each projection test. |
| [test_transcript_projection.py](test_transcript_projection.py#L24) | `TranscriptProjectionTests.tearDown` | `None` | `None` | Remove the isolated session and its generated projection files. |
| [test_transcript_projection.py](test_transcript_projection.py#L28) | `TranscriptProjectionTests._append` | `events: list[dict]` | `None` | Append complete UTF-8 NDJSON records to the authoritative log. |
| [test_transcript_projection.py](test_transcript_projection.py#L38) | `TranscriptProjectionTests._page` | `agent: str, **kwargs: object` | `dict` | Read a projection page using the temporary absolute partition. |
| [test_transcript_projection.py](test_transcript_projection.py#L50) | `TranscriptProjectionTests.test_pages_450_turns_without_duplicates_or_omissions` | `None` | `None` | Three cursor pages cover every turn exactly once, newest page first. |
| [test_transcript_projection.py](test_transcript_projection.py#L77) | `TranscriptProjectionTests.test_incremental_sync_preserves_projection_prefix` | `None` | `None` | A second read processes only the event tail and keeps prior bytes. |
| [test_transcript_projection.py](test_transcript_projection.py#L100) | `TranscriptProjectionTests.test_uncommitted_projection_tail_is_truncated_before_append` | `None` | `None` | Crash bytes after the committed length never become duplicate turns. |
| [test_transcript_projection.py](test_transcript_projection.py#L113) | `TranscriptProjectionTests.test_truncated_or_rewritten_event_log_rebuilds_projection` | `None` | `None` | A changed authoritative prefix invalidates and replaces cached turns. |
| [test_transcript_projection.py](test_transcript_projection.py#L123) | `TranscriptProjectionTests.test_agent_filter_pairs_tools_and_deduplicates_rounds` | `None` | `None` | Shared prompts, selected tools, steering, and round dedup stay stable. |
| [test_transcript_projection.py](test_transcript_projection.py#L144) | `TranscriptProjectionTests.test_malformed_and_incomplete_lines_do_not_block_future_unicode` | `None` | `None` | Malformed records advance while an incomplete tail waits for completion. |
| [test_web_markdown.py](test_web_markdown.py#L8) | `test_markdown_renders_code_and_escapes_raw_html` | `None` | `None` | Render common Markdown while retaining raw HTML as harmless text. |
| [test_web_markdown.py](test_web_markdown.py#L16) | `test_markdown_renders_gfm_style_tables` | `None` | `None` | Enable the table rule needed for column-aligned model output. |
| [test_web_markdown.py](test_web_markdown.py#L23) | `test_live_agent_round_contains_the_same_safe_markdown_html` | `None` | `None` | SSE round updates use the history renderer rather than plain text. |
| [test_webapp_context_threshold.py](test_webapp_context_threshold.py#L13) | `WebAppContextThresholdTests.test_default_context_threshold_is_262144_characters` | `None` | `None` | Keep the documented default compaction threshold stable. |
| [test_webapp_context_threshold.py](test_webapp_context_threshold.py#L17) | `WebAppContextThresholdTests.test_default_retry_count_is_three_additional_attempts` | `None` | `None` | Keep the browser retry default explicit and independently configurable. |
| [test_webapp_context_threshold.py](test_webapp_context_threshold.py#L21) | `WebAppContextThresholdTests.test_build_agent_uses_browser_context_threshold` | `None` | `None` | Pass browser settings and graph retrieval policy into its handler. |
| [test_webapp_context_threshold.py](test_webapp_context_threshold.py#L35) | `WebAppContextThresholdTests.test_context_threshold_rejects_unusable_values` | `None` | `None` | Reject values too small to retain a useful conversation history. |
| [test_workbench_assets.py](test_workbench_assets.py#L13) | `test_event_listeners_target_existing_template_elements` | `None` | `None` | Keep direct Workbench event listeners aligned with static HTML IDs. |
| [test_workbench_assets.py](test_workbench_assets.py#L24) | `test_workspace_button_opens_current_directory_without_replacing_the_session` | `None` | `None` | The workspace button is a host-file-manager action, not a session switch. |
| [test_workbench_assets.py](test_workbench_assets.py#L37) | `test_active_workbench_uses_component_views_through_an_es_module_entrypoint` | `None` | `None` | Keep the running Workbench on the componentized module path. |
| [test_workbench_assets.py](test_workbench_assets.py#L51) | `test_workbench_uses_the_angelus_mission_control_visual_system` | `None` | `None` | Keep the redesigned brand, responsive shell, and accessibility layer active. |
| [test_workbench_assets.py](test_workbench_assets.py#L67) | `test_task_plan_statuses_are_read_only_and_preserve_real_line_breaks` | `None` | `None` | Render lifecycle-owned states as labels and retain JSON newline layout. |
| [test_workbench_assets.py](test_workbench_assets.py#L80) | `test_tool_payloads_use_structured_json_and_verbatim_stdout_views` | `None` | `None` | Tool call cards must decode JSON escapes without altering raw stdout. |
| [test_workbench_assets.py](test_workbench_assets.py#L97) | `test_live_and_historical_tool_cards_share_the_chat_view_renderer` | `None` | `None` | SSE, aggregate replay, and selected-Agent replay must render one card type. |
| [test_workbench_assets.py](test_workbench_assets.py#L106) | `test_transcript_uses_cursor_pages_and_one_top_scroll_loader` | `None` | `None` | Keep 200-message cursor paging locked, retryable, and viewport-stable. |
| [test_workbench_assets.py](test_workbench_assets.py#L127) | `test_new_session_requires_a_native_selected_project_directory` | `None` | `None` | Keep project files separate from internal session manifests and state. |
| [test_workbench_assets.py](test_workbench_assets.py#L142) | `test_trace_uses_reverse_cursor_and_durable_offset_for_sse` | `None` | `None` | Initial Trace hydration must also establish the byte resume watermark. |
| [test_workbench_assets.py](test_workbench_assets.py#L152) | `test_reasoning_is_visible_transcript_content_not_a_disclosure` | `None` | `None` | Reasoning must be visible for both live and restored message cards. |
| [test_workbench_assets.py](test_workbench_assets.py#L165) | `test_context_graph_dialog_contains_selectable_raw_context_preview` | `None` | `None` | Keep the context inspector's full prompt preview wired to its API route. |
| [test_workbench_assets.py](test_workbench_assets.py#L196) | `test_workbench_uses_the_current_settings_persistence_api` | `None` | `None` | Prevent stale setting helper names from blocking session initialization. |
| [test_workbench_assets.py](test_workbench_assets.py#L208) | `test_settings_categories_use_left_navigation_buttons` | `None` | `None` | Keep each settings navigation category connected to one content pane. |
| [test_workbench_assets.py](test_workbench_assets.py#L220) | `test_memory_authorizations_are_selected_and_sent_as_run_grants` | `None` | `None` | Keep memory grants session-scoped, selectable, and present in run payloads. |
| [test_workbench_assets.py](test_workbench_assets.py#L233) | `test_retry_count_is_session_persisted_and_sent_with_runs` | `None` | `None` | Expose the additional timeout retry count as a saved Agent setting. |
| [test_workbench_assets.py](test_workbench_assets.py#L245) | `test_usage_cards_reuse_reconciled_agent_status_lights` | `None` | `None` | Keep per-Agent usage cards aligned with the canonical status projection. |
| [test_workbench_assets.py](test_workbench_assets.py#L257) | `test_usage_tiles_show_current_lifecycle_tokens_in_green` | `None` | `None` | Each session usage tile and per-Agent card shows the latest run's tokens as a green +X line. |
| [test_workbench_assets.py](test_workbench_assets.py#L270) | `test_running_session_does_not_turn_unknown_agents_into_running_agents` | `None` | `None` | Keep each Agent light tied to evidence, not the session-wide run flag. |
| [test_workbench_assets.py](test_workbench_assets.py#L279) | `test_completed_swarm_is_blue_even_when_a_worker_failed` | `None` | `None` | Represent successful coordinator recovery as a completed aggregate run. |
| [test_workbench_assets.py](test_workbench_assets.py#L292) | `test_agents_panel_renders_only_the_single_topology_tree` | `None` | `None` | Avoid presenting the same Swarm hierarchy twice in the Agents panel. |
| [test_workbench_assets.py](test_workbench_assets.py#L301) | `test_plan_panel_selects_an_agent_owned_plan_and_topology_fills_height` | `None` | `None` | The inspector exposes isolated plans and no longer caps topology height. |
| [test_workbench_assets.py](test_workbench_assets.py#L313) | `test_managed_mcp_console_replaces_browser_json_configuration` | `None` | `None` | Keep MCP configuration in the managed global registry and session grants. |
| [test_workbench_assets.py](test_workbench_assets.py#L328) | `test_light_plan_agent_picker_overrides_the_dark_surface` | `None` | `None` | The plan Agent selector must remain readable in the light theme. |
| [test_workbench_assets.py](test_workbench_assets.py#L336) | `test_kimi_code_connector_preset_survives_provider_refresh` | `None` | `None` | Kimi Code is a named connector choice, not a fragile manual preset. |
| [test_workbench_assets.py](test_workbench_assets.py#L351) | `test_applied_steering_is_a_right_aligned_chat_input` | `None` | `None` | Keep applied steering beside the original user messages in chat. |
| [test_workbench_assets.py](test_workbench_assets.py#L372) | `test_context_dialog_exposes_compaction_input_preview_tab` | `None` | `None` | Keep the third context-dialog tab wired to its read-only API route. |
| [test_workspace_deletion.py](test_workspace_deletion.py#L10) | `test_remove_workspace_deletes_only_its_directory_and_registry_record` | `None` | `None` | Remove a stopped non-default workspace while retaining the default one. |
| [test_workspace_opening.py](test_workspace_opening.py#L11) | `test_open_session_folder_launches_windows_explorer` | `monkeypatch: Any, tmp_path: Path` | `None` | Implement `test_open_session_folder_launches_windows_explorer`. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [test_active_run_reuse.py](test_active_run_reuse.py#L10) | `ActiveRunReuseTests` | `None` | `unittest.TestCase` | Ensure persistent Swarm callbacks keep a valid control object. |
| [test_agent_stop_persistence.py](test_agent_stop_persistence.py#L17) | `_CompletedBoundaryFetcher` | `None` | `object` | Return one completed response without contacting a model provider. |
| [test_agent_stop_persistence.py](test_agent_stop_persistence.py#L36) | `_StopAfterBoundary` | `None` | `object` | Request a cooperative stop at the first Agent safe boundary. |
| [test_agent_stop_persistence.py](test_agent_stop_persistence.py#L48) | `_SecondRoundFailureFetcher` | `None` | `object` | Return a tool call, then fail on the continuation request. |
| [test_agent_stop_persistence.py](test_agent_stop_persistence.py#L72) | `_SteerOnce` | `None` | `object` | Keep the Agent alive for one continuation request. |
| [test_agent_stop_persistence.py](test_agent_stop_persistence.py#L88) | `_BlockingFetcher` | `None` | `object` | Block one request until the test releases its simulated provider. |
| [test_agent_stop_persistence.py](test_agent_stop_persistence.py#L119) | `_ForceStopDuringRequest` | `None` | `object` | Expose the optional immediate-stop event used by browser controls. |
| [test_agent_stop_persistence.py](test_agent_stop_persistence.py#L134) | `_CancellingHandler` | `fetcher: LLMFetcher` | `object` | Simulate a transport close that would otherwise look retryable. |
| [test_agent_stop_persistence.py](test_agent_stop_persistence.py#L160) | `AgentStopPersistenceTests` | `None` | `unittest.TestCase` | Verify context and output survive cooperative stops. |
| [test_agent_turns_from_events.py](test_agent_turns_from_events.py#L12) | `AgentTurnsFromEventsTests` | `None` | `unittest.TestCase` | Verify _agent_turns_from_events deduplication and ordering. |
| [test_archive_retrieval.py](test_archive_retrieval.py#L14) | `ArchiveRetrievalTests` | `None` | `unittest.TestCase` | Provide `ArchiveRetrievalTests` behavior. |
| [test_compact.py](test_compact.py#L16) | `FakeFetcher` | `content: str` | `object` | Minimal LLMFetcher stand-in that returns a canned compaction reply. |
| [test_compact.py](test_compact.py#L75) | `TestCompact` | `None` | `object` | Exercise the staged manual-compaction stream. |
| [test_context_archive_api.py](test_context_archive_api.py#L14) | `ContextArchiveApiTests` | `None` | `unittest.TestCase` | Provide `ContextArchiveApiTests` behavior. |
| [test_context_archive_api.py](test_context_archive_api.py#L194) | `CompactionInputPreviewApiTests` | `None` | `unittest.TestCase` | Read-only preview of the exact text the context compactor would send. |
| [test_context_editing.py](test_context_editing.py#L19) | `ContextEditingTests` | `None` | `unittest.TestCase` | Exercise append-only revisions without changing archived evidence. |
| [test_context_stats.py](test_context_stats.py#L46) | `ContextLengthStatsTests` | `None` | `unittest.TestCase` | ``estimate_context_length`` produces spec-compliant size statistics. |
| [test_context_stats.py](test_context_stats.py#L142) | `AgentContextStatsTests` | `None` | `unittest.TestCase` | ``_agent_context_stats`` keeps legacy keys and adds the spec fields. |
| [test_context_stats.py](test_context_stats.py#L250) | `AgentContextPreviewStatsTests` | `None` | `unittest.TestCase` | ``RemoteRequestStats`` from ``_agent_context_preview`` stays complete. |
| [test_execution_graph_persistence.py](test_execution_graph_persistence.py#L29) | `ExecutionGraphPersistenceTests` | `None` | `unittest.TestCase` | Verify graph topology and callback identity survive a disk round trip. |
| [test_external_codex_provider.py](test_external_codex_provider.py#L13) | `_FakeRuntime` | `None` | `object` | Record fixed provider RPCs without launching a Codex child process. |
| [test_graph_builder.py](test_graph_builder.py#L13) | `_FakeFetcher` | `payload: str, fail: bool` | `object` | Injectable fetcher returning a fixed JSON extraction. |
| [test_graph_builder.py](test_graph_builder.py#L36) | `BuilderLlmTests` | `None` | `unittest.TestCase` | Provide `BuilderLlmTests` behavior. |
| [test_graph_builder.py](test_graph_builder.py#L90) | `BuilderTimelineTests` | `None` | `unittest.TestCase` | Provide `BuilderTimelineTests` behavior. |
| [test_graph_builder.py](test_graph_builder.py#L118) | `RegexExtractionTests` | `None` | `unittest.TestCase` | Provide `RegexExtractionTests` behavior. |
| [test_graph_builder.py](test_graph_builder.py#L135) | `StatsTests` | `None` | `unittest.TestCase` | Provide `StatsTests` behavior. |
| [test_graph_edit_api.py](test_graph_edit_api.py#L31) | `GraphEditApiTests` | `None` | `unittest.TestCase` | Exercise the graph editing toolbar endpoints against a live Swarm. |
| [test_graph_handler.py](test_graph_handler.py#L19) | `_RecordingCompactor` | `None` | `object` | Fake fetcher that returns a valid compaction payload. |
| [test_graph_handler.py](test_graph_handler.py#L37) | `_FakeExtractionFetcher` | `payload: str` | `object` | Fake LLM that returns a fixed entity/relation JSON payload. |
| [test_graph_handler.py](test_graph_handler.py#L51) | `_FakeQueryFetcher` | `payload: str` | `object` | Fake LLM that returns fixed seed entities for a query. |
| [test_graph_handler.py](test_graph_handler.py#L83) | `InitTests` | `None` | `unittest.TestCase` | Provide `InitTests` behavior. |
| [test_graph_handler.py](test_graph_handler.py#L101) | `RetrievalTriggerTests` | `None` | `unittest.TestCase` | Provide `RetrievalTriggerTests` behavior. |
| [test_graph_handler.py](test_graph_handler.py#L239) | `GraphUpdateTests` | `None` | `unittest.TestCase` | Provide `GraphUpdateTests` behavior. |
| [test_graph_handler.py](test_graph_handler.py#L315) | `BuildMessageTests` | `None` | `unittest.TestCase` | Provide `BuildMessageTests` behavior. |
| [test_graph_handler.py](test_graph_handler.py#L358) | `PersistenceTests` | `None` | `unittest.TestCase` | Provide `PersistenceTests` behavior. |
| [test_graph_handler.py](test_graph_handler.py#L449) | `ClearTests` | `None` | `unittest.TestCase` | Provide `ClearTests` behavior. |
| [test_graph_handler.py](test_graph_handler.py#L471) | `RetrieveApiTests` | `None` | `unittest.TestCase` | Provide `RetrieveApiTests` behavior. |
| [test_graph_retriever.py](test_graph_retriever.py#L18) | `_FakeFetcher` | `payload: str, fail: bool` | `object` | Injectable query-fetcher returning a fixed JSON entity list. |
| [test_graph_retriever.py](test_graph_retriever.py#L53) | `RetrievalConfigTests` | `None` | `unittest.TestCase` | Provide `RetrievalConfigTests` behavior. |
| [test_graph_retriever.py](test_graph_retriever.py#L70) | `SeedExtractionTests` | `None` | `unittest.TestCase` | Provide `SeedExtractionTests` behavior. |
| [test_graph_retriever.py](test_graph_retriever.py#L110) | `FusionTests` | `None` | `unittest.TestCase` | Provide `FusionTests` behavior. |
| [test_graph_retriever.py](test_graph_retriever.py#L170) | `ExpansionTests` | `None` | `unittest.TestCase` | Provide `ExpansionTests` behavior. |
| [test_graph_retriever.py](test_graph_retriever.py#L201) | `CommunityTests` | `None` | `unittest.TestCase` | Provide `CommunityTests` behavior. |
| [test_graph_retriever.py](test_graph_retriever.py#L237) | `RenderTests` | `None` | `unittest.TestCase` | Provide `RenderTests` behavior. |
| [test_graph_retriever.py](test_graph_retriever.py#L271) | `EmptyGraphTests` | `None` | `unittest.TestCase` | Provide `EmptyGraphTests` behavior. |
| [test_graph_retriever.py](test_graph_retriever.py#L285) | `SerializationTests` | `None` | `unittest.TestCase` | Provide `SerializationTests` behavior. |
| [test_graph_semantic.py](test_graph_semantic.py#L13) | `_RecordingFetcher` | `replies: list[str], usage: TokenUsage \| None` | `object` | Provide `_RecordingFetcher` behavior. |
| [test_graph_semantic.py](test_graph_semantic.py#L27) | `SemanticGraphWorkerTests` | `None` | `unittest.TestCase` | Provide `SemanticGraphWorkerTests` behavior. |
| [test_graph_semantic.py](test_graph_semantic.py#L73) | `SemanticRerankIntegrationTests` | `None` | `unittest.TestCase` | Provide `SemanticRerankIntegrationTests` behavior. |
| [test_graph_store.py](test_graph_store.py#L17) | `NormalizeTests` | `None` | `unittest.TestCase` | Provide `NormalizeTests` behavior. |
| [test_graph_store.py](test_graph_store.py#L33) | `UpsertEntityTests` | `None` | `unittest.TestCase` | Provide `UpsertEntityTests` behavior. |
| [test_graph_store.py](test_graph_store.py#L64) | `RelationTests` | `None` | `unittest.TestCase` | Provide `RelationTests` behavior. |
| [test_graph_store.py](test_graph_store.py#L100) | `PPRTests` | `None` | `unittest.TestCase` | Provide `PPRTests` behavior. |
| [test_graph_store.py](test_graph_store.py#L120) | `CommunityTests` | `None` | `unittest.TestCase` | Provide `CommunityTests` behavior. |
| [test_graph_store.py](test_graph_store.py#L137) | `TimeDecayTests` | `None` | `unittest.TestCase` | Provide `TimeDecayTests` behavior. |
| [test_graph_store.py](test_graph_store.py#L146) | `SerializationTests` | `None` | `unittest.TestCase` | Provide `SerializationTests` behavior. |
| [test_plugin_manager.py](test_plugin_manager.py#L207) | `_FakeHookHost` | `None` | `object` | Minimal event bus exposing the add_hook/remove_hook contract. |
| [test_retrieved_context.py](test_retrieved_context.py#L13) | `RetrievedContextHandlerTests` | `None` | `unittest.TestCase` | Cover parsing, indexing, triggering, and session serialization. |
| [test_retrieved_context.py](test_retrieved_context.py#L266) | `_FakeLinear` | `None` | `object` | Minimal stub returning one canned message. |
| [test_run_profile_persistence.py](test_run_profile_persistence.py#L20) | `_CompletedAgent` | `None` | `object` | Minimal no-network Agent stand-in for the run persistence boundary. |
| [test_run_profile_persistence.py](test_run_profile_persistence.py#L32) | `_ToolLifecycleAgent` | `None` | `_CompletedAgent` | Emit a tool lifecycle event through the hook registered by ``start_run``. |
| [test_run_profile_persistence.py](test_run_profile_persistence.py#L49) | `_CompletedSwarm` | `None` | `object` | Minimal retained Swarm stand-in for multi-turn run construction tests. |
| [test_run_profile_persistence.py](test_run_profile_persistence.py#L72) | `_ImmediateThread` | `target: object, **_kwargs: object` | `object` | Execute a worker target synchronously while retaining Thread's start API. |
| [test_run_profile_persistence.py](test_run_profile_persistence.py#L82) | `RunProfilePersistenceTests` | `None` | `unittest.TestCase` | Exercise provenance snapshots and concurrent event durability. |
| [test_scoped_run_control.py](test_scoped_run_control.py#L12) | `_BlockingAgent` | `started: threading.Event, release: threading.Event` | `object` | Minimal graph Agent that can expose scheduling and controlled release. |
| [test_session_observability.py](test_session_observability.py#L13) | `SessionObservabilityTests` | `None` | `unittest.TestCase` | Exercise event pagination and per-Agent token aggregation. |
| [test_session_steers.py](test_session_steers.py#L13) | `SessionSteersTests` | `None` | `unittest.TestCase` | Ensure applied steering instructions survive browser refreshes. |
| [test_sse_serialization.py](test_sse_serialization.py#L10) | `_ProviderFailure` | `None` | `Exception` | Minimal exception type representing a provider callback failure. |
| [test_sse_stream.py](test_sse_stream.py#L45) | `TestSseStream` | `None` | `object` | Exercise after-offset replay and no-active-run behaviour. |
| [test_sse_stream.py](test_sse_stream.py#L157) | `_CompactionFetcher` | `None` | `object` | Return normal replies, and an abstract for compaction requests. |
| [test_sse_stream.py](test_sse_stream.py#L182) | `TestCompactionLifecycleStream` | `None` | `object` | Agent auto-compaction events persist and reach the SSE stream. |
| [test_state_root.py](test_state_root.py#L10) | `StateRootTests` | `None` | `unittest.TestCase` | Verify standalone and Git-submodule workspace defaults. |
| [test_swarm_failure_isolation.py](test_swarm_failure_isolation.py#L18) | `_StubAgent` | `result: str, error: Exception \| None` | `Agent` | Agent whose ``run`` returns a canned value or raises, no network. |
| [test_swarm_failure_isolation.py](test_swarm_failure_isolation.py#L37) | `SwarmFailureIsolationTests` | `None` | `unittest.TestCase` | Verify failures are isolated to the failing Agent. |
| [test_swarm_restart_recovery.py](test_swarm_restart_recovery.py#L16) | `SwarmRestartRecoveryTests` | `None` | `unittest.TestCase` | Verify local snapshots retain graph identities without retaining keys. |
| [test_tlb_rag.py](test_tlb_rag.py#L19) | `PathSafetyTests` | `None` | `unittest.TestCase` | P0-A: resolve_inside_root blocks escapes. |
| [test_tlb_rag.py](test_tlb_rag.py#L64) | `ReadTraceTests` | `None` | `unittest.TestCase` | P0-D: read_file tool records actual reads. |
| [test_tlb_rag.py](test_tlb_rag.py#L98) | `JSONParseTests` | `None` | `unittest.TestCase` | P0-E: JSON parsing handles braces in strings. |
| [test_tlb_rag.py](test_tlb_rag.py#L148) | `QueryKeyTests` | `None` | `unittest.TestCase` | P0-C: deterministic query key normalization. |
| [test_tlb_rag.py](test_tlb_rag.py#L168) | `TLBRAGHandlerCacheTests` | `None` | `unittest.TestCase` | P0-C: runtime TLB cache validation. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L23) | `PathSafetyExtendedTests` | `None` | `unittest.TestCase` | Provide `PathSafetyExtendedTests` behavior. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L53) | `WorkerLifecycleTests` | `None` | `unittest.TestCase` | Provide `WorkerLifecycleTests` behavior. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L85) | `TLBCacheTests` | `None` | `unittest.TestCase` | Provide `TLBCacheTests` behavior. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L138) | `ReadTraceExtendedTests` | `None` | `unittest.TestCase` | Provide `ReadTraceExtendedTests` behavior. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L197) | `RetrievedContextHandlerReliabilityTests` | `None` | `unittest.TestCase` | Test P0-G through P0-L requirements. |
| [test_tlb_reliability.py](test_tlb_reliability.py#L311) | `_FakeLinear` | `None` | `object` | Provide `_FakeLinear` behavior. |
| [test_transcript_projection.py](test_transcript_projection.py#L13) | `TranscriptProjectionTests` | `None` | `unittest.TestCase` | Exercise incremental projection, recovery, filtering, and pagination. |
| [test_webapp_context_threshold.py](test_webapp_context_threshold.py#L10) | `WebAppContextThresholdTests` | `None` | `unittest.TestCase` | Ensure the browser context setting reaches newly built Agents. |

<!-- END GENERATED SYMBOL MAP -->
