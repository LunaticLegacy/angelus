# Angelus arXiv 论文工作流（Phase 0 定稿）

> **状态**：Phase 0（工作流定稿，本轮交付）。论文正文未开始。
> **依据素材**：`docs/research_innovation/`（9 份）＋ `docs/`（semantic-map、graph_context_design、v0.5.0-spec、INDEX 等）＋ 根 README 定位文案。
> **证据纪律**：论文中一切能力 claim 以 `文件:行` 引用审计已核对的代码证据；README 仅作定位措辞参考，不作能力证据（同 `docs/research_innovation/visible-innovation-audit.md:4`）。
> **仓库先例**：`docs/mnavrag-arxiv-draft.md` 是仓库内已有的 arXiv 草稿范本（状态标注、匿名作者、Abstract、编号章节、baselines/metrics 表、reproducibility checklist），本文工作流与其风格对齐。

---

## 1. 选题与核心论点

### 1.1 选题依据（审计结论）

`docs/research_innovation/visible-innovation-audit.md` 的 Executive Conclusion 明确指出：创新不在"多 Agent 框架"本身，而在于把**动态 Agent 组织当作一等运行时状态**——可持久化、可查看、可干预、可恢复的本地控制台（`visible-innovation-audit.md:10-18`）。最强 3 个创新点及得分：

| # | 创新点 | 得分 | 成熟度 | 审计引用 |
|---|---|---|---|---|
| 1 | 组织级持久化与恢复（Organizational Persistence & Recovery） | 53/70 | 完成态恢复 ✓；运行中恢复 ✗ | `visible-innovation-audit.md:77-86` |
| 2 | 对运行中 Agent 系统的可干预调试（Debugger for Running Agents） | 52/70 | IMPLEMENTED，可即用 | `visible-innovation-audit.md:88-96` |
| 3 | 可审计的每 Agent 上下文修订历史 | 44/70 | IMPLEMENTED | `visible-innovation-audit.md:99-106` |

**必须遵守的边界**：审计 §9 明确列出"绝对不要"作为创新宣传的 commodity 清单（MCP/插件/多模型/token 统计/RAG/支持 Codex/支持持久化/"下一代 Agent 平台"），并诚实声明单项差异都在 commodity 内、差异在**组合 + 组织粒度 + 本地可干预**（`visible-innovation-audit.md:18,141-151`）。论文的 claim 一律按此边界撰写。

### 1.2 中心论点（1 主 1 辅）

**Claim P（主论点）— 组织级持久化与恢复**
> 动态 Agent 组织（运行期 spawn 的 agent、运行时拓扑变更、TaskBus 任务分配、每 agent 私有上下文）可以被整体序列化为一个**可恢复单元**，进程重启后以"组织"粒度还原并继续工作——恢复单元是"有哪些 agent、谁是谁的下属、谁在做什么、任务总线里有什么"，而非"工作流第 N 步"。

支撑事实（均出自能力审计，论文写作时须回溯代码原文）：
- 运行期创建 agent 与拓扑变更 IMPLEMENTED：`angelus_capability_map.md:5-10`（`execution_graph.py:1213/1241/1265/...`）
- 组织快照持久化 IMPLEMENTED：`angelus_capability_map.md:15-17`（`execution_graph.py:295/355/376`、`task_bus.py:485/520`、`runtime.py:763`，无密钥）
- 进程重启后恢复 IMPLEMENTED：`angelus_capability_map.md:18-20`（`runtime.py:795`、`tests/test_swarm_restart_recovery.py`）

**Claim S（辅论点）— 对运行中 Agent 的可干预调试**
> 将"可观测"升级为"可干预"（pause / steer / edit-context / recover / continue），配合**每 agent 粒度、不可变、可审计、可回滚**的上下文修订历史，在独立本地控制台内对任意 worker 生效。

支撑事实：
- steering/stop/force-stop IMPLEMENTED：`angelus_capability_map.md:24-26`（`api/runs.py:490/512/539`）
- 版本化上下文编辑+恢复 IMPLEMENTED：`angelus_capability_map.md:21-23`（`context_editing.py`、`tests/test_context_editing.py`）
- 每 agent 隔离上下文 IMPLEMENTED：`angelus_capability_map.md:18-20`（`execution_graph.py:233`、`runtime.py:557`）

