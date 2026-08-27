# workspace_module/ — Durable Session Identity INDEX

| File | Responsibility |
|---|---|
| `workspace.py` | Immutable workspace/session metadata record and JSON codec. |
| `workspace_catalog.py` | Atomic catalog CRUD, one-time legacy import and legacy-index deletion bridge. |

This module does not own live Sessions, Agents or executions. It is the durable
source for which Session identities are selectable after process restart.

## Class Map

| Source | Class | Semantics |
|---|---|---|
| `workspace.py` | `Workspace` | Session ID, display name, optional user project path and Angelus state path. |
| `workspace_catalog.py` | `WorkspaceCatalog` | Lock-protected catalog and migration marker authority. |
