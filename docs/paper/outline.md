# Angelus arXiv 论文大纲 v1（Phase 1 交付）

> **状态**：Phase 1 完成待批（outline v1 定稿 + 主源核实并入，`docs/paper/phase1-lit-verification.md`）。依据 `docs/paper/arxiv-workflow.md`（Phase 0 工作流）。
> **默认决策已采纳**：D1=匿名草稿；D2=先补实现（2 周硬截止，超时降级方案 B）；D3=用户备 arXiv 账号；D4=12 页 + cs.AI 主 + cs.MA 交叉；D5=附开源仓库；D6=仓库内真实任务案例。
> **证据纪律**：所有能力 claim 以 `文件:行` 回溯（行号以本大纲核对时的工作树为准，可能较审计有漂移，写作时须复核）；竞品判定引用 landscape + Phase 1 独立核实结果（`docs/paper/phase1-lit-verification.md`）。

---

## 1. 研究问题（冻结）

| # | 研究问题 | 对应 claim | 判定指标 | 判定地点 |
|---|---|---|---|---|
| RQ1 | 动态 Agent 组织能否作为一个**可恢复单元**整体序列化并还原？（拓扑+worker+分配+TaskBus） | P（主） | 快照/恢复往返保真度（逐字段比对）；恢复后继续完成回合 | §4.1 Tab.2 + 案例 1 |
| RQ2 | 组织级恢复与现有 workflow/step 级恢复（Temporal/Restate/DBOS/LangGraph checkpoint）在**恢复单元粒度**上的实质差异是什么？ | P | 对比矩阵 Q6 行 + 证据表 | §4.1 Tab.1 |
| RQ3 | 对**运行中** Agent 的 pause/steer/edit-context/recover 是否可做到"对单个 worker 生效、兄弟 worker 零扰动"？ | S（辅） | 干预前后目标 worker 错误率；兄弟 worker 输入扰动=0 | §4.2 案例 2 |
| RQ4 | 每 agent 上下文修订历史的**不可变审计**（SHA-256 基线/actor/reason/rollback）能否支撑"改坏→回滚→恢复"闭环？ | S（辅） | 审计日志完整性；回滚保真度 | §4.2 案例 2 + Tab.2 |
| RQ5 | （D2=是时新增）运行中恢复（mid-run crash→断点继续）相对"完成态恢复 + 重做"的成本/体验差异？ | P 增强 | 恢复耗时、恢复后从断点继续的回合数、vs 重做的 token/时间 | §4.2 案例 1（增强版） |

**失败判据（预注册，防事后 reinterpretation）**：
- F1：若恢复往返后拓扑/分配与快照不一致（≥1 处字段级差异）→ 主 claim P 不成立（案例 1）。
- F2：若干预某 worker 导致兄弟 worker 输入扰动 >0（或目标 worker 无改善）→ 辅 claim S 的"零扰动"表述不成立（案例 2）。
- F3：（D2=是时）若运行中恢复耗时 > 重做耗时的 1.5× 或恢复后无法继续完成原任务 → P 的"断点继续"表述不成立。

---

## 2. Claim → 章节映射

| Claim | 论证章节 | 支撑素材（file:line） | 反 claim 回应（见工作流 1.3） |
|---|---|---|---|
| P 组织级持久化与恢复（53/70） | §1, §3.2-3.3, §4.1-4.2 | `angelus_capability_map.md:15-16`；`angelus_swarm_dynamics.md:26-27`；`tests/test_swarm_restart_recovery.py` | Anti-P1（Julep/Temporal/LangGraph）：`adversarial_attack_report.md:7-17` + `multiswarm_dynamics_landscape.md:39-46,82-88` |
| S 运行中可干预调试（52/70） | §1, §3.4-3.6, §4.2 | `angelus_capability_map.md:21-25,37-38`；`tests/test_session_steers.py`；`tests/test_context_editing.py` | Anti-S1（LangSmith Studio/LangGraph update_state）：`adversarial_attack_report.md:21-31` + `observability_controlplane_landscape_detailed.md:58-60` |
| P 增强：运行中恢复（D2） | §3.3, §4.2, §5 | `visible-innovation-audit.md:155-162`（4 步实现路径）；Phase 2 实现 PR | 反 claim：LangGraph Agent Server 能 mutate——差异在独立本地 + 组织粒度（`adversarial_attack_report.md:88-99` 的 design-center 重述纪律） |

