# Angelus arXiv 论文 — Phase 2 System Design（§3 设计章节素材稿）

> **状态**：Phase 2 交付物 `docs/paper/phase2-design.md`。对应 outline §3.3 System Design 六小节（§3.1-§3.6）的英文草稿 + 素材映射表 + 图注/结构描述。
> **证据纪律**：草稿中所有能力 claim 均带 `文件:行` 回溯（短名解析：`docs/`、`docs/research_innovation/`、`angelus/`、`llmfetcher/swarm_module/`、`frontend/static/`、`tests/`）。行号以 **2026-08-25 工作树**为准（与 `docs/research_innovation/*.md` 审计文档有漂移，本文已复核；漂移处标注）。README 不作能力证据。
> **D2 约定**：outline §7 T1-T6 为本节"恢复语义"与"前端控制台"两小节的 D2 增量设计输入；未实现部分以 ⚑ 标注，写作时不得写成已完成能力。
> **素材表列**：`素材`（file:line）｜`作用`（草稿中的 claim 支撑点）。

---

## §3.1 运行时模型（Runtime Model）

### 英文草稿（Draft，目标 150-300 词）

Angelus executes a swarm as a single in-process runtime owned by one browser session. The runtime separates *topology* from *live state*: an `ExecutionGraph` is a pure description of nodes (agent or routing), directed dependency edges, mappers and routers; the `TaskBus` is the scheduler-of-record that holds live per-task state (`queued`/`running`/terminal) and the structured report mailbox (`angelus_swarm_dynamics.md:3-4`, `execution_graph.py:295-354`, `task_bus.py:80-96`). During `run()`, the scheduler submits agents whose dependency count reaches zero through a `ThreadPoolExecutor`, drives each worker through a per-agent control view (`execution_graph.py:1534-1538`), and drains dynamically revived workers from the ready queue each cycle (`execution_graph.py:1566-1570`). Once the loop quiesces, the API layer finalizes unfinished dynamic tasks in its `finally` block (`api/runs.py:313-322`).

The topology is deliberately mutable during execution. A coordinator can spawn workers at runtime (`dispatch_task`, `dynamic_add_agent`), add or remove edges and callbacks, and revive a terminal worker via `redispatch_task` — each mutation emits a typed lifecycle event (`execution_graph.py:969,1063,1213,1265`). Runtime wiring exposes these as coordinator tools (`_attach_swarm_runtime_tools`, `runtime.py:595-652`). An observer attached by the runtime relays events to the durable event log and to the plan store: `task:dispatched`/`task:redispatched` bind a plan leaf to an assignment, `task:reported` updates its terminal status (`runtime.py:683-706`). The same observer persists a UI-safe `graph-view.json` after every event (`runtime.py:677`), so the console's topology, node states and task states always reflect the latest durable evidence (`execution_graph.py:457-505`).

（词数 ≈ 215；claim 均在素材表中可回溯。）

### 素材映射表

| 素材（file:line） | 作用 |
|---|---|
| `docs/research_innovation/angelus_swarm_dynamics.md:3-4` | "graph 是拓扑描述、TaskBus 持活任务状态"的架构定位句（§3.1 开篇 claim） |
| `llmfetcher/swarm_module/task_bus.py:80-96` | `TaskBus` 类、`_TERMINAL_STATES`、`threading.Condition` 锁（活任务状态机） |
| `llmfetcher/swarm_module/execution_graph.py:295-354` | `to_snapshot`：nodes/edges/callbacks/router_scopes/task_bus/task_by_agent/task_by_id（拓扑+状态的统一容器） |
| `llmfetcher/swarm_module/execution_graph.py:457-505` | `view_snapshot`：UI 安全视图（nodes 含 `dynamic`/`parent`、edges、assignments、task_states、node_states） |
| `llmfetcher/swarm_module/execution_graph.py:1453-1560` | `run()` 主循环：依赖计数、`ThreadPoolExecutor`、`control_for`、`interrupt_assignment` |
| `llmfetcher/swarm_module/execution_graph.py:1534-1538` | `control.for_agent(name)` 解析每 agent 控制视图（§3.1 "per-agent control view" 与 §3.4 交叉引用） |
| `llmfetcher/swarm_module/execution_graph.py:969` | `dispatch_task`：运行时创建 worker 的入口 |
| `llmfetcher/swarm_module/execution_graph.py:1063` | `redispatch_task`：仅终态任务可复活，保留旧 task→agent 映射（`angelus_capability_map.md:13`） |
| `llmfetcher/swarm_module/execution_graph.py:1213` | `dynamic_add_agent`：线程安全、run() 执行中可用 |
| `llmfetcher/swarm_module/execution_graph.py:1265` | `dynamic_add_connection`：仅源节点未完成前生效 |
| `llmfetcher/swarm_module/execution_graph.py:1853` | `_drain_dynamic_ready`：重新调度已复活的终态 worker |
| `angelus/runtime.py:595-652` | `_attach_swarm_runtime_tools`：把 `dispatch_subagent`/`create_swarm_tools` 挂给 coordinator（运行期 spawn 的运行时接线） |
| `angelus/runtime.py:653-681` | `_attach_swarm_observer`：捕获生命周期事件 + 持久化 `graph-view.json` |
| `angelus/runtime.py:683-706` | `_synchronize_plan_with_swarm_event`：:704 `task:dispatched/redispatched` → `bind_execution`，:706 `task:reported` → `update_execution_status` |
| `angelus/classes/browser_run_control.py:101-111` | `for_agent` → `AgentScopedRunControl`（每 agent 控制视图的实现） |

