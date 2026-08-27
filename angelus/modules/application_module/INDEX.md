# application_module/ — Use-case Service INDEX

Application services coordinate existing owners. They contain no HTTP, browser
or terminal presentation logic.

| File | Responsibility |
|---|---|
| `session_service.py` | Create/list/delete Session + Workspace pairs and materialize coordinator from saved configuration. |
| `execution_service.py` | Start/inspect/stop/replay a Session-owned execution attempt. |
| `settings_service.py` | Validate connector/profile relationships and perform settings use cases. |

## Function Map

| Source | Function / method | Semantics |
|---|---|---|
| `SessionService.create` | Register Session/execution boundary then durable Workspace, with rollback on catalog failure. |
| `SessionService.ensure_coordinator` | Build/update coordinator from effective Profile and write-only connector secret. |
| `SessionService.delete` | Force-stop, remove Angelus state/legacy archive/catalog/aggregate in safe order. |
| `ExecutionService.start` | Confirm coordinator then schedule one Session attempt. |
| `ExecutionService.stop` | Apply graceful/forced strategy to same Session controller. |
| `SettingsService.*profile` | Read/replace/clear future-run global or Session profile. |
| `SettingsService.*connector` | CRUD connector and reject deletion while effective profiles reference it. |

## Class Map

| Source | Class | Semantics |
|---|---|---|
| `session_service.py` | `SessionService` | Session/workspace lifecycle and coordinator materialization. |
| `execution_service.py` | `ExecutionService` | Session execution lifecycle facade. |
| `settings_service.py` | `SettingsService` | Cross-store settings transaction boundary. |
| `execution_service.py` | `UnknownSession` | Uniform missing-Session use-case error. |
