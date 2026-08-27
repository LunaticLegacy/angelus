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

- `ExecutionService.start()` currently runs the required coordinator; it does
  not yet dispatch the Session's llmfetcher swarm graph.
- The browser has retained legacy inspector/MCP/plugin handlers. They are not
  backend capabilities until rebuilt Session projections replace them.
- New conversation writes and graph/context safe-point capture remain the next
  phase; current transcript reads use the legacy projection bridge.

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Semantics |
|---|---|---|
| [`angelus/core.py`](angelus/core.py) | `AngelusCore` lifecycle | Compose stores/services, rehydrate Sessions, and coordinate SIGINT shutdown. |
| [`angelus/api/__init__.py`](angelus/api/__init__.py) | `include_api_routes` | Mount the new API surface and SPA assets. |
| [`angelus/modules/`](angelus/modules/INDEX.md) | Domain/application services | Own Session lifecycle, attempts, settings and durable state. |

## Class Map

| Source | Class | Semantics |
|---|---|---|
| [`angelus/core.py`](angelus/core.py) | `AngelusCore` | Process composition root; not Session/swarm owner. |
| [`angelus/modules/session_module/`](angelus/modules/session_module/INDEX.md) | `Session` | Aggregate owner for one logical Agent session. |

<!-- END GENERATED SYMBOL MAP -->
