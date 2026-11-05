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
| [messages.py](messages.py#L46) | `ContextImage.from_reference` | `value: ImageReference` | `'ContextImage'` | Decode one ``ImageReference`` TypedDict. |
| [messages.py](messages.py#L57) | `ContextImage.to_reference` | `None` | `ImageReference` | Encode the record back to the llmfetcher TypedDict. |
| [messages.py](messages.py#L79) | `ContextToolCall.from_call` | `value: LLMToolCall` | `'ContextToolCall'` | Decode one ``LLMToolCall``. |
| [messages.py](messages.py#L88) | `ContextToolCall.to_call` | `None` | `LLMToolCall` | Encode the record back to ``LLMToolCall``. |
| [messages.py](messages.py#L107) | `ContextToolInfo.from_tool_info` | `value: ToolInfo` | `'ContextToolInfo'` | Decode one ``ToolInfo``. |
| [messages.py](messages.py#L115) | `ContextToolInfo.to_tool_info` | `None` | `ToolInfo` | Encode the record back to ``ToolInfo``. |
| [messages.py](messages.py#L141) | `ContextMessage.from_context` | `value: LLMContext` | `'ContextMessage'` | Decode one ``LLMContext`` into the revision record. |
| [messages.py](messages.py#L161) | `ContextMessage.to_context` | `None` | `LLMContext` | Encode the record back to ``LLMContext``. |
| [messages.py](messages.py#L178) | `ContextMessage.from_item` | `value: ContextItem, results: Mapping[str, ToolResultRecord]` | `'ContextEntry'` | Decode one v2 context item into the revision projection. |
| [messages.py](messages.py#L236) | `ContextMessage.to_item_with_results` | `None` | `tuple[ContextItem, list[ToolResultRecord]]` | Rebuild one v2 item plus the result rows its calls reference. |
| [messages.py](messages.py#L301) | `ContextCompactedMessage.from_context` | `value: LLMContextCompacted` | `'ContextCompactedMessage'` | Decode one ``LLMContextCompacted``. |
| [messages.py](messages.py#L310) | `ContextCompactedMessage.to_context` | `None` | `LLMContextCompacted` | Encode the record back to ``LLMContextCompacted``. |
| [messages.py](messages.py#L320) | `ContextCompactedMessage.from_summary` | `value: ContextSummaryItem` | `'ContextCompactedMessage'` | Decode one v2 summary item into the revision projection. |
| [messages.py](messages.py#L328) | `ContextCompactedMessage.to_summary` | `None` | `ContextSummaryItem` | Encode the revision summary back to a v2 context item. |
| [store.py](store.py#L100) | `_normalize_revision` | `value: JsonValue` | `JsonValue` | Migrate legacy revision fields before the strict decoder runs. |
| [store.py](store.py#L135) | `_normalize_images` | `value: JsonValue` | `None` | Fill the optional image detail default omitted by older revisions. |
| [store.py](store.py#L155) | `ContextVersionStore.inspect` | `None` | `dict[str, object]` | Implement `ContextVersionStore.inspect`. |
| [store.py](store.py#L186) | `ContextVersionStore.search_archive` | `query: str, limit: int` | `ArchiveSearchResult` | Search this Agent's compacted-out raw records without mutation. |
| [store.py](store.py#L225) | `ContextVersionStore.read_archive` | `timeline: int` | `ArchiveRecordResult` | Return one compacted-out raw record by its timeline identity. |
| [store.py](store.py#L250) | `ContextVersionStore.apply` | `expected_revision_id: str \| None, operations: list[ContextEditOperation], reason: str` | `dict[str, object]` | Implement `ContextVersionStore.apply`. |
| [store.py](store.py#L274) | `ContextVersionStore.restore` | `expected_revision_id: str \| None, revision_id: str, reason: str` | `dict[str, object]` | Implement `ContextVersionStore.restore`. |
| [store.py](store.py#L291) | `ContextVersionStore._persist` | `None` | `None` | Implement `ContextVersionStore._persist`. |
| [store.py](store.py#L295) | `ContextVersionStore._linear` | `None` | `Any` | Implement `ContextVersionStore._linear`. |
| [store.py](store.py#L298) | `ContextVersionStore._pointer` | `None` | `dict[str, object]` | Implement `ContextVersionStore._pointer`. |
| [store.py](store.py#L304) | `ContextVersionStore._metadata` | `None` | `dict[str, object]` | Implement `ContextVersionStore._metadata`. |
| [store.py](store.py#L310) | `ContextVersionStore._current_revision_id` | `None` | `str \| None` | Implement `ContextVersionStore._current_revision_id`. |
| [store.py](store.py#L314) | `ContextVersionStore._messages` | `None` | `list[ContextEntry]` | Implement `ContextVersionStore._messages`. |
| [store.py](store.py#L325) | `ContextVersionStore._record` | `item: ContextMessage, ordinal: int` | `JsonObject` | Implement `ContextVersionStore._record`. |
| [store.py](store.py#L339) | `ContextVersionStore._snapshot` | `messages: list[ContextEntry], parent: str \| None, actor: str, reason: str, operations: Sequence[ContextEditOperation], restored_from: str \| None` | `str` | Implement `ContextVersionStore._snapshot`. |
| [store.py](store.py#L363) | `ContextVersionStore._activate` | `messages: list[ContextEntry], revision_id: str` | `None` | Implement `ContextVersionStore._activate`. |
| [tool_provider.py](tool_provider.py#L20) | `ContextVersionToolProvider.materialize` | `session: Any, policy: ToolPolicy, role: str, agent_name: str \| None` | `list[Tool]` | Implement `ContextVersionToolProvider.materialize`. |
| [tool_provider.py](tool_provider.py#L51) | `context_version_tool_registration` | `core: 'AngelusCore'` | `ToolProviderRegistration` | Implement `context_version_tool_registration`. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [messages.py](messages.py#L38) | `ContextImage` | `attachment_id: str, media_type: str, detail: Literal['auto', 'low', 'high']` | `object` | One durable image reference attached to a message or tool result. |
| [messages.py](messages.py#L70) | `ContextToolCall` | `name: str, arguments: JsonObject, call_id: str \| None, source: str \| None` | `object` | One tool invocation emitted by the model. |
| [messages.py](messages.py#L99) | `ContextToolInfo` | `call: ContextToolCall, result: str \| None, images: tuple[ContextImage, ...]` | `object` | A tool call paired with its execution result and image outputs. |
| [messages.py](messages.py#L125) | `ContextMessage` | `role: str, timeline: int, content: str, content_reasoning: str, tool_calls: tuple[ContextToolInfo, ...], tags: tuple[str, ...], usage: dict[str, int], model_duration_ms: int \| None, round_duration_ms: int \| None, created_at: float \| None, images: tuple[ContextImage, ...]` | `object` | One active transcript message, mirroring ``LLMContext``. |
| [messages.py](messages.py#L292) | `ContextCompactedMessage` | `abstract_msg: str, source_timeline: tuple[int, ...], source_uuid: tuple[str, ...], tags: tuple[str, ...]` | `object` | One compacted summary, mirroring ``LLMContextCompacted``. |
| [store.py](store.py#L39) | `ContextVersionError` | `None` | `ValueError` | Safe context revision or edit rejection. |
| [store.py](store.py#L44) | `ContextEditOperation` | `kind: str, target_record_id: str, content: str, role: str` | `object` | Provide `ContextEditOperation` behavior. |
| [store.py](store.py#L52) | `ContextRevision` | `revision_id: str, parent_revision_id: str \| None, agent: str, created_at: float, actor: str, reason: str, operations: tuple[ContextEditOperation, ...], restored_from: str \| None, snapshot_sha256: str` | `object` | Immutable metadata describing one context snapshot. |
| [store.py](store.py#L67) | `ContextRevisionDocument` | `revision: ContextRevision, messages: tuple[ContextEntry, ...]` | `object` | The complete ``context-revisions/<revision_id>.json`` document. |
| [store.py](store.py#L82) | `ArchiveSearchResult` | `agent: str, query: str, archive_records: int, scanned_records: int, evidence: tuple[ArchiveEvidence, ...]` | `object` | Ranked lexical evidence from one Agent's compacted-out archive. |
| [store.py](store.py#L93) | `ArchiveRecordResult` | `agent: str, record: LLMContext` | `object` | One full archived context record resolved by timeline identity. |
| [store.py](store.py#L144) | `ContextVersionStore` | `agent: Any, agent_name: str` | `object` | Version and rewrite only one live Agent's active linear context. |
| [tool_provider.py](tool_provider.py#L17) | `ContextVersionToolProvider` | `core: 'AngelusCore'` | `object` | Provide `ContextVersionToolProvider` behavior. |

<!-- END GENERATED SYMBOL MAP -->
