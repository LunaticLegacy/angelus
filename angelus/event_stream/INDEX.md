# angelus/event_stream — Event Broadcast INDEX

## Route Map

| File | Responsibility |
|---|---|
| `broker.py` | 有界、多订阅者的进程内事件广播，维护序号、持久偏移水位、溢出检测和关闭通知。 |
| `publisher.py` | 将持久事件按“追加并 fsync → 广播”的顺序提交。 |
| `sse.py` | 历史回放、实时交接、慢客户端补偿和 SSE `id` 编码。 |
| `__init__.py` | 无循环依赖的公共导出门面。 |

## Invariants

- 持久事件只有在 `events.ndjson` 完成 `fsync` 后才进入广播环。
- 每个订阅者拥有独立游标；广播环不会竞争消费。
- 空闲等待只产生 15 秒 keepalive，不读取事件日志。
- 环溢出只从磁盘补偿持久事件；临时流式 delta 是尽力交付。

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [__init__.py](__init__.py#L17) | `__getattr__` | `name: str` | `Any` | Load storage-dependent helpers lazily to avoid class import cycles. |
| [broker.py](broker.py#L79) | `EventBroker.publish` | `payload: dict[str, Any], durable_offset: int \| None` | `EventEnvelope` | Publish one event and wake every subscriber. |
| [broker.py](broker.py#L107) | `EventBroker.snapshot` | `None` | `BrokerSnapshot` | Return the current sequence and durable handoff watermark. |
| [broker.py](broker.py#L114) | `EventBroker.wait_after` | `sequence: int, timeout: float` | `BrokerBatch` | Wait for and return events newer than one subscriber sequence. |
| [broker.py](broker.py#L144) | `EventBroker.close` | `None` | `None` | Close the broker and wake all waiting subscribers. |
| [publisher.py](publisher.py#L11) | `publish_durable_event` | `active: ActiveRun \| None, workspace_id: str, session_id: str, payload: dict[str, Any]` | `int` | Append, fsync, then broadcast one durable browser event. |
| [sse.py](sse.py#L14) | `encode_sse_event` | `payload: dict[str, Any], durable_offset: int \| None` | `str` | Serialize one payload without advancing SSE IDs for live-only data. |
| [sse.py](sse.py#L31) | `historical_event_stream` | `workspace_id: str, session_id: str, start_offset: int` | `Iterator[str]` | Replay durable records once for a session without a live worker. |
| [sse.py](sse.py#L51) | `live_event_stream` | `workspace_id: str, session_id: str, active: ActiveRun, start_offset: int, keepalive_timeout: float` | `Iterator[str]` | Replay a durable snapshot, then consume event-driven broadcasts. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [broker.py](broker.py#L12) | `EventEnvelope` | `sequence: int, payload: dict[str, Any], durable_offset: int \| None` | `object` | One live event and its optional durable-log commit position. |
| [broker.py](broker.py#L28) | `BrokerSnapshot` | `sequence: int, durable_offset: int, closed: bool` | `object` | Atomic handoff watermark captured before historical disk replay. |
| [broker.py](broker.py#L37) | `BrokerBatch` | `events: tuple[EventEnvelope, ...], latest_sequence: int, durable_offset: int, gap: bool, closed: bool, timed_out: bool` | `object` | Events available after one subscriber cursor and broker state. |
| [broker.py](broker.py#L48) | `EventBroker` | `capacity: int, durable_offset: int` | `object` | Broadcast a bounded event history to independent SSE subscribers. |

<!-- END GENERATED SYMBOL MAP -->
