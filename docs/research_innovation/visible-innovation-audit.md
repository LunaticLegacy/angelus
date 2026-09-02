# Angelus Visible Innovation Audit（可见创新点审计）

> 日期：2026-08-25 ｜ 依据：8 个并行 swarm worker（Angelus 代码审计 ×1、赛道研究 ×4、对抗审查 ×1、本地复核）＋ 本人对源码/前端/测试的二次验证。
> **证据纪律：只使用源码、API 实现、测试、前端代码；未使用 README 作为能力证据。**

---

## 1. Executive Conclusion

**Angelus 有真正值得宣传的创新，但创新不在"多 Agent 框架"本身，而在于它是一个把"动态 Agent 组织"当作一等运行时状态——可持久化、可查看、可干预、可恢复——的本地控制台。**

最强 3 个创新点（全部通过对抗审查）：

1. **组织级持久化与恢复（Organizational Persistence & Recovery）**：把 Agent 拓扑、worker、任务分配、TaskBus 状态整体序列化并在进程重启后还原，且还原后可以继续工作。竞品全部是 workflow/step 级恢复（LangGraph checkpoint、Temporal、DBOS、Julep），**没有把"动态 Agent 名单 + 拓扑 + 分配 + 任务总线"作为一个可恢复单元的产品**。
2. **对运行中 Agent 系统的可干预调试（Debugger for Running Agents）**：唯一把"可观测"升级为"可干预"（pause / steer / edit-context / recover / continue）的**独立本地工具**。LangSmith/Langfuse/AgentOps 全部 observe-only；LangGraph/LangSmith Agent Server 能 mutate 但必须用自家引擎运行。
3. **可审计的每 Agent 上下文修订历史**：不可变修订 + SHA-256 基线 + actor/reason 审计 + 回滚，粒度到每个 worker 的私有上下文。

诚实声明：`MCP`、`多 Agent`、`swarm`、`steering`、`stop/resume`、`持久化`等单项都是 commodity；差异在**组合 + 组织粒度 + 本地可干预**，不在任何单项。

---
## 2. Angelus Actual Capability Map（基于代码）

| 能力 | 状态 | 证据（文件:行） |
|---|---|---|
| 运行期创建 Agent（coordinator 工具 spawn worker） | IMPLEMENTED | `execution_graph.py:1213` dynamic_add_agent；`runtime.py:581` 装配 dispatch_subagent(s) |
| 运行期拓扑变更（增删节点/边/mapper/router） | IMPLEMENTED（环检测推迟到 run 时报错） | `execution_graph.py:1241,1265,1295,1315,1334` |
| Agent 复活（terminal worker 复用 + 保留上下文 + 新任务） | IMPLEMENTED | `execution_graph.py:1063` redispatch_task；`spawn_tools.py:356` _revive_agent；UI `app.js` 有"重新启用 Agent"工具 |
| 组织快照持久化（拓扑+workers+TaskBus+分配） | IMPLEMENTED（完成态） | `execution_graph.py:295/355/376`；`task_bus.py:485/520`；`runtime.py:763` _persist_swarm_snapshot（credential-free）；`api/runs.py:319`（run finally 块） |
| 进程重启后恢复已完成 swarm | IMPLEMENTED | `runtime.py:795` _restore_swarm；`api/runs.py:158`；`tests/test_swarm_restart_recovery.py` |
| 失败隔离（单 worker 崩溃不影响兄弟，结构化 failed 报告） | IMPLEMENTED | `execution_graph.py` run 循环；`tests/test_swarm_failure_isolation.py` |
| 结构化报告边界（TaskReport 排除 raw transcript） | IMPLEMENTED | `task_bus.py:55` TaskReport 字段；`execution_graph.py:1895` _render_assignment |
| 每 Agent 隔离 context/计划/transcript/权限 | IMPLEMENTED | `execution_graph.py:233` serializer 带 context_path；`runtime.py:557` _bind_worker_context_tools；`runtime.py` _tool_permitted 两级权限 |
| 版本化上下文编辑+恢复（audit、SHA 基线、actor/reason、restore） | IMPLEMENTED | `context_editing.py` ContextEditStore.apply/restore；`tests/test_context_editing.py` |
| 中途 steering（安全边界注入） | IMPLEMENTED | `api/runs.py:539` /steer；`browser_run_control.py` drain_steers；`tests/test_session_steers.py` |
| 单 Agent/整 swarm 协作停止、force-stop、MCP 审批 | IMPLEMENTED | `api/runs.py:490/512/549` |
| 计划绑定（plan_task_id ↔ assignment 投影到共享计划） | IMPLEMENTED | `runtime.py:669` _synchronize_plan_with_swarm_event；`task_planning.py:116` |
| 会话记忆/交接（handoff、artifact、跨会话授权记忆） | IMPLEMENTED | `session_memory.py:212` create_handoff、create_session_memory_tools |
| 外部 Coding Agent 统一控制 | PARTIAL | `external_providers/codex.py:668` 完整（start/resume/fork/steer/interrupt/diff/usage/approval）；`claude_code.py:88` 缺 steer/diff/usage |
| 跨 Coding Agent 会话导入/导出（归档） | IMPLEMENTED | `api/external_agents.py:163/193` export/import archive、parse_archive |
| 中途崩溃恢复"进行中"的 run | NOT IMPLEMENTED（仅完成态） | _restore_swarm 忽略无效快照；运行中不写 snapshot |
| 跨进程锁（TaskBus 单进程假设） | NOT IMPLEMENTED | auditor open question |
| 前端 inspector 旧目录 | PARTIAL（legacy 残留） | `inspector/INDEX.md` 自述；活跃 UI 是 `app.js` |

