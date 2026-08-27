# frontend/templates/ — SPA Shell INDEX

| File | Responsibility |
|---|---|
| `index.html` | Workbench structure: Session sidebar, transcript/composer, stop controls, inspector and settings dialogs. Loads versioned `static/app.js`. |
| `external_agents.html` | Historic External Agent Hub shell; its backend route is not mounted in Phase 1. |

The IDs in `index.html` are the contract consumed by `static/app.js`. A cache
version change on the script reference is required whenever controller behavior
changes incompatibly with a previously served browser copy.
