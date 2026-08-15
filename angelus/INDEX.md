# angelus/ — Main Package INDEX

Angelus is the local control plane layered on the pinned `llmfetcher` submodule.
It owns the browser API, durable session projections, connector credentials, and
run controls; model backends, the Agent loop, graph memory, tools, and Swarm
implementation are provided by `llmfetcher`.

## Route Map

| Entry | Type | Purpose |
|---|---|---|
| [`classes/`](classes/INDEX.md) | Package | Web request models and in-memory run/session control dataclasses |
| `webapp.py` | Module | FastAPI control plane: workspaces, sessions, encrypted connectors, runs/SSE, history, archive, graph, usage, and plans |
| `cli.py` | Module | Angelus CLI layer: local `web` and `session` commands plus delegated llmfetcher commands |
| `task_planning.py` | Module | Session-local JSON task-plan store used by the web API and Agent planning tools |
| `__init__.py` | Module | Public Angelus facade; re-exports llmfetcher Agent and Swarm primitives |
| `__main__.py` | Module | `python -m angelus` entry point |

## Durable State Ownership

`LLMFETCHER_STATE_DIR` selects the local state root; otherwise Angelus uses its
default local workspace directory.  All state below is local and is not a
source for browser-provided API keys.

| Scope | Records | Notes |
|---|---|---|
| Global state root | `sessions.json`, `connectors.json`, RSA keypair | Connector records are shared across sessions. API keys in `connectors.json` are RSA-OAEP-SHA256 ciphertext; the private key stays local with owner-only permissions. API responses expose only connector metadata and `has_api_key`. |
| One session directory | `conversation.json`, `events.ndjson`, `run-state.json` | Display transcript, append-only lifecycle ledger, and credential-free runtime-profile/status projection. The event ledger is the authoritative source for new history/usage reconstruction; `conversation.json` remains a display-safe compatibility projection. |
| One session directory | `contexts/<agent>.json` and related graph files | llmfetcher-managed active context, compaction archive, and graph-memory projections. These are rebuildable/Agent-facing state, distinct from the browser transcript. |
| One session directory | `task-plan.json`, `graph-view.json` | Durable task plan and Swarm execution-graph view. |

## Settings and Credential Boundaries

- **Connector settings** are named, global records: provider, model, API URL,
  and encrypted API key. `connector_id` resolves its key only in the server
  process; an API key is never returned to the browser.
- **Agent execution settings** arrive in `RunConfig`: system prompt,
  temperature, token/round/context limits, shell, and Swarm options. The
  browser keeps its per-session UI preferences; Angelus persists only a
  credential-free runtime-profile snapshot (including a system-prompt digest)
  beside each run.
- A direct, unsaved browser key is run-only. It is not written to session state
  or connector storage.

## Primary Control-Plane Flows

- **Run / stop / force-stop / steer** → `webapp.py`: a `BrowserSession`
  prevents concurrent runs. Normal stop is cooperative and takes effect at a
  completed model/tool boundary. Force-stop cancels the active provider
  transport, prevents retry/fallback, and kills registered Shell processes.
  Runs append durable events before notifying SSE clients; normal, stopped,
  and error terminals update `run-state.json`.
- **History and observability** → `webapp.py`: session messages, archive,
  graph, events, per-call token ledger, and Agent/Swarm views are reconstructed
  from durable session artifacts.
- **Agent construction** → `webapp.py._build_agent`: creates a session-owned
  llmfetcher Agent with persisted graph context, a zero-context semantic graph
  worker, task-planning tools, and optionally sandboxed shell tools.
- **Swarm execution** → `webapp.py._build_swarm` plus llmfetcher Swarm:
  Angelus persists its display view and relays lifecycle events; individual
  workers retain their own session-local context paths.
- **CLI** → `cli.py`: `web` starts the local FastAPI console; `session list`
  and `session create` manage browser-visible sessions. Core run/chat/backend/
  tool commands are delegated to llmfetcher.

## Intent Routing

- **HTTP endpoint, persistence, connectors, SSE, UI data** → `webapp.py`
- **Request and in-memory run models** → `classes/INDEX.md`
- **Task-plan persistence** → `task_planning.py`
- **Agent, context, graph memory, tools, or Swarm algorithm** → corresponding
  package in `llmfetcher/`, not `angelus/`
