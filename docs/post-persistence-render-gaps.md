# 持久化之后「新增信息渲染」定位说明

> 状态：**定位完成；B 已双侧修复（服务端帧序 + 前端「已终结 round」守卫）。**
> 记录于 2026-10-08。B 的服务端修复当时即落地，随后在 `2513248` 里被静默回退，2026-11-04 恢复，并补上前端守卫。
> 背景：排查"持久化结束 → 新增信息的渲染"链路时，发现四处彼此独立的缺陷。它们分属不同层（journal / SSE 路由 / 前端 / llmfetcher 上下文 handler），修复互不依赖。
> 行号基线：`frontend/static/app.js` 1634 行（161713 B，纯 CRLF）、`angelus/api/session_console.py` 468 行（CRLF）、`frontend/static/controllers/stream-controller.js`（LF）。

## 结论摘要

| 通路 | 所在层 | 现象 | 状态 |
|---|---|---|---|
| **A** durable offset 未落盘 | `execution_module/journal.py` → `console_module/projection_service/service.py` → 前端 | 后端 `durable_offset` 恒为 `0`；前端两个记账变量**只写不读**，"只渲染新增持久化事件"的机制是死的 | 开放（死管线，无消费方） |
| **B** 帧序竞态：durable 页先于 ephemeral 缓冲 | `angelus/api/session_console.py::events_stream` + `frontend/static/controllers/stream-controller.js` | 终局 round 的尾部 delta 被排在 `agent:round` **之后**，前端因此为已终结的 round 重建流式卡片，且再无清理机会 | **已双侧修复**（服务端每轮先排空 ephemeral；前端 `settled` 集合拒绝为已终结 round 建卡）。注意：服务端修复曾被 `2513248` 静默回退，见下 |
| **B′** 前端结束路径不一致 | `frontend/static/app.js` + `controllers/run-stream-controller.js` | lifecycle `done` / `error` 收尾时**不重取**历史与 Trace，只有 run-graph 完成路径会 | 开放（`finish()` 现在会清掉残留卡片，但仍不与持久化对账） |
| **C** `_pending_resume` 在 `load()` 后被清 | `llmfetcher/context_handlers/linear/handler.py` | "压缩 → 落盘 → 重新 load"之后不再渲染派生 resume 轮 | 条件可见（可达性待确认） |

**已修的是 B，而且是两侧都修**：服务端把"轮内 delta"排到"终结该轮的 durable 记录"之前（把竞态窗口从"每个 round 都可能"收窄到"极窄"），前端再用 `settled` 集合做兜底（把窗口压到 0）。

为什么两侧都要动：ephemeral 帧不带 SSE `id:`、不参与 durable 游标，两条通道各自独立分页，因此服务端顺序**不能**给出严格因果序——它只保证"同一次轮询里 delta 先于事实"，不保证"delta 一定先于事实产生"。要彻底免疫（含客户端漏帧、重连、乱序），必须由前端记住"这个 round 已经结束"，而不是靠到达顺序。

**A** 是失效的死管线；**B′** 是"实时流与持久化存储不对账"的稳健性问题（不是重复渲染的成因）；**C** 是行为不对称，是否需要修取决于下面的可达性分析。

---

## A. durable offset 从未落盘

### 机制

`angelus/modules/execution_module/journal.py` 的 `append()`（L35-72）先把事件序列化写入 NDJSON 并 fsync，**之后**才计算 offset：

```python
event = {                                    # L50-62，键里没有 offset
    "event_id": ..., "execution_id": ..., "type": ..., "timestamp": ...,
    "agent": ..., "message": ..., "usage": ..., "duration_ms": ..., "data": ...,
}
encoded = json.dumps(event, ...) + "\n"      # L63  ← 序列化发生在这
...
handle.write(encoded)                        # L67
handle.flush()                               # L68
os.fsync(handle.fileno())                    # L70
event["offset"] = handle.tell()              # L71  ← 行已经写出去了
```

因此：

- append 的**返回值**（内存里）带 `offset`；
- **落盘的那一行不带** `offset`；
- 读取方 `journal.events()`（L74-91）是从文件 `json.loads(line)` 重新解析的 → **读回的条目也没有 `offset`**。

### 下游影响

`angelus/modules/console_module/projection_service/service.py` 的 `events()`（L572-598）：

```python
page.append(self._event_payload(item))                                     # L596，item 无 offset
return {"events": page, ..., "durable_offset": page[-1].get("offset", 0) if page else 0}   # L598
```

