# file_module — Session Workspace File Tools

This module exposes bounded file operations to coordinator and worker Agents.
Every path is resolved relative to the bound Session project workspace and is
checked for containment before access. Results are size limited so routine file
inspection does not flood model context.

| File | Responsibility |
|---|---|
| `file_service.py` | Path policy and bounded list/read/search/write operations. |
| `tool_provider.py` | ToolRegistry materialization and file capability definitions. |

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [file_service.py](file_service.py#L19) | `_lock_for` | `path: Path` | `threading.RLock` | Return the process-local lock protecting one workspace target. |
| [file_service.py](file_service.py#L35) | `FileService._path` | `value: object, allow_root: bool` | `Path` | Implement `FileService._path`. |
| [file_service.py](file_service.py#L52) | `FileService.list` | `path: object, recursive: bool, depth: int, pattern: str, limit: int` | `dict[str, Any]` | Implement `FileService.list`. |
| [file_service.py](file_service.py#L82) | `FileService.read` | `path: object, start_line: int, max_lines: int, max_chars: int, encoding: str` | `dict[str, Any]` | Implement `FileService.read`. |
| [file_service.py](file_service.py#L100) | `FileService.search` | `query: object, path: object, pattern: str, limit: int, context_lines: int` | `dict[str, Any]` | Implement `FileService.search`. |
| [file_service.py](file_service.py#L127) | `FileService.write` | `path: object, content: object, mode: str` | `dict[str, Any]` | Implement `FileService.write`. |
| [tool_provider.py](tool_provider.py#L20) | `_schema` | `*parameters: ToolParameter` | `ToolSchema` | Implement `_schema`. |
| [tool_provider.py](tool_provider.py#L28) | `FileToolProvider.materialize` | `session: 'Session', policy: ToolPolicy, role: str, agent_name: str \| None` | `list[Tool]` | Implement `FileToolProvider.materialize`. |
| [tool_provider.py](tool_provider.py#L55) | `file_tool_registration` | `core: 'AngelusCore'` | `ToolProviderRegistration` | Implement `file_tool_registration`. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [file_service.py](file_service.py#L25) | `FileService` | `root: Path \| None` | `object` | Perform bounded, workspace-contained file operations. |
| [tool_provider.py](tool_provider.py#L24) | `FileToolProvider` | `core: 'AngelusCore'` | `object` | Provide `FileToolProvider` behavior. |

<!-- END GENERATED SYMBOL MAP -->
