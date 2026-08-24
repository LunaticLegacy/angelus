# frontend/ — Web UI INDEX

Browser-based workbench for Angelus. Single-page app with vanilla JS, no framework.

## Route Map

| Entry | Type | Purpose |
|-------|------|---------|
| [`static/`](static/INDEX.md) | Dir | JavaScript modules, CSS, static assets |
| [`templates/`](templates/INDEX.md) | Dir | Single-page HTML shell, dialogs, and static-asset version references |

## Architecture

- **No framework**: Plain HTML + vanilla ES modules + CSS
- **SSE**: EventSource for live run streaming
- **REST**: Fetch-based API calls for CRUD operations
- **Active runtime**: `templates/index.html` loads the global slash-command parser `static/slash.js` and `static/app.js` as the ES-module composition root. `app.js` owns cross-feature coordination, initializes the active plugin bridge in `static/plugins.js`, and delegates reusable DOM views to `static/components/`.
- **Legacy module split**: the older `static/*.js` and `static/inspector/*.js` modules remain unreferenced migration artifacts. They are distinct from the active `static/components/` directory and must not be changed under the assumption that they run in production.

## Intent Routing

- **HTML structure** → `templates/index.html`
- **Active workbench behavior** → `static/app.js`
- **Reusable active UI components** → `static/components/`
- **Slash-command parsing** → `static/slash.js`
- **Plugin UI bridge, asset loader and runtime lifecycle controls** → `static/plugins.js` + `static/app.js`
- **Static/legacy module inventory** → `static/INDEX.md`
- **Inspector panels** → `static/inspector/INDEX.md`

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| — | — | `None` | `None` | 本索引范围不直接拥有可执行函数；沿 Route Map 进入下级索引。 |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| — | — | `None` | `object` | 本索引范围不直接声明类；沿 Route Map 进入下级索引。 |

<!-- END GENERATED SYMBOL MAP -->
