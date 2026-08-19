# Semantic map

## `src-tauri/src/main.rs`

| Symbol | Responsibility | Calls / called by |
| --- | --- | --- |
| `BackendProcess` | Owns the spawned FastAPI child and terminates it during application shutdown. | Managed by `run`; `Drop::drop` calls `Child::kill` and `Child::wait`. |
| `reserve_port` | Obtains an ephemeral loopback TCP port for the backend. | Called by `run`. |
| `backend_command` | Resolves the development Python command or packaged sidecar and adds loopback host/port arguments. | Called by `start_backend`. |
| `start_backend` | Spawns the backend and polls until its HTTP socket accepts connections. | Called by `run`. |
| `run` | Builds the Tauri application, starts the backend, registers lifecycle state, and creates the native webview. | Called by `main`. |
| `main` | Reports startup errors and exits non-zero. | OS entry point. |

## `scripts/backend_entry.py`

| Symbol | Responsibility | Calls / called by |
| --- | --- | --- |
| module entry point | Prepends the `web` command and delegates remaining arguments to `angelus.cli.main`. | Tauri packaged sidecar. |

## `angelus.storage`

| Symbol | Responsibility | Calls / called by |
| --- | --- | --- |
| `FRONTEND_ROOT` | Selects the source-checkout frontend directory or the PyInstaller extraction directory advertised by `ANGELUS_FRONTEND_ROOT`. | `angelus.webapp.app` and API route assembly. |