### Fig.1 系统架构图（图注 + 结构描述）

> **Caption（英文，供 Phase 3 定稿）**：*Fig. 1. Angelus system architecture. The browser console (left) communicates with the FastAPI control plane through REST/SSE; the runtime (center) holds the in-process ExecutionGraph topology, the TaskBus live task state, and one ContextEditStore per Agent; connectors (right) fan out to model providers, MCP servers, and local tools. Solid arrows are durable writes; dashed arrows are in-memory event/control flows.*

**结构描述**（供 Phase 3 绘图/排版）：
1. **前端控制台**（`frontend/static/app.js`）— 左列；节点：`currentGraph`（`app.js:56`）、agent-card 状态灯（`app.js:283-287`）、上下文图对话框（`app.js:359`）、恢复入口（`app.js:730`，D2 增加按钮）。
2. **API 控制面**（`angelus/api/runs.py` + `angelus/api/sessions.py`）— 中左；节点：`start_run`（`runs.py:85`）、`stop/force-stop/steer`（`runs.py:491/513/540`）、图/上下文编辑端点（`sessions.py:491/388/430/463`）、SSE 事件流（`runs.py:404`）。
3. **运行时核心**（`angelus/runtime.py` + `llmfetcher/swarm_module/`）— 中右；节点：`ExecutionGraph`（拓扑）、`TaskBus`（活任务）、`ContextEditStore`（每 agent 修订审计）、`BrowserRunControl`（停止/steer 注册表）。
4. **模型提供方/外部** — 右列；节点：LLM connector、MCP servers、Shell/本地工具、外部 Codex/Claude Code provider。
5. **持久化文件** — 底部横带：`swarm-runtime.json`（快照）、`graph-view.json`（UI 视图）、`contexts/<agent>.json` + `revisions/` + `context-edits.ndjson`（上下文修订）、`events.ndjson`（durable 事件日志）。
6. **连接标注**：前端↔API 走 REST/SSE（`connectRunEvents`，`app.js:729`）；API→运行时为进程内函数调用；运行时→持久化为原子 JSON 写（`context_editing.py:100` `_atomic_json`）；运行时→模型提供方为 connector 调用。控制流（虚线）:steer/stop 经 `BrowserRunControl` → `AgentScopedRunControl` → `Agent.run`。

---

## §3.2 组织快照格式（Organization Snapshot Format）

### 英文草稿（Draft）

Angelus persists a swarm as one JSON file, `swarm-runtime.json`, written atomically by `_persist_swarm_snapshot` (`runtime.py:824`, `execution_graph.py:355-374`). The payload is the versioned graph snapshot (`execution_graph.py:295-354`): `version`, `max_concurrency_agents`, nodes (kind `agent` or `routing`), dependency edges, declarative and custom callbacks, router scopes, the complete TaskBus mailbox, and the task↔agent index. Because the TaskBus is included, the snapshot is not merely a graph blueprint: completed assignments, reports, inbox ordering and terminal states all survive a restart as one recoverable unit.

The format is deliberately credential-free. Each Agent is encoded by the application-owned serializer `angelus.swarm-agent.v1` into only a `role` (`coordinator`/`dispatched`/`dynamic`) and — for workers — the `system_prompt`; `to_snapshot` runs a final `json.dumps` guard so no non-serializable handle can leak into the file (`runtime.py:843-851`, `execution_graph.py:350-352`). The round-trip regression asserts the file contains no API key: `assertNotIn("ephemeral-key", snapshot)` (`tests/test_swarm_restart_recovery.py:61`), and `_restore_swarm` documents "No secret is read from the snapshot" (`runtime.py:879`). Worker contexts are stored separately as per-agent checkpoints and are rebound deterministically by agent name during restore (`runtime.py:890`, `runtime.py:266`), so the recoverable unit spans topology + workers + TaskBus + private contexts — the Q2/RQ1 unit of the paper.

