# 持久化之后「新增信息渲染」定位说明

> 状态：**定位 + 已修复其中一处（B）。** 记录于 2026-10-08，B 于同日修复。
> 背景：排查"持久化结束 → 新增信息的渲染"链路时，发现四处彼此独立的缺陷。
> 它们分属不同层（journal / SSE 路由 / 前端 / llmfetcher 上下文 handler），修复互不依赖。

## 结论摘要

| 通路 | 所在层 | 现象 | 状态 |
|---|---|---|---|
| **A** durable offset 未落盘 | `execution_module/journal.py` → `console_module/projection_service.py` → 前端 | 后端 `durable_offset` 恒为 `0`；前端两个记账变量**只写不读**，"只渲染新增持久化事件"的机制是死的 | 开放（死管线，无消费方） |
| **B** 帧序竞态：durable 页先于 ephemeral 缓冲 | `angelus/api/session_console.py::events_stream` | 终局 round 的尾部 delta 被排在 `agent:round` **之后**，前端因此为已终结的 round 重建流式卡片，且再无清理机会 | **已修复**（服务端改为每轮先排空 ephemeral；新增 `tests/test_lifecycle_event_stream.py`） |
| **B′** 前端结束路径不一致 | `frontend/static/app.js` | lifecycle `done` / `error` 收尾时**不重取**历史与 Trace，只有 run-graph 完成路径会 | 开放（依赖实时流一帧不丢） |
| **C** `_pending_resume` 在 `load()` 后被清 | `llmfetcher/context_handlers/linear/` | "压缩 → 落盘 → 重新 load"之后不再渲染派生 resume 轮 | 条件可见（可达性待确认） |

**已修的是 B**。**A** 是失效的死管线；**B′** 是"实时流与持久化存储不对账"的稳健性问题（不是重复渲染的成因）；**C** 是行为不对称，是否需要修取决于下面的可达性分析。

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
再让前端真的消费 `durable_offset`；否则现在的策略只能是整页重取（见 B′）。

---

## B. 帧序竞态：durable 页先于 ephemeral 缓冲（**已修复**）

### 症状

一条**已完成**的消息（带用量页脚）之后，同一 round 的**尾部文字又被单独起了一张流式卡片**，标签"正在生成"；卡片内容只是从某个 delta 边界开始的半句（例如原文 `你说了算，我不擅自动手。` 被渲染成 `你说自 算，我不擅自动手。`），并且永不消失。截图见该问题的前端复现。

### 根因

`agent:stream_delta` 是 **live-only**：`angelus/modules/application_module/execution_service.py` 把它交给 `attempt.publish_ephemeral(...)`（`execution_module/execution_attempt.py:106-130`），**不进 journal**。而 SSE 每轮循环**先刷 durable journal 页、再排空 ephemeral 缓冲**（`session_console.py::events_stream`）。

于是"轮内 delta"与"轮末 durable 记录"落在同一次轮询时，到达顺序被反转：

1. 客户端上一次轮询已排空一部分 delta → 流式卡片累积到一半。
2. round 结束：`agent:round`（durable）落盘，可能连同 `agent:complete` / `result`。
3. 下一次轮询：**先**发 durable → `agent:round` 触发 `discardStream(agent, R)`（`app.js:922`）移除卡片并 `appendMessage(...)` 落成正式消息；`agent:complete` / `result` 再触发 `discardAgentStreams(...)`（`:922`、`:923`），甚至 `loadHistory()` 整体重建。
4. **然后**才排空 ephemeral → 剩下的尾部 delta 到达。此时 `streamingMessages` 中已无 `agent:R`，`renderStreamDelta`（`app.js:206`）于是**新建卡片**：

   ```js
   let state=streamingMessages.get(key);
   if(!state){ state={..., view: chatView.beginStream(agent)}; streamingMessages.set(key,state); }
   ```

5. 不会再有任何 `agent:round R` 来 `discardStream` 它；服务端下一轮发现状态非 running 就 `return` 关流 → 卡片永久残留。

只有**终局 round** 的尾部 delta 会被排在这些终态 durable 记录之后（中间 round 即便也竞态留下孤儿卡片，也会被后续 `agent:complete` / `loadHistory()` 顺手清掉），所以现象集中在"最后一块"。

### 修复

`events_stream` 每一轮改为**先排空 ephemeral、再发 durable 页**（`angelus/api/session_console.py`），使轮内 delta 先于"终结该轮的记录"到达；路由 docstring 与循环注释写明了这个顺序约束，避免被改回去。

回归测试：`tests/test_lifecycle_event_stream.py` —— 断言 live 帧先于 `agent:round`，且 ephemeral 帧不带 `id:`。该测试在旧顺序下会失败（已用 `git stash` 反证）。

### 残留窗口

"先排空 ephemeral"把竞态窗口收窄到"delta 与轮末记录恰好在同一次轮询的 ephemeral 排空与 durable 读取之间产生"，但**不是严格因果序**：两者仍未放进同一条有序序列，ephemeral 帧依旧没有 SSE id、也不参与 durable 游标。要彻底免疫需要前端侧的"已终结 round"守卫（见文末"未覆盖"）。

---

## B′. 前端结束路径不一致（仍开放）

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

这**不是**"最后一块被重复渲染"的成因（那是 B），而是"实时流与持久化存储不对账"的稳健性问题：靠 lifecycle 的 `done` / `error` 收尾时不做整页重取，于是漏帧或中途挂载的客户端会留下缺口。**只改 `app.js` 即可闭环**（把终态收尾统一到一处，或在 `done`/`error` 时补 `loadHistory()` + `loadTrace(true)`）。

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

- **B 的残留窗口**：服务端帧序已改，但仍非严格因果序。若要彻底免疫（含客户端漏帧、重连、乱序），建议再加前端"已终结 round"守卫：`agent:round` 过的 `streamKey` 记入集合，`renderStreamDelta` / `renderStreamTool` 命中即拒绝创建卡片；`loadHistory()` / 切会话 / 开跑时清空该集合。
- **B′（结束路径不一致）**：仍开放，按上文建议统一终态收尾。
- **C 的可达性**：需确认"载入 checkpoints（messages 空 + abstract 非空）后直接进入空 msg 轮次"是否真实可达。
- **A 的修复取向**：是"让 offset 落盘后前端消费"，还是"承认不需要增量渲染、删掉这组死变量"，取决于是否真的要为长 journal 省一次整页重取。
- 本说明**不涉及** `agent:retry` / 调用账本的可见性（那部分另见重试语义排查），也不涉及 chat 分页本身（`loadOlderMessages` 与 `loadHistory` 无重复渲染问题）。
