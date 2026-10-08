# 持久化之后「新增信息渲染」定位说明

> 状态：**仅定位，未改动任何代码。** 记录于 2026-10-08。
> 背景：排查"持久化结束 → 新增信息的渲染"链路时，发现三处彼此独立的缺陷。
> 它们分属三个不同层（journal / 前端 / llmfetcher 上下文 handler），修复互不依赖。

## 结论摘要

| 通路 | 所在层 | 现象 | 当前是否用户可见 |
|---|---|---|---|
| **A** durable offset 未落盘 | `execution_module/journal.py` → `console_module/projection_service.py` → 前端 | 后端 `durable_offset` 恒为 `0`；前端两个记账变量**只写不读**，"只渲染新增持久化事件"的机制是死的 | 不可见（死管线，无消费方） |
| **B** 前端结束路径不一致 | `frontend/static/app.js` | lifecycle `done` / `error` 收尾时**不重取**历史与 Trace，只有 run-graph 完成路径会 | 可见（依赖实时流一帧不丢） |
| **C** `_pending_resume` 在 `load()` 后被清 | `llmfetcher/context_handlers/linear/` | "压缩 → 落盘 → 重新 load"之后不再渲染派生 resume 轮 | 条件可见（可达性待确认） |

三者中只有 **B** 是今天就能观察到的渲染差异；**A** 是失效的死管线；**C** 是行为不对称，是否需要修取决于下面的可达性分析。

---

## A. durable offset 从未落盘

### 机制

`angelus/modules/execution_module/journal.py` 的 `append()`（L35-69）先把事件序列化写入 NDJSON 并 fsync，**之后**才计算 offset：

```python
encoded = json.dumps(event, ensure_ascii=False, separators=(",", ":"), default=str) + "\n"
...
handle.write(encoded)
handle.flush()
os.fsync(handle.fileno())
event["offset"] = handle.tell()      # ← 行已经写出去了
```

`event` 组装时（L47-60）的字段是 `event_id / execution_id / type / timestamp / agent / message / usage / duration_ms / data`，**不含 `offset`**。因此：

- append 的**返回值**（内存里）带 `offset`；
- **落盘的那一行不带** `offset`；
- 读取方 `journal.events()`（L72-88）是从文件 `json.loads(line)` 重新解析的 → **读回的条目也没有 `offset`**。

### 下游影响

`angelus/modules/console_module/projection_service.py` 的 `events()`：

```python
page.append({**item, "data": data, "event": "lifecycle", ...})       # L554-565，item 无 offset
...
return {"events": page, ..., "durable_offset": page[-1].get("offset", 0) if page else 0}   # L567
```

→ `durable_offset` **恒为 `0`**。

前端那套"持久化后只渲染新增事件"的记账全部是死代码：

| 变量 | 声明 | 写入 | 读取 |
|---|---|---|---|
| `durableEventCount` | `app.js:61` | `app.js:902`（非 ephemeral 事件 +1）、`app.js:815`（重置） | **无** |
| `durableEventOffset` | `app.js:62` | `app.js:610`（取自 `page.durable_offset`）、`app.js:815`（重置） | **无** |

### 复现 / 验证（只读）

- 静态：确认 `journal.events()` 读回的字典键里没有 `offset`——比较 `journal.append()` 的返回值与 `journal.events()` 的同一条。
- 运行期：对任一有 journal 的 session 调用 `/api/sessions/{id}/events`，观察响应里的 `durable_offset` 恒为 `0`。

### 判定

**没有任何消费方，所以今天不产生可见错误**——它是"想做增量渲染但没做成"的残留。
若要让"持久化后只渲染新增信息"成立，需要先把 offset 写进落盘行（或在读取时按字节反推），
再让前端真的消费 `durable_offset`；否则现在的策略只能是整页重取（见 B）。

---

## B. 前端结束路径不一致（唯一当前可见项）

`app.js` 里"本轮结束"有四个入口，处理**不一致**：

| 结束信号 | 位置 | 处理 |
|---|---|---|
| run-graph `run.state_changed` → `completed` / `failed` / `stopped` / `interrupted` | `app.js:1007` | `loadHistory()` **+ `loadTrace(true)`** + `finish()` |
| lifecycle `result` | `app.js:923` | 只 `loadHistory()` |
| lifecycle `done` | `app.js:926` | 只 `finish()`——**不重取历史，也不重取 Trace** |
| lifecycle `error` | `app.js:924` | 只 `finish()` |

相关配套：

- `finish()`（`app.js:928`）注释写"lifecycle SSE drains committed tail and closes itself"，但客户端在 drain 结束、连接关闭时并不做任何对账。
- `connectLifecycleEvents`（`app.js:1009`）的 `onerror` 分支在 `readyState === CLOSED` 时**只是** `lifecycleSource = null`，既不 `loadTrace(true)` 也不 `loadHistory()`。
- 对比 `connectRunGraphEvents`（`app.js:1008`）的 CLOSED 分支至少会 `finish()`。

### 影响

Trace 面板（标题即 "EVENT STREAM"）与 chat 都同时存在"实时 SSE 渲染"和"从持久化存储重取"两条来源：

