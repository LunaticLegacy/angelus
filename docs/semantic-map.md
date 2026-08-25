# Semantic map

## `src-tauri/src/main.rs`

| Symbol | Responsibility | Calls / called by |
| --- | --- | --- |
| `BackendProcess` | Owns the spawned FastAPI child and terminates it during application shutdown. | Managed by `run`; `Drop::drop` calls `Child::kill` and `Child::wait`. |
| `reserve_port` | Obtains an ephemeral loopback TCP port for the backend. | Called by `run`. |
| `backend_command` | Resolves the development Python command or packaged sidecar, adds loopback host/port arguments, and synchronizes `ANGELUS_STATE_DIR` with its legacy alias for the child. | Called by `start_backend`; Python `angelus.storage` consumes the variables before the web app is assembled. |
| `start_backend` | Spawns the backend and polls until its HTTP socket accepts connections. | Called by `run`. |
| `run` | Builds the Tauri application, starts the backend, registers lifecycle state, and creates the native webview. | Called by `main`. |
| `main` | Reports startup errors and exits non-zero. | OS entry point. |

## `scripts/backend_entry.py`

| Symbol | Responsibility | Calls / called by |
| --- | --- | --- |
| module entry point | Prepends the `web` command and delegates remaining arguments to `angelus.cli.main`. | Tauri packaged sidecar. |

## `angelus.storage`

| Symbol | Responsibility | Calls / called by |
| --- | --- | --- |
| `FRONTEND_ROOT` | Selects the source-checkout frontend directory or the PyInstaller extraction directory advertised by `ANGELUS_FRONTEND_ROOT`. | `angelus.webapp.app` and API route assembly. |
| `STATE_ROOT_ENV` / `LEGACY_STATE_ROOT_ENV` | Canonical `ANGELUS_STATE_DIR` plus backwards-compatible `LLMFETCHER_STATE_DIR`; the former wins when both are set. | Read while initializing `STATE_ROOT`; set together by `angelus.cli._configure_state_root` and the Tauri launcher. |

## `angelus.external_agents`

| Symbol | Responsibility | Calls / called by |
| --- | --- | --- |
| `ConversionReport` | Versioned import/transfer fidelity record listing preserved, degraded, omitted, and summarized content. | Created by `canonicalize_events`; serialized by archive/import/transfer APIs. |
| `provider_catalog` / `save_provider` / `runtime_provider` | Exposes the built-in Codex, Claude Code, OpenCode and reserved-provider capability catalog; persists only non-secret connection metadata; accepts browser endpoint configuration only for OpenCode and creates its adapter for a saved loopback endpoint. | Called by `api.external_agents` provider routes. |
| `canonicalize_events` | Converts supported vendor transcript objects into canonical non-executing `external_agent.*` messages/raw events, preserving unknown records. | Called by import preview and commit routes. |
| `build_archive` / `parse_archive` | Writes and securely validates Angelus Session Archive v1 ZIPs; validates paths, symlinks, member/expanded limits, format and event checksums. | Called by archive export, import preview, and import commit routes. |
| `import_events` | Always creates a new project-bound Angelus session, appends canonical events, projects display messages, and persists provenance/loss metadata. | Called by `api.external_agents.commit_import`; calls `storage` event and conversation writers. |
| `lease_link` | Grants or renews a tab-scoped exclusive 60-second external-control lease and returns read-only status to competing tabs. | Called by `api.external_agents.heartbeat_external_lease`. |

## `angelus.external_providers.codex`

| Symbol | Responsibility | Calls / called by |
| --- | --- | --- |
| `CodexAppServerClient` / `CodexAppServerClient._stdout_closed_error` | Owns an App Server stdio JSON-RPC child, allocates request IDs/Futures, drains JSON stdout, captures bounded stderr, routes notifications/server requests, fails pending calls on disconnect, and only restarts explicitly. On EOF it classifies the known read-only local-state startup failure without exposing raw stderr. | Owned by `CodexAppServerRuntime`; calls `asyncio.create_subprocess_exec`; `_read_stdout` calls `_stdout_closed_error`. |
| `CodexAppServerRuntime` | Bridges the persistent async client into the synchronous provider contract on a private event-loop thread and queues canonicalized notifications. | Owned by `CodexAppServerProvider`; calls `CodexAppServerClient.request` / `stop`. |
| `CodexAppServerProvider` | Implements fixed, capability-gated Codex discovery, thread/turn control, diff, approval, and subscription operations without generic RPC passthrough. | Registered by the external-provider bootstrap; calls `CodexAppServerRuntime.call`. |

## `angelus.external_providers`

