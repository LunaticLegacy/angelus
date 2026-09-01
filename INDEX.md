# Angelus — Refactor Phase 1 INDEX

本仓库是本地优先的 Agent 控制平面。第一阶段已确立唯一的后端
所有权链：`AngelusCore → SessionHandler → Session → execution / swarm / agents`。
`Session` 是 Agent、llmfetcher `AgentSwarm`、coordinator 角色及其执行边界的唯一拥有者；
`AngelusCore` 不再拥有全局 swarm/executor 注册表。

## Route Map

| Intent | Next index / leaf | Current authority |
|---|---|---|
| 应用装配、CLI、SIGINT | [`angelus/INDEX.md`](angelus/INDEX.md) | 新架构入口 |
| HTTP 路由、SPA 挂载 | [`angelus/api/INDEX.md`](angelus/api/INDEX.md) | 新架构 API 边界 |
| Session、执行、设置、持久化 | [`angelus/modules/INDEX.md`](angelus/modules/INDEX.md) | 领域和应用服务 |
| 浏览器工作台 | [`frontend/INDEX.md`](frontend/INDEX.md) | 正在迁移到 Session API |
| llmfetcher 运行时 | [`llmfetcher/INDEX.md`](llmfetcher/INDEX.md) | Git submodule |
| 控制平面回归测试 | [`tests/INDEX.md`](tests/INDEX.md) | Phase 1 验证 |
| 桌面壳 | [`src-tauri/INDEX.md`](src-tauri/INDEX.md) | Sidecar/桌面分发 |
| 构建脚本 | [`scripts/INDEX.md`](scripts/INDEX.md) | 构建与打包 |
| 历史设计资料 | [`docs/INDEX.md`](docs/INDEX.md) | 非运行时权威 |

## Runtime Ownership

```text
AngelusCore
├─ WorkspaceCatalog / ConversationStore / ConnectorStore / RunProfileStore
├─ SessionHandler
│  └─ Session(session_id)
│     ├─ coordinator role → concrete Agent after saved connector is usable
│     ├─ agents / AgentSwarm
│     └─ SessionExecutor → ExecutionAttempt → controller/journal/checkpoints
└─ Services (Session / Execution / Settings)
```

## Persistence Map

| Location | Owner | Contents |
|---|---|---|
| `.angelus-state/workspaces.json` | `WorkspaceCatalog` | Durable selectable Session identity and project binding |
| `.angelus-state/sessions/<id>/` | Session | Run profile, coordinator context, executions and checkpoints |
| `.angelus-state/settings/` | Settings stores | Connector metadata and global run profile |
| `.angelus-state/secrets/connectors/` | `ConnectorStore` | Write-only API-key documents |
| `workspace/` | Legacy bridge only | Imported/deletable historic transcripts; not new write target |

`.angelus-state/`, `workspace/`, virtual environments and build outputs are local state and must not be committed.

## Deliberate Phase-1 Boundaries

- `ExecutionService.start()` runs the Session-owned llmfetcher swarm graph;
  the coordinator remains the root result used for lifecycle outcome.
- The browser retains some historic modular files, but the mounted workbench is
  `frontend/static/app.js`; its transcript renderer and Session-console routes
  are the production authority.
- Conversation context, graph checkpoints, and the Session-console projection
  are durable; legacy `workspace/` transcript reading is migration-only.

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| — | — | `None` | `None` | 本索引范围不直接拥有可执行函数；沿 Route Map 进入下级索引。 |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| — | — | `None` | `object` | 本索引范围不直接声明类；沿 Route Map 进入下级索引。 |

<!-- END GENERATED SYMBOL MAP -->