（词数 ≈ 185。）

### 素材映射表

| 素材（file:line） | 作用 |
|---|---|
| `angelus/runtime.py:824` | `_persist_swarm_snapshot`：写 `swarm-runtime.json` 的运行时入口（§3.2 主锚点） |
| `angelus/runtime.py:843-851` | `serialize_agent`：`angelus.swarm-agent.v1`，仅 role + worker `system_prompt`（无密钥的无密钥编码） |
| `angelus/runtime.py:853` | `swarm.save(_swarm_snapshot_path(...), agent_serializer=serialize_agent)`（调用点） |
| `angelus/runtime.py:511-522` | `_swarm_snapshot_path`：会话私有 `swarm-runtime.json` 路径（含"never API keys"docstring） |
| `llmfetcher/swarm_module/execution_graph.py:295-354` | `to_snapshot`：快照 JSON 结构（version/nodes/edges/callbacks/declarative/router_scopes/task_bus/task_by_agent/task_by_id） |
| `llmfetcher/swarm_module/execution_graph.py:355-374` | `save`：原子替换（tmp + replace） |
| `llmfetcher/swarm_module/execution_graph.py:233-266` | `_default_agent_serializer`：库默认编码含 `context_path`（每 subagent 独立上下文引用） |
| `llmfetcher/swarm_module/task_bus.py:410-429` | `TaskBus.to_snapshot`：assignments/task_states/reports/inboxes（"不携带 condition/回调"） |
| `tests/test_swarm_restart_recovery.py:61` | `assertNotIn("ephemeral-key", snapshot)`：无密钥断言的权威位置（outline §3.3 锚点） |
| `angelus/runtime.py:879` | `_restore_swarm` docstring："No secret is read from the snapshot" |
| `angelus/runtime.py:890` + `angelus/runtime.py:266` | `resolve_agent`→`_build_agent` 用 agent_name 确定性重绑 `context_path`（恢复单元含私有上下文） |
| `docs/research_innovation/angelus_capability_map.md:15-16` | d) 快照持久化 IMPLEMENTED 审计条目（含行号漂移注记：审计写 `:763`，当前工作树 `:824`） |

---

## §3.3 恢复语义（Recovery Semantics）

### 英文草稿（Draft）

Restoring an organization is a *rebuild*, not a replay. `_restore_swarm` (`runtime.py:856`) is invoked by `start_run` whenever a backend restarts and no in-memory swarm exists (`api/runs.py:158`). If no `swarm-runtime.json` exists it returns `None` and a fresh graph is built (`runtime.py:882-883`); an unreadable or schema-incompatible snapshot is deliberately ignored so the session remains usable (`runtime.py:903-904`). For a valid *quiescent* snapshot, the current browser config (connector, ephemeral keys) is reapplied: every node is rebuilt through `_build_agent` (`runtime.py:890`), the coordinator receives runtime tools (`runtime.py:908`), dispatched workers have `report_task` re-attached (`runtime.py:909-914`), and the observer re-attaches so lifecycle persistence continues (`runtime.py:915`).

Today the semantics are **completion-only**: `TaskBus.from_snapshot` rejects any snapshot containing a `running` task with `ValueError` (`task_bus.py:490`), so only terminal-ready organizations are restored; a mid-run crash leaves the browser with an `interrupted` diagnosis (`api/runs.py:380-393`). D2 adds three design decisions to extend recovery into mid-run state: **(T1) snapshot timing** — write the first snapshot immediately at run start and update it on `task:dispatched`/`task:redispatched`/`task:reported` with a debounce window, instead of only in the `finally` block (`api/runs.py:320`, `runtime.py:704-706`); **(T2) in-progress task semantics** — extend `from_snapshot` to persist running assignments (`id/recipient/objective/handoff/expected_artifacts/plan_task_id`) and restore them as `queued`/`interrupted` rather than rejecting them (`task_bus.py:433-491`); **(T3) restored-run marking** — a restore branch that flags the resumed run (`restored=True` in run metadata/events) so the UI and evaluation can distinguish a resumed turn from a fresh start (`api/runs.py:158`).

（词数 ≈ 270。T1-T3 为 D2 设计增量，尚未实现，写作中不作已完成 claim。）

### D2 新增设计要点（供 §3.3 正文与 §4 Evaluation 引用）

