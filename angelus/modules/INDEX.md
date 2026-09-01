# angelus/modules/ — Backend Domain INDEX

Each subdirectory has one ownership domain. Do not route around these modules
by storing mutable runtime state in an API adapter.

| Domain | Index | Responsibility |
|---|---|---|
| Session aggregate | [`session_module/INDEX.md`](session_module/INDEX.md) | Session registry, coordinator role, Agent/Swarm ownership. |
| Execution | [`execution_module/INDEX.md`](execution_module/INDEX.md) | Attempt lifecycle, journal, checkpoint, signal interruption evidence. |
| Application | [`application_module/INDEX.md`](application_module/INDEX.md) | Cross-domain Session, execution and settings use cases. |
| Settings | [`settings_module/INDEX.md`](settings_module/INDEX.md) | Atomic JSON and global/session future-run profiles. |
| Connector | [`connector_module/INDEX.md`](connector_module/INDEX.md) | Provider discovery and secret-separated connector persistence. |
| Workspace | [`workspace_module/INDEX.md`](workspace_module/INDEX.md) | Durable Session metadata catalog and legacy import marker. |
| Conversation | [`conversation_module/INDEX.md`](conversation_module/INDEX.md) | Legacy transcript read/delete bridge during migration. |
| Swarm adapter | [`swarm_module/INDEX.md`](swarm_module/INDEX.md) | Session-local execution boundary; no global swarm registry. |
| Plugins | [`plugin_module/INDEX.md`](plugin_module/INDEX.md) | Controlled global package discovery, typed settings, and ToolRegistry-backed loading. |
| Session console | [`console_module/INDEX.md`](console_module/INDEX.md) | Persisted task-plan/topology blueprints and Session projections. |
| Unified tools | [`tool_module/INDEX.md`](tool_module/INDEX.md) | Canonical Tool identities, authorization policy and future runtime registry. |

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