### 1.3 反 claim（对抗审查的裁决，论文必须正面回应）

`docs/research_innovation/adversarial_attack_report.md` 是仓库内**最严格的自我审查**：6 个候选中有 5 个被判 "CONFIRMED COMPETITOR (kill)"，只有 E（每 agent 上下文 + 版本化编辑）被判 "PARTIAL (weaken)"，结论是"任何幸存 claim 必须重述为 design-center/differentiation，而非 novel capability"（`adversarial_attack_report.md:88-99`）。

| 反 claim | 来源 | 论文回应策略（narrowing） |
|---|---|---|
| Anti-P1：Julep+Temporal 已产品化 durable agent-org restore，LangGraph checkpoint/AutoGen save_state 已覆盖持久化恢复 | `adversarial_attack_report.md:7-17` | 差异在**恢复单元**：竞品恢复 workflow/step 状态（拓扑是代码，不是快照数据）；Angelus 恢复"动态组织"（运行期 spawn + 拓扑变更 + 分配 + 任务总线）。引用 `multiswarm_dynamics_landscape.md:82-88`（Pattern 3 判定：无主流框架快照"agent 数+边+父子+分配"为可恢复单元）与 `observability_controlplane_landscape_detailed.md:55-57`（"No product recovers a true dynamic agent ORGANIZATION as a first-class primitive"） |
| Anti-S1：LangSmith Studio / LangGraph update_state+interrupt / OpenAI RunState 已覆盖 observe+edit+resume 全环 | `adversarial_attack_report.md:21-31` | 差异在**独立性 + 粒度 + 审计**：LangGraph mutate 绑定自家引擎（`observability_controlplane_landscape_detailed.md:58-60`）；Angelus 是本地独立控制台 + 每 agent 不可变审计修订（SHA-256 基线/actor/reason/rollback），非整图 checkpoint 粒度（`adversarial_attack_report.md:63-71` 的 E 项 weaken 建议） |
| Anti-P2：AutoGen v0.4 runtime 注册 + save/load 已覆盖动态组织 | `agent_frameworks_landscape.md:16-21` | 该 landscape 判定 AutoGen **Q2: NO**（无组织级持久化）、**Q3: NO**（无 mid-run steer 协议）；论文对比矩阵以该表为准 |

**论文不主张**（避免被 kill）：不主张"持久化/恢复/调试"单点是新发明；不主张 MCP/多模型/插件等 commodity；不主张"下一代 Agent 平台"空泛定位（`visible-innovation-audit.md:141-151`）。

### 1.4 论文类型定位

**Systems paper**（系统设计 + 实现 + 实证），非 ML 方法论文：
- 贡献 = 一个新的运行时抽象（组织级快照/恢复 + 运行中干预 API）+ 参考实现 + 功能对比矩阵 + 案例研究。
- 评估风格对齐 `mnavrag-arxiv-draft.md` 的"pre-registered claims + 明确的失败判据"（`docs/mnavrag-arxiv-draft.md:120-140`），避免事后 reinterpretation。

---

## 2. 投稿策略

### 2.1 arXiv 分类候选

| 分类 | 契合度 | 理由 |
|---|---|---|
| **cs.AI（主，默认）** | ★★★★★ | 多 Agent 系统、agent 运行时；覆盖面最广，读者群匹配 |
| cs.MA（multiagent systems，交叉） | ★★★★☆ | 动态组织、swarm、任务分配是主题；推荐与 cs.AI 交叉 |
| cs.SE（software engineering） | ★★★☆☆ | 若强调"控制平面/调试器/工程差异化"角度 |
| cs.DC（distributed/durable execution） | ★★☆☆☆ | 若强调 durable execution 对照（Temporal/DBOS/Restate），但非主题 |

**默认建议**：主分类 **cs.AI**，交叉 **cs.MA**（Phase 6 提交时勾选）。

### 2.2 篇幅与语言

- **语言**：英文（正文、图表、参考文献）。
- **篇幅**：两栏 8-15 页。**默认目标 12 页正文 + 参考文献/附录**（上限内留余量给审稿缓冲）。
- 依赖决策 D2：若"不补运行中恢复实现"（方案 B），降级为 8-10 页短文（Evaluation 收缩为"完成态恢复 + 设计展望"）。