1. **快照时机（T1）**：现状仅在 `execute()` 的 `finally` 块写快照（`api/runs.py:320`），运行中崩溃会丢失全部活状态；设计为 `start_run` 成功后立即 `_persist_swarm_snapshot`（`runtime.py:824`），并在 `_synchronize_plan_with_swarm_event` 的 `task:dispatched/redispatched/reported` 分支（`runtime.py:704-706`）触发限流/节流（如 2s 合并）的增量重写。副作用：每轮至少一个快照 + 每任务状态迁移一个（合并后的）快照，恢复保真度与写放大之间取平衡。
2. **进行中任务语义（T2）**：`TaskBus.to_snapshot`（`task_bus.py:410-429`）需序列化 `running` 任务的 assignment 字段；`from_snapshot`（`task_bus.py:433-491`）去掉 :490 的 `running` 拒绝，改为恢复为 `queued`（可重新派发）或 `interrupted`（带结构化报告）。计划层 `update_execution_status` 的 stale 防护（`angelus_swarm_dynamics.md:9`）已能容忍复活后的事件重放。
3. **UI 恢复入口（T3/T4）**：见 §3.6 D2 增强点。

### 素材映射表

| 素材（file:line） | 作用 |
|---|---|
| `angelus/runtime.py:856` | `_restore_swarm` 主锚点（outline §3.3） |
| `angelus/api/runs.py:158` | `start_run` 内恢复调用点（`active.swarm = runtime._restore_swarm(...)`） |
| `angelus/runtime.py:882-883` | 无快照文件 → `None`（回退新图） |
| `angelus/runtime.py:903-904` | `AgentSwarm.load` 异常（`GraphPersistenceError/OSError/ValueError`）→ 忽略并 `None` |
| `angelus/runtime.py:906-907` | coordinator 缺失 → `None` |
| `angelus/runtime.py:890` | `resolve_agent` 用当前 config 重建 agent（恢复=rebuild） |
| `angelus/runtime.py:908` | `_attach_swarm_runtime_tools`（重挂运行时工具） |
| `angelus/runtime.py:909-914` | 对 dispatched worker 重挂 `create_task_report_tool` |
| `angelus/runtime.py:915` | `_attach_swarm_observer`（恢复观察者、续写事件/图视图） |
| `llmfetcher/swarm_module/task_bus.py:490` | `ValueError("Cannot restore a TaskBus snapshot with running tasks")`（完成态✓/运行中✗ 的现状） |
| `llmfetcher/swarm_module/task_bus.py:433-491` | `from_snapshot` 全貌：状态一致性校验、`running` 拒绝、legacy `reported` 归一化 |
| `angelus/api/runs.py:380-393` | `get_run_status`：无活线程的 `running/force_stopping` → `interrupted` 持久化诊断 |
| `angelus/api/runs.py:320` | `finally` 中 `_persist_swarm_snapshot`（D2 T1 的现状锚点） |
| `angelus/runtime.py:704-706` | observer 分支 `task:dispatched/redispatched/reported`（D2 T1 增量触发点） |
| `docs/paper/outline.md:162-174` | D2 任务分解 T1-T6（本文 D2 设计输入的来源） |

### Fig.2 恢复时序图（图注 + 结构描述）

> **Caption（英文）**：*Fig. 2. Organization recovery sequence. (a) Current completion-only path: crash → backend restart → `start_run` → `_restore_swarm` rebuilds a quiescent graph from `swarm-runtime.json` → report tools re-attached → run continues. (b) D2 mid-run path (dashed): the first snapshot is written at run start and refreshed on task lifecycle events; after a mid-run crash the same restore path reconstructs topology plus in-progress tasks (restored as `queued`/`interrupted`) and the UI offers a recovery button.*

**结构描述**（供 Phase 3 绘图）：
- **泳道**：Browser Console → API (`start_run`) → Runtime (`_restore_swarm`) → Storage (`swarm-runtime.json`) → Model provider。
- **主路径（实线，现状）**：
  1. 用户发消息 → `start_run`（`api/runs.py:85`）；
  2. 进程重启后无内存 swarm → `runtime._restore_swarm`（`api/runs.py:158`）；
  3. 读 `swarm-runtime.json`（`runtime.py:881`）；无文件/坏快照 → 分支 A：返回 `None`、建新图；
  4. 重建 nodes（`_build_agent`，`runtime.py:890`）→ 重挂 report tool（`runtime.py:909-914`）→ 重挂 observer（`runtime.py:915`）；
  5. `swarm.run(...)` 继续执行（`api/runs.py:203`）；
  6. 结束 → `finally` 写快照（`api/runs.py:320`）→ 写 run_state。
- **D2 路径（虚线，新增）**：
  - 路径 0a：`start_run` 成功后立即写首个快照；
  - 路径 0b：`task:dispatched/redispatched/reported` 事件 → 限流后增量重写快照（`runtime.py:704-706`）；
  - 路径 4'：恢复分支检测到进行中任务 → `from_snapshot` 以 `queued/interrupted` 恢复（替代 `task_bus.py:490` 的拒绝）；
  - 路径 1'：`start_run` 对 restored run 打 `restored=True` 标记；
  - 路径 3'：前端 `restoreRunState`（`app.js:730`）在 `interrupted` + 可恢复快照时显示"恢复"按钮。
