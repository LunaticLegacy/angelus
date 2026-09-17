# context_version_module/ — Context Revisions INDEX

| File | Responsibility |
|---|---|
| `store.py` | Immutable snapshots, optimistic edits and forward-only restores over the active SQLite checkpoint. |
| `tool_provider.py` | Three tools scoped to the concrete calling Agent. |
| `__init__.py` | Public registration export. |

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [store.py](store.py#L40) | `ContextVersionStore.inspect` | `None` | `dict[str, Any]` | Implement `ContextVersionStore.inspect`. |
| [store.py](store.py#L53) | `ContextVersionStore.apply` | `expected_revision_id: str \| None, operations: list[ContextEditOperation], reason: str` | `dict[str, Any]` | Implement `ContextVersionStore.apply`. |
| [store.py](store.py#L73) | `ContextVersionStore.restore` | `expected_revision_id: str \| None, revision_id: str, reason: str` | `dict[str, Any]` | Implement `ContextVersionStore.restore`. |
| [store.py](store.py#L83) | `ContextVersionStore._persist` | `None` | `None` | Implement `ContextVersionStore._persist`. |
| [store.py](store.py#L87) | `ContextVersionStore._linear` | `None` | `Any` | Implement `ContextVersionStore._linear`. |
| [store.py](store.py#L90) | `ContextVersionStore._pointer` | `None` | `dict[str, Any]` | Implement `ContextVersionStore._pointer`. |
| [store.py](store.py#L94) | `ContextVersionStore._metadata` | `None` | `dict[str, Any]` | Implement `ContextVersionStore._metadata`. |
| [store.py](store.py#L98) | `ContextVersionStore._messages` | `None` | `list[dict[str, Any]]` | Implement `ContextVersionStore._messages`. |
| [store.py](store.py#L102) | `ContextVersionStore._record` | `item: dict[str, Any], ordinal: int` | `dict[str, Any]` | Implement `ContextVersionStore._record`. |
| [store.py](store.py#L110) | `ContextVersionStore._snapshot` | `messages: list[dict[str, Any]], parent: str \| None, actor: str, reason: str, operations: list[dict[str, Any]], restored_from: str \| None` | `str` | Implement `ContextVersionStore._snapshot`. |
| [store.py](store.py#L120) | `ContextVersionStore._activate` | `messages: list[dict[str, Any]], revision_id: str` | `None` | Implement `ContextVersionStore._activate`. |
| [tool_provider.py](tool_provider.py#L18) | `ContextVersionToolProvider.materialize` | `session: Any, policy: ToolPolicy, role: str, agent_name: str \| None` | `list[Tool]` | Implement `ContextVersionToolProvider.materialize`. |
| [tool_provider.py](tool_provider.py#L36) | `context_version_tool_registration` | `core: 'AngelusCore'` | `ToolProviderRegistration` | Implement `context_version_tool_registration`. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [store.py](store.py#L17) | `ContextVersionError` | `None` | `ValueError` | Safe context revision or edit rejection. |
| [store.py](store.py#L22) | `ContextEditOperation` | `kind: str, target_record_id: str, content: str, role: str` | `object` | Provide `ContextEditOperation` behavior. |
| [store.py](store.py#L29) | `ContextVersionStore` | `agent: Any, agent_name: str` | `object` | Version and rewrite only one live Agent's active linear context. |
| [tool_provider.py](tool_provider.py#L15) | `ContextVersionToolProvider` | `core: 'AngelusCore'` | `object` | Provide `ContextVersionToolProvider` behavior. |

<!-- END GENERATED SYMBOL MAP -->
