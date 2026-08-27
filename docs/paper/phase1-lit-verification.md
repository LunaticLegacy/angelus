# Phase 1 竞品核实记录（phase1-lit-verification）

> 日期：2026-08-25 ｜ 执行：coordinator 降级核实
> 背景：literature_review worker（assignment fd62e3d00d53469f92c830b23a983ace，p1-lit）派发后两次 `wait_for_reports`（各 240s）空返；按预案由 coordinator 自行核实 Tab.1 承重行。
> 方法：主源文档直取（llms.txt / `*.md` / 页面文本通道），每条含 primary URL + 原文引句 + 判定。README 不作能力证据（同 `visible-innovation-audit.md:4`）。
> 网络状态：出网可用（arxiv.org 200、各 docs 域可达）；GitHub API 触发 rate-limit，部分仓库改用 HTML/raw 通道仍失败。

## 1. 核实结论摘要

| 系统 | 单元格 | 原判定（landscape） | 核实后判定 | 置信度 | primary 证据（URL + 引句） |
|---|---|---|---|---|---|
| Temporal | Q6 恢复单元 | workflow-step | workflow-step（Workflow Execution 为唯一恢复单元） | CONFIRMED | https://docs.temporal.io/workflow-execution — "A Temporal Workflow Execution is a durable, reliable, and scalable function execution and **the main unit of execution** of a Temporal Application"；"fully recoverable after a failure. The Temporal Platform ensures the state of the Workflow Execution persists … and **resumes execution from the latest state**" |
| Restate | Q6/Q3 | workflow-step / suspend agents | step 级持久化 + agent 可 suspend | CONFIRMED | https://docs.restate.dev/use-cases/ai-agents — "**Persist steps** (LLM calls, tools) and **recover previous progress after failures**"；"**Suspend long-running agents** when idle to save costs" |
| DBOS | Q6 | workflow-step | workflow 级恢复（workflow/step 为单元，非 org） | CONFIRMED | https://docs.dbos.dev/ai/ai-quickstart — "DBOS workflows give you one consistent model for ensuring your agents can **recover from any failure from exactly where they left off**"；"Automatically recover your agents from server restarts, process crashes" |
| LangGraph / LangSmith Agent Server | Q3 | YES（可 mutate，须用自家引擎） | YES——pause/HITL/edit-state 均在 LangGraph 引擎内 | CONFIRMED | https://docs.langchain.com/langsmith/agent-server-overview — assistants/threads/runs 三原语、"pause for human review"、checkpointer 后端（PostgreSQL/MongoDB）；https://docs.langchain.com/langsmith/add-human-in-the-loop — LangGraph interrupt + `Command(resume=...)` 注入编辑文本 |
| Letta | Q1 | PARTIAL（server-API create_agent，agent 不建 peer） | **YES(subagent spawn)**——主 agent 运行期经工具 spawn 子代理（subprocess、独立 system prompt/tools/model、仅返回最终消息）；但无 org 拓扑/边，仍是单 agent+子代理模型 | HIGH | https://docs.letta.com/configuration/subagents — "Your main agent can **launch subagents using a specialized subagent tool** … launches a new subagent in a subprocess. The subagent runs autonomously with its own system prompt, tools, and model. **The final message** from the subagent is returned to the main agent, which keeps the main agent's context clean" |
| Letta | Q5 | YES(blocks) | **YES（git 版化记忆 MemFS）** | CONFIRMED | https://docs.letta.com/concepts/memfs — "memory itself is part of the agent's state, held in a **git repository** … Edits are local until **committed and pushed**, at which point they become the agent's memory everywhere" |
| Letta | Q2 | PARTIAL(单 agent) | PARTIAL（stateful agent 为持久化实体，记忆跨会话/机器；无 swarm/org 级快照） | HIGH | https://docs.letta.com/concepts/stateful-agents（页面导航存在，正文未逐句抓取）＋ MemFS/子代理页均以单 agent 为单位 |
| Mastra | Q3 | YES(suspend/resume) | **降级 PARTIAL/UNVERIFIED**——docs/agents 页未检出 suspend/resume/interrupt/durable 关键词 | LOW | https://mastra.ai/docs/agents（页面 200，全文 grep 无命中） |
| Mastra | Q5 | YES(memory) | PARTIAL/UNVERIFIED（docs 侧栏有 Memory 模块，细节未核实） | LOW | https://mastra.ai/docs/（侧栏 "Harness Memory"） |
| dagent | Q1 | FULL（agents spawning sub-agents） | **UNVERIFIED**——仓库无法唯一确定：block/go-dagent 404；GitHub API rate-limit；搜索多候选（mz0in/DAGent、qpiai/dagent、RobotSe7en/dagent…）均无 "spawn" 主源确认 | — | —（写作前必须定位唯一仓库并核实；否则 Tab.1 降为 PARTIAL） |

