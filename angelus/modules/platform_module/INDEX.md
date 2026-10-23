# platform_module/ — Operating-System Desktop Integration INDEX

| File | Responsibility |
|---|---|
| `system_resource_manager.py` | Serialize folder selection and dispatch it to Windows Explorer shell, macOS's system chooser, or an installed Linux desktop chooser. |

This module owns platform detection and native process invocation. It does not
depend on FastAPI, browser APIs, Tauri APIs, or workspace persistence.

## Public contract

- `SystemResourceManager.select_directory()` returns a resolved directory or
  `None` on user cancellation.
- Availability and invocation failures have separate typed exceptions.

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [system_resource_manager.py](system_resource_manager.py#L38) | `SystemResourceManager.select_directory` | `title: str` | `Path \| None` | Return one existing directory selected by the host desktop shell. |
| [system_resource_manager.py](system_resource_manager.py#L74) | `SystemResourceManager._picker_command` | `title: str` | `list[str]` | Build the command for the current host without invoking it. |
| [system_resource_manager.py](system_resource_manager.py#L102) | `SystemResourceManager._linux_picker_command` | `title: str` | `list[str]` | Use an installed desktop chooser belonging to the Linux session. |
| [system_resource_manager.py](system_resource_manager.py#L117) | `SystemResourceManager._first_available` | `*names: str` | `str` | Implement `SystemResourceManager._first_available`. |
| [system_resource_manager.py](system_resource_manager.py#L126) | `SystemResourceManager._is_cancelled` | `returncode: int, stderr: str` | `bool` | Implement `SystemResourceManager._is_cancelled`. |
| [system_resource_manager.py](system_resource_manager.py#L134) | `_powershell_literal` | `value: str` | `str` | Escape a value for a single-quoted PowerShell literal. |
| [system_resource_manager.py](system_resource_manager.py#L139) | `_applescript_literal` | `value: str` | `str` | Escape a value embedded in an AppleScript string literal. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [system_resource_manager.py](system_resource_manager.py#L15) | `SystemResourceManagerError` | `None` | `RuntimeError` | The operating-system folder picker could not complete successfully. |
| [system_resource_manager.py](system_resource_manager.py#L19) | `SystemResourceManagerUnavailable` | `None` | `SystemResourceManagerError` | The host has no supported operating-system folder picker. |
| [system_resource_manager.py](system_resource_manager.py#L23) | `SystemResourceManager` | `system_name: str \| None, which: Callable[[str], str \| None], runner: Callable[..., Any]` | `object` | Select directories through the system desktop, never the web runtime. |

<!-- END GENERATED SYMBOL MAP -->