### 2.3 时间线（含缓冲）

总周期约 **7-8 周**（含 1.25× 缓冲系数；每 Phase 末尾预留缓冲日）。假设 D2 = 补实现（+2 周），D3 = 用户已有 arXiv 账号。

| 周次 | Phase | 内容 | 产出 |
|---|---|---|---|
| W1 | Phase 1 | 大纲 + 文献调研并行启动 | 大纲 v1、文献清单 |
| W2-3 | Phase 2+实现 | 草稿写作（Design ∥ Eval 计划）＋（若 D2=是）补运行中恢复实现 | 草稿 v1、实现 PR |
| W4 | Phase 3 | 评估数据收集（跑测试/案例研究） | 数据表、图 |
| W5 | Phase 4 | 整合润色 | 草稿 v2（英文通稿） |
| W6 | Phase 5 | 预审（对抗审查/查重/LaTeX 编译） | 终稿 v3 |
| W7 | Phase 6 | 提交（含 1 周 endorsement/账号缓冲） | arXiv 提交 |

---

## 3. 论文结构草案

### 3.1 标题候选（5 个）

1. **Your Agent Organization Should Survive Crashes: Persistence and Recovery for Dynamic Multi-Agent Systems**（呼应审计 §8 Landing Hero "Your agent org should survive crashes, not just your chat"）
2. **Angelus: A Local Control Plane with Organizational Persistence and Runtime Intervention for Dynamic Agent Swarms**
3. **Dynamic Agent Organizations as First-Class Runtime State: Snapshot, Restore, and Intervention**
4. **Organizational Persistence for Agent Swarms: Recovering Topology, Assignments, and Context After Process Death**
5. **Operating the Agent Organization: A Local Control Plane for Persistence, Debugging, and Recovery of Dynamic Swarms**

**默认推荐 #1 或 #2**（#1 记忆点强；#2 规范、含系统名）。Phase 1 大纲定稿时锁定。

### 3.2 摘要要点（6 句骨架）

1. **问题**：长周期 swarm 崩溃/关机/网络中断即全部白做；现有恢复是 workflow/step 级，不是"动态组织"级。
2. **现状差距**：可观测工具全部 observe-only；能 mutate 的必须绑定自家引擎。
3. **方法**：把"Agent 组织"（拓扑 + worker + TaskBus 分配 + 每 agent 上下文）作为一等持久化单元；快照无密钥、重启后还原并继续。
4. **干预**：运行中 pause/steer/edit-context/recover/continue + 每 agent 不可变审计修订历史。
5. **证据**：功能对比矩阵（vs LangGraph/AutoGen/CrewAI/OpenAI Agents SDK）+ 恢复/干预案例研究 + 自动化测试套件。
6. **边界**：诚实声明单项均为 commodity，贡献在组合与组织粒度；运行中恢复（若 D2=否）列为设计展望。

### 3.3 章节大纲