- **时间标注**：Phase 3 定稿时在 0b 事件处标 `t₀..tₙ` 快照时间戳；Evaluation §4.3 指标（恢复耗时/保真度/继续回合数）落在此图上。

---

## §3.4 运行中干预 API（Runtime Intervention API）

### 英文草稿（Draft）

Three HTTP endpoints expose mid-flight control, all validated against the live graph. `POST /runs/{session}/stop` requests a *cooperative* stop at the next safe boundary; `POST .../force-stop` additionally closes the current model/tool I/O and persists a `force_stopping` run state; `POST .../steer` queues a steering message applied between steps (`api/runs.py:491-546`). Each accepts an optional `agent` field resolved by `_control_target`, which reads the live `view_snapshot`, rejects unknown agents with 404 and already-terminal targets with 409 (`api/runs.py:459-487`).

Intervention is Agent-scoped by construction. The run owns a `BrowserRunControl` registry with one stable stop event per agent (`browser_run_control.py:64-99`); `for_agent(name)` returns an `AgentScopedRunControl` view that combines run-level and agent-level force-stop events without copying them (`browser_run_control.py:11,34-61,101-111`). The graph scheduler resolves one view per worker through `control.for_agent(name)` (`execution_graph.py:1534-1538`) and checks `should_stop(agent)` before submission (`execution_graph.py:1539-1547`), so stopping one worker leaves sibling branches untouched — the zero-perturbation claim of RQ3. Steers are drained only by the coordinator (`browser_run_control.py:54-56`) and applied at the next safe model boundary; `test_session_steers.py` verifies that the applied steering history survives browser refresh, and `test_swarm_failure_isolation.py` verifies that a failed worker's siblings and downstream dependents proceed unperturbed.

（词数 ≈ 180。）

### 素材映射表

| 素材（file:line） | 作用 |
|---|---|
| `angelus/api/runs.py:491-511` | `stop_run`：cooperative stop，`control.stop(target)` + `swarm.request_shutdown()` |
| `angelus/api/runs.py:513-538` | `force_stop_run`：`active.force_stop(target)` + 持久化 `force_stopping` run_state |
| `angelus/api/runs.py:540-546` | `steer_run`：`control.steer(request.message)` |
| `angelus/api/runs.py:459-487` | `_control_target`：agent 目标校验 + `view_snapshot` 状态快照（404/409） |
| `angelus/classes/browser_run_control.py:11,34-61` | `AgentScopedRunControl`：`_CombinedEvent` 合并全局+agent 级 force-stop 事件 |
| `angelus/classes/browser_run_control.py:64-99` | `BrowserRunControl`：注册表（`_agent_stopped`/`_agent_force_stopped` 每 agent 事件） |
| `angelus/classes/browser_run_control.py:101-111` | `for_agent` → `AgentScopedRunControl`（不复制事件，仅视图） |
| `angelus/classes/browser_run_control.py:54-56` | `drain_steers`：仅 coordinator 接收 steer |
| `angelus/classes/browser_run_control.py:129-153` | `stop`/`force_stop`：`all` 或单 agent 事件设置 |
| `angelus/classes/browser_run_control.py:183-189` | `steer`：入队 session 级消息 |
| `llmfetcher/swarm_module/execution_graph.py:1534-1538` | `control_for`：`getattr(control,"for_agent")` 解析每 agent 视图 |
| `llmfetcher/swarm_module/execution_graph.py:1539-1547` | `target_stopped`：提交前按 agent 检查停止标志 |
| `tests/test_session_steers.py:16-38` | 应用后的 steer 历史可从 durable 事件日志重建（刷新不丢） |
| `tests/test_swarm_failure_isolation.py:40-62` | 失败 worker 隔离、兄弟/下游不受扰（RQ3 佐证测试） |
| `angelus/api/runs.py:355-402` | `get_run_status`：干预后的状态查询（active/status/error） |

---

## §3.5 上下文修订审计（Context Revision Audit）

### 英文草稿（Draft）

Each Agent owns an append-only, immutable revision history for its active context, managed by `ContextEditStore` (`context_editing.py:111`). Edits are optimistic: the caller must supply `expected_revision_id`; any mismatch with the current revision raises `ContextEditError` and the browser API maps it to HTTP 409 (`context_editing.py:248-249`, `api/sessions.py:457-459`). The first mutation of a legacy context automatically writes a `baseline-<uuid>` snapshot (`actor="system"`), so recovery never depends on an already-mutated file (`context_editing.py:197-224`). Every revision records `revision_id`, `parent_revision_id`, `agent_name`, `created_at`, `actor`, `reason`, the ordered operations, and a `snapshot_sha256` digest of the resulting message list; the revision snapshot is written atomically and the same record is appended to `context-edits.ndjson` with fsync, so the human-readable audit cannot lag the activated revision (`context_editing.py:58-74,181-196,226-289`).

