# angelus/classes/ — Data Classes INDEX

Java-style one-class-per-file layout. All web-facing request/response models and runtime state dataclasses.

## Route Map — Leaf Files

| File | Class | Base | Purpose |
|------|-------|------|---------|
| `run_config.py` | `RunConfig` | `BaseModel` | LLM backend + Agent config: provider, model, API key, temperature, max_tokens, max_rounds, context threshold, shell/swarm toggles |
| `run_request.py` | `RunRequest` | `BaseModel` | Incoming run request: session_id, workspace_id, message, nested `RunConfig` |
| `steer_request.py` | `SteerRequest` | `BaseModel` | Mid-run steering instruction injected at next safe boundary |
| `workspace_request.py` | `WorkspaceRequest` | `BaseModel` | Create/rename workspace: name (1-80 chars) |
| `workspace_delete_request.py` | `WorkspaceDeleteRequest` | `BaseModel` | Delete confirmation: explicit second confirmation string |
| `connector_request.py` | `ConnectorRequest` | `BaseModel` | Named persisted backend connection config; separate from Agent execution settings |
| `task_plan_request.py` | `TaskPlanRequest` | `BaseModel` | Task plan payload: goal, summary, tasks list |
| `task_status_request.py` | `TaskStatusRequest` | `BaseModel` | Single task status transition |
| `browser_run_control.py` | `BrowserRunControl` | `AgentRunControl` | Thread-safe run controls: stop, force_stop, steer via queue |
| `active_run.py` | `ActiveRun` | `dataclass` | Live run state: control, event queue, done flag, swarm ref, process tracking with force_stop |
| `browser_session.py` | `BrowserSession` | `dataclass` | Per-session concurrency guard: lock + optional ActiveRun |

## Dependencies

- `ConnectorRequest` stores only connection fields and is independent of `RunConfig`
- `RunRequest` contains `RunConfig`
- `ActiveRun` uses `BrowserRunControl`
- `BrowserSession` uses `ActiveRun`

All classes re-exported from `__init__.py` for `from angelus.classes import X`.
