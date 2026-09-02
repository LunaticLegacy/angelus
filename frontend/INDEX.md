# frontend/ — Workbench INDEX

The workbench is a static browser client served by `angelus/api/__init__.py`.
It must treat a selected `session_id` as the identity for all new Phase-1
operations. Browser localStorage is only UI selection/theme state, never
Session/Agent/credential authority.

| Path | Responsibility |
|---|---|
| [`templates/INDEX.md`](templates/INDEX.md) | SPA HTML shell and dialog/control IDs. |
| [`static/INDEX.md`](static/INDEX.md) | Runtime controller, styles and render components. |

## Current Boundary

Session selection, creation/deletion, message reads, connector settings and
run-profile writes target Phase-1 APIs. Inspector, MCP, plugin and graph UI
code still contains legacy requests and is intentionally not a reliable
capability surface until Session projections replace it.

The global External Agent Hub dialog uses `/api/external-agents` to configure
adapter definitions and inspect their health, declared capabilities and remote
session summaries. It intentionally does not offer context import or export
until the audited context-exchange API exists.

The Hub can explicitly scan local known Agent processes and show ephemeral
candidate cards. Scanning neither attaches to nor persists a discovered
process; a separate user action creates any durable definition.

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