| Symbol | Responsibility | Calls / called by |
| --- | --- | --- |
| `ExternalAgentProvider` | Private fixed-action adapter contract for discovery, reads, owned session lifecycle, subscriptions, diff, and approval; it deliberately rejects generic vendor-protocol pass-through. | Implemented by Codex, OpenCode, and Claude Code adapters; stored in `ExternalProviderRegistry`. |
| `ExternalSession` / `ExternalEvent` | Credential-free provider-neutral descriptors and canonical event envelopes; raw vendor events remain private to synchronization callers. | Returned by provider discovery/read/subscription methods. |
| `ExternalProviderRegistry` / `provider_registry` | Owns registered built-in runtime adapters and exposes their available capability catalog. | Populated during adapter bootstrap; consumed by the External Agent Hub. |
| `bootstrap_builtin_providers` | Lazily instantiates Codex, OpenCode, and Claude Code adapters without spawning their optional runtimes; repeated calls retain the same process-scoped instances. | Called by `external_agents.provider_catalog` and API discovery/action routes. |
| `CodexAppServerClient.initialize` / `CodexAppServerRuntime` / `CodexAppServerProvider.probe` / `api.external_agents.probe_external_provider` | Runs the Codex App Server over stdio JSON-RPC with request futures, mandatory ordered `initialize`/`initialized` handshake, notifications/server requests, stderr monitoring, restart and no-write-replay semantics; the provider maps only fixed thread/turn actions. A failed probe returns its safe transport reason to the Hub instead of discarding it. | `CodexAppServerClient.request` ensures initialization before each non-handshake RPC; `api.external_agents.probe_external_provider` invokes the fixed probe before discovery; `probeProvider` renders its response. |
| `OpenCodeProvider` | Enforces loopback-or-explicit-auth endpoint policy and maps fixed OpenCode HTTP operations plus cursor-resuming, de-duplicated SSE into canonical events. | Registered by `bootstrap_builtin_providers`; invoked by discovery/action routes. |
| `ClaudeCodeProvider` | Inspects Claude transcript JSONL read-only and runs CLI `stream-json` only for Angelus-owned processes; discovered external sessions are never attached or controlled. | Registered by `bootstrap_builtin_providers`; invoked by discovery/action routes. |

## `angelus.api.external_agents`

| Symbol | Responsibility | Calls / called by |
| --- | --- | --- |
| provider/import/archive/transfer routes | Provides capability discovery, Codex App Server handshake probing, safe local runtime auto-detection, credential-free archive export, import preview/commit, and no-side-effect handoff preview. | Mounted by `api.include_api_routes`; calls `angelus.external_agents`. |
| link/lease/action routes | Stores safe Angelus UUID links, enforces exclusive leases, and capability-gates fixed actions without arbitrary vendor protocol pass-through. | Mounted by `api.include_api_routes`; action route intentionally does not execute absent a provider runtime. |
| `external_agent_hub_page` | Serves the isolated External Agent Hub at `/external-agents`, preserving the existing main workbench layout and asset contract. | Calls FastAPI `FileResponse`; its page loads `frontend/static/external-agents.js`. |

## `frontend/static/external-agents.js`

| Symbol | Responsibility | Calls / called by |
| --- | --- | --- |
| `loadProviders` / `autoDetectProviders` / `renderProviderSettings` / `selectProvider` / `saveProvider` / `probeProvider` | Fetches and renders the public Provider catalog, safely detects local Codex/Claude/OpenCode availability, renders only settings supported by the selected Provider, saves only OpenCode's non-secret loopback setting, and makes the Codex probe complete its App Server handshake before discovery. | Called by Hub initialization and Provider card/form controls; calls Provider catalog/auto-detect/config/probe APIs. |
| Hub tutorial listeners | Opens an in-page quick-start dialog describing detection, provider configuration, Codex handshake probing, discovery, lease acquisition, and capability-gated controls. | Called by `#open-hub-tutorial` / `#close-hub-tutorial`; controls `#hub-tutorial`. |
| `discoverSessions` / `linkSession` / `renewLease` / `activateLink` / `renderLink` / `runAction` | Discovers read-only vendor sessions, creates safe Angelus links, maintains a tab-scoped control lease every 20 seconds, and exposes only provider-advertised fixed actions with idempotency keys. | Called by Hub controls; calls discovery, link, lease, and action APIs. |
| `frontend/static/app.js` external-hub listeners | Opens and closes the modal iframe from the Workbench sidebar without navigating away from the current Angelus session. | Called by `#open-external-agent-hub` and `#close-external-agent-hub`; loads `/external-agents` inside `#external-agent-hub-frame`. |

## `angelus.cli`