`_event_payload()`（L654）返回的是 `{**item, "data": ..., "event": ..., ...}`（L670-）、**不会补 `offset`** → `durable_offset` **恒为 `0`**。

前端那套"持久化后只渲染新增事件"的记账全部是死代码：

| 变量 | 声明 | 写入 | 读取 |
|---|---|---|---|
| `durableEventCount` | `app.js:88` | `app.js:1206`（非 ephemeral 事件 +1）、`app.js:1083`（切会话归零） | **无** |
| `durableEventOffset` | `app.js:89` | 只剩两处归零：`app.js:845`（`loadTrace`）、`app.js:1084`（切会话） | **无** |

比原先的记录更死一步：`app.js` 里**已经没有任何 `durable_offset` 字样**——"从 `page.durable_offset` 写入"的那条路径在后续重构中一并消失了，所以 `durableEventOffset` 现在连"写错值"的机会都没有，只是两个恒为 0 的变量。

### 复现 / 验证（只读）

- 静态：比较 `journal.append()` 的返回值与 `journal.events()` 的同一条，后者键集合里没有 `offset`。
- 运行期：对任一有 journal 的 session 调 `/api/sessions/{id}/events`，响应里的 `durable_offset` 恒为 `0`。

### 判定

**没有任何消费方，所以今天不产生可见错误**——它是"想做增量渲染但没做成"的残留。
若要让"持久化后只渲染新增信息"成立，需要先把 offset 写进落盘行（或读取时按字节反推），再让前端真的消费 `durable_offset`；否则现在的策略只能是整页重取（见 B′）。

---

## B. 帧序竞态：durable 页先于 ephemeral 缓冲（**已双侧修复**）

### 症状

一条**已完成**的消息（带用量页脚）之后，同一 round 的**尾部文字又被单独起了一张流式卡片**，标签"正在生成"；卡片内容只是从某个 delta 边界开始的半句（例如原文 `你说了算，我不擅自动手。` 被渲染成 `你说自 算，我不擅自动手。`），并且永不消失。

复现对象是**实际被服务的那份前端**：先确认 HTTP 返回的 `app.js` 与磁盘一致（161713 B，sha256 前缀 `9f4d7db1…`，`ephemeral_first=True`），排除"改了没生效 / 浏览器拿旧缓存"这一类干扰。`app-loader.js:8` 的版本号（`app.js?v=context-architecture-17`）保证新控制器与会话切换的重置逻辑真的被浏览器取到。

### 根因

`agent:stream_delta` 是 **live-only**：`angelus/modules/application_module/execution_service.py` 把它交给 `attempt.publish_ephemeral(...)`，**不进 journal**。而 SSE 每轮循环原本**先刷 durable journal 页、再排空 ephemeral 缓冲**（`session_console.py::events_stream`）。

于是"轮内 delta"与"轮末 durable 记录"落在同一次轮询时，到达顺序被反转：

1. 客户端上一次轮询已排空一部分 delta → 流式卡片累积到一半。
2. round 结束：`agent:round`（durable）落盘，可能连同 `agent:complete` / `result`。
3. 下一次轮询：**先**发 durable → `agent:round` 触发 `settleStream(agent, R)`（`app.js:1226`，**在任何 agent 过滤判断之前**）移除卡片；同一条 `if` 链里的 `agent:complete` 触发 `discardAgentStreams(...)`（`app.js:373`）；`result` 触发 `loadHistory()`（`app.js:1227`，其中 `streamController.clear()`，`app.js:992`）。
4. **然后**才排空 ephemeral → 剩下的尾部 delta 到达：`renderStreamDelta`（`app.js:369`）→ `streamController.updateDelta`。
5. 旧版控制器在 `updateDelta` 开头就 `stateFor(...)`，`stateFor` 里"没有就新建"⇒ 为已终结的 round **重新建卡**；此后不会再有 `agent:round R` 来收拾它，服务端下一轮发现状态非 running 就 `return` 关流 ⇒ 卡片永久残留。

只有**终局 round** 的尾部 delta 会被排在这些终态 durable 记录之后（中间 round 即便也竞态留下孤儿卡片，也会被后续 `agent:complete` / `loadHistory()` 顺手清掉），所以"永不消失"的现象集中在"最后一块"。

### 修复（一）服务端帧序

`events_stream` 每一轮改为**先排空 ephemeral、再发 durable 页**（`angelus/api/session_console.py:277-297`）：

