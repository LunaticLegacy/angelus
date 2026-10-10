# Angelus Agent Workbench — Frontend Redesign & Layout Specification

**Target:** `docs/redesign/frontend-redesign-v0.6.0.md`
**Scope:** Layout and visual design only. This document specifies a redesigned frontend surface for the Angelus Agent Workbench. It does **not** change, and must never change, any file under `angelus/` or `frontend/`. Everything new lives under `docs/redesign/`.
**Companion artifacts:** `docs/redesign/mockups/README.md`, `docs/redesign/mockups/visual-philosophy.md`, `docs/redesign/mockups/workbench-mockup.html`.

---

## 1. Research

### 1.1 Backend API inventory

This section records the HTTP surface the current frontend actually consumes, so the redesign can be wired to real endpoints rather than invented ones. Routes were read from `angelus/api/*.py`; the client-side URLs were read from `frontend/static/app.js` and its imported components.

#### 1.1.1 Router mounting (authoritative)

`angelus/api/__init__.py` exposes `include_api_routes(app, core)` and mounts exactly these routers, in this order:

`runs`, `sessions`, `providers`, `workspace_directory`, `settings`, `session_console`, `plugins`, `external_agent_hub`, `mcp`, `attachments`, `compact`.

It also serves `GET /` (uncached `frontend/templates/index.html`), `GET /favicon.ico` (`angelus-icon.svg`), and mounts `/static` from `frontend/static`. Startup does nothing beyond a comment; shutdown calls `core.shutdown()` to force-stop and persist live attempts.

Important: the module `angelus/api/external_agents.py` defines a router with a *second, different* family of `/api/external-agents/*` routes (providers, import, links, transfer, export), but `include_api_routes` never imports or includes it. Unless it is mounted elsewhere (it is not, under `angelus/`), those endpoints are **unmounted** in the running app. This is treated as a gap in §2, not a task for the redesign.

#### 1.1.2 Route inventory

Legend: **S** = session-scoped (a `session_id` path parameter). **M** = mounted. **U** = defined but unmounted.

**runs.py** (mounted)

| M | Method | Path | Purpose |
| --- | --- | --- | --- |
| M | POST | `/api/runs` | Create/start a run for a session. |
| M | GET | `/api/runs/{session_id}/status` | Poll run state; used as the SSE onerror fallback probe. |
| M | POST | `/api/runs/{session_id}/stop` | Graceful stop. |
| M | POST | `/api/runs/{session_id}/force-stop` | Force stop. |
| M | POST | `/api/runs/{session_id}/control` | Run control channel. |

**sessions.py** (mounted)

| M | Method | Path | Purpose |
| --- | --- | --- | --- |
| M | GET | `/api/sessions` | List sessions. |
| M | POST | `/api/sessions` | Create session (201). |
| M | DELETE | `/api/sessions/{session_id}` | Delete session. |
| M | GET | `/api/sessions/{session_id}/messages` | Paged transcript (before/agent/limit). |

**session_console.py** (mounted, prefix `/api/sessions/{session_id}`) — the core live surface

| M | Method | Path | Purpose |
| --- | --- | --- | --- |
| M | GET | `/agents` | Agent roster for the session. |
| M | GET | `/graph` | Context graph snapshot (restore on load). |
| M | GET | `/graph/events` | **SSE** graph-event stream (cursor param). |
| M | GET | `/workflow` | Workflow definition. |
| M | POST | `/graph/recover` | Recover graph state. |
| M | GET | `/graph/info` | Graph metadata. |
| M | POST | `/workflow/agents` | Add agent. |
| M | DELETE | `/workflow/agents/{name}` | Remove a named agent. |
| M | DELETE | `/workflow/agents` | Remove agent (bulk). |
| M | POST | `/workflow/connections` | Add connection. |
| M | DELETE | `/workflow/connections` | Remove connection. |
| M | POST | `/workflow/mapper` | Set mapper. |
| M | POST | `/workflow/router` | Set router. |
| M | GET | `/plan` | Task plan. |
| M | GET | `/events` | **Paged** trace events (limit 200). |
| M | GET | `/events/stream` | **SSE** lifecycle-event stream (cursor param). |
| M | GET | `/usage` | Token/usage totals per agent. |
| M | GET | `/agents/{agent}/context` | Agent context. |
| M | GET | `/agents/{agent}/context/export` | Export context package. |
| M | POST | `/agents/{agent}/context/import` | Import context package (JSON body). |
| M | GET | `/agents/{agent}/context-graph` | Per-agent context graph. |
| M | POST | `/agents/{agent}/context/request-preview` | Preview a context request. |
| M | GET | `/agents/{agent}/context/compaction-input` | Compaction input view. |
| M | GET | `/agents/{agent}/calls` | Tool/LLM call log. |

**compact.py** (mounted)

| M | Method | Path | Purpose |
| --- | --- | --- | --- |
| M | POST | `/api/sessions/{session_id}/compact` | Start compaction. |
| M | POST | `/api/sessions/{session_id}/compact/stop` | Stop compaction. |
| M | POST | `/api/sessions/{session_id}/compact/force-stop` | Force-stop compaction. |

**attachments.py** (mounted)

| M | Method | Path | Purpose |
| --- | --- | --- | --- |
| M | POST | `/api/sessions/{session_id}/attachments/images` | Upload an image. |
| M | GET | `/api/sessions/{session_id}/attachments/images/{attachment_id}` | Fetch an image. |

**mcp.py** (mounted)

| M | Method | Path | Purpose |
| --- | --- | --- | --- |
| M | GET | `/api/mcp/servers` | List MCP servers. |
| M | POST | `/api/mcp/servers` | Add server (201). |
| M | PUT | `/api/mcp/servers/{server_id}` | Update server. |
| M | DELETE | `/api/mcp/servers/{server_id}` | Delete server (204). |
| M | POST | `/api/mcp/servers/{server_id}/probe` | Probe server health. |
| M | GET | `/api/mcp/servers/{server_id}/capabilities` | Server capabilities. |
| M | GET | `/api/sessions/{session_id}/mcp-bindings` | Session MCP bindings. |
| M | PUT | `/api/sessions/{session_id}/mcp-bindings` | Set session MCP bindings. |
| M | POST | `/api/mcp/servers/{server_id}/oauth/connect` | Start OAuth. |
| M | GET | `/api/mcp/oauth/callback` | OAuth callback. |
| M | POST | `/api/mcp/servers/{server_id}/oauth/disconnect` | Disconnect OAuth. |
| M | POST | `/api/mcp/servers/{server_id}/oauth/refresh` | Refresh OAuth. |

**plugins.py** (mounted)

