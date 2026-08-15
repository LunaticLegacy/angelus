# frontend/static/ — Static Assets INDEX

JavaScript modules and CSS for the Angelus workbench UI.

## Active Runtime

| Entry | Type | Purpose |
|-------|------|---------|
| `app.js` | Classic script | The only JavaScript file currently loaded by `templates/index.html`. It owns bootstrap, session/connector settings, runs and SSE, chat/steer replay, inspector panels, usage, and Agent-swarm topology. |
| `app.css` | File | Styles for the entire workbench: responsive three-column layout, dialogs, sidebar session states, chat, settings, and inspector views. |

`index.html` deliberately cache-versions both active assets. Update those version query strings when a browser-visible change needs an immediate refresh.

## Legacy Module Inventory

The following files form a prior ES-module decomposition. They are **not loaded by the current HTML shell**, so they are useful only as migration/reference material until the active `app.js` is split again. Do not treat their APIs or DOM assumptions as current behavior.

| Entry | Type | Purpose |
|-------|------|---------|
| `inspector/` | Dir | Legacy inspector modules; see its own INDEX for their status |
| `main.js` | ES module | Former bootstrap/wiring entry point |
| `api.js` | ES module | Former REST helper layer |
| `state.js` | ES module | Former in-memory state store |
| `chat.js` | ES module | Former chat and stream rendering layer |
| `sessions.js` | ES module | Former session-list API/UI layer |
| `connectors.js` | ES module | Former connector API layer |
| `settings.js` | ES module | Former browser-local settings layer |
| `events.js` | ES module | Former EventSource wrapper |
| `utils.js` | ES module | Former shared DOM/formatting helpers |

## Active Responsibilities (`app.js`)

| Function | Role |
|----------|------|
| `loadWorkspaces` | Load session registry into sidebar selector |
| `loadHistory` | Load message history for selected agent |
| `loadAllAgentBehavior` | Render aggregate behavior with lifecycle blocks |
| `start` | Submit message, begin SSE stream |
| `handleEvent` | Process live SSE events |
| `appendMessage` | Render a single chat turn |
| `appendAgentBehavior` | Group agent lifecycle events into expandable block |
| `renderAgentSelector` | Build agent filter dropdown from graph evidence |
| `rehydrateSelectedView` | Restore filter state after refresh |
| `switchSession` | Persist the current settings, then restore the selected session's settings and durable views |

It also owns settings-dialog navigation, encrypted connector CRUD calls, persistent session-status rendering, Swarm topology/Agent inspector rendering, and token-ledger presentation. Direct event listeners must target IDs present in `templates/index.html`; `tests/test_workbench_assets.py` enforces that contract.
