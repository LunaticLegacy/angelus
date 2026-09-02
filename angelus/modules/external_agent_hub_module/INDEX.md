# external_agent_hub_module/ — External Agent Hub INDEX

This module owns phase-one configuration and non-executing inspection of
external Agent runtimes. It stores no credentials: a definition can only name
an optional `ConnectorStore` reference. Protocol implementations are isolated
behind the adapter base and are not yet allowed to dispatch remote work.

| File | Responsibility |
|---|---|
| `models.py` | Dataclass contracts for definitions, health, capabilities, sessions, and ephemeral process candidates. |
| `discovery.py` | Bounded Linux procfs process scanner; discovery is read-only and never attaches to a process. |
| `store.py` | Atomic credential-free definition persistence. |
| `adapter.py` | Read-only protocol adapter contract and process-local registry. |
| `codex_app_server.py` | Constrained local-stdio Codex App Server handshake and thread inspection. |
| `adapters/claude_sdk.py` | Lazy, injectable Claude Agent SDK session-discovery adapter. |
| `adapters/read_only.py` | Shared typed HTTP/CLI/SDK facade boundary and session normalizer. |
| `adapters/coze.py` | Read-only Coze Bot and Workflow adapter. |
| `adapters/opencode.py` | Read-only OpenCode Server adapter. |
| `adapters/workbuddy.py` | Read-only WorkBuddy adapter. |
| `service.py` | Validation, CRUD, health, capability, session, and local process discovery use cases. |

## Phase-one Boundary

- The Hub can create, replace, list, delete, health-check, and inspect an
  external Agent definition.
- Missing protocol adapters produce `unsupported`; no fallback request is made.
- No remote run, context handoff, ToolRegistry projection, or connector-secret
  read occurs in this module yet. Phase two permits only bounded remote session
  discovery through an installed adapter.
- Coze, OpenCode, and WorkBuddy adapters receive an injected HTTP, CLI, or SDK
  facade. They only health-check and list bounded session summaries; they do
  not start, resume, import, steer, or cancel a remote run.
- Local process discovery is an explicitly invoked, ephemeral procfs scan. A
  candidate is never persisted or attached automatically; the browser must
  create a separate durable definition after user confirmation.