| 章节 | 要点 | 主要素材 |
|---|---|---|
| **1. Introduction** | 问题场景（40 分钟 swarm 白跑）；三个 Demo 场景（杀掉组织→复活 / 跑偏 worker 动手术 / 上下文回滚，`visible-innovation-audit.md:110-121`）；贡献列表；诚实边界 | 审计 §6-9 |
| **2. Related Work** | 分层：Agent Framework（LangGraph/AutoGen/CrewAI/SDK/ADK）、Durable Execution（Temporal/Restate/DBOS）、Observability（LangSmith/Langfuse/AgentOps/Phoenix）、Coding-Agent 控制（Codex/Claude Code/ACP/ccr/NexusOps）、GraphRAG 记忆（Graphiti 等，若涉及上下文） | 4 份 landscape + adversarial + `graph_context_design.md:20-60` |
| **3. System Design** | 3.1 运行时模型（ExecutionGraph 拓扑 + TaskBus 调度，`angelus_swarm_dynamics.md:3-4`）；3.2 组织快照格式（swarm-runtime.json、无密钥、`angelus_capability_map.md:15-17`）；3.3 恢复语义（`_restore_swarm`、完成态 vs 运行中，`angelus_capability_map.md:18-20` + `visible-innovation-audit.md:155-162`）；3.4 运行中干预 API（steer/stop/force-stop/context 编辑，`angelus_capability_map.md:21-26`）；3.5 上下文修订审计（ContextEditStore、SHA-256、actor/reason、`angelus_capability_map.md:21-23`）；3.6 前端控制台（app.js 图视图、agent-card、`angelus_capability_map.md:37-39`） | capability map + swarm dynamics + `semantic-map.md` 各模块 |
| **4. Evaluation** | 4.1 功能对比矩阵（见 4.4）；4.2 恢复正确性（自动化测试：`tests/test_swarm_restart_recovery.py`、`test_swarm_failure_isolation.py`、`test_context_editing.py`、`test_session_steers.py`）；4.3 案例研究 1（崩溃恢复）；4.4 案例研究 2（运行中干预）；4.5 成本对比（重做 vs 恢复，token/时间） | 测试套件 + landscape + 案例脚本 |
| **5. Discussion** | 局限（单进程 TaskBus 假设、无运行中恢复或方案 B、无端到端 benchmark）；失败判据（pre-registered）；威胁有效性 | 审计 §10 + 本文 4.3 |
| **6. Conclusion** | 贡献回扣 + 未来工作（运行中恢复、tool 副作用重放、异构 agent 统一控制） | 审计 §10 #1-#3 |

### 3.4 图表规划

| 图/表 | 内容 | 素材来源 | 责任人 |
|---|---|---|---|
| Fig.1 系统架构图 | 前端控制台 ↔ API（runs/context/graph）↔ 运行时（ExecutionGraph/TaskBus/上下文存储）↔ 模型提供方 | `angelus_swarm_dynamics.md` + `semantic-map.md` | architecture_writer |
| Fig.2 恢复时序图 | crash → restart → `_restore_swarm` → 重建 agent/重挂 report 工具 → 继续 run | `angelus_capability_map.md:18-20` | architecture_writer |
| Fig.3 上下文修订历史 | edit/restore 链：baseline → rev1(actor/reason) → rev2 → restored_from | `angelus_capability_map.md:21-23` | architecture_writer |
| Tab.1 功能对比矩阵 | Q1-Q6 × LangGraph/AutoGen/CrewAI/SDK/ADK/Angelus（YES/PARTIAL/NO + 置信度） | `agent_frameworks_landscape.md:5-40` + `multiswarm_dynamics_landscape.md` | evaluation_runner（重新核实 MED/LOW 行） |
| Tab.2 恢复正确性 | 测试名 × 场景 × 断言 × 通过状态 | `tests/` 4 个套件 | evaluation_runner |
| Tab.3 案例研究 | 场景 × 指标（恢复耗时/保真度/干预前后轮数/成本） | 案例脚本 | evaluation_runner |

---

## 4. 素材盘点与缺口分析

### 4.1 可直接复用素材

| 素材 | 用途 | 引用起点 |
|---|---|---|
| `docs/research_innovation/visible-innovation-audit.md` | 创新点定界、能力表（file:line 证据）、竞品表、Demo、What-NOT-to-Market | `:11-18`、`:21-45`、`:46-57`、`:77-121`、`:141-151` |
| `docs/research_innovation/angelus_capability_map.md` | System Design 的代码级证据（a-j 全部实现项 + 缺项） | `:5-40` |
| `docs/research_innovation/angelus_swarm_dynamics.md` | 运行时语义（TaskBus/图/快照/恢复/隔离/revival） | `:3-34` |
| `docs/research_innovation/adversarial_attack_report.md` | 反 claim 正典（论文必须回应的裁决书） | `:7-99` |
| `docs/research_innovation/agent_frameworks_landscape.md` | Tab.1 对比矩阵骨架（Q1-Q5，含置信度） | `:5-40` |
| `docs/research_innovation/multiswarm_dynamics_landscape.md` | Pattern 1-6 竞品判定 + "genuinely rare" 5 条结论 | `:82-88` |
| `docs/research_innovation/observability_controlplane_landscape_detailed.md` | observe-only vs mutate+continue 分类表 + gap summary | `:7-34`、`:55-60` |
| `docs/research_innovation/coding_agents_landscape.md` | 异构 Coding Agent 控制（工程差异化章节） | `:5-48` |
| `docs/semantic-map.md` | System Design 的模块职责（代码语义权威参考） | 全篇 |
| `docs/graph_context_design.md` | 上下文系统设计（若论文涉及图记忆/压缩） | `:1-30` |
| `tests/`（`test_swarm_restart_recovery.py` 等 4 套） | Evaluation 正确性证据 | — |
| `docs/mnavrag-arxiv-draft.md` | 论文格式范本（状态标注/匿名/编号节/checklist） | `:1-30`、`:120-140`、`:180-264` |
| 根 `README.md` | 仅作定位措辞与 Hero 文案参考（不作能力证据） | `:1-30` |