Restore is forward-only: `restore(revision_id)` activates a saved snapshot as a *new* revision whose `restored_from` field points at the source, so no history is ever rewritten (`context_editing.py:291-323`). Browser editing is restricted to inactive agents — live agents edit through the same revision protocol via their context tools (`api/sessions.py:358,378-381`) — which together support the "改坏→回滚→恢复" closed loop of RQ4. `test_context_editing.py` verifies baseline creation, forward-only restore, stale/unknown-record rejection, entity-graph staleness marking, and that the browser API and the live tool share one revision protocol.

（词数 ≈ 195。）

### 素材映射表

| 素材（file:line） | 作用 |
|---|---|
| `angelus/context_editing.py:111-118` | `ContextEditStore` 类：绑定 path + agent_name，revision/audit 目录 |
| `angelus/context_editing.py:58-74` | `ContextRevision` dataclass：revision_id/parent/agent/created_at/actor/reason/operations/snapshot_sha256/restored_from |
| `angelus/context_editing.py:197-224` | `_write_baseline`：首次编辑前自动 `baseline-<uuid>`（`actor="system"`） |
| `angelus/context_editing.py:226-289` | `apply`：`expected_revision_id` 乐观并发（:248-249 stale 拒绝）、ops 校验、`snapshot_sha256`（:278）、原子写 + 审计 |
| `angelus/context_editing.py:291-323` | `restore`：forward-only、`restored_from=revision_id`（:313）、stale 防护（:300-301） |
| `angelus/context_editing.py:181-196` | `_append_audit`：`context-edits.ndjson` append + fsync |
| `angelus/context_editing.py:100` | `_atomic_json`：tmp+fsync+replace 原子写（revision/active 双写一致） |
| `angelus/api/sessions.py:358,378-381` | `_editable_context_store`：浏览器编辑拒绝运行中 agent（409）；live 走 agent 工具 |
| `angelus/api/sessions.py:388-401` | `inspect_editable_agent_context`（GET editable：records+revisions） |
| `angelus/api/sessions.py:430-456` | `edit_agent_context`（POST edit：`expected_revision_id` + operations + reason） |
| `angelus/api/sessions.py:463-481` | `restore_agent_context`（POST restore：revision_id 回滚） |
| `tests/test_context_editing.py:42-73` | baseline 创建 + restore forward-only（`restored_from` 断言 :70） |
| `tests/test_context_editing.py:74-98` | stale revision / unknown record 拒绝 |
| `tests/test_context_editing.py:100-128` | 编辑标记实体图 stale（`graph_stale=True`） |
| `tests/test_context_editing.py:129-180` | 浏览器 API 与 live 工具共享同一修订协议 |
| `docs/research_innovation/angelus_capability_map.md:21-22` | f) 版本化编辑/回滚 IMPLEMENTED 审计条目 |

### Fig.3 上下文修订历史（图注 + 结构描述）

> **Caption（英文）**：*Fig. 3. Per-agent context revision history. The active context is a linear checkpoint; edits create immutable revision snapshots (SHA-256 of the resulting messages) linked by `parent_revision_id`. The first edit snapshots a `baseline`; a restore reactivates any saved revision as a new forward revision whose `restored_from` records the source, preserving full history. `context-edits.ndjson` appends every revision for audit.*

**结构描述**（供 Phase 3 绘图）：
- **节点链**（横排，时间从左到右）：
  1. `contexts/<agent>.json`（active checkpoint，当前激活状态）——图中为最右高亮节点；
  2. 快照节点：`baseline-<uuid>`（`context_editing.py:197-224`，`actor=system`）→ `rev₁`（`apply`，`actor=tool/api`，`reason="..."`）→ `rev₂` → ... → `revₙ`（当前）；
  3. 每条快照标注字段：`revision_id` / `parent_revision_id`（箭头）/ `snapshot_sha256`（内容指纹）/ `actor` / `reason`（`context_editing.py:58-74`）。
- **回滚分支**：从 `revₙ` 指向 `rev₁` 的虚线箭头标 `restore(revision_id=rev₁)`，落点为新节点 `rev₃'`（`restored_from=rev₁`，`context_editing.py:291-323`）——不修改 rev₁。
- **审计侧栏**：`context-edits.ndjson` 追加行与快照一一对应（`context_editing.py:181-196`）。
- **图例**：实线=parent 链；虚线=restore 引用；节点右下角六角形=SHA-256 校验标记。API 端点标注在对应交互上：GET `.../context/editable`、POST `.../context/edit`、POST `.../context/restore`（`sessions.py:388/430/463`）。

