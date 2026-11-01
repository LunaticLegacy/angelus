# frontend/ — Workbench INDEX

The workbench is a static browser client served by `angelus/api/__init__.py`.
Its mounted entry is `templates/index.html`, which loads `static/slash.js` and
`static/app-loader.js`; the loader retries the composition root `static/app.js`
when a localhost module request fails. Domain requests live under
`static/runtime/`, coordination under `static/controllers/`, and DOM rendering
under `static/components/` and `static/ui/`.

A selected `session_id` is the identity for Session operations. Browser
`localStorage` is limited to UI selection, theme, and local Notes state; it is
not Session, Agent, or credential authority.

| Path | Responsibility |
|---|---|
| [`templates/INDEX.md`](templates/INDEX.md) | SPA HTML shell and dialog/control IDs. |
| [`static/INDEX.md`](static/INDEX.md) | Active runtime, controllers, components and styles. |

## Current Boundary

Session selection, message history, connectors, run profiles, Inspector
resources, MCP, plugins, and run streams cross the runtime API modules. The
composition root coordinates shared Session, connector, profile, tool, agent,
and locale resources; components do not call backend URLs directly.

The global External Agent Hub dialog uses `/api/external-agents` to configure
adapter definitions and inspect health, declared capabilities, remote session
summaries, and capability-gated readable context descriptors. A selected
external context can be previewed as a credential-redacted portable package;
unsupported adapters surface their domain error rather than an empty result.

The Hub can explicitly scan local known Agent processes and show ephemeral
candidate cards. Scanning neither attaches to nor persists a discovered
process; a separate user action creates any durable definition.