```python
while True:
    # Deltas first.  The two channels have independent cursors and a
    # round's trailing deltas are published *before* the round's own
    # durable fact, so draining the journal first would hand the
    # browser a settled card followed by deltas for the same round.
    live = _service(request).ephemeral_events(session_id, live_after)      # L282
    for event in live["events"]: ... yield f"data: ..."                    # L283-285，无 id:
    page = _service(request).events(session_id, next_cursor, 500)          # L286
    for event in records: next_cursor += 1; yield f"id: {next_cursor}..."  # L288-290
```

轮询节奏仍由 durable 页驱动（`if not records: yield ": keep-alive"` + `time.sleep(0.25)`，L295-297），ephemeral 只是被提前——不改变"何时关流"的判定。注释 + docstring 写明了这个顺序约束，避免被再次当成"随手排一下"改回去。

回归测试：`tests/test_lifecycle_event_stream.py`——断言 live 帧先于 `agent:round`，且 ephemeral 帧不带 `id:`。

### 该修复曾丢失：`2513248` 静默回退

- `9daba7a`（2026-10-08，"fix(console): order live frames before the durable page in the lifecycle stream"）**同时**加入"先排空 ephemeral"与上述测试。
- `2513248`（2026-11-01，"Migrate backend core and API modules"）是一次大范围迁移提交，它把 ephemeral 排空**移回** durable 页之后、并**删掉了 3 行解释顺序的注释**（`git show 2513248 -- angelus/api/session_console.py`：该文件 +10/−9，其中顺序 hunk 为 −7/+4）。
- 后果：测试从绿变红，但因为同一次提交动了十几个模块，红灯没有被注意；缺陷在 `2513248` 之后一直在线，直到 2026-11-04 被重新定位。
- 2026-11-04 恢复：顺序 + 注释 + docstring 约束一起回来。反证用**改动前的模块副本**跑同一套测试（`_redgreen.py`，不动工作树）：改前 `assertIn("agent:stream_delta", frames[0])` 实际拿到 `id: 1 … agent:round`（FAIL），改后 PASS。

教训写在这里而不是提交信息里：**这类"顺序约束"必须由测试锁定，否则下一次批量迁移会再抹一遍**。

### 修复（二）前端「已终结 round」守卫

`frontend/static/controllers/stream-controller.js` 新增 `settled` 集合：

| 动作 | 语义 | 触发点 |
|---|---|---|
| `settle(agent, round)` | 记入 `settled` **并**移除该 round 的卡片 | `agent:round` → `settleStream`（`app.js:1226`） |
| `updateDelta` / `updateTool` | 命中 `settled` 直接 `return`（不再建卡，也不更新已删的卡） | 迟到的 delta / 工具事件 |
| `discard` / `discardAgent` | 只移除卡片，`settled` **保留** | `agent:complete`、`result` 的清理路径 |
| `clear()` | 移除所有卡片，`settled` **保留** | `loadHistory()`（`app.js:992`）、`finish()`（`app.js:1232`） |
| `reset()` | `clear()` + 清空 `settled` | `start()`（`app.js:1120`）、`switchSession()`（`app.js:1075`） |

接线要点（每条都对应一个具体的错误可能）：

- `settleStream`（`app.js:372`）与 `discardStream`（:371）、`discardAgentStreams`（:373）并列，都是控制器的薄包装，`app.js` 不再直接碰 `streamingMessages`。
- **`agent:round` 的 settle 放在 agent 过滤之前**：过滤只决定"要不要渲染正式消息"，而"该 round 已结束"是全局事实——被过滤掉的 agent 的迟到 delta 同样不该建卡。
- **`clear()` 保留 `settled`**：`loadHistory()` 每次刷新都会清卡片，如果连 `settled` 一起清，刷新之后到达的迟到 delta 又能重建卡片——那正是原 bug 的第二次机会。所以"清卡片"与"忘掉已终结 round"是两个动作。
- **`switchSession()` 必须 `reset()`**：`settled` 的键是 `agent:round`，跨会话会撞（新会话的 `coordinator:1` 会被上一会话的 `coordinator:1` 静音）。这是本轮新增的一行（`app.js:1075`）。
- `finish()`（`app.js:1232`）改用 `clear()`：终态收尾时把还开着的卡片收干净，避免"run 结束了但卡片还在转圈"。

### 实测证据：四格矩阵

用两个真实 attempt 的 journal + ephemeral 流驱动渲染器回放（`_matrix.mjs`，数据取自本机实际运行记录，不是构造样例）：

