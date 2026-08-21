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
| `decodeJson(value)` | Safely unwraps up to three JSON-encoded string layers and then safely accepts legacy dict/list strings, decoding escaped quotes/newlines/Unicode. | Called by `renderToolPayload`; ordinary stdout remains raw when neither parser accepts it. |
| `renderJson(value)` | Produces escaped, nested object/array markup for structured tool payloads. | Called recursively and by `renderToolPayload`; CSS bounds the rendered tree with scrolling. |
| `renderToolPayload(value, emptyText)` | Selects the structured JSON tree or a literal stdout `<pre>` block for tool inputs and outputs. | Called by `renderTools`, which is called by `buildMessage`. |

## `frontend/static/app.js`

| Symbol | Responsibility | Calls / called by |
| --- | --- | --- |
| `liveTools(data)` | Normalizes tool lifecycle fields but preserves object/array results instead of coercing them to strings. | Called by `handleEvent`; its output feeds `createChatView` tool-card rendering. |

## `angelus.history`

| Symbol | Responsibility | Calls / called by |
| --- | --- | --- |
| `_display_tool_result(value)` | Normalizes new typed events and safely restores JSON or legacy `str(dict)`/`str(list)` results while leaving stdout text intact. | Called by `_read_session_history`, `_turns_from_legacy_context`, and `_display_tools_from_event`; every historical transcript path therefore feeds the shared frontend tool renderer with the same data shape as live SSE. |
| `_agent_context_page(session_id, agent_name, before, limit)` | Reads a clamped newest-first page of active persisted context, preserving typed tool arguments/results and returning an older-page cursor. | Called by `api.sessions.get_agent_context_page`; reads a context file only. |

## `angelus.api.sessions`

| Symbol | Responsibility | Calls / called by |
| --- | --- | --- |
| `get_agent_context_page(session_id, agent_name, before, limit)` | Serves one bounded page of the selected Agent's current context; rejects aggregate `all`. | Browser context viewer calls it from `frontend/static/app.js::loadContextPage`; delegates to `_agent_context_page`. |

## `frontend/static/app.js` — context viewer

| Symbol | Responsibility | Calls / called by |
| --- | --- | --- |
| `renderContextPage(payload)` | Converts a page API response into the existing chat cards, so context tool data uses the exact same JSON/stdout renderer as live and historical transcripts. | Called by `loadContextPage`; calls `chatView.buildMessage`. |
| `loadContextPage(agentId, before)` / `changeContextPage(direction)` | Requests 12 active-context entries at a time and maintains older/newer cursors. | Called by `openContextGraph` and the dialog pagination buttons. |

## `llmfetcher.agent`

| Symbol | Responsibility | Calls / called by |
| --- | --- | --- |
| `_tool_result_text(value)` | Produces the complete text representation required by the next model round, without formatting a lifecycle event. | Called while building the model-facing `tool_results` map in `Agent.run`. |
| `Agent.run` tool-completion event | Keeps each raw tool result in `agent:tools_completed`; JSON-compatible values therefore cross the FastAPI/SSE boundary as objects rather than Python `str()` output. | Consumed by Angelus runtime event persistence and `frontend/static/app.js::liveTools`. |