| Symbol | Responsibility | Calls / called by |
| --- | --- | --- |
| `_configure_state_root(state_dir)` | Resolves `--state-dir` and synchronizes canonical and legacy state-root environment variables before state-owning Angelus modules import. | Called by `main`; its values are consumed by `angelus.storage` and then `angelus.plugin_paths` / `angelus.plugin_registry`. |
| `main(argv)` | Parses control-plane commands, applies the optional state-root selection, and dispatches CLI behavior. | Package and sidecar entry point; calls `_configure_state_root` before command handlers. |

## `frontend/static/components/chat-view.js`

| Symbol | Responsibility | Calls / called by |
| --- | --- | --- |
| `createChatView({ getAgentLabel })` | Builds transcript cards without persisting state. | Called by `frontend/static/app.js`; returns the rendering operations below. |
| `legacyPythonContainerToJson(source)` | Converts only quoted dict/list-like Python literals to JSON text without evaluation, handling quoted escapes and `True`/`False`/`None`. | Called by `decodeJson` for persisted legacy results that strict `JSON.parse` rejects. |
| `decodeJson(value)` / `decodeDisplayString(value)` | Safely unwrap up to three complete JSON-encoded string layers, including verified escaped newlines, and then accept legacy dict/list strings without evaluation. `decodeDisplayString` is scalar-only and never rewrites arbitrary backslash sequences. | `decodeJson` is called by `renderToolPayload`; `decodeDisplayString` is called by `renderJson`; ordinary stdout remains raw when neither parser accepts it. |
| `renderJson(value)` | Produces escaped, nested object/array markup for structured tool payloads, displaying verified JSON line feeds as actual lines. | Called recursively and by `renderToolPayload`; CSS bounds the rendered tree with scrolling. |
| `renderToolPayload(value, emptyText)` | Selects the structured JSON tree or a literal stdout `<pre>` block for tool inputs and outputs. | Called by `renderTools`, which is called by `buildMessage`. |
| `buildMessage(message, agentName)` | Builds the common live/history transcript card. Non-empty reasoning is rendered before the formal answer in an always-visible, bounded scroll region rather than a disclosure control. | Called by `app.js` SSE append and history render paths. |
| `beginStream(agentName)` | Creates a mutable assistant card and safely appends incremental plain-text content and reasoning until the final durable round replaces it. | Called by `app.js::renderStreamDelta`; returns update/remove operations. |

## `frontend/static/app.js`

| Symbol | Responsibility | Calls / called by |
| --- | --- | --- |
| `liveTools(data)` | Normalizes tool lifecycle fields but preserves object/array results instead of coercing them to strings. | Called by `handleEvent`; its output feeds `createChatView` tool-card rendering. |
| `renderStreamDelta(agent, data)` / `discardStream(agent, round)` / `isTraceVisible(event)` | Keeps one pending streamed card per Agent/round, appending SSE deltas in arrival order and removing it before the authoritative final `agent:round` transcript card is rendered. Deltas are live-only (`ephemeral`) transport messages, excluded from durable Trace records and from the event-log offset counter. | Called by `handleEvent` for `agent:stream_delta` and `agent:round`; `loadTrace` filters historical deltas; cleared by `loadHistory`. |

## `angelus.history` package

The former `angelus/history.py` monolith is now a compatibility facade over
`history/models.py`, `history/transcripts.py`, `history/usage.py`, and
`history/context.py`. Existing imports remain stable; each leaf owns one
projection concern and is indexed by `angelus/history/INDEX.md`.

| Symbol | Responsibility | Calls / called by |
| --- | --- | --- |
| `_display_tool_result(value)` | Normalizes new typed events and safely restores JSON or legacy `str(dict)`/`str(list)` results while leaving stdout text intact. | Called by `_read_session_history`, `_turns_from_legacy_context`, and `_display_tools_from_event`; every historical transcript path therefore feeds the shared frontend tool renderer with the same data shape as live SSE. |
| `AgentContextMetadata` / `RemoteRequestStats` / `AgentContextPreview` | Immutable API schemas for message provenance, live request size accounting, and the complete context-inspector response. The envelope fixes response keys while provider/plugin-extensible message and tool payloads remain JSON objects. | Constructed by `_agent_context_preview`; `AgentContextPreview.to_dict` is consumed by `api.sessions.get_agent_context_preview`. |
| `ContextGraphNode` / `ContextGraphEdge` / `ContextGraphCommunity` / `ContextGraphSnapshot` | Immutable, bounded browser schemas for persisted entity, relation, community, and aggregate graph data. | Constructed by `_agent_context_graph`; `ContextGraphSnapshot.to_dict` is consumed by `api.sessions.get_agent_context_graph`. |
| `ContextGraphSnapshot.stale` / `_agent_context_graph(session_id, agent_name, limit)` | Marks the graph unavailable when the active linear context was version-edited, preventing entity relations derived from pre-edit text from being shown as current. | Reads `contexts/<agent>.json` before its graph companion; consumed by `api.sessions.get_agent_context_graph` and `frontend/static/app.js::renderContextGraph`. |
| `_agent_context_preview(session_id, agent_name)` | Builds checkpoint metadata and retrieves the latest credential-free `agent:remote_request` snapshot. When a snapshot exists, its visible messages and metadata are derived from that same request; checkpoint data is never an exact-request fallback. | Called by `api.sessions.get_agent_context_preview`; reads context and event-log files only. |
| `angelus.history._agent_turns_page(...)` | Compatibility facade for the transcript pager; forwards the historic facade-level `_session_path` patch hook into `history.transcripts` for the call. | Existing API/tests call the package facade; delegates to `history.transcripts._agent_turns_page`. |

