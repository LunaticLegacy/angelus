# frontend/static/ — Browser Runtime INDEX

| File / directory | Responsibility |
|---|---|
| `app.js` | Main workbench state/controller: selected Session, history, settings form, connector/profile calls and legacy inspector wiring. |
| `app.css` | Workbench visual layout, dialogs, session controls and responsive styling. |
| `components/` | DOM, chat transcript, task-plan and trace rendering helpers. |
| `inspector/` | Historic inspector helpers; not all APIs are mounted in Phase 1. |
| `api.js`, `sessions.js`, `settings.js`, `connectors.js`, etc. | Older modular client surface retained during migration; do not introduce a second route contract through them. |

## Phase-1 Controller Route Map

| Intent | `app.js` operation | API |
|---|---|---|
| List/select/create/delete session | `loadWorkspaces`, `switchSession`, `createAndSwitchSession` | `/api/sessions` |
| Read transcript | `loadHistory`, `loadOlderMessages` | `/api/sessions/{id}/messages` |
| Connector CRUD | `loadConnectors`, `createConnector`, `saveSelectedConnector` | `/api/connectors` |
| Profile reads/writes | `restoreSettings`, `persistSettings` | `/api/settings/run-profile`, `/api/sessions/{id}/run-profile` |
| Start/stop | `start`, stop controls | `/api/runs` |

`app.js` must refresh `availableSessions` after creation before membership
validation; otherwise a successful POST appears as an “unknown session”.