---

## 3. 章节骨架（含素材映射）

### 3.1 Introduction（~1.5 页）
- 开场问题：长周期 swarm 崩溃即全部白做；现有恢复是 workflow/step 级，不是"动态组织"级（`visible-innovation-audit.md:14`）。
- 三个 Demo 场景（杀组织→复活 / 跑偏 worker 动手术 / 上下文回滚，`visible-innovation-audit.md:110-120`）作为动机叙事。
- 贡献列表（4 条，与 §2 claim 对齐）：①组织级快照/恢复抽象；②运行中干预 API（steer/edit/restore/continue）；③每 agent 不可变审计修订历史；④参考实现 + 对比矩阵 + 案例研究。
- 诚实边界声明：单项均为 commodity，贡献在组合与组织粒度（`visible-innovation-audit.md:18,141-151`）。

### 3.2 Related Work（~2.5 页）
- **分层结构**：Agent Framework（LangGraph/AutoGen/CrewAI/OpenAI Agents SDK/Semantic Kernel/ADK/dagent）→ Durable Execution（Temporal/Restate/DBOS/Inngest/Conductor）→ Observability（LangSmith/Langfuse/AgentOps/Phoenix/Braintrust）→ Coding-Agent 控制（Codex/Claude Code/OpenCode/ACP/claude-code-router/NexusOps）→ 记忆/上下文（Letta/Graphiti/Microsoft GraphRAG/LightRAG/HippoRAG，若涉及）。
- 每条竞品定位 + 与 Angelus 的差异句（一律引用 Phase 1 核实表或 landscape）。
- 定位句（与审计 §7 一致，`visible-innovation-audit.md:124-129`）：不是又一个 agent 框架，而是"你的 Agent 组织的工作区与急救台"。

### 3.3 System Design（~4 页）
- **3.1 运行时模型**：ExecutionGraph 拓扑描述 + TaskBus 活任务状态（`angelus_swarm_dynamics.md:3-4`）；运行期 spawn/拓扑变更（`angelus_capability_map.md:5-10`）。
- **3.2 组织快照格式**：`swarm-runtime.json`（`runtime.py:824`）、`angelus.swarm-agent.v1` serializer、无密钥（`tests/test_swarm_restart_recovery.py:61` 断言无 `ephemeral-key`）；拓扑+workers+TaskBus+分配（`angelus_capability_map.md:15-16`）。
- **3.3 恢复语义**：`_restore_swarm`（`runtime.py:856`）重建 agent、重挂 report 工具、恢复 graph view；完成态 ✓；运行中 ✗ → 本节含 D2 新增设计（快照时机/进行中任务语义/UI 恢复入口）。
- **3.4 运行中干预 API**：stop/force-stop/steer（`api/runs.py` 相应行）+ AgentScopedRunControl（`angelus_capability_map.md:24-25`）。
- **3.5 上下文修订审计**：ContextEditStore、expected_revision_id 乐观并发、SHA-256 基线、actor/reason、restore（`angelus_capability_map.md:21-22`）。
- **3.6 前端控制台**：app.js 图视图/agent-card/上下文对话框（`angelus_capability_map.md:37-38`；`app.js:730` restoreRunState 现状 + D2 UI 增强点）。