## `scripts.sync_indexes`

| Symbol | Responsibility | Calls / called by |
| --- | --- | --- |
| `sync_indexes(root, check)` | Regenerates nearest-index Function/Class maps from Python AST and JavaScript/Rust declarations, or reports drift without writes. | Invoked by `scripts/sync_indexes.py`; updates every repository `INDEX.md` generated block. |

## `angelus.context_editing`

| Symbol | Responsibility | Calls / called by |
| --- | --- | --- |
| `ContextRecordRef` / `ContextEditOperation` / `ContextRevision` | Immutable dataclass schema for editable record identity, three allowed operations, and audit/recovery revisions. | Produced by `ContextEditStore.inspect/apply/restore`; serialized to revision snapshots and `context-edits.ndjson`. |
| `ContextEditStore` | Owns one Agent's active checkpoint, atomically creates the first-edit baseline and every later full snapshot, checks optimistic revision IDs, writes append-only audit data, and restores only as a new forward revision. | Constructed by `runtime._build_agent`, `runtime._build_swarm` worker binder, and `api.sessions._editable_context_store`; invalidates the companion graph via `context_editing.graph_stale`. |
| `create_context_editing_tools(store, persist_context, reload_context)` | Exposes inspect/edit/restore tools scoped to the owning Agent. Persist/reload callbacks make a live Agent use a successful mutation immediately. | Added by `_build_agent` and the `create_swarm_tools` worker binder. |

## `angelus.runtime` — Swarm recovery

| Symbol | Responsibility | Calls / called by |
| --- | --- | --- |
| `_persist_swarm_snapshot(swarm, workspace_id, session_id)` | Persists a quiescent `swarm-runtime.json` with local worker prompt blueprints, topology, TaskBus history, and declarative callbacks; excludes API keys and connector secrets. | Called by `api.runs.start_run` terminal cleanup after `finalize_tasks`; delegates to `AgentSwarm.save`. |
| `_restore_swarm(config, workspace_id, session_id, active)` | Reconstructs a stopped Swarm after a process restart using the current request's ephemeral provider credentials plus the local blueprint. Reattaches coordinator control tools, worker report tools, and observers. | Called by `api.runs.start_run` only when no in-memory Swarm exists; delegates to `AgentSwarm.load` and `_build_agent`. |
| `_build_agent` / `_enable_optional_agent_controls` / `_attach_swarm_runtime_tools` / `_attach_swarm_observer` / `_synchronize_plan_with_swarm_event` | Enables `stop_turn` and default streaming through post-construction capability checks, so a temporarily older installed LLMFetcher cannot reject new constructor keywords; where the current swarm-tool factory supports them, it also requires each dispatched/revived worker assignment to name a valid coordinator-plan leaf and projects bound TaskBus events back into that plan before SSE persistence. | Called by `_build_swarm` and `_restore_swarm`; introspects `create_swarm_tools` before passing newer optional controls; `TaskPlanStore` derives parent state from updated leaves. |
| `_synchronize_context_threshold` / `_synchronize_swarm_context_threshold` | Applies the current run setting to every participating Agent and saves its context before `Agent.run` reloads the checkpoint, keeping persisted topology stats aligned with the effective compaction threshold. | Called by `api.runs.start_run` on both single-Agent and Swarm paths; delegates to `Agent.set_context_threshold`. |

## `angelus.classes.active_run` / `angelus.classes.browser_run_control`

