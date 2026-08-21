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

## `frontend/static/app.js`

| Symbol | Responsibility | Calls / called by |
| --- | --- | --- |
| `liveTools(data)` | Normalizes tool lifecycle fields but preserves object/array results instead of coercing them to strings. | Called by `handleEvent`; its output feeds `createChatView` tool-card rendering. |

## `angelus.history`

| Symbol | Responsibility | Calls / called by |
| --- | --- | --- |
| `_display_tool_result(value)` | Normalizes new typed events and safely restores JSON or legacy `str(dict)`/`str(list)` results while leaving stdout text intact. | Called by `_read_session_history`, `_turns_from_legacy_context`, and `_display_tools_from_event`; every historical transcript path therefore feeds the shared frontend tool renderer with the same data shape as live SSE. |
| `AgentContextMetadata` / `RemoteRequestStats` / `AgentContextPreview` | Immutable API schemas for message provenance, live request size accounting, and the complete context-inspector response. The envelope fixes response keys while provider/plugin-extensible message and tool payloads remain JSON objects. | Constructed by `_agent_context_preview`; `AgentContextPreview.to_dict` is consumed by `api.sessions.get_agent_context_preview`. |
| `ContextGraphNode` / `ContextGraphEdge` / `ContextGraphCommunity` / `ContextGraphSnapshot` | Immutable, bounded browser schemas for persisted entity, relation, community, and aggregate graph data. | Constructed by `_agent_context_graph`; `ContextGraphSnapshot.to_dict` is consumed by `api.sessions.get_agent_context_graph`. |
| `ContextGraphSnapshot.stale` / `_agent_context_graph(session_id, agent_name, limit)` | Marks the graph unavailable when the active linear context was version-edited, preventing entity relations derived from pre-edit text from being shown as current. | Reads `contexts/<agent>.json` before its graph companion; consumed by `api.sessions.get_agent_context_graph` and `frontend/static/app.js::renderContextGraph`. |
| `_agent_context_preview(session_id, agent_name)` | Builds checkpoint metadata and retrieves the latest credential-free `agent:remote_request` snapshot. When a snapshot exists, its visible messages and metadata are derived from that same request; checkpoint data is never an exact-request fallback. | Called by `api.sessions.get_agent_context_preview`; reads context and event-log files only. |

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
| `_attach_swarm_runtime_tools` / `_attach_swarm_observer` | Shares worker factories and event persistence between first construction and recovery. | Called by `_build_swarm` and `_restore_swarm`. |
| `_synchronize_context_threshold` / `_synchronize_swarm_context_threshold` | Applies the current run setting to every participating Agent and saves its context before `Agent.run` reloads the checkpoint, keeping persisted topology stats aligned with the effective compaction threshold. | Called by `api.runs.start_run` on both single-Agent and Swarm paths; delegates to `Agent.set_context_threshold`. |

## `angelus.classes.active_run` / `angelus.classes.browser_run_control`

| Symbol | Responsibility | Calls / called by |
| --- | --- | --- |
| `BrowserRunControl.reset()` | Clears terminal stop/force-stop state and stale steering messages without replacing the control object. | Called by `ActiveRun.reset_for_next_turn`; preserves event references captured by shell/tool handlers. |
| `ActiveRun.reset_for_next_turn()` | Reopens a completed in-process Swarm holder in place, preserving its graph, Agent instances, and closure identity while replacing only per-turn queue/process state. | Called by `api.runs.start_run` before a subsequent Swarm turn in the same session. |

## `angelus.api.sessions`