| M | Method | Path | Purpose |
| --- | --- | --- | --- |
| M | GET | `/api/plugins` | List plugins. |
| M | GET | `/api/plugins/status` | Plugin load status. |
| M | POST | `/api/plugins/rescan` | Rescan plugin directories. |
| M | POST | `/api/plugins/discovered/{name}/register` | Register a discovered package. |
| M | POST | `/api/plugins/{plugin_id}/load` | Load plugin. |
| M | POST | `/api/plugins/{plugin_id}/unload` | Unload plugin. |
| M | GET | `/api/plugins/{plugin_id}/settings` | Plugin settings. |
| M | PUT | `/api/plugins/{plugin_id}/settings` | Update plugin settings. |
| M | POST | `/api/plugins/{plugin_id}/panels/{panel_id}/invoke` | Invoke plugin UI panel. |
| M | GET | `/plugins/{name}/static/{asset:path}` | Serve plugin static asset (hidden from schema). |

**external_agent_hub.py** (mounted)

| M | Method | Path | Purpose |
| --- | --- | --- | --- |
| M | GET | `/api/external-agents` | List external agents. |
| M | POST | `/api/external-agents` | Register an external agent (201). |
| M | POST | `/api/external-agents/discover` | Discover external agents. |
| M | GET | `/api/external-agents/{agent_id}` | Fetch one agent. |
| M | PUT | `/api/external-agents/{agent_id}` | Update agent. |
| M | DELETE | `/api/external-agents/{agent_id}` | Delete agent (204). |
| M | POST | `/api/external-agents/{agent_id}/health` | Health probe. |
| M | GET | `/api/external-agents/{agent_id}/capabilities` | Agent capabilities. |
| M | GET | `/api/external-agents/{agent_id}/sessions` | Remote session summaries. |
| M | GET | `/api/external-agents/{agent_id}/contexts` | Context packages. |
| M | GET | `/api/external-agents/{agent_id}/contexts/{context_id}` | One context package. |
| M | POST | `/api/external-agents/{agent_id}/contexts/import` | Import context package. |

**settings.py** (mounted)

| M | Method | Path | Purpose |
| --- | --- | --- | --- |
| M | GET | `/api/tool-registry` | Tool catalog. |
| M | GET | `/api/version` | Runtime versions. |
| M | GET | `/api/connectors` | List connectors. |
| M | POST | `/api/connectors` | Add connector (201). |
| M | PUT | `/api/connectors/{connector_id}` | Update connector. |
| M | DELETE | `/api/connectors/{connector_id}` | Delete connector (204). |
| M | GET | `/api/settings/run-profile` | Global run profile. |
| M | PUT | `/api/settings/run-profile` | Set global run profile. |
| M | GET | `/api/sessions/{session_id}/run-profile` | Per-session run profile. |
| M | PUT | `/api/sessions/{session_id}/run-profile` | Set per-session run profile. |
| M | DELETE | `/api/sessions/{session_id}/run-profile` | Clear per-session run profile. |

**providers.py** (mounted)

| M | Method | Path | Purpose |
| --- | --- | --- | --- |
| M | GET | `/api/providers` | List model providers. |

**workspace_directory.py** (mounted)

| M | Method | Path | Purpose |
| --- | --- | --- | --- |
| M | POST | `/api/workspace-directory/pick` | Native directory picker. |



**external_agents.py** (defined but **UNMOUNTED**)

This module builds its own `APIRouter()` with no prefix and declares a second `/api/external-agents/*` family that partly overlaps the mounted hub. `angelus/api/__init__.py` never imports it and no other module mounts it, so every route below is unreachable in the running app. It is recorded so a later backend task can decide whether to mount or delete it; the redesign must not build UI against these paths.

| M | Method | Path | Purpose |
| --- | --- | --- | --- |
| U | GET | `/external-agents` | Legacy HTML shim (hidden from schema). |
| U | GET | `/api/external-agents/providers` | List external providers. |
| U | PUT | `/api/external-agents/providers/{provider_id}` | Update a provider. |
| U | POST | `/api/external-agents/providers/{provider_id}/probe` | Probe a provider. |
| U | POST | `/api/external-agents/providers/auto-detect` | Auto-detect providers. |
| U | GET | `/api/external-agents/providers/{provider_id}/sessions` | List remote sessions. |
| U | POST | `/api/external-agents/providers/{provider_id}/sessions/{external_session_id}/import` | Import a remote session (201). |
| U | GET | `/api/sessions/{session_id}/external-meta` | External metadata for a session. |
| U | GET | `/api/sessions/{session_id}/export` | Export a session. |
| U | POST | `/api/external-agents/import/preview` | Preview an import. |
| U | POST | `/api/external-agents/import` | Import (201). |
| U | POST | `/api/sessions/{session_id}/transfer/preview` | Preview a transfer. |
| U | POST | `/api/external-agents/links` | Create a link (201). |
| U | GET | `/api/external-agents/links` | List links. |
| U | POST | `/api/external-agents/links/{link_id}/lease` | Lease a link. |
| U | POST | `/api/external-agents/links/{link_id}/actions` | Apply a link action. |

#### 1.1.3 Client call map (frontend -> backend)

`frontend/static/api.js` is the thin network layer used by the live modules: `apiJson(url)`, `apiPost(url, body)`, `apiPut`, `apiPatch`, `apiDelete`. Each wraps `fetch`, parses JSON, and on a non-2xx response throws an `Error` built from `payload.detail` or the HTTP status line plus the request URL. There is no retry, no timeout and no `AbortController`; SSE is opened directly with `EventSource` in `app.js` (see 1.1.4).

`frontend/static/app.js` (1,142 lines) is the live composition root and the only module script `index.html` loads. It imports exactly `components/dom.js`, `components/chat-view.js`, `components/image-composer.js`, `components/trace-view.js`, `components/task-plan-view.js`, `components/external-agent-hub-view.js`, `plugins.js`, `runtime/backend-bridge.js`, `ui/shell.js` and `i18n.js`. It centralises session-scoped URLs in helpers: `sessionApi(p)` returns `/api/sessions/{sessionId}{p}`, alongside `messagesUrl()`, `graphUrl()`, `graphEventsUrl(cursor)`, `lifecycleEventsUrl(cursor)`, `traceUrl(cursor)` and `workflowUrl()`.

The reachable call map (live modules only):

