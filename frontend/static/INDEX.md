# frontend/static/ — Static Assets INDEX

JavaScript modules and CSS for the Angelus workbench UI.

## Route Map

| Entry | Type | Purpose |
|-------|------|---------|
| [`inspector/`](inspector/INDEX.md) | Dir | Right-side inspector panels: graph, trace, metrics, plan |
| `app.js` | Module | Main application: session management, run lifecycle, SSE event handling, chat rendering, agent selector |
| `main.js` | Module | Bootstrap: module loading, initialization |
| `api.js` | Module | REST API client: fetch wrappers for all endpoints |
| `state.js` | Module | Client-side state management |
| `chat.js` | Module | Chat pane rendering: message display, tool result formatting |
| `sessions.js` | Module | Session list UI: create, switch, delete |
| `connectors.js` | Module | Connector configuration UI |
| `settings.js` | Module | Run settings panel: model, temperature, max_tokens, swarm toggles |
| `events.js` | Module | SSE event stream handling |
| `utils.js` | Module | Shared utilities: HTML escaping, formatting |
| `app.css` | File | All styles: layout, chat, inspector, settings |

## Key Functions (app.js)

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