- 重取是**整体重建**——`loadTrace(true)` 重置 `traceEvents` 与 DOM（`app.js:610`）；`loadHistory()` 是 `streamingMessages.clear()` + `chat.replaceChildren(...)`（`app.js:746-760`）。所以重取**不会**产生重复渲染。
- 但正因为它只在部分路径发生：如果本轮靠 lifecycle 的 `done` / `error` 收尾，则**持久化后的对账不会发生**，界面保留的是实时流那一份。此时若实时流丢帧、或客户端是在中途挂上来的（`lifecycleCursor` 从当前位置开始），持久化里已有、但没被这客户端收到的事件就**不会出现在 Trace 里**，且本轮结束后不再有机会补齐（除非用户手动刷新或点"加载更早事件"）。

### 复现 / 验证

- 纯前端观察：让 lifecycle 流先收尾（例如 run-graph 流先关闭）而不触发 `run.state_changed` 的终态，看 Trace 是否发生整页重取。
- 也可直接对比两条结束路径到达 `handleEvent` 后的 state：`traceEvents` 是否被重置。

### 判定

这是"持久化后新增渲染"里唯一当前可见的缺陷，且**只改 `app.js` 即可闭环**（把终态收尾统一到一处，或在 `done`/`error` 时补 `loadHistory()` + `loadTrace(true)`）。

---

## C. `_pending_resume` 在 `load()` 之后被清掉

### 机制

- `llmfetcher/context_handlers/linear/handler.py` 的 `compact()` 成功归档后置 `self._pending_resume = True`。意图（代码注释）：压缩会把全部 active 消息移入 archive，下一次请求否则只剩 system prompt + abstract，某些 provider 对"没有 user 轮"的请求回 EMPTY_RESPONSE。
- `build_messages()` → `linear/rendering.py::render_messages(host, *, pending_resume=...)` 在 `pending_resume` 为真时追加一个**派生** user 轮 `"Continue user's job from your checkpoint, now."`（刻意不落盘、不占 timeline、不会被再次归档）。
- 但 `handler.py` 的 `load()` 里**无条件**：

  ```python
  # The resume prompt is derived state, never persisted.
  self._pending_resume = False
  ```

### 影响

"压缩 → 落盘 → 重新 `load()`"之后，resume 轮**不再渲染**。而落盘的 checkpoint 恰好是"`messages` 为空 + `abstract` 非空"的状态，正是当初需要它的场景：
只有当该轮 `msg` 为空（例如同一 run 内工具结果驱动的后续轮）时请求才会退化为 system-only。

> 说明：这段行为在 2026-10-08 把 `linear.py` 拆成 `linear/` 包时是**原样保留**的，不是那次重构引入的。

### 可达性（待确认）

是否真的可触发，取决于"load 之后紧接着跑一个 `msg` 为空的轮次"是否可达：

- 会话恢复路径：`angelus/modules/application_module/session_service.py` 在恢复会话时会 `agent.context_handler.load(context_path)`；
- 需要确认：恢复后是否可能在不插入新 user 消息的前提下直接继续一个工具轮。

若可达，则该请求会退化成 system-only，命中当初加 resume 轮要防的 EMPTY_RESPONSE。

### 复现 / 验证

构造 `ContextHandlerLinear`：加若干 user/assistant 消息 → `compact()` 成功 → `save(path)` → `load(path)` → `build_messages()`，
观察结果里**不再**出现 `"Continue user's job from your checkpoint, now."`（而 `compact()` 之后立刻 `build_messages()` 会出现）。

---

## 附带：SSE id 与分页游标的语义差一位（当前靠约定回避）

- `/events/stream` 的 SSE `id:` 取的是 **index + 1**：

  ```python
  page = _service(request).events(session_id, next_cursor, 500)   # 返回 index >= next_cursor
  for event in records:
      next_cursor += 1
      yield f"id: {next_cursor}\ndata: ..."                       # session_console.py:236-240
  ```

- `/events` 分页的 `next_cursor` 取的是 **index**：

  ```python
  next_cursor = start + len(page)                                  # projection_service.py:566
  ```

两者的"续读"语义（`index >= cursor`）恰好自洽，所以今天不会出错——但前提是前端用**两个独立变量**承接：
`lifecycleCursor`（来自 SSE `id:`）与 `traceBefore`（来自分页 `next_cursor`），见 `app.js:63-64`、`610`、`1009`。
一旦有人把二者混用（例如拿分页游标去当 `Last-Event-ID`），就会少渲染或多渲染恰好一条。

---

## 未覆盖 / 需要确认

- **C 的可达性**：需确认"载入 checkpoints（messages 空 + abstract 非空）后直接进入空 msg 轮次"是否真实可达。
- **A 的修复取向**：是"让 offset 落盘后前端消费"，还是"承认不需要增量渲染、删掉这组死变量"，取决于是否真的要为长 journal 省一次整页重取。
- 本说明**不涉及** `agent:retry` / 调用账本的可见性（那部分另见重试语义排查），也不涉及 chat 分页本身（`loadOlderMessages` 与 `loadHistory` 无重复渲染问题）。