---

## §3.6 前端控制台（Frontend Console）

### 英文草稿（Draft）

The console is a single-page control plane (`frontend/static/app.js`). It maintains `currentGraph` (`app.js:56`) — nodes, edges, assignments, task/node states — and renders one agent-card per vertex with a state light (`app.js:238-287`), plus a context-graph dialog and revision picker (`app.js:359`, `api/sessions.py:281,388`). A reconciliation endpoint merges the persisted view with durable terminals, so a refresh never shows stale topology (`api/sessions.py:491-699`).

On rehydration it calls `restoreRunState` (`app.js:730`): a live run reattaches to the SSE stream, `error`/`interrupted` renders an error block, `completed`/`stopped` a label. Today there is **no recovery affordance**: an interrupted run is terminal in the UI, matching §3.3's completion-only semantics.

**D2 UI enhancement points** (four): (1) *recovery entry* — detect "unfinished last run + `swarm-runtime.json` exists" and surface a "恢复" button; (2) *resume action* — issue a normal run start with `restored=True` (outline T4), reusing `start(message)`; (3) *state flow* — add an `interrupted → restoring → running` transition so stop controls (`app.js:280`) enable correctly; (4) *snapshot affordance* — show snapshot timestamp/coverage (quiescent vs mid-run, D2 T1/T2) to judge recoverable work. Live controls (`app.js:679-680`) and the steer-on-enter composer (`app.js:731`) are unchanged.

（词数 ≈ 250。D2 增强点为设计建议，未实现。）

### D2 UI 增强点（供实现 PR / Evaluation 引用）

| # | 增强点 | 现状锚点 | 目标 |
|---|---|---|---|
| U1 | 恢复入口按钮 | `app.js:730`（现状无恢复按钮） | `interrupted` + 有快照 → 横幅"恢复"按钮 |
| U2 | 恢复动作复用启动路径 | `app.js:577` `start(message)`；`runs.py:85` | 复用 `start` + `restored=True`（outline T4） |
| U3 | 状态流转 `interrupted→restoring→running` | `app.js:280` `updateStopAvailability` | 恢复期正确启停 stop/force-stop |
| U4 | 快照信息展示 | `runtime.py:511` `_swarm_snapshot_path` | 显示快照时间戳/覆盖（quiescent vs mid-run） |

### 素材映射表

| 素材（file:line） | 作用 |
|---|---|
| `frontend/static/app.js:56` | `currentGraph`（节点/边/assignments/task_states/node_states 的 UI 状态） |
| `frontend/static/app.js:233` | `graphUrl()` → `/api/sessions/{sessionId}/graph` |
| `frontend/static/app.js:238-287` | `agentStateView`/`agentCard`/`renderAgentSelector`：状态灯、agent-card、ack |
| `frontend/static/app.js:280` | `updateStopAvailability`：按 canonical state 启停 stop/force-stop（U3 依赖） |
| `frontend/static/app.js:359` | `openContextGraph`：上下文图对话框（Fig.3 的前端载体） |
| `frontend/static/app.js:679-680` | `runStop`/`runForceStop`：调 `stop`/`force-stop` 端点（§3.4 前端对端） |
| `frontend/static/app.js:730` | `restoreRunState`：现状——live 重连 SSE / error-interrupted 只展示 / completed-stopped 只显示状态（无恢复按钮，D2 U1/U2 锚点） |
| `frontend/static/app.js:731` | composer 提交：`runActive` 时 `sendSteer`，否则 `start`（恢复动作可复用） |
| `frontend/static/app.js:729` | `connectRunEvents`：SSE 重连（restoreRunState 内 live 分支） |
| `angelus/api/sessions.py:491-699` | `get_session_graph`（:491）+ `_reconcile_graph_view`（:512-699）：持久图与 durable 终态合并（刷新不陈旧） |
| `angelus/api/sessions.py:700-701` | 会话级图端点（legacy 兼容） |
| `angelus/runtime.py:511-522` | `_swarm_snapshot_path`（U1 判定"可恢复快照存在"的服务端依据） |
| `docs/research_innovation/angelus_capability_map.md:37-38` | 前端运行图注：live 图渲染在 `app.js`，`inspector/*` 为 legacy（`angelus_swarm_dynamics.md:38`） |
| `docs/paper/outline.md:171` | D2 UI 恢复入口任务分解（U1-U4 的来源） |

---

## 附录 A：行号核对记录（工作树 2026-08-25）