### 3.4 Evaluation（~3 页）
- **4.1 功能对比矩阵**（Tab.1）：Q1-Q6 × 竞品行（冻结行列见 §5）。
- **4.2 正确性测试**（Tab.2）：4 套测试（restart_recovery / failure_isolation / context_editing / session_steers）+（D2=是时）新增 mid-run 恢复测试。
- **4.3 案例研究 1（崩溃恢复）**：仓库内真实多 worker 研究任务；kill → 重启 → 恢复 → 继续；指标：恢复耗时/保真度/继续回合数/vs 重做成本。
- **4.4 案例研究 2（运行中干预）**：跑偏 worker → edit_context 注入修正 → 继续；指标：错误率变化/兄弟扰动=0/审计完整性。
- **4.5 明确不做**：端到端公共 benchmark（理由：无标准任务集 + 选任务攻击风险）。

### 3.5 Discussion（~1 页）
- 局限：单进程 TaskBus（`threading.Condition` 线程内同步、ExecutionGraph 进程内驻留，无跨进程锁：`task_bus.py:95` + `api/runs.py:144`）；运行中恢复方案 B 兜底；无用户研究。
- 威胁有效性：恢复保真度测什么/不测什么；案例研究的外推边界。
- 失败判据复述（F1-F3）。

### 3.6 Conclusion（~0.5 页）
- 贡献回扣 + 未来工作：tool 副作用重放（`visible-innovation-audit.md:164-165`）、Claude Code provider 补齐 steer/diff/usage（`:167-169`）、异构 agent 统一控制。

---

## 4. 图表清单（定稿）

| 图/表 | 内容 | 素材 | 责任人 | 截止 |
|---|---|---|---|---|
| Fig.1 系统架构图 | 前端控制台 ↔ API ↔ 运行时（ExecutionGraph/TaskBus/ContextEditStore）↔ 模型提供方 | `angelus_swarm_dynamics.md:3-4` + `semantic-map.md` | architecture_writer | Phase 3 |
| Fig.2 恢复时序图 | crash → restart → `_restore_swarm`（`runtime.py:856`）→ 重建/重挂 → 继续 run；（D2）含 mid-run 快照时机标注 | `angelus_capability_map.md:18-19` | architecture_writer | Phase 3 |
| Fig.3 上下文修订历史 | baseline → rev1(actor/reason) → rev2 → restore 链 | `angelus_capability_map.md:21-22` | architecture_writer | Phase 3 |
| Tab.1 功能对比矩阵 | Q1-Q6 × 16 行（行列冻结见 §5） | landscape + phase1-lit-verification | evaluation_runner | Phase 3 |
| Tab.2 恢复/干预正确性 | 测试名 × 场景 × 断言 × 通过状态（4 套 + D2 新增） | `tests/` | evaluation_runner | Phase 3 |
| Tab.3 案例研究 | 场景 × 指标（恢复耗时/保真度/扰动/成本） | 案例脚本 | evaluation_runner | Phase 3 |

---

## 5. Tab.1 对比矩阵（行列冻结 v1）

### 5.1 列（Q1-Q6，冻结）
- **Q1** 运行期创建 agent（mid-run spawn）｜ **Q2** 组织级持久化/快照（群体+拓扑+分配为一个可恢复单元）｜ **Q3** 运行中 pause/steer/edit-context/resume ｜ **Q4** 私有上下文 + 有界报告交接（排除 raw transcript）｜ **Q5** 每 agent 上下文版本化编辑/回滚 ｜ **Q6** 恢复单元粒度（workflow-step vs 动态组织）。

### 5.2 行（冻结 16 项）
Framework：LangGraph（+LangSmith Agent Server）、AutoGen/AG2、CrewAI、OpenAI Agents SDK、Semantic Kernel、Google ADK、dagent ｜
Durable：Temporal、Restate、DBOS、Inngest ｜
Observability：LangSmith、Langfuse、AgentOps ｜
记忆/其他：Letta、Mastra ｜
**Angelus（最后一行，自评）**

### 5.3 初步判定（Phase 1 主源核实已并入）

