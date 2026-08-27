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