### 4.2 章节缺口分析

| 章节 | 缺什么 | 补法 |
|---|---|---|
| Introduction | 无标准 benchmark 故事线；Demo 需录屏/截图 | 用审计 Demo 场景 + 案例研究；Phase 3 录屏 |
| Related Work | landscape 中 MED/LOW 置信度条目（smolagents、AG2、Mastra、Kagent 等）未核实；2025-2026 新文献未覆盖 | literature_review worker 逐条核实 primary docs（`agent_frameworks_landscape.md:76` 已自标"spot-check before use"；`multiswarm_dynamics_landscape.md:88-90` 已列 verification gaps） |
| System Design | 运行中恢复未实现（`visible-innovation-audit.md:86`）；单进程 TaskBus 假设（无跨进程锁） | 见 4.3 决策 D2；局限写入 Discussion |
| Evaluation | 无端到端 benchmark；无竞品同场跑分；无用户研究 | 不做 benchmark（成本/无标准任务集），改为"对比矩阵 + 正确性测试 + 案例研究"组合（见 4.4） |
| Discussion | 失败判据、威胁有效性未写 | 仿 `mnavrag-arxiv-draft.md:120-132` 预注册失败判据 |

### 4.3 关键决策：运行中恢复未实现的论文定位（→ D2）

现状：完成态恢复 IMPLEMENTED，运行中恢复 NOT IMPLEMENTED（`visible-innovation-audit.md:86`）。审计 §10 #1 已给出**实现路径 4 步 + 工作量约 1-2 周**（`visible-innovation-audit.md:155-162`），并明确"补完后 Completeness 从 7 拉到 9-10，Demo #1 升级为运行中杀掉→点恢复→从断点继续"（`visible-innovation-audit.md:161`）。

**方案 A（默认推荐）：先补实现，再写 Evaluation。**
- 理由：主 claim P 的锋利度完全依赖"进程重启后组织可恢复"；完成态恢复已有测试证据（`tests/test_swarm_restart_recovery.py`），但"运行中恢复"才是用户心智模型里最锋利的一刀（`visible-innovation-audit.md:161`）；工作量 1-2 周可控，且实现路径已被审计细化。
- 风险：延期 1-2 周；若实现卡壳，降级到方案 B（见下），论文结构不变，仅 Evaluation/未来工作措辞变化。

**方案 B（降级路径）：不补实现，论文定位为"完成态恢复实证 + 运行中恢复设计展望"。**
- 主 claim 改写为"组织级快照/恢复抽象（完成态实证）+ 运行中恢复协议设计（未来工作）"；Evaluation 收缩为 8-10 页短文。
- 适用：时间硬约束、或用户判断实现风险高。

### 4.4 对比实验设计

**（1）功能对比矩阵（Tab.1）**——沿用 `agent_frameworks_landscape.md:5` 的 Q1-Q5 并扩展 Q6（恢复单元粒度）：
- Q1 运行期创建 agent / Q2 组织级持久化 / Q3 运行中 pause-steer-resume / Q4 私有上下文+有界报告 / Q5 版本化上下文编辑 / Q6 恢复单元（workflow-step vs 动态组织）。
- 竞品行：LangGraph、AutoGen（AG2/v0.4）、CrewAI、OpenAI Agents SDK、Semantic Kernel、ADK、dagent、Temporal、Restate、DBOS、LangSmith、Langfuse、Letta。
- 纪律：每格标 YES/PARTIAL/NO + 置信度（CONFIRMED/HIGH/MED/LOW）；MED/LOW 在 Phase 1 由 literature_review 重新核实 primary docs。

