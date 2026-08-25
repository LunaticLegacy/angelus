# angelus/history/ — History Projections INDEX

兼容入口 `angelus.history` 已由原来的单体 `history.py` 原地包化。调用方仍从包入口导入原符号，具体实现按读模型职责拆分。

## Route Map — Leaf Files

| File | Responsibility |
|---|---|
| `__init__.py` | 稳定兼容门面，重导出拆分前的历史、用量、上下文和图检查 API。 |
| `models.py` | 上下文预览、远程请求统计和图快照的只读 dataclass 响应模型。 |
| `transcripts.py` | 会话/Agent 事件归约规则、工具结果显示规范化及旧状态迁移。 |
| `projection.py` | 惰性增量转录投影、崩溃恢复、Agent 过滤与反向字节游标分页。 |
| `usage.py` | token 用量聚合、当前运行窗口和压缩归档分页。 |
| `context.py` | Agent checkpoint、远程请求、压缩输入和持久图的只读检查。 |

## Boundaries

- `__init__.py` 是兼容导入边界；新增实现应放入职责对应的叶文件。
- 所有读取投影都保持浏览器安全，不持久化模型凭据，也不修改上下文。
- `events.ndjson` 是权威历史；`projection.py` 写入的展示投影是可删除、可校验并自动重建的缓存。
- 投影记录保留原始 Markdown，只有返回页在响应前渲染 HTML；checkpoint 始终在投影 fsync 后原子提交。

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [__init__.py](__init__.py#L51) | `_agent_turns_page` | `workspace_id: str, session_id: str, agent_name: str, cursor: str \| None, before: int \| None, limit: int` | `dict[str, Any]` | Return a transcript page while preserving facade-level patchability. |
| [context.py](context.py#L20) | `_agent_context_preview` | `session_id: str, agent_name: str` | `AgentContextPreview` | Return context metadata and the latest exact remote request snapshot. |
| [context.py](context.py#L155) | `_agent_context_stats` | `session_id: str, agent_name: str` | `dict[str, Any]` | Return current context-length statistics for one Agent. |
| [context.py](context.py#L229) | `_agent_compaction_input_preview` | `session_id: str, agent_name: str` | `dict[str, Any]` | Return the exact text the context compactor would send for one Agent. |
| [context.py](context.py#L310) | `_agent_context_graph` | `session_id: str, agent_name: str, limit: int` | `ContextGraphSnapshot` | Return a bounded, browser-safe snapshot of one Agent's memory graph. |
| [models.py](models.py#L66) | `AgentContextPreview.to_dict` | `None` | `dict[str, Any]` | Serialize the stable response envelope for FastAPI and JSON. |
| [models.py](models.py#L147) | `ContextGraphSnapshot.to_dict` | `None` | `dict[str, Any]` | Serialize the graph snapshot for FastAPI without leaking storage data. |
| [projection.py](projection.py#L23) | `_projection_lock` | `path: Path` | `threading.Lock` | Return the process-local serialization lock for one projection. |
| [projection.py](projection.py#L36) | `_empty_checkpoint` | `None` | `dict[str, Any]` | Create the initial incremental event-reducer state. |
| [projection.py](projection.py#L58) | `_atomic_checkpoint` | `path: Path, checkpoint: dict[str, Any]` | `None` | Atomically commit reducer state after projection bytes are durable. |
| [projection.py](projection.py#L81) | `_load_checkpoint` | `session_path: Path, event_size: int` | `dict[str, Any] \| None` | Load and validate one committed projection checkpoint. |
| [projection.py](projection.py#L128) | `_append_turn` | `checkpoint: dict[str, Any], turns: list[dict[str, Any]], turn: dict[str, Any]` | `None` | Stage one raw display turn and update checkpoint counters. |
| [projection.py](projection.py#L148) | `_reduce_event` | `checkpoint: dict[str, Any], event: dict[str, Any]` | `list[dict[str, Any]]` | Reduce one durable lifecycle event into zero or more raw turns. |
| [projection.py](projection.py#L229) | `_synchronize_projection` | `session_path: Path` | `dict[str, Any]` | Bring one projection checkpoint to the latest complete event record. |
| [projection.py](projection.py#L302) | `_visible` | `turn: dict[str, Any], agent_name: str` | `bool` | Return whether one projection record belongs in an Agent filter. |
| [projection.py](projection.py#L316) | `_render_turn` | `turn: dict[str, Any]` | `dict[str, Any]` | Strip projection metadata and render Markdown for one returned turn. |
| [projection.py](projection.py#L332) | `transcript_page` | `workspace_id: str, session_id: str, agent_name: str, cursor: str \| None, before: int \| None, limit: int, path_resolver: Any` | `dict[str, Any]` | Return a cursor page from an incrementally maintained transcript. |
| [transcripts.py](transcripts.py#L26) | `_display_tool_result` | `value: Any` | `Any` | Recover structured tool data for every browser transcript path. |
| [transcripts.py](transcripts.py#L60) | `_history_context_paths` | `workspace_id: str, session_id: str` | `list[Path]` | Return current and legacy context locations in restoration priority. |
| [transcripts.py](transcripts.py#L80) | `_read_session_history` | `workspace_id: str, session_id: str` | `list[dict[str, Any]]` | Read display-safe user and assistant turns from persisted context. |
| [transcripts.py](transcripts.py#L138) | `_turns_from_legacy_context` | `path: Path` | `list[dict[str, Any]]` | Extract browser-safe transcript turns from one old Agent context file. |
| [transcripts.py](transcripts.py#L164) | `_turns_from_event_log` | `path: Path` | `list[dict[str, Any]]` | Recover a minimal chat transcript from durable swarm event records. |
| [transcripts.py](transcripts.py#L196) | `migrate_legacy_state` | `None` | `None` | Migrate all `.llmfetcher` data into independent `workspace` sessions. |
| [transcripts.py](transcripts.py#L261) | `_iter_agent_turns_from_events` | `workspace_id: str, session_id: str, agent_name: str` | `Iterator[dict[str, Any]]` | Stream an Agent transcript from the append-only lifecycle log. |
| [transcripts.py](transcripts.py#L391) | `_agent_turns_from_events` | `workspace_id: str, session_id: str, agent_name: str` | `list[dict[str, Any]]` | Reconstruct an Agent transcript from the append-only lifecycle log. |
| [transcripts.py](transcripts.py#L411) | `_paginate_turns` | `turns: list[dict[str, Any]], before: int \| None, limit: int` | `dict[str, Any]` | Slice a fully materialized turn list into a newest-first page. |
| [transcripts.py](transcripts.py#L443) | `_agent_turns_page` | `workspace_id: str, session_id: str, agent_name: str, before: int \| None, limit: int, _path_resolver: Callable[[str, str], Path] \| None` | `dict[str, Any]` | Return a bounded page of one Agent's display transcript. |
| [transcripts.py](transcripts.py#L517) | `_display_tools_from_event` | `data: dict[str, Any]` | `list[dict[str, Any]]` | Normalize completed lifecycle tool calls for browser display. |
| [transcripts.py](transcripts.py#L542) | `_read_agent_history` | `workspace_id: str, session_id: str, agent_name: str` | `list[dict[str, Any]]` | Read one Agent's complete display transcript from durable events. |
| [usage.py](usage.py#L10) | `_empty_usage` | `None` | `dict[str, int]` | Return the complete token-usage shape used by session aggregations. |
| [usage.py](usage.py#L14) | `_usage_from_events` | `events: list[dict[str, Any]]` | `tuple[dict[str, int], dict[str, dict[str, int]]]` | Aggregate usage events into (session-wide, per-agent) token dicts. |
| [usage.py](usage.py#L51) | `_current_run_window` | `events: list[dict[str, Any]]` | `list[dict[str, Any]]` | Return the durable events of the most recent lifecycle run. |
| [usage.py](usage.py#L81) | `_session_usage_summary` | `events: list[dict[str, Any]]` | `dict[str, Any]` | Aggregate the canonical per-call token ledger for a browser session. |
| [usage.py](usage.py#L129) | `_archived_context_page` | `workspace_id: str, session_id: str, agent_name: str, before: int \| None, limit: int` | `dict[str, Any]` | Return a bounded, read-only page of compacted raw context evidence. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [models.py](models.py#L9) | `AgentContextMetadata` | `index: int, source: str, type: str, length: int, timeline: str` | `object` | Schema for one provider message represented in an Agent context preview. |
| [models.py](models.py#L32) | `RemoteRequestStats` | `messages: int, characters: int, tool_schemas: int, tool_schema_characters: int, estimated_tokens: int` | `object` | Live size summary for one captured remote-request snapshot. |
| [models.py](models.py#L43) | `AgentContextPreview` | `messages: list[dict[str, Any]], metadata: list[AgentContextMetadata], request: dict[str, Any] \| None, total: int, stats: RemoteRequestStats \| None` | `object` | Schema returned to the workbench for one Agent context inspection. |
| [models.py](models.py#L83) | `ContextGraphNode` | `id: str, name: str, entity_type: str, summary: str, aliases: list[str], first_seen: int, last_seen: int, freq: int` | `object` | Browser-safe schema for one persisted long-term-memory entity. |
| [models.py](models.py#L97) | `ContextGraphEdge` | `source_id: str, target_id: str, relation: str, weight: float, first_seen: int, last_seen: int, valid: bool, evidence: list[int]` | `object` | Browser-safe schema for one relation between visible graph entities. |
| [models.py](models.py#L111) | `ContextGraphCommunity` | `level: int, community_id: str, summary: str, member_entity_ids: list[str]` | `object` | Browser-safe schema for one bounded persisted graph community. |
| [models.py](models.py#L121) | `ContextGraphSnapshot` | `available: bool, node_count: int, edge_count: int, community_count: int, truncated: bool, nodes: list[ContextGraphNode], edges: list[ContextGraphEdge], communities: list[ContextGraphCommunity], stale: bool` | `object` | Bounded API schema for an Agent's persisted long-term memory graph. |

<!-- END GENERATED SYMBOL MAP -->