| 系统 | Q1 | Q2 | Q3 | Q4 | Q5 | Q6 |
|---|---|---|---|---|---|---|
| LangGraph | PARTIAL | PARTIAL | YES | PARTIAL | PARTIAL | step |
| AutoGen/AG2 | PARTIAL | NO | NO | PARTIAL | NO | step/无 |
| CrewAI | NO | PARTIAL(flow) | PARTIAL | PARTIAL | NO | step |
| OpenAI Agents SDK | PARTIAL | NO | PARTIAL | PARTIAL | NO | step/会话 |
| Semantic Kernel | NO | PARTIAL(process) | NO | NO | NO | step |
| Google ADK | NO | PARTIAL(session) | NO | PARTIAL | NO | 会话 |
| dagent | FULL¹ | NO | NO | — | NO | 无 |
| Temporal | — | PARTIAL(近似) | YES | — | — | workflow-step |
| Restate | — | PARTIAL(近似) | YES | — | YES(对象级) | workflow-step |
| DBOS | — | PARTIAL(近似) | YES | — | PARTIAL | workflow-step |
| Inngest | — | NO | PARTIAL | — | — | step |
| LangSmith | NO | NO | NO(observe-only) | — | NO | 无 |
| Langfuse | NO | NO | NO(observe-only) | — | NO | 无 |
| AgentOps | NO | NO | NO(observe-only) | — | NO | 无 |
| Letta | PARTIAL→YES² | PARTIAL(单 agent) | YES(单 agent) | PARTIAL/FULL | YES(MemFS)² | agent 级(无 org) |
| Mastra | PARTIAL | NO | PARTIAL¹ | — | PARTIAL¹ | step/agent |
| **Angelus** | **YES** | **YES** | **YES** | **YES** | **YES** | **动态组织** |

> 判定来源：`agent_frameworks_landscape.md:5-40`（Q1-Q5）、`multiswarm_dynamics_landscape.md:39-46,82-88`（Pattern 3）、`observability_controlplane_landscape_detailed.md:7-34`（分类）。
> ① UNVERIFIED/降级：dagent（仓库未唯一确定）、Mastra Q3/Q5（主源未检出 suspend/resume）——写作前复核，见 `docs/paper/phase1-lit-verification.md` §3。
> ② CONFIRMED/HIGH（primary 文档）：Letta MemFS=git 版化记忆（docs.letta.com/concepts/memfs）、Letta 子代理=运行期 spawn（docs.letta.com/configuration/subagents）；Temporal/Restate/DBOS/LangGraph Agent Server 恢复单元粒度全部 CONFIRMED（证据表见 phase1-lit-verification.md §1）。
> 其余 MED/LOW 格沿用 landscape 内部知识（`agent_frameworks_landscape.md:3`），写作时逐格复核。

---

## 6. 文献清单（初稿，Phase 2 扩充为 refs.bib）

### 6.1 框架/运行时（primary 文档为主）
- LangGraph 文档：checkpointers / interrupts / time-travel（docs.langchain.com/oss/python/langgraph）；Agent Server（docs.langchain.com/langsmith/agent-server-overview —— pause/HITL/edit-state）
- AutoGen v0.4 Architecture（Agent Runtime Environments）与 AG2 docs（docs.ag2.ai）
- CrewAI：Flows persistence、HITL、structured task outputs（docs.crewai.com）
- OpenAI Agents SDK：handoffs / sessions / HITL（openai.github.io/openai-agents-python）
- dagent（仓库待定——UNVERIFIED：block/go-dagent 404、GitHub 搜索多候选，写作前必须定位主源）
- Mastra（mastra.ai/docs —— Q3 suspend/resume 未主源确认，写作前复核）
- Semantic Kernel（learn.microsoft.com/semantic-kernel）

### 6.2 Durable execution
- Temporal docs（docs.temporal.io/workflow-execution —— 恢复单元=Workflow Execution；另有 Pause/Unpause、Signals、AI cookbook）
- Restate（docs.restate.dev/use-cases/ai-agents —— step 级持久化 + suspend agents）
- DBOS（docs.dbos.dev/ai/ai-quickstart —— workflow 级恢复）
- Julep（github.com/julep-ai/julep）