**（2）案例研究 1 — 崩溃恢复**（D2=是 时执行）：
- 场景：3-5 worker 的 swarm 跑真实任务（如仓库内的多文件研究任务）；运行中 kill 后端进程 → 重启 → 同一会话恢复 → 继续。
- 指标：恢复耗时、恢复后拓扑/worker/任务分配保真度（与快照逐字段比对）、恢复后继续完成的回合数、与"重做"的 token/时间成本对比。
- 对照：不恢复、从零重建（基线）。

**（3）案例研究 2 — 运行中干预**：
- 场景：一个 worker 重复犯错 → 打开其私有上下文 → `edit_context` 注入修正 → 继续 → 兄弟 worker 无感。
- 指标：干预前/后目标 worker 的错误率、兄弟 worker 的输入扰动（应为 0）、上下文修订审计完整性（actor/reason/基线）。
- 对照：不干预（整体停掉重来）成本对比。

**（4）明确不做**：端到端公共 benchmark（无标准任务集、成本高、易被攻击"选任务"），改为正确性测试套件 + 案例研究 + 矩阵。

---

## 5. 分工方案（swarm worker）

沿用审计的 swarm 模式（coordinator 统筹 + 并行 worker + 对抗审查独立复核），每 worker 交付必须带 `文件:行` 证据。

### 5.1 Worker 角色

| Worker | 职责 | 输入 | 产出 | 证据纪律 |
|---|---|---|---|---|
| `coordinator` | 分派任务、整合各 worker 输出、维护本文工作流状态 | 工作流文档 | 章节成稿合并 | 全篇统稿 |
| `literature_review` | Related Work：核实 MED/LOW 竞品条目、补 2025-2026 文献、生成参考文献库（BibTeX） | 4 份 landscape + verification gaps 清单 | related-work.md + refs.bib | 每条引用 = primary URL + 访问日期；未核实条目标 MED/LOW |
| `architecture_writer` | System Design 章节 + Fig.1-3 | capability map + swarm dynamics + semantic-map | system-design.md（英文）+ 图源文件 | 每个机制 claim 回溯代码 `文件:行` |
| `evaluation_runner` | Tab.1 矩阵核实、跑 4 个测试套件、执行案例研究 1/2、产数据表 | tests/ + landscape + 案例脚本 | evaluation.md + 数据表 + 录屏 | 每个数字可复现（记录环境/版本/种子） |
| `adversarial_reviewer` | 对抗审查：独立核实竞品 primary 证据，输出 CONFIRMED/PARTIAL/ELIMINATE 裁决书 | 论文草稿 v1/v2 | adversarial-review-v2.md | 沿用 `adversarial_attack_report.md` 传统（逐条判定 + 引用） |
| `language_polisher` | 英文润色、术语统一、LaTeX 排版 | 草稿 v2 | 终稿 v3 | 不改变技术 claim 语义 |

### 5.2 各阶段并行度

```
Phase 1:  coordinator(大纲) ────────────────► literature_review(启动) ─┐
Phase 2:  architecture_writer ∥ evaluation_runner（Design 与 Eval 解耦） │
          literature_review 全程并行（Related Work 与正文互不阻塞）       ├─► coordinator 整合
Phase 3:  evaluation_runner 收集数据（测试/案例）                        │
Phase 4:  coordinator 合并 ──► language_polisher（润色）                 │
Phase 5:  adversarial_reviewer（独立对抗）＋ 引用核查 ∥ 格式编译 ─────────┘
Phase 6:  coordinator 提交
```
- Phase 2 最大并行度 3（architecture ∥ evaluation ∥ literature）。
- Phase 5 对抗审查与正文作者**必须隔离**（沿用审计"对抗审查 ×1、本地复核"的双轨）。

---

## 6. 质量流程

### 6.1 内部对抗审查（沿用 `adversarial_attack_report.md` 传统）

