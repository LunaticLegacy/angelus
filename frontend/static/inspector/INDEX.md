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

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [graph.js](graph.js#L10) | `load` | `None` | `Promise<unknown>` | Perform the browser runtime operation: load. |
| [graph.js](graph.js#L26) | `renderAgentStrip` | `graph: unknown` | `unknown` | Perform the browser runtime operation: render agent strip. |
| [graph.js](graph.js#L67) | `renderGraph` | `graph: unknown` | `unknown` | Perform the browser runtime operation: render graph. |
| [graph.js](graph.js#L107) | `taskFor` | `id: unknown` | `unknown` | Perform the browser runtime operation: task for. |
| [graph.js](graph.js#L115) | `renderNode` | `nodeId: unknown, depth: unknown, path: unknown` | `unknown` | Perform the browser runtime operation: render node. |
| [index.js](index.js#L4) | `initTabs` | `None` | `unknown` | Perform the browser runtime operation: init tabs. |
| [metrics.js](metrics.js#L7) | `update` | `data: unknown` | `unknown` | Perform the browser runtime operation: update. |
| [plan.js](plan.js#L10) | `load` | `None` | `Promise<unknown>` | Perform the browser runtime operation: load. |
| [plan.js](plan.js#L25) | `renderTask` | `task: unknown, depth: unknown` | `unknown` | Perform the browser runtime operation: render task. |
| [plan.js](plan.js#L54) | `updateStatus` | `taskId: unknown, status: unknown` | `Promise<unknown>` | Perform the browser runtime operation: update status. |
| [plan.js](plan.js#L60) | `bindStatusUpdates` | `None` | `unknown` | Perform the browser runtime operation: bind status updates. |
| [trace.js](trace.js#L6) | `append` | `title: unknown, message: unknown, data: unknown, kind: unknown` | `unknown` | Perform the browser runtime operation: append. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| — | — | `None` | `object` | 本索引范围不直接声明类；沿 Route Map 进入下级索引。 |

<!-- END GENERATED SYMBOL MAP -->