| attempt | journal 行 / 流字符 | 配置 | lateDeltas | ghostCards | ghostsAtEnd |
|---|---|---|---|---|---|
| `0693238f…`（19 rounds） | 259 / 15537 | 旧序 + 旧渲染（改动前） | 37（18223 字符） | 9（9414 字符） | 0 |
| 同上 | 同上 | 旧序 + **新**渲染 | 37 | **0** | 0 |
| 同上 | 同上 | **新**序 + 旧渲染 | **0** | 0 | 0 |
| 同上 | 同上 | 新序 + 新渲染（线上组合） | 0 | 0 | 0 |
| `01a4edcb…`（1 round） | 22 / 2734 | 旧序 + 旧渲染（改动前） | 12（20 字符） | 1（21 字符） | **1** |
| 同上 | 同上 | 旧序 + **新**渲染 | 12 | **0** | 0 |
| 同上 | 同上 | **新**序 + 旧渲染 | **0** | 0 | 0 |
| 同上 | 同上 | 新序 + 新渲染（线上组合） | 0 | 0 | 0 |

读法与边界（不要过度解读）：

- 两个样本里"旧序 + 旧渲染"都产生了幽灵卡片，线上组合都是 0 ⇒ 与用户报告一致。
- `0693238f` 的 9 张幽灵卡片在 run 结束前被后续 `agent:complete` / `loadHistory()` 顺手清掉（`ghostsAtEnd=0`）；只有 `01a4edcb` 那张活到最后（`ghostsAtEnd=1`）——正好印证"只有终局 round 的尾部 delta 会永久残留"。
- 两个样本里"新序"单独就能把 `lateDeltas` 压到 0；反过来"新渲染"在旧序下也能把幽灵卡片压到 0 ⇒ 两半各自有效、互不依赖（服务端修因，前端修果）。
- `durableNoFooter=0` 在全部 8 行都成立：两个样本的 durable 消息本身都带页脚，所以**这一形态不由这两个样本承载**。矩阵复现的是本缺陷的卡片层症状（重复的"正在生成"卡片），"已完成消息缺页脚"是同一竞态在更早版本上的另一种可见形态，别拿矩阵去证明那个。
- 控制器契约另有 9 项断言全过（轮内 1 张卡、settle 后 0 张、settle 后迟到 delta/工具被丢弃、下一轮仍能重新建卡、`clear` 清卡但不清 `settled`、未 settle 的 round 在 `clear` 后仍能重开、`reset` 清卡且忘掉 `settled`）。

### 残留窗口

服务端顺序仍**不是严格因果序**：delta 与轮末记录若恰好落在"ephemeral 排空"与"durable 读取"之间，迟到 delta 依然可能晚于事实到达；ephemeral 帧也依旧没有 SSE id、不参与 durable 游标。

但这一窗口现在被前端守卫吸收了：任何 `agent:round` 过的 `(agent, round)` 都已进 `settled`，迟到 delta 一律丢弃。因此**"永久残留的流式卡片"这一可见故障已被两侧同时封死**；剩下的只是理论窗口，不再产生用户可见后果。

已知的良性边界：

- `settled` 只在内存、按标签页独立。多标签页时另一个标签页的 `settled` 不含本页刚 settle 的 round——但那只影响"另一标签页自己是否收到迟到 delta"这一极窄情形，而每个标签页有自己的 SSE 连接与游标，且 durable 卡片照常从持久化渲染，最多是预览态短暂缺失，不会出现幽灵卡片。
- `settled` 不持久化：刷新页面即重建，因此不存在"陈旧的静音"（刷新本来就会整页重取历史）。

---

## B′. 前端结束路径不一致（仍开放）

`app.js` 里"本轮结束"有四个入口，处理**不一致**：

| 结束信号 | 位置 | 处理 |
|---|---|---|
| run-graph `run.state_changed` → `completed` / `failed` / `stopped` / `interrupted` | `app.js:1322` | `loadHistory()` **+ `loadTrace(true)`** + `finish()` |
| lifecycle `result` | `app.js:1227` | 只 `loadHistory()`（不重取 Trace） |
| lifecycle `done` | `app.js:1230` | 只 `finish()`——**不重取历史，也不重取 Trace** |
| lifecycle `error` | `app.js:1228` | 只 `finish()` |

相关配套：

