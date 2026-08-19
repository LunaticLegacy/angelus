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
- **Active runtime**: `templates/index.html` loads `static/app.js` as an ES-module composition root. It owns cross-feature coordination; reusable DOM views are in `static/components/`.
- **Legacy module split**: the older `static/*.js` and `static/inspector/*.js` modules remain unreferenced migration artifacts. They are distinct from the active `static/components/` directory and must not be changed under the assumption that they run in production.

## Intent Routing

- **HTML structure** → `templates/index.html`
- **Active workbench behavior** → `static/app.js`
- **Reusable active UI components** → `static/components/`
- **Static/legacy module inventory** → `static/INDEX.md`
- **Inspector panels** → `static/inspector/INDEX.md`