---

## 3. Competitive Landscape

| 赛道 | 代表 | 与 Angelus 重叠 | Angelus 差异 |
|---|---|---|---|
| Agent Framework | LangGraph、AutoGen、CrewAI、OpenAI Agents SDK、ADK | 多 Agent、HITL、checkpoint | 代码即拓扑 + step 级恢复；无组织级恢复；运行期 spawn 仅 dagent（小众）接近 |
| Coding Agent | Codex、Claude Code、OpenCode | 各自会话控制协议（Codex 最完整） | 无统一生命周期/权限/跨 agent 观察层；ACP 只是协议标准 |
| Multi-Agent/Swarm | OpenAI Swarm、CrewAI、AutoGen、Letta、Mastra | 动态 handoff、结构化输出 | 无"组织快照+拓扑变更+revival"组合；TaskBus 结构化报告 + task_id 关联共享计划是独有组合 |
| Observability | LangSmith、Langfuse、AgentOps、Braintrust、Phoenix | trace、session 回放 | 全部 observe-only；不能改运行中 context、不能恢复组织 |
| Agent Runtime/Durable | Temporal、Restate、DBOS、LangGraph Agent Server | durable resume、pause/resume、workflow fork | 恢复的是 workflow/step 状态；组织需由历史近似重建 |
| Control Plane | HumanLayer（已转型 AI IDE）、claude-code-router、NexusOps | 多 coding agent 路由/观察 | 无组织级恢复、无运行中 context 手术、无跨 agent 会话归档 |
| Governance | AutoGen v0.4 安全边界、Claude 子代理权限 | 每 agent 权限 | 无本地可查看/可干预的组织 UI |

---
## 4. Innovation Elimination Table

| 候选 | 相似项目 | 差异 | 结论 |
|---|---|---|---|
| 支持 MCP / 插件 / 多 Agent / swarm / RAG / token stats / 多模型 | 几乎所有人 | 无 | 淘汰（commodity） |
| steering / stop / resume | Codex steer、Claude remote-control、OpenAI HITL | 较弱 | 淘汰为独立卖点；仅作为"组织恢复"链条一环 |
| 动态组织（runtime spawn + 拓扑变更） | dagent（部分）、AutoGen v0.4 runtime（部分） | 完整工具链 + 持久化 + UI | 保留（组合差异） |
| 组织级恢复（org 快照还原） | LangGraph checkpoint（step）、Temporal（workflow）、Julep | 无人以"动态组织"为单位恢复 | 保留 |
| 运行中可干预调试（mutate+continue） | LangSmith Agent Server（需自家引擎）、LangGraph update_state | 独立本地工具、对任意 agent | 保留（范围限定） |
| 结构化报告边界 | OpenAI input_filter、CrewAI pydantic 输出、Claude 子代理摘要 | 报告 schema + TaskBus 排除 transcript + task_id 关联 | 弱化保留（组合细节） |
| 复活 worker | LangGraph 重新 invoke、Temporal worker pool | 生命周期审计 + 保留上下文 + plan 绑定 | 弱化保留（组织管理的子能力） |
| 异构 Coding Agent 统一控制 | claude-code-router、NexusOps、ACP | 本地 + 会话归档 + 观察 | 弱化保留（工程差异化，非独立创新） |
| 版本化上下文编辑/恢复 | LangGraph time-travel、Letta rollback/fork | 不可变 audit log（SHA 基线/actor/reason/restore） | 保留（窄化） |

---

## 5. Surviving Innovations