| 锚点 | 核对结果 | 与 outline/审计文档的漂移 |
|---|---|---|
| `api/runs.py:85` `start_run` | ✅ `@router.post("/api/runs")` + `def start_run` | 无漂移 |
| `api/runs.py:158` 恢复点 | ✅ `active.swarm = runtime._restore_swarm(...)` | outline 标 `:158`，一致 |
| `api/runs.py:320` finally 快照 | ✅ `runtime._persist_swarm_snapshot(...)` | outline 标 `:320`，一致 |
| `runtime.py:704-706` observer 分支 | ✅ `task:dispatched/redispatched`（:704）、`task:reported`（:706） | outline 标 `704-706`，一致 |
| `runtime.py:824` `_persist_swarm_snapshot` | ✅ | capability map 写 `:763`，漂移 +61 |
| `runtime.py:856` `_restore_swarm` | ✅ | capability map 写 `:795`，漂移 +61 |
| `task_bus.py:433` `from_snapshot` | ✅ | capability map 写 `:520`，漂移（审计文档行号过期） |
| `task_bus.py:490` 拒 running | ✅ `ValueError("Cannot restore a TaskBus snapshot with running tasks")` | capability map 未标此行 |
| `app.js:730` `restoreRunState` | ✅ | 一致 |
| `tests/test_swarm_restart_recovery.py:61` 无密钥断言 | ✅ `assertNotIn("ephemeral-key", snapshot)` | capability map 写 `:60`，实际 `:61` |
| `runtime.py:890` `_build_agent`（restore 内） | ✅ | — |
| `app.js:729` `connectRunEvents` | ✅ | outline 引 `:724`，实际 `:729`，漂移 +5（本稿已更正） |
| `runs.py:491/513/540`（stop/force-stop/steer def） | ✅ | outline 引 `490/512/539`，实际 `491/513/540`，漂移 +1（本稿已更正） |
| `sessions.py:358/388/430/463`（编辑/检查/恢复 def） | ✅ | 草稿曾引 `373-386/387/429/462`，为 def 行差异（本稿已更正） |
| `context_editing.py:100` `_atomic_json` / `:181-196` audit / `:197-224` baseline | ✅ | 草稿曾引 `:113-118`/`:191-203`/`:196-216`（本稿已更正） |
| `context_editing.py:58-74` `ContextRevision` / `:226-289` apply / `:291-323` restore | ✅ | 草稿曾引 `:69-87`/`:226-286`/`:291-318`（本稿已更正） |
| `runtime.py:843-851` `serialize_agent` | ✅ | 草稿曾引 `:837-849`（本稿已更正） |
| `runtime.py:879` "No secret is read" docstring | ✅ | 草稿曾引 `:874-876`（本稿已更正） |
| `runtime.py:677` graph-view.json 持久化 | ✅ | 草稿曾引 `:675`（本稿已更正） |
| `browser_run_control.py:54-56` drain_steers（coordinator-only） | ✅ | 草稿曾引 `:112-114`（本稿已更正） |
| `runtime.py:595` `_attach_swarm_runtime_tools` def | ✅ | 草稿曾引 `:581-652`（本稿已更正为 `:595-652`；capability_map 亦引 `:581`，漂移 +14） |
| `sessions.py:491-699` `get_session_graph` + `_reconcile_graph_view` | ✅ | 草稿曾引 `:491-560`（本稿已更正；`_reconcile_graph_view` 实际 512-699） |
| `execution_graph.py` finalize 归属 | ✅ | 草稿曾引 `:1453`（run() 内 finalize），实际 `finalize_tasks` 定义于 `:508`、调用于 `api/runs.py:315`（finally 块，runs.py:313-322），本稿已更正 |

## 附录 B：[VERIFY] 待复核项

1. `llmfetcher/swarm_module/execution_graph.py:1265` `dynamic_add_connection` 的"仅源未完成前生效"语义——docstring 已述（`execution_graph.py:1268-1271`），但 `tests/` 无直接行为级测试（静态 `add_connection` 覆盖于 `test_execution_graph_persistence.py:37`、`test_swarm_failure_isolation.py:47-50`；API 能力清单见 `test_graph_edit_api.py:123`）[VERIFY: 行为级测试文件定位]。
2. §3.4 中 `execution_graph.py:1539-1547` `target_stopped` 的"提交前检查"——已按工作树核对，但 `control.should_stop` 的异常兜底分支（:1541-1545）在写论文时应避免展开。
3. Fig.1 中 `connectRunEvents` 行号 `app.js:729`——与 `restoreRunState`（`app.js:730`）相邻，已核对，不再待复核。
4. §3.3 T2 的 `plan_task_id` 持久化字段——`TaskAssignment` 已有该字段（`task_bus.py` 构建处），`to_snapshot` 已序列化（`task_bus.py:410-429`），故 D2 只缺 `from_snapshot` 的 running 分支，无需改 schema [VERIFY: 以 T5 集成测试最终确认]。
