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

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Semantics |
|---|---|---|
| `__init__.py` | module exports | Expose only Session and execution primitives required by package consumers. |

## Class Map

| Source | Class | Semantics |
|---|---|---|
| `session_module/session_handler.py` | `Session`, `SessionHandler` | Aggregate and process-local registry. |
| `execution_module/execution_attempt.py` | `ExecutionAttempt` | One controller/journal/checkpoint/worker lifecycle. |
| `application_module/*` | services | Transport-neutral use cases. |

<!-- END GENERATED SYMBOL MAP -->