## 2. 对 outline.md 的修正清单（已并入）

**锚点行号修正**
- `tests/test_swarm_restart_recovery.py:60` → `:61`（`self.assertNotIn("ephemeral-key", snapshot)` 实际在 61 行；capmap:16 有同样的 1 行漂移，本文档留痕，capmap 待后续审计修订）。
- §3.5「单进程 TaskBus（无跨进程锁）」原引 `angelus_capability_map.md:40`（该行为 "Notable absences" 标题，无此内容）→ 改引代码证据：`task_bus.py:95`（`threading.Condition` 同步）+ `api/runs.py:144`（"Keep the in-process execution graph and every Agent instance"）。

**区间端点修正（端点须为非空行，段内空行不计）**
- `angelus_capability_map.md:15-20` → `:15-16`；`:15-17` → `:15-16`；`:18-20` → `:18-19`；`:21-23` → `:21-22`（×2）；`:21-26,37-39` → `:21-25,37-38`；`:24-26` → `:24-25`；`:37-39` → `:37-38`
- `angelus_swarm_dynamics.md:26-28` → `:26-27`
- `multiswarm_dynamics_landscape.md:39-47` → `:39-46`（×2）
- `visible-innovation-audit.md:110-121` → `:110-120`；`:164-166` → `:164-165`

**判定更新**
- Tab.1 dagent Q1：`FULL` → `FULL¹`（UNVERIFIED）
- Tab.1 Mastra Q3：`YES(suspend/resume)` → `PARTIAL¹`；Q5：`YES(memory)` → `PARTIAL¹`
- Tab.1 Letta Q1：`PARTIAL` → `PARTIAL→YES²`（subagent spawn，无 org 拓扑）；Q5：`YES(blocks)` → `YES(MemFS)²`
- §6 文献 URL 增补（Temporal/Restate/DBOS/LangSmith Agent Server/Letta 主源；dagent 标 UNVERIFIED）

## 3. 未核实 / 降级清单（写作前必须复核）

1. **dagent**（Tab.1 Q1 承重格）：UNVERIFIED。写作前定位唯一仓库并取 create_agent/spawn 主源；失败则降 PARTIAL 并删去差异化引用。
2. **Mastra**（Q3/Q5）：UNVERIFIED。补 docs.mastra.ai 正确页面路径后再判定。
3. **AutoGen/AG2、CrewAI、Semantic Kernel、Google ADK、OpenAI Agents SDK、smolagents、PydanticAI、Langfuse/AgentOps observe-only、Inngest、Julep、LangSmith Studio**：MED/LOW 格沿用 landscape 内部知识（`agent_frameworks_landscape.md:3,17-63`；`multiswarm_dynamics_landscape.md:5`），论文写作时逐格以 primary 源复核。
4. **Temporal/Restate/DBOS 的 Q2「无 org 级存储」为否定性 claim**：正面证据（workflow/step 级单元）已 CONFIRMED；「org 须从历史重派生」作为设计推断（HIGH），论文中须以「未发现 org 存储原语」措辞表述而非绝对断言。

## 4. 对论文写作的提示

- RQ2（恢复单元粒度差异）的支撑现在有 3 条 CONFIRMED 主源（Temporal/Restate/DBOS）+ 1 条框架侧（LangGraph checkpoint 为 thread 级，landscape HIGH）。
- Letta 的 subagent spawn 与 MemFS 是 Related Work 里最需要正面回应的两点（Q1/Q5 竞品接近项）；差异句须落在「org 拓扑/边 + 每 agent 私有上下文 + 可恢复单元」上，而不是「能 spawn」。
- 论文 References 用 §1 表中 URL 对应的稳定文档页（带版本/日期），不用 llms.txt 链接。

---

## 3.1 承重格复核记录（2026-08-26，literature_review worker p1-lit 补做）

> 方法同 §1：primary 源直取（GitHub API / llms.txt / `*.md` 页面文本），README 不作能力证据；每条含 URL + 原文引句。网络：GitHub API 已恢复（60 req/h），mastra.ai 与 export.arxiv.org 可达。

### (a) dagent（Tab.1 Q1 承重格）——UNVERIFIED → **降级 PARTIAL**