| Symbol | Responsibility | Calls / called by |
| --- | --- | --- |
| `BrowserRunControl.for_agent(agent)` / `AgentScopedRunControl` | Projects stable global-plus-local cooperative and terminal events for one graph Agent while retaining the original run-wide control ABI. | `ExecutionGraph.run` feature-detects `for_agent`; Agent model I/O and name-bound Shell tools consume the view. |
| `BrowserRunControl.stop(agent)` / `BrowserRunControl.force_stop(agent)` | Targets `all` or one Agent; global flags also affect future views, while local flags leave independent Workers untouched. | Called by `api.runs.stop_run` / `force_stop_run`; `ActiveRun.force_stop` also cancels matching Shell and MCP work. |
| `ActiveRun.register_process(process, agent)` / `ActiveRun.force_stop(agent)` | Tracks Shell ownership and kills only matching process groups for a targeted terminal stop; `all` additionally closes the MCP manager. | Name-bound closures in `runtime._build_agent` and `_worker_tools_for` register processes; run control routes call `force_stop`. |
| `BrowserRunControl.reset()` | Clears terminal stop/force-stop state and stale steering messages without replacing the control object. | Called by `ActiveRun.reset_for_next_turn`; preserves event references captured by shell/tool handlers. |
| `ActiveRun.reset_for_next_turn()` | Reopens a completed in-process Swarm holder in place, preserving graph, Agent instances, and closure identity while replacing the per-turn broadcast broker and process state. | Called by `api.runs.start_run` with the current durable-log byte watermark before a subsequent Swarm turn. |
| `EventBroker` / `EventEnvelope` / `BrokerSnapshot` / `BrokerBatch` | Maintains a bounded, condition-backed broadcast ring with independent subscriber sequences, a durable byte watermark, explicit overflow detection, and terminal wake-up. | Owned by `ActiveRun`; producers call `publish` after durable commit or for ephemeral deltas, while `live_event_stream` calls `snapshot` and `wait_after`. |
| `publish_durable_event(active, workspace_id, session_id, payload)` | Appends and fsyncs one NDJSON record, obtains its end byte offset, then broadcasts the committed payload. | Called by run terminals, single-Agent hooks, Swarm hooks, and plan-change publication; delegates to `storage._append_session_event` and `EventBroker.publish`. |
| `historical_event_stream` / `live_event_stream` / `encode_sse_event` / `_sse_json_fallback` | Replays durable records with byte-offset SSE IDs, atomically hands off to the live ring, waits without disk polling, and falls back to a bounded disk range after ring overflow. Ephemeral records never advance SSE IDs; unexpected callback objects such as provider exceptions are converted to bounded typed text instead of terminating every subscriber. | Called by `api.runs.stream_events`; live clients resume through `Last-Event-ID`, `cursor`, or the legacy `after` count conversion. |
| `ContextHandlerLinear.save/load` | Atomically commits schema-v2 checkpoints with generation and editing metadata; load validates into temporary values before replacing live memory. | Called by `Agent` and composed handlers; corrupt input returns failure without clearing retained state. |
| `GraphContextHandler.save/load` | Writes an immutable generation graph before atomically committing its reference from the primary context; legacy fixed companions remain readable and committed companion failures fail closed. | Called through the `ContextHandler` interface by `Agent`; delegates graph serialization to `GraphStore` and linear state to `ContextHandlerLinear`. |
| `ContextLoadError` / `ContextSaveError` | Make existing-checkpoint corruption and failed safe-boundary commits explicit run failures instead of silently continuing with empty or non-durable state. | Raised by `Agent.run` / `Agent._save_context`; caught by Angelus run execution's normal terminal error path. |

## `angelus.api.sessions`

| Symbol | Responsibility | Calls / called by |
| --- | --- | --- |
| `get_agent_context_preview(session_id, agent_name)` | Serves the selected Agent's complete persisted model-context preview; rejects aggregate `all`. | Browser context viewer calls it from `frontend/static/app.js::loadContextPrompt`; delegates to `_agent_context_preview`. |
| `_editable_context_store` / `inspect_editable_agent_context` / `edit_agent_context` / `restore_agent_context` | Refuse aggregate selections and live browser runs, then expose record inspection, version-checked checkpoint edits, and forward-only recovery through the session API. | HTTP clients call the three `/context/editable`, `/context/edit`, and `/context/restore` routes; delegates to `ContextEditStore`. |
| `start_run(request)` — retained Swarm path | Reuses an in-memory completed `ActiveRun`/`AgentSwarm`; after a server restart it attempts `runtime._restore_swarm` before building a new graph. The execution thread calls `AgentSwarm.run` on the retained or rebuilt object. | Calls `ActiveRun.reset_for_next_turn`, conditionally calls `_restore_swarm`/`_build_swarm`, then calls `AgentSwarm.run`; terminal cleanup persists the recovery snapshot. |

## `angelus.mcp_registry` / `angelus.mcp_tools` / `angelus.api.mcp`

