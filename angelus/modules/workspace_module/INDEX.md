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

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [workspace.py](workspace.py#L23) | `Workspace.to_json` | `None` | `dict[str, str \| None]` | Return the stable registry representation without runtime state. |
| [workspace.py](workspace.py#L33) | `Workspace.from_json` | `value: dict[str, object]` | `'Workspace'` | Recreate a workspace record previously written by the catalog. |
| [workspace_catalog.py](workspace_catalog.py#L22) | `WorkspaceCatalog.list` | `None` | `tuple[Workspace, ...]` | Return every registered workspace in deterministic name order. |
| [workspace_catalog.py](workspace_catalog.py#L28) | `WorkspaceCatalog.get` | `session_id: str` | `Workspace` | Return one workspace or raise ``KeyError`` when it is unknown. |
| [workspace_catalog.py](workspace_catalog.py#L33) | `WorkspaceCatalog.add` | `workspace: Workspace` | `None` | Record a new workspace, refusing to overwrite another session. |
| [workspace_catalog.py](workspace_catalog.py#L42) | `WorkspaceCatalog.replace` | `workspace: Workspace` | `None` | Replace one existing workspace binding without changing its identity. |
| [workspace_catalog.py](workspace_catalog.py#L61) | `WorkspaceCatalog.remove` | `session_id: str` | `Workspace` | Remove one durable workspace identity from the authoritative catalog. |
| [workspace_catalog.py](workspace_catalog.py#L69) | `WorkspaceCatalog.import_legacy_sessions` | `path: Path, state_root: Path` | `tuple[Workspace, ...]` | Import old ``workspace/sessions.json`` identities once, without copying data. |
| [workspace_catalog.py](workspace_catalog.py#L116) | `WorkspaceCatalog.remove_legacy_session` | `path: Path, session_id: str` | `None` | Remove one legacy index entry after its confirmed session deletion. |
| [workspace_catalog.py](workspace_catalog.py#L134) | `WorkspaceCatalog._read` | `None` | `dict[str, Workspace]` | Read valid registry records; an absent file denotes an empty catalog. |
| [workspace_catalog.py](workspace_catalog.py#L138) | `WorkspaceCatalog._read_document` | `None` | `dict[str, object]` | Read the validated catalog envelope while preserving migration metadata. |
| [workspace_catalog.py](workspace_catalog.py#L147) | `WorkspaceCatalog._records` | `document: dict[str, object]` | `dict[str, Workspace]` | Decode workspace entries from one previously validated envelope. |
| [workspace_catalog.py](workspace_catalog.py#L155) | `WorkspaceCatalog._write` | `records: dict[str, Workspace], legacy_workspace_imported: bool \| None` | `None` | Atomically replace the registry after flushing file and parent directory. |
| [workspace_catalog.py](workspace_catalog.py#L186) | `WorkspaceCatalog._write_legacy_index` | `path: Path, entries: list[object]` | `None` | Atomically replace the old list-shaped index during explicit deletion. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [workspace.py](workspace.py#L10) | `Workspace` | `session_id: str, name: str, project_path: Path \| None, state_path: Path` | `object` | Bind one session identity to its user project and Angelus state paths. |
| [workspace_catalog.py](workspace_catalog.py#L14) | `WorkspaceCatalog` | `path: Path` | `object` | Persist workspace metadata without owning Sessions or live executions. |

<!-- END GENERATED SYMBOL MAP -->