GitHub 搜索 `dagent`（total=143）无法唯一定位「运行期 create_agent/spawn 子代理」主源。逐一核验候选：

| 候选仓库 | stars | 实际形态 | 判定 |
|---|---|---|---|
| RobotSe7en/dagent | 6 | Dynamic DAG Agent：`Runner` 持有运行期会话，`runner.add_agent` 注册 agent；顶层 agent 经 `ToolAgent(agents=["agent.helper"])` 委派给**已注册** subagent（`examples/agent_delegation.py`） | **注册委派，非运行期 spawn** |
| mz0in/DAGent | 1 | `DecisionNode`/`FunctionNode` 静态 DAG，LLM 选函数执行 | 静态 DAG，非 agent spawn |
| qpiai/dagent | 9 | 静态多 agent DAG 编排（planner→DAG builder→kernel→judge） | 静态编排 |
| svdh2/dagent | 1 | 确定性 DSL（2026-03 创建，early dev）；README grep "spawn/sub-agent" 无命中 | 非主线 |
| d-agent/dagent-api | 0 | 商业化路由平台（"Use any AI agent instantly"） | 路由平台 |
| block/go-dagent | — | GitHub API 404 | 不存在 |

**结论**：无 primary 证据支持 landscape 原「FULL（agents spawning sub-agents）」表述（`multiswarm_dynamics_landscape.md:24,35,84`）。差异点最多到「运行期注册 + 工具委派给已注册 subagent」。Tab.1 Q1 降 **PARTIAL**，删除「true mid-run create_agent」差异化引用；论文如引用 dagent 须以 RobotSe7en/dagent 的 delegation 模型为准（另三个候选 stars≤9 非主流，谨慎使用）。

### (b) Mastra（Q3/Q5）——UNVERIFIED → **CONFIRMED**（正确路径在 mastra.ai/docs，非 docs.agents 顶层）

- **Q3 suspend/resume**：https://mastra.ai/docs/workflows/suspend-and-resume ——「Workflows can be paused at any step to collect additional data or wait for API callbacks... When a workflow is suspended, its current execution state is saved as a snapshot. You can later resume the workflow from a specific step ID」；且「Snapshots are stored in your configured storage provider and persist across deployments and application restarts」。agent 侧 HITL：https://mastra.ai/docs/agents/human-in-the-loop ——「you can suspend a tool call before it executes so a human can approve or decline it, or let tools suspend themselves to request additional context from the user」（pre-execution approval + runtime suspension 双机制）。
- **Q5 memory**：https://mastra.ai/docs/memory/overview ——「Memory enables your agent to remember user messages and agent replies, and tool results across interactions」；分层：message history、observational memory、working memory、semantic recall、multi-user threads。
- Tab.1 更新：Mastra Q3 → YES（snapshot 持久化、跨部署恢复）；Q5 → YES（memory 模块 multi-layer）。

### (c) §6 文献 → refs.bib 交付状态

- `docs/paper/refs.bib` 已产出（236 行、28 条 @misc），按 outline §6 五组（6.1 框架 / 6.2 durable / 6.3 observability / 6.4 记忆 / 6.5 先例）组织；每条含稳定 URL + note（检索日期 2026-08-26、primary 判定、CONFIRMED 引句）。
- 6.4 arXiv 5 篇元数据（title/author/version）经 export.arxiv.org API 核对：2404.16130（GraphRAG，v2）、2405.14831（HippoRAG，v3）、2501.13956（Zep，v1）、2502.14802（HippoRAG 2，v2）、2410.05779（LightRAG，v3）。
- **命名注意**：arXiv 2501.13956 官方标题为「Zep: A Temporal Knowledge Graph Architecture for Agent Memory」（Graphiti 是 Zep 的库）。bib key 沿用 `zep_graphiti`（与 outline §6.4 一致），但论文正文/参考文献应写 **Zep (Graphiti)** 以利检索。
- 6.3 可达性：langfuse.com/docs、docs.agentops.ai、docs.ag2.ai、docs.crewai.com、learn.microsoft.com/semantic-kernel、openai.github.io/openai-agents-python、docs.letta.com/{concepts/memfs,configuration/subagents} 均 HTTP 200；braintrust.dev/docs 与 docs.arize.com/phoenix 本轮未复测（bib 内已标 UNVERIFIED，写作时复核）。
- outline.md Tab.1 的 dagent/Mastra 格本次未改（避免与审核中的 outline 冲突），由论文写作阶段并入；§3.1 (a)(b) 两表即合并依据。