| Symbol | Responsibility | Calls / called by |
| --- | --- | --- |
| `_normalize_server(payload, existing_id)` / `read_servers()` / `write_servers(records)` | Validates stdio or Streamable HTTP definitions, rejects legacy SSE and unsafe templates, and encrypts headers, environment values, Bearer/OAuth credentials before global persistence. | MCP CRUD routes call these under the application state lock; `resolve_session_servers` receives decrypted internal records only. |
| `read_bindings(session_id)` / `write_bindings(session_id, bindings)` / `resolve_session_servers(session_id, project_root)` | Stores session-local server, role, and tool grants; resolves `${project_root}` only in stdio args/cwd at the run boundary and ignores unprobed servers. | `api.mcp` manages grants; `api.runs.start_run` resolves them into `ActiveRun.mcp_servers`. |
| `MCPToolBridge.start()` / `tools_for(agent, allowed)` / `cancel_agent(agent)` / `close()` | Owns a dedicated asyncio loop and one persistent client per server, creates role-filtered synchronous wrappers, attributes in-flight calls for targeted cancellation, and closes all transports at run shutdown. Failed side-effecting calls are not replayed. | `runtime._mcp_tools` creates/reuses the bridge; `ActiveRun.force_stop` cancels calls; run cleanup closes it. |
| `MCPToolBridge.capability_snapshot()` / `read_resource()` / `subscribe_resource()` / `get_prompt()` / `complete()` | Discovers and accesses tools, resources/templates, subscriptions, prompts, and completion through run-persistent clients; roots expose only the bound project. Logging, progress/resource notifications, and connection changes are emitted as MCP Trace events. | Probe uses discovery; run integrations may use the explicit capability methods without rebuilding transports. |
| `ActiveRun.request_mcp_approval()` / `resolve_mcp_approval()` | Rejects sampling/elicitation immediately without a live SSE browser, otherwise emits a display-safe request and waits at most five minutes. Session-remembered sampling approval is supported; elicited values are returned only to the waiting server callback and never retained. | MCP client callbacks call `request_mcp_approval`; the run approval API calls `resolve_mcp_approval` and audits only server, Agent, capability, field names, and decision. |
| `runtime._build_agent::sample_mcp` | Executes an approved sampling request through the current session connector with no tools and caps tokens to the minimum of request, session setting, and 4096. | Installed once on `ActiveRun`; invoked by `MCPToolBridge` only after browser approval. |
| `create_mcp_server` / `update_mcp_server` / `delete_mcp_server` / `probe_mcp_server` | Implements global managed server CRUD, secret-preserving masked updates, temporary capability probing, and public redaction. | Called by `frontend/static/app.js` MCP console. |
| `connect_mcp_oauth` / `callback_mcp_oauth` / `refresh_mcp_oauth` / `disconnect_mcp_oauth` | Applies OAuth state, five-minute expiry, PKCE S256, token exchange/refresh, encrypted token storage, and explicit disconnect. | Called by MCP settings OAuth controls and the configured authorization server callback. |
| `get_mcp_bindings` / `put_mcp_bindings` | Reads or atomically replaces one session's Coordinator/Worker and tool allowlist policy. | Called by `loadMcpConsole`, `saveMcpBinding`, and indirectly consumed at the next run boundary. |

## `llmfetcher.swarm_module.execution_graph` / `task_bus`

| Symbol | Responsibility | Calls / called by |
| --- | --- | --- |
| `ExecutionGraph.run(..., control)` scoped-control path | Resolves `control.for_agent(name)` when available, closes targeted queued tasks before submission, isolates `AgentRunStopped` from unrelated nodes, and skips only dependency downstream. Legacy single controls retain graph-wide behavior. | Called by `AgentSwarm.run`; delegates structured interruption delivery to `TaskBus.interrupt_task`. |
| `TaskBus.interrupt_task(task_id, reporter, reason)` | Submits an `interrupted` report to `reply_to` and wakes waiters so a coordinator never waits for timeout after a targeted stop. | Called by `ExecutionGraph.run` for queued and running dynamic Workers. |

## `frontend/static/app.js` — control and MCP projection

| Symbol | Responsibility | Calls / called by |
| --- | --- | --- |
| `agentStateView(agentId)` / `updateStopAvailability()` | Gives aggregate state the priority running → queued → durable run terminal, preserving a failed Worker's own red indicator, and enables stop only for actionable selected scope. | Agent cards, usage views, graph refresh, and `setRunning` share this projection. |
| `runStop()` / `runForceStop()` | Sends `{agent: selectedAgent}` and presents scope-specific confirmation/status text. | Stop buttons and slash commands call these; backend control routes validate targets. |
| `loadMcpConsole()` / `selectMcpServer()` / `saveMcpServer()` / `saveMcpBinding()` | Renders structured global server forms, masked credentials, OAuth/probe state, capabilities, and current-session role/tool grants without localStorage JSON migration. | Settings navigation loads the console; MCP form and server cards invoke the managed APIs. |
| `openMcpApproval(event)` / `answerMcpApproval(decision)` | Displays server, Agent, sampling token exposure or elicitation field names, and offers one-shot, session-remembered, or reject decisions. Submitted elicitation values are sent only in the approval response. | `handleEvent` opens the dialog for ephemeral `mcp_approval_requested`; the backend emits redacted `mcp_approval_resolved` audit events into Trace. |