| Symbol | Responsibility | Calls / called by |
| --- | --- | --- |
| `get_agent_context_preview(session_id, agent_name)` | Serves the selected Agent's complete persisted model-context preview; rejects aggregate `all`. | Browser context viewer calls it from `frontend/static/app.js::loadContextPrompt`; delegates to `_agent_context_preview`. |
| `_editable_context_store` / `inspect_editable_agent_context` / `edit_agent_context` / `restore_agent_context` | Refuse aggregate selections and live browser runs, then expose record inspection, version-checked checkpoint edits, and forward-only recovery through the session API. | HTTP clients call the three `/context/editable`, `/context/edit`, and `/context/restore` routes; delegates to `ContextEditStore`. |
| `start_run(request)` — retained Swarm path | Reuses an in-memory completed `ActiveRun`/`AgentSwarm`; after a server restart it attempts `runtime._restore_swarm` before building a new graph. The execution thread calls `AgentSwarm.run` on the retained or rebuilt object. | Calls `ActiveRun.reset_for_next_turn`, conditionally calls `_restore_swarm`/`_build_swarm`, then calls `AgentSwarm.run`; terminal cleanup persists the recovery snapshot. |

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
| `Agent.run` tool-completion event | Keeps each raw tool result in `agent:tools_completed`; JSON-compatible values therefore cross the FastAPI/SSE boundary as objects rather than Python `str()` output. | Consumed by Angelus runtime event persistence and `frontend/static/app.js::liveTools`. |
| `Agent.run` remote-request event | Serializes `RemoteRequestSnapshot` into an `agent:remote_request` lifecycle event before each provider attempt. | `LLMFetcher.fetch` calls the typed observer; Angelus history reads the durable event for context preview. |

## `llmfetcher.llm_types` / `llmfetcher.llm_fetcher`

| Symbol | Responsibility | Calls / called by |
| --- | --- | --- |
| `RemoteRequestSnapshot` | Immutable, credential-free boundary schema for a dispatch-ready remote request: model, provider-neutral messages, generation settings, stream flag, and provider-prepared tool schemas. `to_dict` creates the persisted application payload. | Constructed by `LLMFetcher.fetch`; serialized by `Agent.run`; displayed through `angelus.history.AgentContextPreview`. |
| `LLMFetcher.fetch(..., on_request)` | Invokes the optional typed preflight observer immediately before each provider call, after tool-schema preparation and before provider I/O. | Called by `Agent.run` and direct library consumers; constructs `RemoteRequestSnapshot`. |

## `llmfetcher.tools.spawn_tools`

| Symbol | Responsibility | Calls / called by |
| --- | --- | --- |
| `create_swarm_tools(..., worker_tool_pool, worker_tool_factory=None, worker_tool_binder=None, ...)` | Creates coordinator graph-mutation and task-dispatch tools. A supplied name-bound factory returns a fresh worker-local tool set; an optional live-Agent binder then adds handlers needing the constructed worker's context or controls. `revive_agent` reuses a terminal worker with a new task record. | Called by `angelus.runtime._build_swarm`; both `dynamic_add_agent` and `dispatch_subagent(s)` call its binding path before registering a new Agent. |
| `ExecutionGraph.task_id_for_agent` / `ExecutionGraph.redispatch_task` | Resolves a worker's current assignment and atomically advances a terminal dispatched worker to a newly queued immutable task without replacing its Agent instance or topology. | Exposed by `AgentSwarm`; `spawn_tools.revive_agent` uses it, while dynamic `report_task` handlers resolve the current task ID at call time. |
| `ExecutionGraph.run(message, max_rounds, control)` — retained task filter | Builds each scheduling pass from the retained topology, but excludes dispatched workers whose TaskBus assignment is terminal. | Repeated by persistent `AgentSwarm` browser turns; completed/failed workers remain in `agent_dict` for inspection until explicitly removed or redispatched. |
| `ExecutionGraph.to_snapshot/load` / `AgentSwarm.save/load` | Serializes and reconstructs quiescent topology, agents through application serializers, TaskBus state, and declarative dynamic mapper/router configuration. | Angelus runtime writes and restores `swarm-runtime.json`; custom callback persistence remains opt-in through explicit callback adapters. |
| `create_task_report_tool(swarm, reporter, on_report)` | Creates a worker report handler that resolves the worker's current TaskBus ID at call time, including after revival or restart recovery. | Used by `create_swarm_tools` and `runtime._restore_swarm`. |
| `Agent.set_context_threshold(max_context_threshold, persist=False)` | Updates an Agent's configured and linear/graph-backed compaction threshold, optionally flushing it to the checkpoint before the next run load. | Called by Angelus runtime threshold synchronization; compatible wrappers without this method are skipped rather than blocking a run. |
