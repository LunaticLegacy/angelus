# session_memory_module/ — Cross-Session Memory INDEX

| File | Responsibility |
|---|---|
| `store.py` | Immutable evidence snapshots, handoffs and read-only artifact copies. |
| `tool_provider.py` | Six tools enforcing the four run-profile Session allowlists. |
| `__init__.py` | Public registration export. |

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [store.py](store.py#L28) | `_lock_for_path` | `path: Path` | `threading.RLock` | Return the process-local lock shared by every store for one session path. |
| [store.py](store.py#L42) | `SessionMemoryStore._lock_for` | `session_id: str` | `threading.RLock` | Return the process-wide lock for one Session's memory files. |
| [store.py](store.py#L46) | `SessionMemoryStore.snapshot` | `session_id: str` | `dict[str, Any]` | Implement `SessionMemoryStore.snapshot`. |
| [store.py](store.py#L59) | `SessionMemoryStore.manifest` | `session_id: str, generation: int \| None` | `dict[str, Any]` | Implement `SessionMemoryStore.manifest`. |
| [store.py](store.py#L68) | `SessionMemoryStore.create_handoff` | `session_id: str, handoff: dict[str, Any]` | `dict[str, Any]` | Implement `SessionMemoryStore.create_handoff`. |
| [store.py](store.py#L85) | `SessionMemoryStore.read_handoff` | `session_id: str, handoff_id: str` | `dict[str, Any]` | Implement `SessionMemoryStore.read_handoff`. |
| [store.py](store.py#L94) | `SessionMemoryStore.copy_artifact` | `source_session: str, artifact_id: str, target_session: str` | `dict[str, Any]` | Implement `SessionMemoryStore.copy_artifact`. |
| [store.py](store.py#L111) | `SessionMemoryStore._session_root` | `session_id: str` | `Path` | Implement `SessionMemoryStore._session_root`. |
| [store.py](store.py#L114) | `SessionMemoryStore._context_evidence` | `root: Path` | `list[dict[str, Any]]` | Implement `SessionMemoryStore._context_evidence`. |
| [store.py](store.py#L145) | `SessionMemoryStore._artifacts` | `root: Path, session_id: str` | `list[dict[str, Any]]` | Implement `SessionMemoryStore._artifacts`. |
| [store.py](store.py#L164) | `SessionMemoryStore._missing` | `None` | `dict[str, Any]` | Implement `SessionMemoryStore._missing`. |
| [tool_provider.py](tool_provider.py#L25) | `SessionMemoryToolProvider.materialize` | `session: object, policy: ToolPolicy, role: str, agent_name: str \| None` | `list[Tool]` | Implement `SessionMemoryToolProvider.materialize`. |
| [tool_provider.py](tool_provider.py#L67) | `session_memory_tool_registration` | `core: 'AngelusCore'` | `ToolProviderRegistration` | Implement `session_memory_tool_registration`. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [store.py](store.py#L20) | `SessionMemoryError` | `None` | `ValueError` | Safe rejection of an invalid or unauthorized memory operation. |
| [store.py](store.py#L35) | `SessionMemoryStore` | `state_root: Path, project_root: Callable[[str], Path \| None]` | `object` | Build immutable evidence manifests from current Angelus state. |
| [tool_provider.py](tool_provider.py#L17) | `SessionMemoryToolProvider` | `core: 'AngelusCore'` | `object` | Provide `SessionMemoryToolProvider` behavior. |

<!-- END GENERATED SYMBOL MAP -->