| Caller | URL template | Matching backend route |
| --- | --- | --- |
| `app.js` | `/api/sessions` (GET/POST) | GET/POST `/api/sessions` |
| `app.js` | `/api/sessions/{id}` (DELETE) | DELETE `/sessions/{session_id}` |
| `app.js` | `/api/sessions/{id}/messages?agent&limit&before` | GET `/messages` |
| `app.js` | `/api/runs` (POST) | POST `/api/runs` |
| `app.js` | `/api/runs/{id}/control` (actions steer/stop/force_stop) | POST `/api/runs/{session_id}/control` |
| `app.js` | `/api/runs/{id}/status` (GET, SSE onerror fallback) | GET `/api/runs/{session_id}/status` |
| `app.js` | `/api/sessions/{id}/{agents,graph,plan,usage,workflow,mcp-bindings}` | `session_console` / `mcp` routes |
| `app.js` | `/api/sessions/{id}/agents/{agent}/{context,calls,context-graph,context/request-preview,context/compaction-input,context/export,context/import}` | agent-context routes |
| `app.js` | `/api/sessions/{id}/compact`, `/compact/stop`, `/compact/force-stop` | compact family |
| `app.js` | `/api/mcp/servers`, `/api/mcp/servers/{id}`, `/api/mcp/oauth/callback` | mcp family |
| `app.js` | `/api/plugins/status`, `/api/plugins/rescan`, `/api/plugins` | plugins family |
| `app.js` | `/api/connectors`, `/api/connectors/{id}` | settings family |
| `app.js` | `/api/providers` | providers family |
| `app.js` | `/api/tool-registry` | settings family |
| `app.js` | `/api/workspace-directory/pick` | POST `.../pick` |

**Legacy / dead call map (not reachable in the running app).** Several modules in `frontend/static/` are not loaded by any live entry point and still reference a removed `/api/workspaces/*` family. Because they are dead code, the contract is not broken at runtime; it is a cleanup item (see 2.2):

| Caller (dead module) | URL template | Backend |
| --- | --- | --- |
| `main.js` (dead) | `/api/workspaces/{ws}/runs/{sid}/status` | **no route** |
| `main.js` (dead) | `/api/workspaces/{ws}/runs/{sid}/stop` | **no route** |
| `main.js` (dead) | `/api/workspaces/{ws}/runs/{sid}/force-stop` | **no route** |
| `events.js` (dead) | `/api/workspaces/{ws}/runs/{runId}/events` (SSE) | **no route** |

Reachability was checked against the actual import graph. LIVE: `app.js`, `api.js`, `components/{chat-view,dom,external-agent-hub-view,image-composer,markdown-renderer,task-plan-view,trace-view}.js`, `i18n.js`, `plugins.js`, `runtime/backend-bridge.js`, `slash.js`, `ui/shell.js`, `vendor/marked/marked.esm.js`, `vendor/dompurify/purify.es.mjs`. DEAD: `main.js`, `events.js`, `chat.js`, `connectors.js`, `sessions.js`, `settings.js`, `state.js`, `utils.js`, `external-agents.js`, `slash.test.js`, `inspector/{graph,index,metrics,plan,trace}.js`.

#### 1.1.4 Streaming (SSE) endpoints

The backend exposes three session-scoped event surfaces under `session_console.py` (prefix `/api/sessions/{session_id}`):

- `GET /api/sessions/{session_id}/graph/events` - **SSE** graph mutations, `cursor` query parameter for resume-from-offset.
- `GET /api/sessions/{session_id}/events/stream` - **SSE** lifecycle stream, same `cursor` contract.
- `GET /api/sessions/{session_id}/events` - paged (non-streaming) trace read, `limit` defaults to 200; used for initial trace hydration and load-more.

The live client matches this exactly. `app.js` opens two long-lived `EventSource`s for the selected session:

- `connectRunGraphEvents()` -> `graphEventsUrl(sseCursor)` -> `/api/sessions/{id}/graph/events?cursor=`; the resume cursor is `event.sequence` falling back to `message.lastEventId`, and `onerror` probes `GET /api/runs/{id}/status` before deciding to reconnect or finish.
- `connectLifecycleEvents()` -> `lifecycleEventsUrl(lifecycleCursor)` -> `/api/sessions/{id}/events/stream?cursor=`; the resume cursor is `message.lastEventId`, and each frame is passed to `handleEvent()`.

Trace history is paged separately via `traceUrl(cursor)` -> `/api/sessions/{id}/events?limit=200[&cursor=]`, keyed by an opaque `next_cursor` with a numeric `durable_offset`. The lifecycle envelope consumed by `handleEvent` is a flat object whose `event` field is one of `lifecycle`, `result`, `error`, `stopped`, `done`; graph frames carry granular `type` values (for example `agent:control`, `agent:complete`, tool/task/plan events) with optional `agent`, `message`, `data` and a numeric `sequence`. The redesign must present these frames as one coherent timeline without inventing new server events.

### 1.2 Frontend UI/UX, streaming and component analysis

Everything below was read from `frontend/templates/index.html` and `frontend/static/**`; no file under `angelus/` or `frontend/` is modified by this document.

#### 1.2.1 Shell and DOM regions

The workbench is a single page served by `GET /` as an uncached shell. `index.html` sets `lang="zh-CN"`, a pre-paint inline script that restores `localStorage.llmfetcherTheme` (only `light` is special-cased) to avoid a theme flash, and loads one stylesheet `/static/app.css?v=desktop-agent-2`. The page is a fixed-area rig rather than a scrolling document:

- Left: `aside.sidebar` - brand, session search (`session-filter`), recent sessions (`recent-sessions`), a connector/model block (`connection-field`, `model-chip`, `provider-hint`), privacy note and a `side-footer` with settings and stop controls.
- Center: `main.main-panel` - `header.topbar` (status pill `status`, run duration `header-duration`, token counter `header-tokens`), `section#chat.chat` (the message transcript with `load-more-messages` and `scroll-to-bottom`), then the composer `form#composer` with `steer-hint` / `steer-status`, autogrowing `textarea#message`, model/provider selectors and send/stop/force-stop buttons.
- Right: `aside.activity` (aria-label "会话执行信息") - a four-tab inspector `nav.inspector-tabs` driving panels `inspector-plan`, `inspector-agents`, `inspector-trace`, `inspector-usage`.

Six modal `dialog` elements sit at the top of the body and are the only overlays: MCP approval (`mcp-approval-dialog`), new session, save connector, settings (a tabbed console with panels `connection`, `agent`, `permissions`, `mcp`, `plugins`, `future`), the context-inspection console (tabs `graph`, `prompt`, `compaction`, `calls`), and the external-agent hub.


#### 1.2.2 Module map (live vs dead)

The frontend is native ES modules (no bundler; `api/__init__.py` fixes `.js`/`.mjs` MIME types so the import graph loads). The live entry point is `app.js`: `index.html` loads exactly one module script, `<script type=module src=/static/app.js?v=i18n-1>`, plus a plain `<script src=/static/slash.js>`. Everything `app.js` imports transitively is reachable; everything else is dead code left behind by an earlier migration.