### 6.3 Observability / 控制平面
- LangSmith / Langfuse / AgentOps / Braintrust / Arize Phoenix（各自官方 docs）
- Anthropic Agent Client Protocol（github.com/anthropics/agent-control-protocol）
- claude-code-router（github.com/musistudio/claude-code-router）、NexusOps（github.com/SiWarlock/NexusOps）

### 6.4 记忆/上下文（可选章节素材，arXiv ID 摘自 `graph_context_design.md:20-60`）
- Microsoft GraphRAG（arXiv:2404.16130）
- LightRAG（arXiv:2410.05779）
- Graphiti（arXiv:2501.13956）
- HippoRAG / HippoRAG 2（arXiv:2405.14831 / 2502.14802）
- Letta（docs.letta.com/concepts/memfs —— git 版化记忆；configuration/subagents —— 运行期 spawn 子代理）

### 6.5 论文先例与格式
- 仓库先例：`docs/mnavrag-arxiv-draft.md`（全文 264 行，含 References 格式样板 :181-264）

---

## 7. D2 实现任务分解（Phase 2 开工清单，锚点已核对）

> 锚点行号以 2026-08-25 工作树为准（较 `visible-innovation-audit.md:155-162` 有漂移，已复核）。

| # | 任务 | 锚点（现状） | 改动目标 |
|---|---|---|---|
| T1 | 快照时机：run 启动即写首个快照 + 事件驱动增量更新 | `api/runs.py:158`（start_run 恢复点）、`api/runs.py:320`（仅在 finally 写）；runtime observer 已挂钩 `task:dispatched/redispatched/reported`（`runtime.py:704-706`） | start_run 后立即 `_persist_swarm_snapshot`（`runtime.py:824`）；在 `runtime.py:704-706` 的 observer 分支加快照写触发（限流/节流防抖，如 2s 合并） |
| T2 | 快照格式支持进行中任务 | `task_bus.py:490` 拒绝 running tasks（`ValueError`） | `from_snapshot` 增加进行中 assignment 分支：持久化 `id/recipient/objective/handoff/expected_artifacts/plan_task_id`，恢复为 queued/interrupted 语义；`to_snapshot` 序列化 running 任务状态 |
| T3 | `_restore_swarm` 进行中分支 + run 标记 | `runtime.py:856`（仅完成态还原）；`api/runs.py:158` 恢复后无标记 | 增加"检测到进行中任务 → 恢复为 queued/interrupted + 恢复报告工具"分支；start_run 对 restored run 打标记（`restored=True` 入 run 元数据/事件） |
| T4 | 前端恢复入口 UI | `app.js:730` restoreRunState 仅展示 error/interrupted，无恢复按钮 | 检测"上次运行未完成 + 有可恢复快照"→ 显示恢复选项按钮；点击后发恢复指令（复用现有 run 启动路径 + restored 标记） |
| T5 | 新增测试 | 现有 `tests/test_swarm_restart_recovery.py` 仅覆盖完成态 | 新增 mid-run kill→restore→continue 集成测试：运行中 kill 后端进程（子进程级），重启后断言拓扑/进行中任务/上下文恢复、后续回合完成 |
| T6 | 验收 | — | 全量 tests/ 通过；Demo #1 升级为"运行中杀掉→点恢复→断点继续"（`visible-innovation-audit.md:161`）；2 周硬截止，超时降级方案 B |

---

## 8. Phase 1 验收核对表

- [x] 研究问题 RQ1-RQ5 冻结，各带判定指标与地点
- [x] 失败判据 F1-F3 预注册
- [x] 章节骨架 6 章，各章含素材映射（file:line）
- [x] 图表清单 6 项定稿（图 3 表 3），责任人明确
- [x] Tab.1 行列冻结（Q1-Q6 × 16 行 + Angelus），初步判定 + 置信度注记已完成（phase1-lit-verification.md）
- [x] 文献清单初稿 5 组（含主源 URL 增补）
- [x] D2 实现任务分解 T1-T6，锚点行号已复核
- [x] phase1-lit-verification.md 已产出并并入 §5.3（置信度注记）与 §6（URL 增补）
