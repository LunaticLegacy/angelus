# frontend/static/inspector/ — Inspector Panels INDEX

Legacy ES-module inspector implementation. The active inspector is implemented in
[`../app.js`](../app.js) and is loaded by `templates/index.html`; these files are
not currently loaded by the browser.

## Route Map — Leaf Files

| File | Purpose |
|------|---------|
| `index.js` | Former tab-switching helper; its `data-panel` convention does not match the active template. |
| `graph.js` | Former graph and Agent-strip renderer; assumes DOM nodes no longer present in the active template. |
| `trace.js` | Former in-memory live trace appender. |
| `metrics.js` | Former header/metrics updater; the active UI uses the five-field usage ledger. |
| `plan.js` | Former task-plan renderer and status-update binding. |

## Intent Routing

- **All active inspector behavior** → `../app.js`
- **Potential future ES-module migration reference** → the file matching the concern above