- **时机**：Phase 5（草稿 v2 定稿后）必做一次；Phase 2 草稿 v1 后可做一次轻量预审。
- **方法**：`adversarial_reviewer` 独立核实竞品 primary docs/repos（不依赖本仓库 landscape 转述），逐条输出 CONFIRMED COMPETITOR / PARTIAL / ELIMINATE 判定，并给出证据 URL。
- **闭环要求**：论文团队必须对每条裁决书面回应——接受（改稿）/反驳（给证据）/窄化（改 claim）；无回应的裁决不得进终稿。此纪律直接来自 `adversarial_attack_report.md:88-99` 的教训（broad claim 全被 kill）。
- **验收**：终稿中不存在未回应的"竞品已覆盖"指控。

### 6.2 引用与抄袭检查

- **自家代码 claim**：一律 `文件:行`（审计已核对过一轮；Phase 2 写作时须回溯代码原文复核，防止审计行号漂移）。
- **竞品 claim**：primary 文档 URL + 访问日期；禁止引用本仓库 landscape 转述作为论文直接引用源（只作线索）。
- **相似度检查**：提交前对全文做 plagiarism 检查（如 iThenticate 或等价工具）；重点核查 Related Work 复述句。
- **引用完整性**：refs.bib 全字段（作者/年份/arXiv ID/venue）；匿名草稿阶段不泄漏作者身份（`mnavrag-arxiv-draft.md:4-6` 先例）。

### 6.3 LaTeX / arXiv 格式准备

- **模板**：arXiv 标准两栏（推荐 `article` 11pt twocolumn + 简单宏包，或 IEEEtran 风格）；不做花哨排版。
- **链路**：Phase 2-4 用 Markdown 写作（本仓库先例 `mnavrag-arxiv-draft.md`），Phase 5 用 pandoc 转 LaTeX + 手工修图注/公式；或全程直接 LaTeX（若 architecture_writer 熟悉）。
- **提交前 checklist**：摘要 ≤ 200 词且含方法/证据/边界；无 TODO/占位符；图分辨率 ≥ 300dpi（arXiv 要求）；license 声明（默认 CC BY 4.0 或用户指定）；endorsement 处理（见 D3）；编译零警告通过（`pdflatex -halt-on-error`）。

---

## 7. 决策点清单（需用户拍板）

| # | 决策点 | 选项 | **默认建议** | 影响 |
|---|---|---|---|---|
| **D1** | 作者署名 | (a) 匿名草稿、提交前定 (b) 现在就定 | **(a) 匿名草稿（沿用 `mnavrag-arxiv-draft.md:4-6` 先例），提交前一周定稿**；建议用户为通讯作者 | 影响 Phase 5 前全部流程零成本；匿名可避免早期泄漏 |
| **D2** | 是否先补「运行中恢复」实现 | (a) 先补实现再写 Evaluation（1-2 周） (b) 不补，论文定位"完成态实证 + 设计展望" | **(a) 先补实现**：审计 §10 #1 已给 4 步路径（`visible-innovation-audit.md:155-162`），工作量可控，把主 claim 从"完成态"升级为"断点恢复"，Completeness 7→9；若 2 周内未完成则自动降级 (b) | 决定 Evaluation 强度与篇幅（12 vs 8-10 页） |
| **D3** | arXiv 账号 / endorsement | 用户准备：已有账号 / 需新注册 / 需 endorsement | **用户应已有或提前注册 arXiv 账号**；cs.AI 新分类投稿需 endorsement——若无可背书人，提前 1-2 周申请（对应时间线 W7 缓冲） | 阻塞性前置条件，最迟 Phase 5 前确认 |
| **D4** | 篇幅与分类 | 篇幅 8-15 页；分类 cs.AI/cs.MA/cs.SE/cs.DC | **12 页正文 + cs.AI 主分类 + cs.MA 交叉**（D2=是时）；D2=否则 8-10 页、cs.AI 单分类 | 决定写作深度与评估章节规模 |
| D5（可选） | 是否附开源仓库链接（reproducibility） | 附 / 不附 | **附**（仓库 MIT license、已有公开 GitHub）；可提升可信度 | 影响可复现性声明；需确认仓库公开状态 |
| D6（可选） | 案例研究素材选择 | 仓库内真实任务 / 自造 demo 任务 | **仓库内真实多 worker 任务**（如研究类 swarm），避免"选任务"攻击 | 影响 Evaluation 说服力 |