### 5.1 组织级运行时持久化与恢复（Organizational Persistence & Recovery）
- **实际做了什么**：swarm 拓扑、worker 身份与 system_prompt、TaskBus 分配/报告历史序列化为 `swarm-runtime.json`（无密钥）；进程重启后 `_restore_swarm` 用当前配置重建所有 agent、重挂 report 工具、恢复 graph view，后续回合直接继续使用同一组织。
- **代码证据**：`execution_graph.py:295/355/376`、`task_bus.py:485/520`、`runtime.py:763/795`、`api/runs.py:158/319`、`tests/test_swarm_restart_recovery.py`。
- **最近竞品**：LangGraph（checkpoint 状态通道）、Temporal/Restate/DBOS（workflow 级）、Julep（Temporal 上的 durable agents）。
- **为什么不同**：竞品恢复"工作流第 N 步"；Angelus 恢复"有哪些 agent、谁是谁的下属、谁在做什么、任务总线里有什么"。
- **用户问题**：跑 40 分钟的 swarm 因崩溃/关机/网络中断全部白做；只能重新提示词、重新造 worker。
- **用户可见效果**：崩溃后打开同一会话 → 拓扑还在 → 直接继续。
- **Demo 场景**：见 §6 Demo #1。
- **Visible Innovation Score**：Novelty 8 / User Pain 8 / Visibility 8 / Demoability 9 / Defensibility 5 / Completeness 7 / Market 8 → **53/70**
- **Current maturity**：完成态恢复 ✓；运行中恢复 ✗（见 §10）。

### 5.2 对运行中 Agent 系统的可干预调试（Debugger for Running Agents）
- **实际做了什么**：observe（SSE 生命周期流 + 持久 NDJSON 事件日志）→ inspect（每 agent 上下文对话框 + 上下文实体图 + plan + trace）→ pause/steer（`/steer` 在安全边界注入）→ stop/force-stop（单 agent 或全组织）→ edit/restore context（版本化可回滚）→ 下回合继续。作用于**本地、多提供方**的 agent。
- **代码证据**：`api/runs.py:490/512/539`、`browser_run_control.py` AgentScopedRunControl、`context_editing.py`、`frontend/static/app.js`（agent-card、context 对话框、graph、steer UI）、`event_stream/*`。
- **最近竞品**：LangSmith（observe-only）、Langfuse/AgentOps（observe-only）、LangGraph Agent Server（mutate 但绑定自家引擎）、Codex app-server（单 agent 协议，无 UI 手术刀）。
- **为什么不同**：独立本地控制台 + 对任意 agent 生效 + 上下文手术与恢复进 UI。
- **用户问题**：agent 跑偏只能整体停掉重来；trace 只能看不能改。
- **用户可见效果**：点一个 worker → 看它的私有上下文 → 注入一句修正 → 继续跑，其余 worker 不受影响。
- **Demo 场景**：见 §6 Demo #2。
- **Visible Innovation Score**：Novelty 6 / User Pain 7 / Visibility 9 / Demoability 9 / Defensibility 5 / Completeness 8 / Market 8 → **52/70**
- **Current maturity**：IMPLEMENTED，可即用。

### 5.3 可审计的每 Agent 上下文修订历史（Audited Per-Agent Context Revision History）
- **实际做了什么**：每 agent 独立上下文文件；`edit_context` 带 expected_revision_id 防并发覆盖、不可变修订、SHA-256 基线、actor/reason 审计、`restore_context` 回滚任意修订，旧 evidence 保持不可变。
- **代码证据**：`context_editing.py`（ContextEditStore、apply/restore、audit ndjson）、`tests/test_context_editing.py`。
- **最近竞品**：LangGraph time-travel（整图粒度）、Letta（memory rollback/fork）、Claude Agent SDK。
- **为什么不同**：以"每 agent"为粒度 + 不可变审计 + UI 可视化（上下文图 `app.js:302`）。
- **用户问题**：改坏上下文只能重来；无法证明"这个上下文谁改过、为什么改"。
- **Demo 场景**：改坏 → 回滚 → 恢复。
- **Visible Innovation Score**：Novelty 5 / User Pain 5 / Visibility 7 / Demoability 8 / Defensibility 4 / Completeness 9 / Market 6 → **44/70**
- **Current maturity**：IMPLEMENTED。

---
## 6. Top 3 "Holy Shit" Demos

**Demo #1 — 杀掉组织，组织复活（10-30s）**
跑一个 3 worker 的 swarm → 中途展示左侧拓扑图（coordinator ♛ + 子 agent ↳ + 各自状态灯）→ 关闭后端进程 → 重启 Angelus → 打开同一会话 → 拓扑、worker、任务列表全部还在 → 发一句话，组织继续工作。
（当前实现：完成态 swarm 可直接演示；运行中恢复见 §10 补齐后更炸。）