## `frontend/static/app.js` — context viewer

| Symbol | Responsibility | Calls / called by |
| --- | --- | --- |
| `decodePromptText(value)` / `selectContextDialogTab(tab)` / `renderContextPrompt(payload)` | `decodePromptText` unwraps only verified complete JSON-string layers, retaining literal backslash sequences in unstructured text while preserving real line feeds. The context functions switch the dialog's top-level entity-graph/context panels and render only a captured remote-request snapshot; when present, its metadata table has the same message source. The near-viewport dialog keeps its chrome fixed; the graph canvas stays fixed-height while its lower entity/detail cards fill remaining height with independent scrolling. | `readablePromptValue` calls `decodePromptText`; tab buttons call `selectContextDialogTab`; `handleEvent` refreshes an open matching dialog on `agent:remote_request`. |
| `loadContextPrompt(agentId)` | Requests the complete persisted model-context shape once, without cursors or pagination. | Called by `openContextGraph`; fetches `api.sessions.get_agent_context_preview`. |

## `frontend/templates/index.html` — Agents inspector

| Element | Responsibility | Calls / called by |
| --- | --- | --- |
| `#inspector-agents .agents-legend` | Explains the delegation-tree indentation, task labels, and that selecting an Agent card opens that Agent’s context viewer. | `frontend/static/app.js::renderAgentTopology` renders the clickable cards. |

## `llmfetcher.agent`

| Symbol | Responsibility | Calls / called by |
| --- | --- | --- |
| `_tool_result_text(value)` | Produces the complete text representation required by the next model round, without formatting a lifecycle event. | Called while building the model-facing `tool_results` map in `Agent.run`. |
| `Agent._build_prompt()` | Returns only the configured system instruction. Registered Tool objects are deliberately excluded because `Agent.run` passes them once through `LLMFetcher.fetch(..., tools=...)` for provider-native schema preparation. | Called by `Agent.run`; regression-covered by `llmfetcher/tests/test_agent_prompt.py`; prevents message-body and top-level `tools` duplication in persisted remote-request snapshots. |
| `AgentRunTermination` / `AgentRunOutcome` | Typed terminal contract for one Agent invocation: formal final response, reserved `stop_turn`, workflow completion, user stop, invalid empty response, or exhausted tool-loop budget. `AgentRunOutcome.to_dict()` emits credential-free lifecycle data. | Produced by `Agent._set_outcome`; observed by host lifecycle consumers and tests. |
| `Agent.add_stop_turn_tool()` / `Agent.request_turn_stop()` / `Agent._create_stop_turn_tool()` | Opt-in registration for the reserved native `stop_turn` tool; it records a request without interrupting sibling calls, and `Agent.run` applies it only after the full tool batch is persisted. Angelus enables it for coordinators and dynamic workers. | Called by the `stop_turn` handler and Angelus runtime; `Agent.run` emits `agent:stop_turn` and terminal outcome. |
| `Agent.run` terminal branch | Uses tool-call presence—not tool-result text—to continue. Formal text without calls completes; blank content without calls becomes `empty_response`; a last-round tool call raises `AgentRunLimitReached` rather than leaking an unfinished response. | Calls `_set_outcome`, persistence, controls, and tool execution; covered by `llmfetcher/tests/test_agent_termination.py`. |
| `LLMFetcher.fetch_stream(..., on_request=None)` / `Agent._stream_model_response` | Captures a credential-free streaming request snapshot, normalizes provider text/thinking/tool-call chunks into a final `LLMOutput`, and emits `agent:stream_delta` text or reasoning events before normal tool/context handling. | Angelus sends deltas through the multi-subscriber `EventBroker` without appending them to `events.ndjson`; `agent:round` remains the durable final record. |
| `Agent.run` tool-completion event | Keeps each raw tool result in `agent:tools_completed`; JSON-compatible values therefore cross the FastAPI/SSE boundary as objects rather than Python `str()` output. | Consumed by Angelus runtime event persistence and `frontend/static/app.js::liveTools`. |
| `Agent.run` remote-request event | Serializes `RemoteRequestSnapshot` into an `agent:remote_request` lifecycle event before each provider attempt. | `LLMFetcher.fetch` calls the typed observer; Angelus history reads the durable event for context preview. |