---

## 8. 里程碑

| Phase | 名称 | 目标 | 产出与验收 | 预计 | 依赖 |
|---|---|---|---|---|---|
| **Phase 0** | 工作流定稿（本轮） | 本文件 | ✅ 本文档经用户确认（8 节齐全、决策点拍板） | 0.5 周 | — |
| **Phase 1** | 大纲 | 研究问题 + 章节骨架 + 图表清单 + 文献清单 | 大纲 v1 验收：每章有 claim + 素材映射；Tab.1 行/列冻结 | 1 周 | Phase 0 决策 D1-D6 |
| **Phase 2** | 草稿 | System Design + Evaluation 计划 + Related Work 初稿（D2=是时并行实现） | 草稿 v1（英文）：各章由对应 worker 交付，file:line 齐全 | 2 周 | Phase 1 + D2 |
| **Phase 3** | 评估 | 跑测试套件 + 案例研究 1/2 + 矩阵核实 | evaluation.md + 数据表 + 录屏；每个数字可复现 | 1 周 | Phase 2（D2=是时含实现合入） |
| **Phase 4** | 整合润色 | 合并各章 + 英文通稿 + 图表定稿 | 草稿 v2：单一文档、无占位符、术语统一 | 1 周 | Phase 3 |
| **Phase 5** | 预审 | 对抗审查 + 引用/抄袭检查 + LaTeX 编译 | 终稿 v3 + adversarial-review-v2.md（逐条回应）+ 编译零警告 + checklist 全过 | 1 周 | Phase 4 |
| **Phase 6** | 提交 | arXiv 上传 | 提交成功 + endorsement 处理 + 摘要/元数据核对 | 0.5-1 周（含缓冲） | Phase 5 + D3 |

**关键路径与风险**：
1. D2 实现延期（缓解：2 周硬截止，超时自动降级方案 B）。
2. D3 endorsement 等待（缓解：Phase 5 前确认，W7 留缓冲）。
3. 竞品文献在写作期间更新（缓解：literature_review 在 Phase 2/3 各做一次增量核查）。

---

## 附录 A：证据索引（关键 file:line 一览）

| 论据 | 引用 |
|---|---|
| 证据纪律（README 不作能力证据） | `docs/research_innovation/visible-innovation-audit.md:4` |
| 3 大创新点 + 诚实声明 | `visible-innovation-audit.md:10-18` |
| 能力表（a-j 全部实现项） | `angelus_capability_map.md:5-40` |
| 组织恢复成熟度（完成态✓/运行中✗） | `visible-innovation-audit.md:86` |
| 运行中恢复实现路径（4 步 + 1-2 周） | `visible-innovation-audit.md:155-162` |
| 3 个 Demo 场景 | `visible-innovation-audit.md:112-121` |
| What-NOT-to-Market | `visible-innovation-audit.md:141-151` |
| 对抗审查裁决（A-F + Bottom line） | `adversarial_attack_report.md:7-99` |
| 竞品矩阵 Q1-Q5（含置信度） | `agent_frameworks_landscape.md:5-40` |
| Pattern 3 组织快照判定（无竞品） | `multiswarm_dynamics_landscape.md:39-47,82-88` |
| observe-only vs mutate 分类 + gap | `observability_controlplane_landscape_detailed.md:7-34,55-60` |
| 运行时语义（TaskBus/图/快照） | `angelus_swarm_dynamics.md:3-34` |
| 论文格式范本 | `docs/mnavrag-arxiv-draft.md:1-30,120-140,180-264` |

## 附录 B：Phase 0 验收核对表

- [ ] 8 节齐全：选题论点 / 投稿策略 / 结构草案 / 素材缺口 / 分工 / 质量流程 / 决策点 / 里程碑
- [ ] 中心论点 1 主 1 辅 + 反 claim 与回应策略已写明
- [ ] 每个决策点（D1-D4 + 可选 D5-D6）有默认建议
- [ ] 全部关键引用为 `文件:行` 格式且经 grep 核实
- [ ] 时间线含缓冲；里程碑含验收标准与依赖
