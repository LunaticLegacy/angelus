# Session 控制台后端设计

> 目标：保留 Workbench 右侧的任务计划、Agents/执行图、Trace、用量及 Agent 上下文查看能力，但所有状态均以新 `Session` aggregate 为唯一所有者；不恢复旧 `/api/workspaces/{workspace_id}/runs/{run_id}` 模型。

```mermaid
flowchart LR
  UI["Inspector 前端"] --> API["Session Console API\n/api/sessions/{session_id}/…"]
  API --> SERVICE["SessionConsoleService\n读取/修改 Session-owned projections"]
  SERVICE --> SESSION["Session\nagents · swarm · execution"]
  SERVICE --> PLAN["SessionConsoleStore\nplans.json：任务计划投影"]
  SERVICE --> ATTEMPT["ExecutionAttempt\njournal + checkpoint"]
  SESSION --> SWARM["llmfetcher.AgentSwarm\n真实 graph topology、状态、TaskBus"]
  ATTEMPT --> JOURNAL["execution.events.ndjson\n持久 Trace 事实"]
  ATTEMPT --> CHECKPOINT["graph/context checkpoint\n可恢复上下文证据"]
```

## API 契约

```mermaid
flowchart TB
  A["GET /agents\nAgent 列表与安全的上下文统计"]
  B["GET /graph · /graph/info\nAgentSwarm.view_snapshot 的 UI 投影"]
  C["POST/DELETE /graph/agents\nPOST/DELETE /graph/connections\nPOST /graph/mapper · /router\n受 Session 执行状态保护的真实图编辑"]
  D["GET /plan?agent=…\n持久任务计划投影"]
  E["GET /events?cursor&limit\n将 ExecutionJournal 规范化成 Inspector Trace 页"]
  F["GET /usage\n从 AgentSwarm/Agent usage 汇总五维 token"]
  G["GET /agents/{agent}/context*\n读取已保存线性上下文、图与压缩输入；无 checkpoint 时返回空投影"]
  H["GET /api/runs/{session}/events\n同一规范事件的 SSE 回放/跟随，不再需要 run_id"]
```

## 不变量

- 图编辑在运行中仅可使用 `AgentSwarm` 明确支持的动态变更；初版 API 会拒绝会改变已完成节点语义的静态编辑。
- 每次执行的 Trace 由 `ExecutionAttempt.journal` 持久化；Graph/Agent 生命周期事件写入同一 journal，再由控制台投影为 UI 事件。
- Agent 及其图的真实来源是 `Session.swarm`；`SessionConsoleStore` 仅保存计划等不能从运行时图推导的控制台投影。
- API 不返回 API key、LLM endpoint、系统提示词或工具配置。