| Module | Lines | State | Responsibility |
| --- | --- | --- | --- |
| `app.js` | 1142 | **LIVE (root)** | Composition root: session picking, run control, streaming, plugins/MCP/settings console, inspector panels. |
| `api.js` | 48 | LIVE | Thin `fetch` JSON wrapper (get/post/put/patch/delete). |
| `components/dom.js` | 11 | LIVE | `$` / `escapeHtml` DOM helpers. |
| `components/chat-view.js` | 605 | LIVE | Message/bubble/markdown DOM builders. |
| `components/task-plan-view.js` | 25 | LIVE | Task-plan item renderer. |
| `components/trace-view.js` | 59 | LIVE | Trace-event DOM builder plus kind/time formatting. |
| `components/image-composer.js` | 85 | LIVE | Attachment staging and previews. |
| `components/external-agent-hub-view.js` | 305 | LIVE | External-agent hub view. |
| `components/markdown-renderer.js` | 133 | LIVE | Markdown and code rendering; imports vendored DOMPurify and marked. |
| `plugins.js` | 541 | LIVE | Plugin discovery, lifecycle, settings panels, static asset iframes. |
| `runtime/backend-bridge.js` | 32 | LIVE | `apiJson`/`apiPost`/`apiPut` bridge used by `app.js`. |
| `ui/shell.js` | 45 | LIVE | Shell-level UI helpers (element lookup). |
| `i18n.js` | 187 | LIVE | Locale dictionaries (`zh-CN` default, `en`). |
| `slash.js` | 91 | LIVE (plain script) | Slash-command parsing; loaded non-module. |
| `vendor/marked/marked.esm.js` | 2189 | LIVE (vendor) | Markdown parser. |
| `vendor/dompurify/purify.es.mjs` | 1346 | LIVE (vendor) | HTML sanitiser; **present on disk** (imported by `markdown-renderer.js`). |
| `main.js` | 346 | DEAD | Old composition root; only place referencing the removed `/api/workspaces/*` family. |
| `events.js` | 55 | DEAD | Old single `EventSource` against `/api/workspaces/{ws}/runs/{id}/events`. |
| `chat.js` | 214 | DEAD | Old `handleEvent` fan-out (superseded inside `app.js`). |
| `state.js` | 41 | DEAD | Old pub/sub store (`sessionId`, `workspaceId`, `connectorId`, ...). |
| `connectors.js` | 56 | DEAD | Old connectors adapter (`app.js` calls `/api/connectors` directly). |
| `sessions.js` | 61 | DEAD | Old sessions adapter. |
| `settings.js` | 122 | DEAD | Old run-profile/tool-registry settings adapter. |
| `utils.js` | 32 | DEAD | Old shared helpers. |
| `external-agents.js` | 54 | DEAD | Old external-agent adapter (view now lives in `components/`). |
| `slash.test.js` | 65 | DEAD | Test file, not loaded. |
| `inspector/{index,graph,plan,trace,metrics}.js` | 19/143/69/16/19 | DEAD | Old inspector panels; `app.js` renders these regions itself. |

Two consequences matter more than the individual files: (1) the repository carries a full shadow frontend (14 dead modules) that renders the same concepts as the live one, so any selector or id found only in a dead module must be ignored; (2) there is no `theme_light.html` in the current tree, so light mode is a single `localStorage.llmfetcherTheme` branch in `app.css` only.

#### 1.2.3 Streaming and data flow

The live loop is small and dual-channel:

1. The user submits `#composer`; the handler trims and clears the textarea and starts a run with `POST /api/runs`.
2. `app.js` then opens two concurrent streams for the session: `connectRunGraphEvents()` (graph/control) and `connectLifecycleEvents()` (lifecycle/trace), each with its own resume cursor.
3. Each `EventSource` keeps its own cursor: graph frames use `event.sequence` (fallback `message.lastEventId`), lifecycle frames use `message.lastEventId`. Frames from a session that is no longer selected are dropped via a captured `sourceSessionId` / `lifecycleSourceSessionId` guard.
4. `onerror` does not blindly finalise: a graph-stream error probes `GET /api/runs/{id}/status` and reconnects while the run is `running`/`stopping`/`force_stopping`, otherwise it finishes; a lifecycle error just clears the source so `EventSource` can auto-reconnect.
5. `handleEvent` fans lifecycle frames out by `event`:
   - `lifecycle` -> trace plus agent-card updates; `agent:complete` also emits metrics; `source=graph` or any `task:`/`plan:` type triggers a graph refresh; `agent:control` steer events surface as steering records.
   - `result` -> append assistant message (content plus reasoning plus server-rendered `*_html`), then refresh metrics/plan/graph and append a completion trace.
   - `error` -> trace and `statusClass=error`.
   - `stopped` -> trace.
   - `done` -> finish the run (disconnect plus idle status unless errored).
6. On session switch `app.js` persists settings, closes both streams, reloads sessions/connectors, then parallel-loads history (`GET /messages`), plan, graph and usage, hydrates the paged trace (`GET /events?limit=200`), and probes `GET /api/runs/{id}/status` to resume a live run. Run control (steer/stop/force_stop) goes to `POST /api/runs/{id}/control`.

Implication for the redesign: the transcript, the trace, the plan and the graph are four projections of one event log, but today they are refreshed by independent calls from a single 1,142-line controller with no shared timeline model. The redesign should treat the event log as the single source of truth (see 3.2 and 3.3).

#### 1.2.4 Visual system as built (the thing being replaced)

`frontend/static/app.css` is 906 lines with 459 selector blocks and 209 `:root`-prefixed rules - the signature of a stylesheet that has been re-skinned by appending, not edited. Four token layers stack in cascade order, so only the last one is actually visible in the default theme:

1. Legacy base `:root` (dark blue): `--bg:#080d17; --panel:#0d1421; --line:#1f2c42; --purple:#a995ff; --green:#a4f03d;`. A saturated sci-fi palette with a lime accent.
2. A second `:root` re-skin (green-tinted): `--bg:#101311; --panel:#171b18; --accent:#d8f36a;` plus an `Aptos/Segoe UI` font stack and a scanline body overlay (`background-size:80px 80px,100% 4px`). Another acid-lime accent, now on near-black green.
3. `:root[data-theme="light"]` - the light theme, reachable only via `localStorage.llmfetcherTheme`. It re-declares roughly 150 rules (every surface, chip, bubble, dialog and graph node), which is why theme parity is fragile.
4. "Workbench 2026" override block (final): `--bg:#090a0f; --panel:#0f1118; --panel2:#141720; --surface:#171a24; --surface-raised:#1c202c; --line:#262a37; --line2:#383e50; --text:#f4f5f8; --muted:#858b9b; --soft:#c7cad3; --purple:#9b8cff; --green:#54dc9b; --amber:#f2b84b; --red:#ff6b7a;` with `body{grid-template-columns:248px minmax(560px,1fr) 368px; font-size:13px}`.

