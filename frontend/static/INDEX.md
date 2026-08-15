# frontend/static/ — Static Assets INDEX

JavaScript modules and CSS for the Angelus workbench UI.

## Active Runtime

| Entry | Type | Purpose |
|-------|------|---------|
| `app.js` | Classic script | The only JavaScript file currently loaded by `templates/index.html`. It owns bootstrap, session/connector settings, runs and SSE, chat replay (including durable steering inputs), the main-panel steer composer, usage, and Agent-swarm topology. |
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

It also owns settings-dialog navigation, encrypted connector CRUD calls, persistent session-status rendering, Swarm topology/Agent inspector rendering, and token-ledger presentation. The dialog labels connector settings as globally shared and Agent settings as session-local. Its memory-authorisation picker searches and selects other session IDs, persists them with the current session's Agent settings, and sends them as the four run-scoped SessionMemory capability allowlists. The Agent settings include a persisted `max-retries` field: it is the additional timeout retry count, defaults to three, and is sent in every run payload. The dialog uses left-side category buttons (`data-settings-section`) and matching content panes (`data-settings-panel`); `showSettingsSection()` keeps their active and ARIA-selected states synchronized. Usage cards refresh the graph snapshot and reuse `agentStateView()` so their indicator matches the selector, Inspector and graph. The main-panel steer composer replaces the new-task composer while a run is active, while each durable applied instruction is a distinct amber, right-aligned transcript item beside original user messages. Transcript replay renders stored `steer` turns, and live `agent:steer_applied` events use a stable event key to avoid duplicate cards after an SSE reconnect. The Inspector intentionally contains only plan, Agents, Trace and usage; its stored selected-tab value falls back to plan if an older browser preference references the removed steer tab. Its normal stop remains cooperative at a model/tool boundary; its force-stop confirmation and live guidance state that the current model request is interrupted and registered Shell processes are killed. Direct event listeners must target IDs present in `templates/index.html`; `tests/test_workbench_assets.py` enforces that contract.
