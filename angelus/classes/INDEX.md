# angelus/classes/ — Data Classes INDEX

Small web-facing Pydantic models and in-memory control-state dataclasses.
Each class has its own module and is re-exported by `__init__.py`.

## Route Map — Leaf Files

| File | Class | Base | Purpose |
|---|---|---|---|
| `run_config.py` | `RunConfig` | `BaseModel` | One run's backend selector/reference plus execution settings: provider, model, optional `connector_id`, direct run-only key/API URL, system prompt, generation/context limits, shell, and Swarm options |
| `run_request.py` | `RunRequest` | `BaseModel` | Incoming run: `session_id`, `workspace_id`, user message, and nested `RunConfig` |
| `connector_request.py` | `ConnectorRequest` | `BaseModel` | Named persisted connector fields only: name, provider, model, API URL, and API key. It deliberately excludes Agent behavior settings; `connectors.py` encrypts the key before disk persistence. |
| `steer_request.py` | `SteerRequest` | `BaseModel` | Mid-run instruction queued for the next safe Agent boundary |
| `compact_request.py` | `CompactRequest` | `BaseModel` | Manual context compaction: target agent name plus the browser run config used to build the compactor |
| `workspace_request.py` | `WorkspaceRequest` | `BaseModel` | Create or rename a user-visible local workspace/session name |
| `workspace_delete_request.py` | `WorkspaceDeleteRequest` | `BaseModel` | Explicit confirmation required to delete a workspace/session directory |
| `task_plan_request.py` | `TaskPlanRequest` | `BaseModel` | Complete task-plan replacement: goal, optional summary, and task records |
| `task_status_request.py` | `TaskStatusRequest` | `BaseModel` | Single task status transition |
| `browser_run_control.py` | `BrowserRunControl` | `AgentRunControl` | Thread-safe stop/steer implementation: `stop()` is cooperative; `force_stop()` also exposes the terminal model-I/O cancellation event |
| `active_run.py` | `ActiveRun` | `dataclass` | Live browser-run state: control, event queue, completion signal, optional Swarm, and tracked shell processes; force-stop propagates model cancellation and kills tracked process groups |
| `browser_session.py` | `BrowserSession` | `dataclass` | In-memory per-session concurrency guard: lock plus optional active run |

## Boundaries and Dependencies

- `RunRequest` contains `RunConfig`; neither model is a persisted connector
  record. A saved `connector_id` is resolved server-side, while a direct
  `api_key` is valid only for that request.
- `ConnectorRequest` is stored separately from Agent execution settings. Its
  API key is RSA-encrypted by `connectors.py`; public connector responses omit it
  and instead indicate whether a key exists.
- `ActiveRun` owns `BrowserRunControl`; `BrowserSession` owns the optional
  `ActiveRun`. These are process-memory coordination state, not durable
  session history.
- Durable transcripts, event ledgers, run profiles, contexts, and plans are
  owned by `storage.py` / `history.py` / `runtime.py` / `task_planning.py`, not these data classes.
