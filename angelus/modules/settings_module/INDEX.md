# settings_module/ — Future-run Profile INDEX

| File | Responsibility |
|---|---|
| `json_store.py` | Shared fsync + atomic-replace JSON primitive. |
| `profile_store.py` | Global default and complete Session override documents; validation and effective merge. |

Settings apply only to a future attempt. Execution creation snapshots effective
values; it never mutates a live attempt from this store.

## Function Map

| Source | Function / method | Semantics |
|---|---|---|
| `json_store.py` | `read_json`, `write_json` | Decode optional document / atomically publish JSON generation. |
| `profile_store.py` | `global_profile`, `replace_global` | Read/replace global defaults. |
| `profile_store.py` | `session_profile`, `replace_session`, `clear_session` | Resolve, replace or restore Session inheritance. |
| `profile_store.py` | `connector_references` | Find global/effective Session references before connector deletion. |

## Class Map

| Source | Class | Semantics |
|---|---|---|
| `profile_store.py` | `RunProfileStore` | Lock-protected authority for future-run profile JSON. |

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [json_store.py](json_store.py#L11) | `read_json` | `path: Path, default: object` | `object` | Read one JSON document, returning ``default`` only when it is absent. |
| [json_store.py](json_store.py#L29) | `write_json` | `path: Path, value: object` | `None` | Atomically replace one JSON document after flushing file and directory. |
| [profile_store.py](profile_store.py#L55) | `RunProfileStore.global_profile` | `None` | `dict[str, Any]` | Return the complete global default profile with omitted fields filled. |
| [profile_store.py](profile_store.py#L60) | `RunProfileStore.replace_global` | `values: Mapping[str, Any]` | `dict[str, Any]` | Validate and atomically replace global defaults. |
| [profile_store.py](profile_store.py#L71) | `RunProfileStore.session_profile` | `session_id: str` | `dict[str, Any]` | Return effective settings and whether this Session has an override. |
| [profile_store.py](profile_store.py#L87) | `RunProfileStore.replace_session` | `session_id: str, values: Mapping[str, Any]` | `dict[str, Any]` | Replace a Session override with validated complete future-run values. |
| [profile_store.py](profile_store.py#L100) | `RunProfileStore.clear_session` | `session_id: str` | `dict[str, Any]` | Remove override file so the Session again resolves global defaults. |
| [profile_store.py](profile_store.py#L113) | `RunProfileStore.effective` | `session_id: str` | `dict[str, Any]` | Return resolved values that execution creation will snapshot later. |
| [profile_store.py](profile_store.py#L117) | `RunProfileStore.connector_references` | `connector_id: str, session_ids: tuple[str, ...]` | `tuple[str, ...]` | Return profile scopes whose effective setting references a connector. |
| [profile_store.py](profile_store.py#L131) | `RunProfileStore._read` | `path: Path` | `Mapping[str, Any]` | Decode one optional profile envelope, rejecting malformed documents. |
| [profile_store.py](profile_store.py#L141) | `RunProfileStore._session_path` | `session_id: str` | `Path` | Resolve a validated Session-local path without allowing traversal. |
| [profile_store.py](profile_store.py#L147) | `RunProfileStore._validated` | `values: Mapping[str, Any], partial: bool` | `dict[str, Any]` | Normalize supported fields and reject unknown or ill-typed settings. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [profile_store.py](profile_store.py#L34) | `RunProfileStore` | `state_root: Path` | `object` | Persist global defaults and sparse per-session overrides. |

<!-- END GENERATED SYMBOL MAP -->
