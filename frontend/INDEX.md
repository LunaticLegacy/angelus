# frontend/ — Web UI INDEX

Browser-based workbench for Angelus. Single-page app with vanilla JS, no framework.

## Route Map

| Entry | Type | Purpose |
|-------|------|---------|
| [`static/`](static/INDEX.md) | Dir | JavaScript modules, CSS, static assets |
| [`templates/`](templates/INDEX.md) | Dir | Single-page HTML shell, dialogs, and static-asset version references |

## Architecture

- **No framework**: Plain HTML + vanilla JS + CSS
- **SSE**: EventSource for live run streaming
- **REST**: Fetch-based API calls for CRUD operations
- **Active runtime**: `templates/index.html` currently loads the single classic script `static/app.js`.
- **Legacy module split**: the remaining `static/*.js` and `static/inspector/*.js` modules are source artifacts from an earlier ES-module split; they are not referenced by the HTML shell and must not be changed under the assumption that they run in production.

## Intent Routing

- **HTML structure** → `templates/index.html`
- **Active workbench behavior** → `static/app.js`
- **Static/legacy module inventory** → `static/INDEX.md`
- **Inspector panels** → `static/inspector/INDEX.md`
