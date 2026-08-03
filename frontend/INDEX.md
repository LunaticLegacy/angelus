# frontend/ — Web UI INDEX

Browser-based workbench for Angelus. Single-page app with vanilla JS, no framework.

## Route Map

| Entry | Type | Purpose |
|-------|------|---------|
| [`static/`](static/INDEX.md) | Dir | JavaScript modules, CSS, static assets |
| `templates/index.html` | File | Single HTML page: chat pane, session selector, settings panel, inspector sidebar |

## Architecture

- **No framework**: Plain HTML + vanilla JS + CSS
- **SSE**: EventSource for live run streaming
- **REST**: Fetch-based API calls for CRUD operations
- **Modular JS**: Each feature area is a separate `.js` file loaded via `<script>` tags

## Intent Routing

- **HTML structure** → `templates/index.html`
- **JavaScript modules** → `static/INDEX.md`
- **Inspector panels** → `static/inspector/INDEX.md`
