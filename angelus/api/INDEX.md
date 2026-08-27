# angelus/api/ — Phase 1 HTTP INDEX

Routes are transport adapters only. They resolve `AngelusCore` from app state,
validate HTTP input, call one service, and map known domain errors to HTTP.
They do not own Session, Agent, execution, persistence or credentials.

| File | Mounted routes | Responsibility |
|---|---|---|
| `__init__.py` | `/`, `/favicon.ico`, `/static/*` | Install mounted routers and SPA shell; call core shutdown hook. |
| `sessions.py` | `/api/sessions` | Create/list/delete Session identities and page legacy transcript projection. |
| `runs.py` | `/api/runs`, `/api/runs/{id}/…` | Start, inspect, stop/force-stop and replay one Session attempt. |
| `settings.py` | `/api/connectors`, `/api/settings/run-profile`, `/api/sessions/{id}/run-profile` | Connector CRUD and global/Session future-run settings. |
| `providers.py` | `/api/providers` | Read installed LLMFetcher provider capabilities. |
| `workspace_directory.py` | `/api/workspace-directory/pick` | Optional local native directory chooser. |

## Not Mounted in Phase 1

`compact.py`, `external_agents.py` and `mcp.py` are retained historic source
files but are not registered by `include_api_routes`. They must not be used as
backend capabilities or revived route-by-route; their replacement belongs to
the next Session-projection phase. Removed `connectors.py`/`profiles.py` are
replaced solely by `settings.py`.

## Function Map

| Source | Function / method | Semantics |
|---|---|---|
| `__init__.py` | `include_api_routes` | Register Phase-1 routers, static assets and host shutdown callback. |
| `sessions.py` | `list_sessions`, `create_session`, `delete_session` | Session identity lifecycle over `SessionService`. |
| `sessions.py` | `get_session_messages` | Bounded legacy conversation projection for selected Session. |
| `runs.py` | `start_run`, `run_status`, stop endpoints | Execution lifecycle over `ExecutionService`. |
| `settings.py` | connector/profile endpoints | Settings use cases over `SettingsService`. |
| `providers.py` | `list_providers` | Runtime capability read. |
| `workspace_directory.py` | directory picker endpoint | Desktop-only local directory selection. |

## Class Map

| Source | Class | Semantics |
|---|---|---|
| `runs.py` | `RunRequest`, `StopRequest` | Typed input for starting/cancelling a Session attempt. |
| `sessions.py` | `CreateSessionRequest`, `DeleteSessionRequest` | Typed Session registration/deletion input. |
| `settings.py` | `ConnectorPayload`, `ProfilePayload` | Typed connector and future-run profile input. |