So the docs must reason about a four-layer cascade where the effective theme is #4 (near-black + purple accent), the app is locked to `font-size:13px`, and the shell is a `248 / 560+ / 368` three-column grid. The 21 media queries argue over the same shell at 9 different widths (`1280, 1180, 1100, 1020, 900, 700, 650, 640`), including three separate one-off shell re-declarations (`260/520/350`, `240/420/315`, `246/580/386`), one of which collapses to a 72px rail. There is only a single `prefers-reduced-motion` block.

The recurring visual vocabulary is a dark instrument panel: rounded cards on `--surface`, 1px `--line` borders, subtle raises, small dot/state indicators, monospace numerics, and a purple accent. The redesign keeps the instrument-panel intent but replaces the palette, type and surface logic wholesale (3).

#### 1.2.5 Accessibility, i18n and current constraints

- **Language / i18n:** `index.html` is `lang="zh-CN"` with hard-coded Chinese copy in the template; `i18n.js` holds only two dictionaries (`zh-CN` default, `en`, 187 lines) and is used sparsely. Most labels are literal, so the redesign must keep selector/id contract and avoid depending on text.
- **Semantics present:** the shell already uses `aside`/`main`/`header`/`section`/`nav`, `aria-label` on the inspector and activity column, `role=tablist`/`tabpanel` on the settings and context dialogs, `aria-labelledby` on dialogs, and `aria-live=polite` on feedback lines. Dialogs are native `<dialog>` elements.
- **Gaps:** contrast is unverified against the four palettes; accent-lime on near-black (#101311 / #d8f36a) and purple are both risky; focus states are per-theme rather than token-driven; motion is not reduced-aware except one block; the composer relies on Enter/Shift+Enter with `isComposing` handled, but there is no global shortcut map.
- **Density:** `font-size:13px` is global, and the three-column shell assumes a wide desktop; the narrowest real breakpoint folds to `1fr` (single column) with the inspector below. There is no explicit mobile message-column design.
- **Rendering:** `marked.esm.js` (2,189 lines) is vendored and produces `content_html`, so the client trusts server-provided HTML for assistant messages - a security and theming consideration the redesign should note, not change.


### 1.3 Design-skill references and mockups

Five design skills were consulted and are preserved verbatim under `docs/redesign/references/`. They are the external craft standards the redesign is measured against; each is cited where it shaped a decision.

| Skill file | Lines | What it contributes |
| --- | --- | --- |
| `references/skill-frontend-design.md` | 71 | Anti-cliché aesthetic direction: distinct palette/type/layout, type scale after The Elements of Typographic Style, line lengths under 80ch, structure as information, and an explicit list of generated-page tells to avoid (all-caps labels, accenting one word, eyebrow labels, decorative numbering). |
| `references/skill-canvas-design.md` | 130 | Two-step method: write a VISUAL PHILOSOPHY (a movement) first, then express it - form, space, colour, composition. Drives `mockups/visual-philosophy.md`. |
| `references/skill-brand-guidelines.md` | 73 | A worked brand system as reference material: base dark `#141413`, light `#faf9f5`, mid `#b0aea5`, light-gray `#e8e6dc`; accents orange `#d97757`, blue `#6a9bcc`, green `#788c5d`; Poppins headings + Lora body. Cited as a system to learn from, and its orange is deliberately the accent we avoid. |
| `references/skill-theme-factory.md` | 59 | A 10-theme catalogue with hex palettes and font pairings; the model for shipping the redesign as a token-set that can be swapped rather than hard-coded. |
| `references/skill-web-artifacts-builder.md` | 74 | Single-file HTML bundling, and the anti-"AI slop" checklist: avoid excessive centered layouts, purple gradients, uniform rounded corners, and Inter. |

**Synthesis - what the skills collectively forbid.** Read together they name the same failure mode: near-black glass + one acid accent, centered hero layouts, purple gradients, uniform rounded cards with the same soft shadow, the Inter typeface, tracked all-caps eyebrow labels, and decorative numbered markers where content is not actually a sequence. The current app (1.2.4) violates several of these literally - a purple `#9b8cff` accent in the final layer, acid-lime in the two layers beneath it, and a purple-gradient body wash. The redesign is a direct response to that list.

**Mockups produced** (in `docs/redesign/mockups/`):

- `visual-philosophy.md` (20 lines) - the movement "The Signal Ledger": two traditions fused (the engineering instrument panel, read at a glance, plus the bound operating ledger, trusted per mark), blueprint-slate base with a brass-amber "human intent" accent, semantic-only state colour (teal live / green done / amber pending / rose error), a single Plex superfamily (Sans / Mono / Serif), ruled 4px grid with hairline rules instead of floating cards, and motion as a response only. This is the doc that answers the canvas-design method.
- `workbench-mockup.html` (234 lines) - one self-contained, dependency-free page rendering the full three-zone desktop workbench (`.wb > .rail | .stage | .bay`) with the redesign tokens applied inline, near-square corners, a live agent strip, transcript with a live marker, composer, and the four-tab inspector with Trace active. Verified self-contained: `<div>` tags balanced 41/41, one `<style>` block, closed with `</body></html>`, no external assets or scripts required.
- `README.md` (31 lines) - index and viewing instructions for the mockups.

**What each skill changed in the design:** frontend-design forced the move away from the purple/lime defaults and set the type discipline; canvas-design produced the written movement instead of jumping to layouts; brand-guidelines supplied a calibration point for warm-accent systems and marks `#d97757` terracotta as a color the workbench must *not* reuse; theme-factory shaped the token architecture in 3.2; web-artifacts-builder supplied the "AI slop" checklist that 3.1 answers. The mockups are the visual proof of the philosophy and are the build target referenced throughout 3.

## 2. Synthesis: capability to surface

This section joins 1.1 and 1.2: every backend capability the live client can exercise is mapped to the surface that should own it in the redesign, and the structural gaps found while joining the two are named.

### 2.1 Capability -> surface matrix

Legend: **Surface** = the redesigned region (see 3.4). **Status**: live = already wired in `app.js`; partial = wired but with a UX gap; dead = reachable only through dead modules; none = no client consumer.

| Capability (backend) | Live route(s) | Current consumer | Redesign surface | Status |
| --- | --- | --- | --- | --- |
| Session list / create / delete | `/api/sessions` | `app.js` | 3.4.1 Rail | live |
| Transcript and paging | `/messages` | `app.js` | 3.4.2 Stage | live |
| Start run | POST `/api/runs` | `app.js` | 3.4.3 Composer | live |
| Run control (steer/stop/force) | `/api/runs/{id}/control` | `app.js` | 3.4.3 Run bar | live |
| Run status probe | `/api/runs/{id}/status` | `app.js` (SSE fallback) | 3.4.2 live state chip | live |
| Graph snapshot / recover / info | `/graph`, `/graph/recover`, `/graph/info` | `app.js` | 3.4.4 Bay: Graph tab | live |
| Graph SSE | `/graph/events` | `app.js` | 3.4.2 live canvas | live |
| Lifecycle SSE | `/events/stream` | `app.js` | 3.4.2 ledger timeline | live |
| Paged trace | `/events` | `app.js` | 3.4.4 Bay: Trace tab | live |
| Plan / workflow | `/plan`, `/workflow`, `/workflow/*` | `app.js` | 3.4.4 Bay: Plan tab | live |
| Usage | `/usage` | `app.js` | 3.4.4 Bay: Usage tab | partial (totals only; no per-round cost) |
| Agent roster and state | `/agents` | `app.js` | 3.4.2 agent strip | live |
| Agent context inspection | `/agents/{agent}/context*`, `/calls`, `/context-graph` | `app.js` | Context console dialog | live |
| Compaction | `/compact[/stop|/force-stop]` | `app.js` | Context console dialog | partial (no progress surface) |
| Attachments | `/attachments/images` | `image-composer.js` | 3.4.3 Composer | live |
| MCP servers and bindings | `/api/mcp/*` | `app.js` | Settings console: MCP | live |
| Plugins | `/api/plugins/*` | `plugins.js` | Settings console: Plugins | live |
| Connectors | `/api/connectors` | `app.js` | Settings console: Connection | live |
| Providers | `/api/providers` | `app.js` | Composer model picker | live |
| Tool registry | `/api/tool-registry` | `app.js` | Settings console: Permissions | live |
| Run profiles | `/api/settings/run-profile`, `/api/sessions/{id}/run-profile` | `app.js` | Settings console: Agent | live |
| Directory picker | `/api/workspace-directory/pick` | `app.js` | Rail workspace control | live |
| External-agent hub | `/api/external-agents/*` (hub) | `components/external-agent-hub-view.js` | Bay: Agents tab | live |
| External-agent providers/import/links/transfer | `/api/external-agents/*` (second family) | none | **do not surface** | none (unmounted backend) |
| Workspace/run family | `/api/workspaces/*` | dead `main.js` / `events.js` only | **do not surface** | dead |

### 2.2 Gaps and coupling found while joining 1.1 and 1.2

1. **A whole shadow frontend is dead.** 14 modules (`main.js`, `events.js`, `chat.js`, `connectors.js`, `sessions.js`, `settings.js`, `state.js`, `utils.js`, `external-agents.js`, `slash.test.js`, `inspector/*`) are unreachable. They carry the only references to the non-existent `/api/workspaces/*` family, so the apparent broken contract is a cleanup item, not a live bug. The redesign must not inherit selectors, ids or URLs from them.
2. **Four CSS token layers, one visible.** `app.css` (906 lines, 459 blocks, 209 `:root` rules) stacks legacy blue, a green re-skin, the light theme and the final Workbench 2026 override; only the last is visible by default, and the light theme re-declares roughly 150 rules, so theme parity is fragile by construction.
3. **Two duplicated component layers.** The dead `inspector/*` plus `chat.js` render the same concepts (transcript, trace, plan, graph) as the live `components/*` with different markup. There is no single source of truth for a message or event row.
4. **No shared timeline model.** Transcript, trace, plan and graph refresh via independent calls; the same event log is projected four times and ordering or latency between projections is not reconciled.
5. **No global shortcut map.** The composer handles Enter/Shift+Enter and composition events, but there is no documented, discoverable shortcut set for run control, panel switching or navigation.
6. **Theme and density fragility.** 21 media queries argue over 9 widths (1280, 1180, 1100, 1020, 900, 700, 650, 640 plus reduced-motion); three re-declare the shell grid with different numbers (`260/520/350`, `240/420/315`, `246/580/386`) and one collapses to a 72px rail. A global `font-size:13px` and a wide three-column assumption leave no explicit mobile message-column design.
7. **Server-trusted HTML.** Assistant messages can arrive as `content_html` and are injected; `markdown-renderer.js` imports vendored DOMPurify, which is present. The redesign must keep the sanitiser in the render path and must not style untrusted HTML permissively.
8. **Unmounted backend.** `external_agents.py` defines a second `/api/external-agents/*` family (and a `GET /external-agents` FileResponse to `templates/external_agents.html`) that `include_api_routes` never mounts. No redesign surface may depend on it.
9. **Id drift between static shell and controller.** `app.js` queries some ids that `index.html` does not define (for example `execution-graph`), so the live controller already depends on markup it injects or on ids that moved. The redesign should publish one canonical id table (3.4) and keep it in sync.

## 3. Redesigned layout

### 3.1 Design philosophy: The Signal Ledger

The workbench fuses two traditions. The **engineering instrument panel** is read at a glance: fixed regions, persistent status, values that never move. The **bound operating ledger** is trusted mark by mark: entries accrue in time order, each carries a source and a state, and the book itself is the record. The redesign is a two-panel workbench: a stage that reads like a ledger, and a bay that reads like an instrument cluster. The full written movement lives in `mockups/visual-philosophy.md`; the renderable proof is `mockups/workbench-mockup.html`.

Five operating principles:

1. **One event log, four projections.** Transcript, trace, plan and graph are views over the same ordered events (1.2.3). The redesign gives them one shared sequence and one shared empty/loading/error vocabulary.
2. **Rules, not floating cards.** Region boundaries are 1px hairlines on a ruled 4px grid. Surfaces differ by line weight and one step of lightness, not by drop shadows or uniform rounded corners.
3. **Colour is state, never decoration.** Amber marks human intent; teal is live; green is done; amber is pending; rose is error. No gradient fills, no accent words.
4. **Density with rhythm.** 13px mono numerics, 15px body, tabular figures, and a vertical rhythm that lets a long run be scanned without decoration.
5. **Motion is a response.** Transitions are 90-140ms and exist only to confirm a state change; `prefers-reduced-motion` removes them.

Anti-slop commitments (from 1.3): no purple gradient, no acid-lime accent, no “glassmorphism”, no centered hero, no Inter, no tracked all-caps eyebrow labels, no decorative numbering, no uniform corner radius.

### 3.2 Token architecture

Replace the four stacked overrides (1.2.4) with a single three-layer cascade. Layer 1 holds raw values under a namespace; layer 2 assigns them to semantic roles; layer 3 maps roles to component parts. Themes switch by one attribute on `html`, never by re-declaring components.

| Layer | Examples | Rule |
| --- | --- | --- |
| 1 primitives | `--lg-slate-900`, `--lg-amber-500`, `--lg-teal-500` | Raw values only; never referenced by components directly. |
| 2 semantic | `--lg-bg`, `--lg-surface`, `--lg-raised`, `--lg-line`, `--lg-line-2`, `--lg-ink`, `--lg-muted`, `--lg-soft`, `--lg-accent`, `--lg-live`, `--lg-done`, `--lg-pending`, `--lg-error` | One role each; the only colours components may use. |
| 3 component | `--lg-rail-bg`, `--lg-stage-bg`, `--lg-bay-bg`, `--lg-row-line`, `--lg-chip-bg` | Aliases of layer 2 for a specific surface. |

Default theme `html[data-theme=ledger-dark]`: `--lg-bg:#0b0d10; --lg-surface:#12151a; --lg-raised:#171b21; --lg-line:#232a33; --lg-line-2:#333c48; --lg-ink:#e8ecf1; --lg-muted:#8a93a0; --lg-soft:#c2c9d2; --lg-accent:#d7a54a; --lg-live:#3fb6a8; --lg-done:#5fbf7f; --lg-pending:#d7a54a; --lg-error:#e0656f;`. Blueprint slate base with a brass-amber human-intent accent; the accent is deliberately not the `#d97757` terracotta that `skill-brand-guidelines.md` uses.

Type, spacing, radius and motion are tokens too, so density is one variable, not 21 media queries:

| Token group | Values |
| --- | --- |
| Families | `--lg-sans: IBM Plex Sans`, `--lg-mono: IBM Plex Mono`, `--lg-serif: IBM Plex Serif` (one superfamily). |
| Sizes | `--lg-fs-micro:12px`, `--lg-fs-body:13px`, `--lg-fs-lede:15px`, `--lg-fs-title:18px`, `--lg-fs-display:24px`. |
| Space | `--lg-s1:4px` through `--lg-s7:32px`, doubling from a 4px base. |
| Radius | `--lg-r:3px`, `--lg-r-sm:2px` (near-square; no pills except the live dot). |
| Motion | `--lg-t-fast:90ms`, `--lg-t:140ms`, `--lg-ease:cubic-bezier(.2,.6,.2,1)`. |
| Grid | `--lg-rail:236px`, `--lg-bay:344px`, `--lg-stage-min:520px`. |

Semantics of state colour are the contract: teal means a stream is connected and events are arriving, green means a terminal success that is acknowledged, amber means pending or awaiting human input, rose means failure. Nothing else may use those hues.

### 3.3 Shell grid and wireframe

The shell is a full-height three-column CSS grid with hairline dividers. It never scrolls as a page; each column is its own scroll context. The two fixed bars of the stage (run bar above, composer below) are docked so the ledger scrolls between them.

```
+----------+-----------------------------------------+----------------------+
|  RAIL    |  STAGE                                  |  BAY                 |
|  236px   |  minmax(520px, 1fr)                     |  344px               |
|          |                                         |                      |
|  brand   |  run bar: state | tokens | duration      |  tabs: Trace Plan    |
|  filter  |  -------------------------------------  |        Graph Usage   |
|  session |                                         |        Agents        |
|   ledger |  transcript (ledger rows)               |  ------------------  |
|          |    user intent   [amber rule]           |  projection body     |
|  agents  |    agent run     [live teal]            |  (paged / streamed)  |
|   strip  |    result        [done green mark]      |                      |
|          |    trace inline  [muted mono]           |  foot: cursor /      |
|  context |  -------------------------------------  |        load more     |
|   foot   |  composer: textarea | model | send      |                      |
+----------+-----------------------------------------+----------------------+
```

Grid rules:

- `body` (or a single `#app` wrapper) is `display:grid; grid-template-columns: var(--lg-rail) minmax(var(--lg-stage-min),1fr) var(--lg-bay); height:100dvh; overflow:hidden`.
- Every grid child gets `min-height:0; min-width:0` so internal scrollers actually shrink instead of growing the page.
- Column dividers are `border-left: 1px solid var(--lg-line)` on the stage and bay, not gap + background.
- The rail and bay carry their own `overflow-y:auto`; the stage splits into run bar (auto), transcript (`flex:1; overflow-y:auto`), composer (auto) in a column flex.
- Dialogs stay native `<dialog>` overlays (six exist today, 1.2.1) and are the only elements allowed above the grid.
- The live canvas (graph) is a Bay tab, not a fourth column, so adding capability never widens the shell.

### 3.4 Region specification

Each region keeps the ids the live controller already queries (or adds an alias) so the redesign can be applied as a stylesheet plus markup pass without breaking `app.js`. The anchors below are from `frontend/templates/index.html`; the id contract is summarised in 3.6.

**3.4.1 Rail (236px).** File-drawer navigation, not a settings menu.

| Part | Anchor / class | Contents and states |
| --- | --- | --- |
| Brand | `.rail-brand` | Wordmark plus run-count; no logo animation. |
| Session filter | `#session-filter` | Search input, `/` focuses; empty state shows a single line. |
| Session ledger | `#recent-sessions` | Rows: title, relative time, one state mark (teal live, amber pending, rose error). Active row uses a 2px amber left rule, not a filled pill. |
| New session | `#new-workspace` (kept id), `#new-session-dialog` | Opens the existing new-session dialog. |
| Workspace | `#workspace`, `#choose-session-directory` | Current directory, truncated from the left; opens the picker. |
| Agents strip | `#agent-row` | Compact agent chips with live state; selecting one filters the ledger. |
| Rail foot | `#open-settings`, `#theme-toggle`, `#language-toggle` | Settings, theme and locale as text buttons; no icon-only controls. |

**3.4.2 Stage (1400px and up: minmax(520px,1fr)).** The ledger proper.

| Part | Anchor / class | Contents and states |
| --- | --- | --- |
| Run bar | `#status`, `#header-tokens`, `#header-duration` | Persistent: state chip (idle teal-off, live teal, pending amber, error rose), token count, elapsed time in tabular mono. |
| Transcript | `#chat`, `#load-more-messages`, `#scroll-to-bottom` | Ordered ledger rows. Row grammar: intent (amber rule), run (teal pulse), tool/plan inline trace (muted mono, one line, expandable), result (green mark, markdown body), error (rose). |
| Live canvas edge | graph stream (`/graph/events`) | A 1px teal edge indicator when the graph stream is connected, decoupled from scroll position. |
| Steer feedback | `#steer-hint`, `#steer-status` | One-line under the composer; never a toast. |
| Composer | `#composer`, `#message`, `#model`, `#provider`, `#send`, `#stop`, `#force-stop`, `#attach-image`, `#image-previews` | See 3.4.3. |

**3.4.3 Composer and run bar.** The only two controls that mutate a live run, so both are always visible and always labelled.

- `#message` autogrows from 2 to 12 rows, mono for code, sans for prose, Enter sends, Shift+Enter newline, IME composition respected.
- `#model` and `#provider` are one line of plain text selects with the provider as a muted suffix, not chips.
- `#send` is the single amber commit affordance; while a run is live it becomes `#stop`, and `#force-stop` sits behind a confirm dialog only.
- Attachments render as thumbnails on a hairline strip above the textarea (`#image-previews`, `#image-feedback`); upload errors are inline.
- Shortcuts (new, global, documented in a `?` panel): `Enter` send, `Shift+Enter` newline, `Esc` stop-with-confirm, `Ctrl+K` session filter, `1-4` bay tabs when the bay has focus, `?` shortcut sheet. This replaces the current implicit map (2.2 item 5).

**3.4.4 Bay (344px).** One instrument cluster, five projections of the same log.

| Tab | Panel anchor | Projection | Empty / error / loading |
| --- | --- | --- | --- |
| Trace | `#inspector-trace`, `#trace`, `#load-more-trace`, `#refresh-trace` | Paged and streamed event ledger, newest at the bottom, one row per event with source and state mark. | Empty: one line; error: rose line with retry; loading: shimmer-free three-row skeleton. |
| Plan | `#inspector-plan`, `#task-plan`, `#plan-summary`, `#plan-agent`, `#refresh-plan` | Workflow tree; pending amber, running teal, done green, failed rose; per-agent filter via `#plan-agent`. | Same vocabulary, scoped to plan nodes. |
| Graph | `#inspector-agents`, `#context-graph-canvas`, `#graph-edit-toolbar`, `#refresh-graph` | Context graph; static snapshot by default, live mutations highlighted during a run. | Never a blank canvas: axes or a text-only fallback. |
| Usage | `#inspector-usage`, `#usage-total`, `#usage-agents`, `#refresh-usage` | Token totals per agent plus per-run figures in tabular mono. | Zero state is a single line, not an empty table. |
| Agents | `#inspector-agents-list` | Roster and per-agent state, mirrors the rail strip at higher detail. | Rose row on a failed agent. |

Tab switching is `role=tablist`/`tabpanel` with roving `tabindex`, arrow-key navigation and `aria-selected`; the panel keeps its scroll position per session.

### 3.5 Responsive behaviour and accessibility

Four breakpoints replace the nine competing widths and three shell re-declarations (2.2 item 6). The bay narrows before the rail collapses, and below 768px the shell becomes one column with the bay as a full-height sheet.

| Range | Rail | Stage | Bay |
| --- | --- | --- | --- |
| 1400px and up | 236px | minmax(520px,1fr) | 344px |
| 1024-1399px | 216px | minmax(480px,1fr) | 320px |
| 768-1023px | 56px icon rail | 1fr | overlay drawer, opened by a bay button |
| under 768px | top bar | 1fr | full-screen tab sheet |

Card-level responsiveness uses **container queries** on the transcript and bay panels, not new media queries, so a panel behaves the same in the bay and in a dialog.

Accessibility targets:

- **Contrast:** WCAG AA - 4.5:1 for body text and 3:1 for large text and non-text state marks, verified on both themes before merge; the accent amber is used for text only at the lede size and above.
- **Focus:** one visible ring token (`--lg-focus`) on every interactive element, never removed without replacement; focus order follows the grid rail -> stage -> bay.
- **Keyboard:** dialogs are native and trap focus; tabs rove with arrow keys; a documented `?` sheet lists shortcuts (3.4.3); no functionality is pointer-only.
- **Live regions:** `aria-live=polite` on `#status` and `#steer-status`; streaming panels set `aria-busy` while a stream is open; token ticks are throttled so they are not announced continuously.
- **Motion:** one `prefers-reduced-motion` rule neutralises all transitions and the live pulse.
- **Internationalisation:** no copy in CSS, no text-dependent selectors; `lang` follows the active locale; `zh-CN` remains the default; ids, not labels, are the test contract (1.2.5).
- **Structure:** the `aside` / `main` / `header` / `section` / `nav` semantics and `aria-label` regions from 1.2.5 are kept and extended to the new rail and bay.

### 3.6 Implementation notes and id contract

This document is design-only; nothing under `angelus/` or `frontend/` is modified by it. When it is implemented, the intended order is:

1. Add `frontend/static/ledger.css` containing the three token layers and the four-breakpoint shell, loaded after `app.css`.
2. Migrate the shell and stage markup to the region classes while preserving the ids below; delete the four override blocks in `app.css` once the new file owns them.
3. Rebuild the transcript row grammar and the five bay tabs against the existing render functions (`components/chat-view.js`, `components/trace-view.js`, `components/task-plan-view.js`) rather than writing new ones.
4. Apply the focus, live-region and shortcut work in 3.5.
5. Separately, delete the 14 dead modules and the unmounted backend family (2.2 items 1 and 8) - a cleanup task, not part of this redesign.

Ids the live controller queries that must survive the visual pass (non-exhaustive, drawn from `index.html` and `app.js`):

`session-filter`, `recent-sessions`, `new-workspace`, `workspace`, `choose-session-directory`, `agent-row`, `chat`, `load-more-messages`, `scroll-to-bottom`, `composer`, `message`, `model`, `provider`, `send`, `stop`, `force-stop`, `steer-hint`, `steer-status`, `status`, `header-tokens`, `header-duration`, `inspector-plan`, `inspector-trace`, `inspector-usage`, `inspector-agents`, `inspector-agents-list`, `trace`, `load-more-trace`, `refresh-trace`, `task-plan`, `plan-summary`, `plan-agent`, `refresh-plan`, `context-graph-canvas`, `graph-edit-toolbar`, `refresh-graph`, `usage-total`, `usage-agents`, `refresh-usage`, `open-settings`, `theme-toggle`, `language-toggle`, `attach-image`, `image-previews`, `image-feedback`.

Success measures for the redesign: one visible token layer instead of four, four breakpoints instead of nine widths, one row grammar shared by transcript and trace, one documented shortcut map, and contrast and focus verified on both themes. The mockup in `mockups/workbench-mockup.html` is the reference rendering of every region above.

---

End of specification.
