# settings_module/ — Future-run Profile INDEX

| File | Responsibility |
|---|---|
| `json_store.py` | Shared fsync + atomic-replace JSON primitive. |
| `profile_store.py` | Global default and complete Session override documents; validation and effective merge. |

Settings apply only to a future attempt. Execution creation snapshots effective
values; it never mutates a live attempt from this store.
`compaction_output_max_tokens` is an independently persisted summary-output
budget (default `8192`), separate from the Agent reply `max_tokens` budget.
`request_timeout_seconds` is the provider-neutral future-attempt model and
project-tool I/O deadline (default `60`, validated from 1 through 3600
seconds). The shell tool advertises and enforces this value as its maximum
per-call timeout.
`tool_result_context_limit` controls complete tool results visible in one
model request (default `0`, meaning unlimited); complete results remain in
the durable context and artifact store.
The default run profile grants the `vision` category and `view_image` Tool so
native image input works out of the box; an explicit `false` still opts a
Session or the global default out.

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
| [json_schema.py](json_schema.py#L37) | `_persisted_fields` | `None` | `tuple[str, ...]` | Return the field names that both directions must agree on. |
| [json_schema.py](json_schema.py#L54) | `encode_record` | `value: object, where: str` | `dict[str, object]` | Encode a dataclass instance as the object ``decode_record`` accepts. |
| [json_schema.py](json_schema.py#L80) | `encode_value` | `value: object, where: str` | `object` | Encode one field value without losing the type it will decode back to. |
| [json_schema.py](json_schema.py#L118) | `decode_record` | `value: object, where: str \| None` | `T` | Decode one object into ``cls``, requiring every persisted field. |
| [json_schema.py](json_schema.py#L151) | `decode_value` | `annotation: object, value: object, where: str` | `object` | Decode one JSON value against its declared annotation. |
| [json_schema.py](json_schema.py#L210) | `validate_json` | `value: object, where: str` | `object` | Prove that a value is representable as JSON, and return it unchanged. |
| [json_schema.py](json_schema.py#L240) | `_assert_supported` | `annotation: object, where: str, seen: set[object]` | `None` | Reject an annotation the decoder could not restore from its JSON form. |
| [json_schema.py](json_schema.py#L294) | `_type_hints` | `None` | `dict[str, object]` | Resolve annotations once per class, surfacing forward-ref mistakes. |
| [json_schema.py](json_schema.py#L304) | `_decode_union` | `arguments: tuple[object, ...], value: object, where: str` | `object` | Decode ``X \| None`` and small unions without guessing silently. |
| [json_schema.py](json_schema.py#L322) | `_decode_tuple` | `arguments: tuple[object, ...], value: object, where: str` | `tuple[object, ...]` | Decode both fixed-length and homogeneous tuples. |
| [json_store.py](json_store.py#L22) | `require_mapping` | `value: object, where: str` | `dict[str, object]` | Return ``value`` as a JSON object. |
| [json_store.py](json_store.py#L37) | `reject_unknown_keys` | `value: Mapping[str, object], allowed: Collection[str], where: str` | `None` | Reject fields the writer never emits for this schema version. |
| [json_store.py](json_store.py#L50) | `require_string` | `value: object, where: str` | `str` | Return ``value`` as a string. |
| [json_store.py](json_store.py#L61) | `optional_string` | `value: Mapping[str, object], key: str, default: str, where: str` | `str` | Return one optional string field, falling back to ``default``. |
| [json_store.py](json_store.py#L70) | `require_int` | `value: object, where: str` | `int` | Return ``value`` as an integer, rejecting booleans. |
| [json_store.py](json_store.py#L81) | `require_number` | `value: object, where: str` | `float` | Return ``value`` as a float, rejecting booleans and strings. |
| [json_store.py](json_store.py#L92) | `require_list` | `value: object, where: str` | `list[object]` | Return ``value`` as a JSON array. |
| [json_store.py](json_store.py#L103) | `string_list` | `value: object, where: str` | `list[str]` | Return an array whose every element is a string. |
| [json_store.py](json_store.py#L111) | `string_map` | `value: object, where: str` | `dict[str, str]` | Return an object whose every value is a string. |
| [json_store.py](json_store.py#L119) | `string_list_map` | `value: object, where: str` | `dict[str, list[str]]` | Return an object mapping string keys to arrays of strings. |
| [json_store.py](json_store.py#L127) | `read_json` | `path: Path, default: object` | `object` | Read one JSON document, returning ``default`` only when it is absent. |
| [json_store.py](json_store.py#L147) | `write_json` | `path: Path, value: object` | `None` | Atomically replace one JSON document after flushing file and directory. |
| [profile_store.py](profile_store.py#L84) | `RunProfileStore.global_profile` | `None` | `dict[str, Any]` | Return the complete global default profile with omitted fields filled. |
| [profile_store.py](profile_store.py#L89) | `RunProfileStore.replace_global` | `values: Mapping[str, Any]` | `dict[str, Any]` | Validate and atomically replace global defaults. |
| [profile_store.py](profile_store.py#L100) | `RunProfileStore.session_profile` | `session_id: str` | `dict[str, Any]` | Return effective settings and whether this Session has an override. |
| [profile_store.py](profile_store.py#L116) | `RunProfileStore.replace_session` | `session_id: str, values: Mapping[str, Any]` | `dict[str, Any]` | Replace a Session override with validated complete future-run values. |
| [profile_store.py](profile_store.py#L129) | `RunProfileStore.clear_session` | `session_id: str` | `dict[str, Any]` | Remove override file so the Session again resolves global defaults. |
| [profile_store.py](profile_store.py#L142) | `RunProfileStore.effective` | `session_id: str` | `dict[str, Any]` | Return resolved values that execution creation will snapshot later. |
| [profile_store.py](profile_store.py#L146) | `RunProfileStore.connector_references` | `connector_id: str, session_ids: tuple[str, ...]` | `tuple[str, ...]` | Return profile scopes whose effective setting references a connector. |
| [profile_store.py](profile_store.py#L160) | `RunProfileStore._read` | `path: Path` | `Mapping[str, Any]` | Decode one optional profile envelope, rejecting malformed documents. |
| [profile_store.py](profile_store.py#L170) | `RunProfileStore._session_path` | `session_id: str` | `Path` | Resolve a validated Session-local path without allowing traversal. |
| [profile_store.py](profile_store.py#L176) | `RunProfileStore._validated` | `values: Mapping[str, Any], partial: bool` | `dict[str, Any]` | Normalize supported fields and reject unknown or ill-typed settings. |
| [session_preferences.py](session_preferences.py#L29) | `SessionPreference.to_json` | `None` | `dict[str, object]` | Encode the value exactly as it is persisted. |
| [session_preferences.py](session_preferences.py#L34) | `SessionPreference.from_json` | `value: object, where: str` | `'SessionPreference'` | Decode one stored preference object. |
| [session_preferences.py](session_preferences.py#L58) | `SessionPreferencesDocument.to_json` | `None` | `dict[str, object]` | Encode the document exactly as it is persisted. |
| [session_preferences.py](session_preferences.py#L69) | `SessionPreferencesDocument.from_json` | `value: object` | `'SessionPreferencesDocument'` | Decode one complete document. |
| [session_preferences.py](session_preferences.py#L104) | `SessionPreferenceStore.get` | `session_id: str` | `SessionPreference` | Return one Session's preference, defaulting every field. |
| [session_preferences.py](session_preferences.py#L109) | `SessionPreferenceStore.set_default_connector` | `session_id: str, connector_id: str \| None` | `SessionPreference` | Store or clear the Session's default connector identity. |
| [session_preferences.py](session_preferences.py#L122) | `SessionPreferenceStore.clear_connector` | `connector_id: str` | `tuple[str, ...]` | Remove every Session default that references a deleted connector. |
| [session_preferences.py](session_preferences.py#L137) | `SessionPreferenceStore._read` | `None` | `dict[str, SessionPreference]` | Decode the document; a missing file means no preferences yet. |
| [session_preferences.py](session_preferences.py#L144) | `SessionPreferenceStore._write` | `sessions: dict[str, SessionPreference]` | `None` | Atomically replace the complete document. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [json_store.py](json_store.py#L18) | `JsonSchemaError` | `None` | `ValueError` | A decoded JSON document does not match the schema for its version. |
| [profile_store.py](profile_store.py#L63) | `RunProfileStore` | `state_root: Path` | `object` | Persist global defaults and sparse per-session overrides. |
| [session_preferences.py](session_preferences.py#L24) | `SessionPreference` | `default_connector_id: str \| None` | `object` | Optional UI conveniences owned by one Session. |
| [session_preferences.py](session_preferences.py#L52) | `SessionPreferencesDocument` | `sessions: dict[str, SessionPreference], schema_version: int` | `object` | The complete ``session-preferences.json`` document. |
| [session_preferences.py](session_preferences.py#L97) | `SessionPreferenceStore` | `state_root: Path` | `object` | Persist UI conveniences without making them execution dependencies. |

<!-- END GENERATED SYMBOL MAP -->