- `finish()`（`app.js:1232`）注释写"lifecycle SSE drains committed tail and closes itself"，但客户端在 drain 结束、连接关闭时并不做任何对账；它现在只多做了一件事——`streamController.clear()`，把还开着的卡片收干净（**清残留 ≠ 对账**）。
- `connectLifecycleEvents` 已迁到 `run-stream-controller.js`：收到终态事件时只 `source.close()` 并把 `lifecycleSource` 置空（`run-stream-controller.js:130-133`）；`onerror` 的 `CLOSED` 分支同样只置空就 `return`（`:138-143`），既不 `loadTrace(true)` 也不 `loadHistory()`。
- 对比 graph 流的 `onerror` 分支（`run-stream-controller.js:146-156`）至少会在确认 run 不再 active 后 `onFinish()`。

### 影响

Trace 面板（标题即 "EVENT STREAM"）与 chat 都同时存在"实时 SSE 渲染"和"从持久化存储重取"两条来源：

- 重取是**整体重建**——`loadTrace(true)` 重置 `traceEvents` 与游标（`app.js:845`）；`loadHistory()` 是 `streamController.clear()` + 重建消息区（`app.js:992`、`:1007`）。所以重取**不会**产生重复渲染。
- 但正因为它只在部分路径发生：如果本轮靠 lifecycle 的 `done` / `error` 收尾，则**持久化后的对账不会发生**，界面保留的是实时流那一份。此时若实时流丢帧、或客户端是在中途挂上来的（`lifecycleCursor` 从当前位置开始），持久化里已有、但没被这客户端收到的事件就**不会出现在 Trace 里**，且本轮结束后不再有机会补齐（除非用户手动刷新或点"加载更早事件"）。

### 复现 / 验证

- 纯前端观察：让 lifecycle 流先收尾（例如 run-graph 流先关闭）而不触发 `run.state_changed` 的终态，看 Trace 是否发生整页重取。
- 也可直接对比两条结束路径到达 `handleEvent` 后的 state：`traceEvents` 是否被重置。

### 判定

这**不是**"最后一块被重复渲染"的成因（那是 B），而是"实时流与持久化存储不对账"的稳健性问题。**只改前端即可闭环**：把终态收尾统一到一处，或在 `done`/`error`（含 `CLOSED` 分支）补 `loadHistory()` + `loadTrace(true)`。

注意：`finish()` → `clear()` 只是**让残留卡片不再可见**，它既不知道持久化里有什么，也不补漏帧——把它当成 B′ 的修复会是误判。

---

## C. `_pending_resume` 在 `load()` 之后被清掉

### 机制

- `llmfetcher/context_handlers/linear/handler.py` 的 `compact()`（L364）成功归档后置 `self._pending_resume = not self.messages`（L558）。意图（代码注释）：压缩会把全部 active 消息移入 archive，下一次请求否则只剩 system prompt + abstract，某些 provider 对"没有 user 轮"的请求回 EMPTY_RESPONSE。
- `build_messages()`（L587）把它传给装配层（L601），`llmfetcher/context_handlers/linear/assembly.py:274-275` 在 `pending_resume` 为真时追加一个**派生** user 轮 `RESUME_PROMPT`（`llmfetcher/context_handlers/placement.py:7`，内容 `"Continue user's job from your checkpoint, now."`，刻意不落盘、不占 timeline、不会被再次归档）。
- 但 `handler.py` 的 `load()`（L809）里**无条件**：

  ```python
  # The resume prompt is derived state, never persisted.     # L913
  self._pending_resume = False                              # L914
  ```

### 影响

"压缩 → 落盘 → 重新 `load()`"之后，resume 轮**不再渲染**。而落盘的 checkpoint 恰好是"`messages` 为空 + `abstract` 非空"的状态，正是当初需要它的场景：只有当该轮 `msg` 为空（例如同一 run 内工具结果驱动的后续轮）时请求才会退化为 system-only。

> 说明：这段行为在 2026-10-08 把 `linear.py` 拆成 `linear/` 包时是**原样保留**的（后来 `rendering.py` 又拆成 `assembly.py`/`paging.py`/`compaction.py`，逻辑未变），不是那几次重构引入的。

### 可达性（待确认）

是否真的可触发，取决于"load 之后紧接着跑一个 `msg` 为空的轮次"是否可达：

- 会话恢复路径：`angelus/modules/application_module/session_service.py` 在恢复会话时会 `agent.context_handler.load(context_path)`；
- 需要确认：恢复后是否可能在不插入新 user 消息的前提下直接继续一个工具轮。

若可达，则该请求会退化成 system-only，命中当初加 resume 轮要防的 EMPTY_RESPONSE。

### 复现 / 验证

