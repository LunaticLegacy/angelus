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
