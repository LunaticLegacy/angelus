# frontend/static/inspector/ — Inspector Panels INDEX

Right-side inspector tabs for the workbench: execution graph, event trace, token metrics, task plan.

## Route Map — Leaf Files

| File | Purpose |
|------|---------|
| `index.js` | Tab panel container: tab switching, panel lifecycle |
| `graph.js` | Execution graph visualization: DAG rendering with node states, task terminals, agent assignments |
| `trace.js` | Event trace viewer: paginated ExecutionEvent log from durable NDJSON |
| `metrics.js` | Token usage display: per-agent and aggregate token counts from session events |
| `plan.js` | Task plan viewer/editor: display goal/summary/tasks, status transitions |

## Intent Routing

- **Execution graph visualization** → `graph.js`
- **Event trace / debugging** → `trace.js`
- **Token usage statistics** → `metrics.js`
- **Task plan management** → `plan.js`
- **Tab switching logic** → `index.js`