## `llmfetcher.llm_types` / `llmfetcher.llm_fetcher`

| Symbol | Responsibility | Calls / called by |
| --- | --- | --- |
| `ToolSchema` / `ToolSchema.to_dict()` | Represents either compact first-party `ToolParameter` declarations or a lossless external `raw_schema`; returns a fresh JSON-ready mapping and gives the external schema precedence so MCP nested constraints survive provider delivery. | Constructed by built-in tools and `angelus.mcp_tools.MCPToolBridge.start`; consumed by provider handlers through `Tool` objects. |
| `RemoteRequestSnapshot` | Immutable, credential-free boundary schema for a dispatch-ready remote request: model, provider-neutral messages, generation settings, stream flag, and provider-prepared tool schemas. `to_dict` creates the persisted application payload. | Constructed by `LLMFetcher.fetch`; serialized by `Agent.run`; displayed through `angelus.history.AgentContextPreview`. |
| `LLMFetcher.fetch(..., on_request)` | Invokes the optional typed preflight observer immediately before each provider call, after tool-schema preparation and before provider I/O. | Called by `Agent.run` and direct library consumers; constructs `RemoteRequestSnapshot`. |

## `llmfetcher.tools.spawn_tools`

| Symbol | Responsibility | Calls / called by |
| --- | --- | --- |
| `create_swarm_tools(..., worker_tool_pool, worker_tool_factory=None, worker_tool_binder=None, worker_enable_stop_turn=False, require_plan_task_id=False, plan_task_validator=None, ...)` | Creates coordinator graph-mutation and task-dispatch tools. A supplied name-bound factory returns a fresh worker-local tool set; an optional live-Agent binder then adds handlers needing the constructed worker's context or controls. `worker_enable_stop_turn` gives new workers the reserved terminal tool; optional plan validation requires `dispatch_subagent(s)` and `revive_agent` to carry a valid external leaf ID. | Called by `angelus.runtime._build_swarm`; both `dynamic_add_agent` and `dispatch_subagent(s)` call its binding path before registering a new Agent. |
| `TaskAssignment.plan_task_id` / `TaskPlanStore.bind_execution` / `TaskPlanStore.update_execution_status` | Carries an opaque browser-plan leaf ID through TaskBus snapshots and lifecycle events; binds the active assignment to one leaf, ignores stale revived assignments, and recomputes every parent state instead of cascading fabricated completion. `TaskPlanStore` accepts model-facing `task_id` as an alias for persisted `id` and rejects duplicate IDs. | `ExecutionGraph` forwards the ID to graph hooks; Angelus runtime observes it and emits `plan:execution` after a successful plan write. |
| `renderTaskPlanItem(task, depth)` | Renders leaf task statuses as editable controls and parent statuses as a derived-state badge, reflecting the server invariant that only leaves can be changed directly. | Called by `app.loadPlan`; `TaskPlanStore.update_status` rejects parent mutations. |
| `ExecutionGraph.task_id_for_agent` / `ExecutionGraph.redispatch_task` | Resolves a worker's current assignment and atomically advances a terminal dispatched worker to a newly queued immutable task without replacing its Agent instance or topology. | Exposed by `AgentSwarm`; `spawn_tools.revive_agent` uses it, while dynamic `report_task` handlers resolve the current task ID at call time. |
| `ExecutionGraph.run(message, max_rounds, control)` — retained task filter | Builds each scheduling pass from the retained topology, but excludes dispatched workers whose TaskBus assignment is terminal. | Repeated by persistent `AgentSwarm` browser turns; completed/failed workers remain in `agent_dict` for inspection until explicitly removed or redispatched. |
| `ExecutionGraph.to_snapshot/load` / `AgentSwarm.save/load` | Serializes and reconstructs quiescent topology, agents through application serializers, TaskBus state, and declarative dynamic mapper/router configuration. | Angelus runtime writes and restores `swarm-runtime.json`; custom callback persistence remains opt-in through explicit callback adapters. |
| `create_task_report_tool(swarm, reporter, on_report)` | Creates a worker report handler that resolves the worker's current TaskBus ID at call time, including after revival or restart recovery. | Used by `create_swarm_tools` and `runtime._restore_swarm`. |
| `Agent.set_context_threshold(max_context_threshold, persist=False)` | Updates an Agent's configured and linear/graph-backed compaction threshold, optionally flushing it to the checkpoint before the next run load. | Called by Angelus runtime threshold synchronization; compatible wrappers without this method are skipped rather than blocking a run. |
