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
| [workspace_catalog.py](workspace_catalog.py#L34) | `WorkspaceCatalog.list` | `None` | `tuple[Workspace, ...]` | Return every registered workspace in deterministic name order. |
| [workspace_catalog.py](workspace_catalog.py#L40) | `WorkspaceCatalog.get` | `session_id: str` | `Workspace` | Return one workspace or raise ``KeyError`` when it is unknown. |
| [workspace_catalog.py](workspace_catalog.py#L45) | `WorkspaceCatalog.add` | `workspace: Workspace` | `None` | Record a new workspace, refusing to overwrite another session. |
| [workspace_catalog.py](workspace_catalog.py#L54) | `WorkspaceCatalog.replace` | `workspace: Workspace` | `None` | Replace one existing workspace binding without changing its identity. |
| [workspace_catalog.py](workspace_catalog.py#L73) | `WorkspaceCatalog.remove` | `session_id: str` | `Workspace` | Remove one durable workspace identity from the authoritative catalog. |
| [workspace_catalog.py](workspace_catalog.py#L81) | `WorkspaceCatalog.rename` | `session_id: str, name: str` | `Workspace` | Rename one workspace display name without changing its identity. |
| [workspace_catalog.py](workspace_catalog.py#L106) | `WorkspaceCatalog.import_legacy_sessions` | `path: Path, state_root: Path` | `tuple[Workspace, ...]` | Import old ``workspace/sessions.json`` identities once, without copying data. |
| [workspace_catalog.py](workspace_catalog.py#L153) | `WorkspaceCatalog.remove_legacy_session` | `path: Path, session_id: str` | `None` | Remove one legacy index entry after its confirmed session deletion. |
| [workspace_catalog.py](workspace_catalog.py#L171) | `WorkspaceCatalog._read` | `None` | `dict[str, Workspace]` | Read valid registry records; an absent file denotes an empty catalog. |
| [workspace_catalog.py](workspace_catalog.py#L175) | `WorkspaceCatalog._read_document` | `None` | `WorkspaceCatalogDocument` | Read and strictly decode the catalog envelope. |
| [workspace_catalog.py](workspace_catalog.py#L197) | `WorkspaceCatalog._records` | `document: WorkspaceCatalogDocument` | `dict[str, Workspace]` | Index decoded workspace entries by their stable Session identity. |
| [workspace_catalog.py](workspace_catalog.py#L206) | `WorkspaceCatalog._write` | `records: dict[str, Workspace], legacy_workspace_imported: bool \| None` | `None` | Atomically replace the registry after flushing file and parent directory. |
| [workspace_catalog.py](workspace_catalog.py#L238) | `WorkspaceCatalog._write_legacy_index` | `path: Path, entries: list[object]` | `None` | Atomically replace the old list-shaped index during explicit deletion. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [workspace.py](workspace.py#L10) | `Workspace` | `session_id: str, name: str, project_path: Path \| None, state_path: Path` | `object` | Bind one session identity to its user project and Angelus state paths. |
| [workspace_catalog.py](workspace_catalog.py#L18) | `WorkspaceCatalogDocument` | `workspaces: tuple[Workspace, ...], schema_version: int, legacy_workspace_imported: bool` | `object` | The complete durable ``workspaces.json`` document. |
| [workspace_catalog.py](workspace_catalog.py#L26) | `WorkspaceCatalog` | `path: Path` | `object` | Persist workspace metadata without owning Sessions or live executions. |

<!-- END GENERATED SYMBOL MAP -->
