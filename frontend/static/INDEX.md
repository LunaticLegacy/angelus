# frontend/static/ — Browser Runtime INDEX

| File / directory | Responsibility |
|---|---|
| `app-loader.js` | Retryable browser entry that imports the composition root after transient static-request failures. |
| `app.js` | Main workbench state/controller: selected Session, history, settings, Session-run control, image composer wiring and Session-console inspector calls. |
| `app.css` | Workbench visual layout, dialogs, session controls and responsive styling. |
| `plugins.js` | Loads active plugin assets and renders manifest-declared, host-owned Inspector panels with validated action submissions. |
| `components/` | DOM, session list, chat transcript, task-plan, trace, Notes, and External Agent Hub rendering helpers. |
| `controllers/` | Feature coordination for Session, Connector, Chat stream, Run SSE, Agent state, Inspector, Plugin, MCP, and Settings state. |
| `runtime/` | Browser transport boundary and domain API clients for sessions, connectors, settings, Inspector, Run, Plugin, and MCP. |
| `vendor/` | Pinned browser ESM copies of Marked and DOMPurify, including upstream licenses. |
| `api.js` | Low-level JSON transport used by `runtime/backend-bridge.js`; domain calls belong in `runtime/*-api.js`. |

## Phase-1 Controller Route Map

| Intent | `app.js` operation | API |
|---|---|---|
| List/select/create/delete session | `loadWorkspaces`, `switchSession`, `createAndSwitchSession` | `/api/sessions` |
| Read transcript | `loadHistory`, `loadOlderMessages` | `/api/sessions/{id}/messages` |
| Connector CRUD | `loadConnectors`, `createConnector`, `saveSelectedConnector` | `/api/connectors` |
| Profile reads/writes | `restoreSettings`, `persistSettings` | `/api/settings/run-profile`, `/api/sessions/{id}/run-profile` |
| Start/stop | `start`, stop controls | `/api/runs` (`target_agent` for concrete selection) |
| Attach/send image | `createImageComposer` upload, `beginSend` | `/api/sessions/{id}/attachments/images`, `/api/runs` |
| Inspector graph/plan/trace/usage/context | `loadGraph`, `loadPlan`, `loadTrace`, `loadUsage`, context dialog | `/api/sessions/{id}/…` |

Graph removal uses the mounted contracts: Agent removal uses the path identity
route, while connection removal sends its typed source/target JSON body.
The permissions panel exposes only the registered Session-console tools; both
its category and individual Tool switches control actual model tool schemas.

`app.js` must refresh `availableSessions` after creation before membership
validation; otherwise a successful POST appears as an “unknown session”.
Its graph and lifecycle SSE cursors are event counts maintained separately from
the journal byte offset used by Trace pagination. Lifecycle SSE feeds model
deltas directly into chat/Trace; graph SSE remains topology-only.
On an SSE reconnect error, it checks the Session run state and closes the
browser stream once the attempt is terminal.
The MCP console is live against the mounted managed-MCP routes. It edits only
public server metadata, write-only credentials and Session bindings; SDK
transports remain backend-owned.
Plugin discovery errors are terminal in the browser lifecycle UI: an invalid
manifest can be inspected but is never offered a registration or load action.
Plugin settings are manifest-declared user parameters. The mounted editor
renders typed scalar controls, bounded choices, numeric ranges, URI fields,
path hints, and multi-line text areas before the API persists them.
Active tool plugins may also declare transient `frontend.panels`; `plugins.js`
renders their fields and submit buttons inside the Inspector, posts only
declared values to the active plugin action endpoint, and displays textual
results without accepting plugin-supplied HTML.
The Agent settings form persists reply `max_tokens` and the independent
`compaction_output_max_tokens` separately; the latter controls only context
summary responses and is applied when the next Agent lifecycle is materialized.
It also persists the 1–3600 second provider request timeout used by future
coordinator, worker, preview, compaction, and retrieval model calls.
Image drafts live in `components/image-composer.js`, isolated per Session and uploaded as raw bytes; only
`attachment_id` references are sent with a run, and the chat renderer shows durable image URLs (no inline
bytes). While a run is active the composer accepts text steering only and explicitly keeps (never drops)
image drafts for a later run. Agent Markdown is parsed and sanitized only by `components/markdown-renderer.js`;
the active `components/chat-view.js` uses it for both restored and streamed
Agent output. The legacy modular entry and inspector files were removed after migration;
the active entry is `app.js` and the active transcript renderer is `components/chat-view.js`.