构造 `ContextHandlerLinear`：加若干 user/assistant 消息 → `compact()` 成功 → `save(path)` → `load(path)` → `build_messages()`，观察结果里**不再**出现 `RESUME_PROMPT`（而 `compact()` 之后立刻 `build_messages()` 会出现）。

---

## 附带：SSE id 与分页游标的语义差一位（当前靠约定回避）

- `/events/stream` 的 SSE `id:` 取的是 **index + 1**（`session_console.py:289-290`）：

  ```python
  next_cursor += 1
  yield f"id: {next_cursor}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
  ```

  而同一循环里的 ephemeral 帧只发 `data:`、**不带 `id:`**（`:285`）⇒ 它们不推进 `Last-Event-ID`。

- `/events` 分页的 `next_cursor` 取的是 **index**（`projection_service/service.py:597-598`）：

  ```python
  next_cursor = start + len(page)
  ```

- 另一条通路又不一样：`/graph/events` 的 `id:` 取 `event["sequence"]`（`session_console.py:164-165`），是真正的序号而非 index+1。

这几种语义各自的"续读"都自洽，所以今天不会出错——但前提是前端用**不同的变量**承接：`traceBefore`（`app.js:78`，重置于 `:845`/`:1080`）与 `lifecycleCursor`（`run-stream-controller.js:21`，按 `message.lastEventId` 更新于 `:123`）。
一旦有人混用（例如拿分页游标去当 `Last-Event-ID`，或把 graph 的 `sequence` 当 index），就会少渲染或多渲染恰好一条。

---

## 本轮验证（2026-11-04）

| 命令 | 结果 |
|---|---|
| `python -m unittest tests.test_session_console tests.test_lifecycle_event_stream` | `Ran 54 tests … OK (skipped=10)` |
| `_redgreen.py`（用改动前的模块副本跑同一测试） | `baseline_before_patch=FAIL  after_patch=PASS` → 测试有效 |
| `_matrix.mjs`（真实 attempt 四格回放 + 控制器契约） | `RESULT: PASS`，矩阵见 B 节，契约 9/9 |
| `_verify_final.py`（结构/EOL/导出/接线断言） | `STRUCTURE: PASS`（26 项） |
| `node --check frontend/static/app.js` 等 + `node scripts/check-frontend-architecture.mjs` | 通过 |
| `_probe_served.py`（运行中的服务） | 三份静态资源的 `sha` 与磁盘一致；`import` 新进程 `ephemeral_first=True` |

---

## 未覆盖 / 需要确认

- **B 的理论窗口**：顺序仍非严格因果序，但已被前端 `settled` 守卫吸收，不再产生可见故障。若要连"理论窗口"一起消掉，得让 ephemeral 帧参与同一条有序序列（带 id、并入 durable 游标），成本和收益都不划算。
- **`settled` 的作用域**：内存态、per-tab、不持久化。跨标签页的极窄预览缺失是良性降级（durable 卡片照常渲染）；若将来要求"多标签页严格一致"，得把"已终结 round"下沉到服务端或持久化。
- **B′（结束路径不一致）**：仍开放。具体待改点：`app.js:1227`（`result` 缺 `loadTrace`）、`app.js:1228`（`error`）、`app.js:1230`（`done`）、`run-stream-controller.js:130-133` 与 `:138-143`（终态/`CLOSED` 只关流不入账）。
- **C 的可达性**：需确认"载入 checkpoints（messages 空 + abstract 非空）后直接进入空 msg 轮次"是否真实可达。
- **A 的修复取向**：是"让 offset 落盘后前端消费"，还是"承认不需要增量渲染、删掉这组死变量"，取决于是不是真要为长 journal 省一次整页重取。
- **前端没有 CI 级守卫**：`tests/test_session_console.py:1413` 的 `FrontendContextLoadTests` 是 `@unittest.skip("legacy static frontend retired; React/Tauri frontend is canonical")`，它原本是最适合放这层断言的地方；而回放矩阵依赖本机的真实 attempt 数据（硬编码绝对路径），只能留在 session 内、不进仓库。因此前端这一半目前靠：`_matrix.mjs` 回放 + `_verify_final.py` 结构断言 + `node scripts/check-frontend-architecture.mjs`。**这是本轮最薄的一环**，改控制器时务必重跑矩阵。
- 本说明**不涉及** `agent:retry` / 调用账本的可见性（那部分另见重试语义排查），也不涉及 chat 分页本身（`loadOlderMessages` 与 `loadHistory` 无重复渲染问题）。
