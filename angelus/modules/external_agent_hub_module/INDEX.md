# external_agent_hub_module/ — External Agent Hub INDEX

This module owns credential-free configuration, bounded inspection, and typed
historical-context exchange boundaries for external Agent runtimes. It stores
no credentials: a definition can only name an optional `ConnectorStore`
reference. Protocol implementations remain isolated behind the adapter base
and are never allowed to dispatch remote work as part of context exchange.

| File | Responsibility |
|---|---|
| `models.py` | Dataclass contracts for definitions, health, capabilities, sessions, process candidates, and portable context envelopes. |
| `context_codec.py` | Strict bounded decoding of a JSON context package into dataclasses. |
| `context_exchange.py` | Session-owned paged export and idle-only historical append import; redacts credential-like text and never executes imported tool calls. |
| `discovery.py` | Bounded Linux procfs process scanner; discovery is read-only and never attaches to a process. |
| `store.py` | Atomic credential-free definition persistence. |
| `adapter.py` | Read-only protocol adapter contract and process-local registry. |
| `codex_app_server.py` | Constrained local-stdio Codex App Server handshake and thread inspection. |
| `adapters/claude_sdk.py` | Lazy, injectable Claude Agent SDK session-discovery adapter. |
| `adapters/read_only.py` | Shared typed HTTP/CLI/SDK facade boundary and session normalizer. |
| `adapters/coze.py` | Read-only Coze Bot and Workflow adapter. |
| `adapters/opencode.py` | Read-only OpenCode Server adapter. |
| `adapters/workbuddy.py` | Read-only WorkBuddy adapter. |
| `service.py` | Validation, CRUD, health, capability, session/context inspection, external context writes, and local process discovery use cases. |

## Phase-one Boundary

- The Hub can create, replace, list, delete, health-check, and inspect an
  external Agent definition.
- Missing protocol adapters produce `unsupported`; no fallback request is made.
- Context exchange uses `ContextPackage` schema 1 and is bounded to 200
  messages per package. Session export has an older-page cursor and therefore
  does not load a durable transcript in full.
- Session imports are allowed only while idle and append historical `system`,
  `user`, and `assistant` records. Historical tool calls are never executed;
  unsupported `tool`-role records are reported as rejected.
- External reads/writes exist only when an adapter exposes an audited protocol.
  Unsupported adapters raise a domain failure; they never return fake context
  data or successful writes.
- Coze, OpenCode, and WorkBuddy adapters receive an injected HTTP, CLI, or SDK
  facade. They only health-check and list bounded session summaries; they do
  not start, resume, import, steer, or cancel a remote run.
- Local process discovery is an explicitly invoked, ephemeral procfs scan. A
  candidate is never persisted or attached automatically; the browser must
  create a separate durable definition after user confirmation.
