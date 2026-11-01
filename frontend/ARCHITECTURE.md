# Desktop frontend boundary

The desktop client is split into two frontiers:

## Presentation frontier (`static/ui/` and `static/components/`)

Owns DOM structure, visual state, accessibility, themes, inspector navigation,
transcript rendering, composer behavior, and responsive layout. It should not
know backend URLs or parse transport envelopes.

## Runtime frontier (`static/runtime/` and `static/api.js`)

Owns REST requests, server-sent events, local persistence, session/run state,
and backend error normalization. It should expose stable methods and events to
the presentation layer rather than manipulating DOM nodes.

`static/app-loader.js` is the browser entry and retries transient module
requests; `static/app.js` remains the composition root while the migration is
underway. It wires the two frontiers and owns cross-feature orchestration. New features
should add transport code under `runtime/` and view code under `ui/` or
`components/`, then connect them from the composition root.

The boundary is implemented by:

- `runtime/backend-bridge.js`: API exports, low-level request access, event-stream adapter, storage adapter
- `runtime/session-api.js`: Session CRUD, message pagination, image upload, and deletion result normalization
- `runtime/connector-api.js`: Connector CRUD operations
- `runtime/plugin-api.js`: Plugin discovery, settings, lifecycle, and rescan requests
- `runtime/mcp-api.js`: MCP server, binding, probe, OAuth, and deletion requests
- `runtime/settings-api.js`: Run profile, preferences, tool registry, and context catalog requests
- `runtime/inspector-api.js`: Graph, workflow, plan, trace, usage, context, and compaction resource requests
- `runtime/run-api.js`: Run start, control, status, and streamed compaction requests
- `ui/shell.js`: DOM lookup, theme persistence, inspector navigation
- `components/session-list.js`: Session list markup and local event binding
- `components/connector-select.js`: Connector option rendering
- `controllers/session-controller.js`: Session identity, list loading, and list actions
- `controllers/connector-controller.js`: Connector loading and persistence orchestration
- `controllers/stream-controller.js`: Transient streamed Chat state and stream cleanup
- `controllers/run-stream-controller.js`: Run graph and lifecycle SSE ownership, cursors, and stale-session guards
- `controllers/plugin-controller.js`: Plugin status, settings, lifecycle confirmation, and asset refresh orchestration
- `controllers/mcp-controller.js`: MCP server and Session binding load/save/delete/probe orchestration
- `controllers/settings-controller.js`: Run profile persistence and settings catalog coordination
- `controllers/run-controller.js`: Session-aware Run commands and Compact stream ownership
- `controllers/inspector-controller.js`: Inspector tab registration, activation, persistence, and loader dispatch
- `controllers/agent-state-controller.js`: Canonical Agent state mapping and acknowledgement persistence
- `components/notes-view.js`: Session-scoped local Notes panel mounted in the right Inspector

`app.js` remains the composition root during migration. It may coordinate
feature state and pass callbacks to components, but active presentation modules
must not construct `fetch` or `EventSource` directly. The `check:frontend`
script enforces this boundary for the mounted frontend surface.

This keeps the current API contract intact while making a future Tauri/native
transport replaceable without reworking the interface.

## Bootstrap and shared resources

`app.js` mounts DOM components and creates Controllers synchronously, but those
objects read shared resources through getters or explicit refresh calls. The
async bootstrap then runs in this order: locale and Inspector chrome, provider
and context catalogs, Session identity, tool registry, Run Profile and
Preferences, Connector choices, Agent/history state, and finally Plugin assets.
Plugin loading is deliberately explicit; importing `plugins.js` only creates
the bridge and no longer starts an asynchronous side effect.

## Localization

`static/i18n.js` loads locale data from `static/locales/*.json`. The selected
locale is stored as `angelusLocale`; unsupported or failed locale loads fall
back to English. Adding a language means adding a JSON file and registering its
locale code in `LOCALE_FILES`, without adding language branches to components.