**Demo #2 — 给跑偏的 worker 动手术（10-20s）**
swarm 运行中一个 worker 在重复犯错 → 点它的 agent-card → 打开它的私有上下文 → `edit_context` 注入一句修正 → 继续跑 → 兄弟 worker 全程无感。旁白："其他产品只能看，Angelus 能改。"

**Demo #3 — 上下文回滚（10s）**
Agent 在某轮被打入错误信息后开始胡说 → 展示版本化修订历史 → `restore_context` 回滚到健康版本 → 下回合恢复正常。

---

## 7. Product Positioning

**一句话定位**：
> Angelus 是**唯一一个把"Agent 组织"当作可保存、可查看、可手术、可复活的一等运行时状态**的本地控制台——它不是又一个 agent 框架，而是"你的 Agent 组织的工作区与急救台"。

---

## 8. Landing Page Hero

- **Headline**：Your agent org should survive crashes, not just your chat.
- **Subheadline**：Angelus 把整个多 Agent 组织（拓扑、worker、任务、上下文）持久化为运行时状态——观察它、干预它、杀掉进程，再把它复活，然后继续工作。
- **Bullet 1**：Observe — 每个 worker 的私有上下文、计划、状态灯、上下文实体图，实时可见。
- **Bullet 2**：Surgery — 运行中暂停、注入方向、版本化编辑并回滚任意 agent 的上下文。
- **Bullet 3**：Resurrect — 崩溃/关机后恢复整个 Agent 组织，而不是回到第 0 步。

---

## 9. What NOT to Market

以下功能虽然工程量巨大，但**绝对不要**作为"创新"宣传（会稀释可信度）：

- MCP / 插件 / 多模型 / token 统计 / 上下文压缩 / RAG —— 全是 commodity。
- "支持 Codex / Claude Code" —— 同质化连接能力。
- "支持任务计划" "支持持久化" "支持 stop/resume" —— commodity 单项。
- **"下一代 Agent 平台"** —— 空泛措辞，禁止。
- 外部 agent 统一控制 —— 仅作为工程差异化，不当核心卖点。

---

## 10. Next Engineering Priority（按 ROI 排序）

### #1 运行中组织恢复（Mid-Run Organizational Recovery）— ROI 最高
- **当前缺什么代码**：
  1. run 启动后即写入首个 swarm 快照（当前仅在 run 结束的 `finally` 块 `api/runs.py:319` 写入）；在每次 `task:dispatched` / `task:reported` / `dynamic_*` 拓扑变更事件后增量更新 `swarm-runtime.json`。
  2. 快照格式需要记录**进行中任务**（`task_bus.py:520` `from_snapshot` 目前拒绝 running tasks——需改为持久化进行中 assignment 的 `id/recipient/objective/handoff/expected_artifacts/plan_task_id` 并恢复为 queued/interrupted 语义）。
  3. `_restore_swarm`（`runtime.py:795`）目前只还原"完成态"；需增加对"进行中任务"的还原分支，并在 `start_run`（`api/runs.py:158`）时对 restored run 打标记。
  4. 前端 `app.js` 增加"检测到上次运行未完成 → 显示恢复选项"的 UI（现有 `restoreRunState` 只显示 error/interrupted 状态，无恢复按钮）。
- **为什么补完后用户价值突然变强**：这是 §6 Demo #1 从"完成态恢复"升级为"**运行中杀掉 → 点恢复 → 组织从断点继续**"，正是 §1 用户心智模型里最锋利的那一刀；直接把 5.1 的 Completeness 从 7 拉到 9-10。
- **工作量估计**：约 1-2 周。

### #2 恢复"不丢失已完成的 tool 副作用"的失败语义
- 当前 `Agent` 只在安全边界保存上下文；强制 kill 会丢失进行中的 tool 结果。补：模型/tool 边界处写入增量 checkpoint（事件日志已具备，NDJSON 每事件落盘），恢复时重放已完成副作用。与 #1 共用事件日志机制，ROI 次高。

### #3 Claude Code provider 补齐 steer/diff/usage
- `external_providers/claude_code.py:88` 缺三项，补齐后"异构 Coding Agent 统一控制"的 Demo 才完整。工作量小（协议已存在，抄 codex 模式）。

### #4 前端 legacy inspector 目录清理 / 迁移
- `frontend/static/inspector/*` 已过时（`inspector/INDEX.md` 自述），迁移到 `app.js` 后删除，避免维护分裂。

---
