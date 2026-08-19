# Semantic map

## `frontend.static` Workbench component boundary

`frontend/templates/index.html` loads `frontend/static/app.js` as a browser ES
module. `app.js` remains the Workbench composition root: it owns mutable
session/run state, REST and SSE calls, and invokes the component views below.
It is called by the template and calls `createChatView()`, `createTraceView()`,
and `renderTaskPlanItem()`; it has no class hierarchy. The components do not
make network calls or own durable application state.

### `frontend.static.app.agentStateView(agentId, agents)`

Projects the newest lifecycle evidence, then the persisted graph
`node_states`, into the shared status shown by the selector, topology, and
usage cards. `agentId` identifies one Agent and `agents` is the visible Agent
list used to calculate the aggregate `all` state. A session-wide active run
never changes an Agent's state by itself: an Agent without evidence returns
`idle` with the message “尚无执行事件”. When the persisted run terminal is
`completed`, the aggregate `all` state is completed even if an individual
worker remains failed; the worker's own state is unchanged. It is called by
all three Agent-status renderers and has no I/O beyond reading browser-local
acknowledgements.

### `frontend.static.components.dom.$(id)` / `escapeHtml(text)`

`$()` returns the static-template element identified by `id`; callers must
provide an existing Workbench ID. `escapeHtml()` converts arbitrary text to
HTML-safe text using a detached DOM node. Both are called by active components
and have no persistent side effects.

### `frontend.static.components.chat-view.createChatView({ getAgentLabel })`

Creates the transcript component used by `app.js`. `getAgentLabel` is a
controller callback that supplies the currently selected Agent for live
assistant messages. Its returned `append(message, agentName)`,
`appendError(title, message)`, and `render(messages, assistantLabel)` methods
mutate only `#chat`; the component binds copy-result buttons and may write to
the browser clipboard. It calls DOM helpers and is called only by the active
composition root.

### `frontend.static.components.trace-view.createTraceView()`

Creates the expandable Trace component used by `app.js`. Its returned
`append()` and `appendEvent()` methods classify and render event records into
`#trace`; its internal toggle handlers mutate only the card's expanded state.
It calls `escapeHtml()` and is called by the active composition root.

### `frontend.static.components.task-plan-view.renderTaskPlanItem(task, depth)`

Recursively converts one API task record and its `subtasks` into escaped
inspector HTML. `depth` is a CSS-only nesting level and is incremented for
descendants. It makes no I/O and is called by `app.js` when refreshing the
task-plan endpoint.

## `angelus` runtime boundary

Angelus owns the local control plane while importing provider backends, core
tool contracts, event types, and context handlers from the pinned
`llmfetcher` submodule. `angelus.webapp.app` serves top-level `frontend/` and
persists its state under top-level `workspace/`; `angelus.cli.main()` exposes
the `angelus web` and session-management commands. `angelus.agent.Agent`
extends the base Agent behavior with durable safe-stop persistence, and is the
Agent class consumed by the Angelus Swarm and TLB RAG adapter.

## Test and CI contract

`pyproject.toml` exposes the `test` optional dependency group, currently
including `pytest>=8`. The GitHub Actions `test` job installs Angelus with
`-e '.[test]'` after installing the local `llmfetcher` submodule, then invokes
`python -m pytest tests -v`. This keeps test-only dependencies out of the
runtime package while ensuring both pytest-style functions and `unittest`
test cases are collected in CI.

## `angelus.session_memory.SessionMemoryStore`

Owns immutable, generation-numbered session manifests, registered artifact
metadata, and validated handoff files under the webapp state root. It has no
base class or known subclasses. `webapp._session_memory_store()` constructs it;
session-memory tools call `snapshot()`, `get_manifest()`,
`register_artifact()`, and `create_handoff()`.

### `SessionMemoryStore._collect_evidence(session_id, artifacts)` / `snapshot(session_id)`

`snapshot()` carries registered artifact metadata from the latest manifest into
the next immutable generation and passes it to `_collect_evidence()`. Along
with conversation, context, graph, event, and prior-handoff records,
`_collect_evidence()` emits an `artifact` evidence record for every registered
artifact. The record contains metadata only, never attachment bytes, so a
session containing only an uploaded artifact can create a handoff whose
evidence is validated against that snapshot.

### `angelus.rag_module_tlb.create_read_file_tool(root)`

Creates the Angelus TLB worker's private file-reading tool. Its handler calls
`Path.resolve()` and then `relative_to(root.resolve())`, so a sibling path
sharing the root's textual prefix raises `PermissionError` rather than escaping
the knowledge-tree sandbox. It is called by `angelus.rag_module_tlb.core`.

## `angelus.swarm_module.execution_graph.ExecutionGraph`

Owns a dependency DAG of `Agent` nodes, routing-only nodes, callbacks and a
`TaskBus`. It is called by `AgentSwarm` and application code; it calls Agent
`run()`, `TaskBus` lifecycle APIs, and registered event hooks. It has no base
class or known subclasses.

### `ExecutionGraph.to_snapshot(agent_serializer, callback_serializer)`

Builds a JSON-compatible snapshot of a quiescent graph. It serializes topology,
Agent specifications, callback IDs, router scopes, TaskBus state and dynamic
task indexes while holding the topology lock. Calls the supplied serializers or
the default tool-free Agent serializer, then `TaskBus.to_snapshot()`. It raises
`GraphPersistenceError` when executable application objects cannot be safely
identified. Called by `save()` and applications needing an external store.

### `ExecutionGraph.save(path, agent_serializer, callback_serializer)`

Calls `to_snapshot()`, creates the destination parent and atomically replaces
the JSON destination through a sibling temporary file. It is called by
application/session persistence code and returns the written `Path`.

### `ExecutionGraph.load(path, agent_resolver, callback_resolver)`

Reads a snapshot into a new graph, rebuilds nodes and edges, resolves callback
IDs, restores router scopes and calls `TaskBus.from_snapshot()`. It is called
by recovery/session loading code. It raises `GraphPersistenceError` for invalid
or unresolved data; it does not resume running threads.

### `ExecutionGraph._default_agent_serializer` / `_default_agent_resolver`

Persist and recreate only standard tool-free `Agent` instances using
`LLMBackendConfig` and `LLMFetcher`. Tool handlers and custom context handlers
must use application-owned serializer/resolver pairs.

### `ExecutionGraph.view_snapshot()` / `AgentSwarm.view_snapshot()`

Produce a JSON-safe live topology view: graph node identities and kinds,
typed dependency edges, concurrency limit, TaskBus assignment mapping, precise
task terminals and per-node UI states.
Unlike the recoverable graph snapshot APIs, this intentionally excludes Agent
objects, prompts, credentials and tools and is safe while the scheduler is
running. `AgentSwarm` exposes the underlying graph method for session UIs.

### `ExecutionGraph.finalize_tasks()` / `AgentSwarm.finalize_tasks()`

Call `TaskBus.finalize_unfinished()` after any scheduler terminal. Claimed work
becomes `interrupted`, never-started work becomes `cancelled`, and existing
completed/failed reports remain unchanged. The graph emits `task:finalized`
events for each transition. `AgentSwarm.run()` guarantees the call in a
`finally` block; `webapp.start_run()` repeats it idempotently before persisting
the last graph view and run terminal.

### `ExecutionGraph._record_node_state(agent_name, event_type, message, data)`

Projects Agent and task lifecycle events into the graph's UI-safe
`node_states` cache. `_emit()` calls it before notifying hooks, so the graph
snapshot written by the web hook contains the same state as the event that
triggered the write.

### `ExecutionGraph._attach_agent_events(agent)`

Registers a forwarding hook for every normally or dynamically registered
Agent. The graph therefore emits model lifecycle and tool request/result
events from coordinator and worker Agents to the same graph subscribers that
receive scheduling events. Called by `add_agent()`, `dispatch_task()` and
`dynamic_add_agent()`; the web session runtime persists those events.

## `angelus.swarm_module.task_bus.TaskBus`

Thread-safe mailbox for immutable task assignments and reports. It has no base
class or subclasses. `ExecutionGraph` owns and calls it.

### `TaskBus.to_snapshot()` / `TaskBus.from_snapshot(snapshot)`

Round-trip assignments, states, reports and inbox ordering. The restore method
rejects malformed data and `running` task states because an active worker has
no safe process-restart continuation.

### `TaskBus.set_terminal_state()` / `finalize_unfinished()`

Close one or all unfinished assignments without fabricating structured task
reports. Legal terminals are `completed`, `failed`, `interrupted` and
`cancelled`; terminal states are immutable. `submit_report()` maps recognized
success labels to `completed` and every other report outcome to `failed`.
Legacy `reported` snapshots are normalized from their saved `TaskReport`.

## `angelus.webapp` connector store

### `BrowserRunControl.force_stop()` / `ActiveRun.force_stop()` / `webapp.force_stop_run()`

The normal `stop_run()` path sets only the cooperative stop flag and is
observed after a completed model-and-tool boundary.  The force-stop endpoint
calls `ActiveRun.force_stop()`, which sets the additional `force_stopped`
event and kills registered Shell process groups.  `Agent.run()` observes that
event while its model call is pending, calls
`LLMFetcher.abort_active_requests()` to close provider client transports, and
raises `AgentRunStopped` without persisting an incomplete model response.
`BrowserRunControl` is the browser implementation; `ActiveRun` owns the
process registry; the endpoint is called by the Workbench's force-stop button.

### `LLMFetcher.abort_active_requests()` / `LLMBackendHandler.abort_active_request()`

`LLMFetcher.abort_active_requests()` calls each registered handler's terminal
transport-abort hook and returns the number of handlers asked to close.
`LLMBackendHandler.abort_active_request()` closes an SDK client when it
exposes `close()` and otherwise returns `False`; failures are isolated per
handler.  `LLMRequestCancelled` is raised from the fetch and streaming loops
whenever the terminal cancellation latch is set, including after a close
produces a timeout-like provider error.  This prevents retries and backend
fallback after force-stop; ordinary timeout retries and fallback remain
unchanged.  The API is called exclusively by an Agent force-stop and leaves no
closed handler for reuse because that Agent run is terminal.

### `RunConfig.max_retries` / `LLMFetcher._sleep_before_retry()`

The Agent execution setting `max_retries` is session-local browser state and
means the number of *additional* attempts following a timeout; it defaults to
three and is validated from zero through ten. `webapp._build_agent()` passes it
to the session's `LLMBackendConfig`, and the credential-free runtime profile
records it for later diagnosis. `LLMFetcher` therefore performs at most one
initial request plus `max_retries` timeout retries, waiting 1, 2, 4, then at
most 8 seconds between attempts. The wait observes terminal force-stop, which
cancels instead of issuing another request. Non-timeout failures remain
fallback-eligible in multi-backend callers; each backend appears only once in
the fallback order, so the primary never receives a duplicate retry budget.

### `webapp._default_state_root(project_root)` / `STATE_ROOT`

Resolves the browser Workbench state location before module startup creates it.
An explicit `LLMFETCHER_STATE_DIR` takes priority. Without that override, a
standalone LLMFetcher checkout uses `project_root/workspace`; when its parent
superproject registers the exact project directory as a `llmfetcher`
submodule, it instead uses the parent `workspace/`. This keeps Angelus session
history, connectors and traces visible after package installation moves from
the superproject root into the submodule. The helper only reads `.gitmodules`;
it is called by module-level `STATE_ROOT` initialization and has no subclasses.

The local web console owns a JSON connector registry at
`workspace/connectors.json`. The registry is separate from conversation
context and can contain API keys, so writes attempt filesystem mode 0600.
`LLMFETCHER_STATE_DIR` overrides the `workspace` directory under the project
root; this keeps runtime state out of the Python package directory.

### `webapp.RunConfig.max_context_threshold` / `_build_agent()`

`RunConfig.max_context_threshold` is the browser-configurable character count
at which `ContextHandlerLinear` compacts older history; it defaults to 262144
and is validated from 1024 through 16777216. `_build_agent()` passes it to
every browser-created coordinator Agent. The value is not a model-provider
context-window claim. `frontend/templates/index.html` exposes the control as
“上下文压缩阈值”, and `frontend/static/app.js.config()` persists and sends it
with each run and connector payload. `_build_swarm()` forwards the same value
to `create_swarm_tools()`, so both direct dynamic Agents and task-dispatched
workers receive the coordinator's compaction setting.

### `llmfetcher.context_handlers.linear.ContextHandlerLinear.save()` / `load()` / `clear_context()`

`save(path)` serializes the compaction threshold, current round counter,
compacted abstract, and retained messages. `Agent._save_context()` calls it at
completed execution boundaries. `load(path)` is called by `Agent.run()` before
the new user message is added; it replaces in-memory history and restores the
round counter as the maximum of the saved counter, retained message timelines,
and compacted `source_timeline` values. Deriving that maximum keeps context
files written before the explicit `round` field backward compatible and
prevents timeline reuse after restart. Invalid persistence data clears the
partially loaded state and returns `False`. `clear_context()` clears retained
and compacted history and resets the counter so the next message starts at
timeline one. `RetrievedContextHandler` delegates all three operations to its
contained linear handler; both classes implement the `ContextHandler`
interface and have no known subclasses in this repository.

### `llmfetcher.tools.spawn_tools.create_swarm_tools()`

Builds runtime swarm-management tools from a coordinator, shared worker tool
pool, and per-worker execution defaults. Its
`worker_max_context_threshold` parameter defaults to 262144 characters and is
passed to the `Agent` instances created by both `dynamic_add_agent` and
`dispatch_subagent`; values below 1024 raise `ValueError`. It is called by
`webapp._build_swarm()`.

## Repository layout and session persistence

Angelus runtime source lives under `angelus/`, imports model primitives from
the pinned `llmfetcher/` submodule, and serves independently owned browser
assets from `frontend/` through `FRONTEND_ROOT`. Runtime data has one root,
`workspace/`: each user-visible session has one independent
directory (`workspace/default/`, `workspace/test1/`, and so on). The frontend
uses `/api/sessions` and session-scoped history/plan/graph endpoints; legacy
workspace endpoints remain backend compatibility aliases only.

### `webapp.migrate_legacy_state()` / `conversation.json`

On first startup after the layout change, `migrate_legacy_state()` copies every
old `.llmfetcher` workspace, global session, connector and artifact into the
new layout, selects the newest conflicting context, reconstructs event-only
transcripts, then moves the old tree into `workspace/migration-backup-*`.
Every subsequent user turn and completed assistant result is written to the
session's `conversation.json`. `_read_session_history()` uses that file as its
authority, which makes browser refresh independent of Agent-context placement.

### `_read_connectors()` / `_write_connectors(connectors)`

Read and atomically replace the complete connector collection. `_write_connectors`
serializes JSON, attempts restrictive permissions, then replaces a sibling
temporary file. Called by connector CRUD handlers.

### `list_connectors()` / `create_connector(request)` / `update_connector(connector_id, request)` / `delete_connector(connector_id)`

The REST API used by `web/static/app.js` to list, create, replace and delete
named Provider/model/API-key settings. Creation assigns a UUID; update retains
the ID; deletion removes the stored credential together with its record. The
frontend uses document-native name dialogs for new connectors and shows a
temporary success/failure label on the save control, so a global connector
save is visible even when the Trace inspector is not selected. The connection
control keeps that label on one line with a fixed minimum width, preventing
the compact sidebar from splitting `保存` or `已保存` into separate rows.

### `webapp.render_markdown(text)`

Renders final Agent content for the SSE `result` event through a shared
`MarkdownIt` instance with table support. Raw HTML and automatic linkification are disabled; the
frontend inserts only these server-rendered HTML fields into `.markdown`
message bubbles, while user messages and trace data remain escaped text.

## `frontend/static/app.css` activity panel

The `.activity` sidebar is a fixed-height session inspector with Plan, Agents,
Trace, and Usage tabs. Exactly one `.inspector-panel` is visible at a time;
each panel owns its own scrolling content. `frontend/static/app.js` keeps the
selected tab in local storage, reloads durable Trace pages on demand, and
renders session-wide and per-Agent token totals from the usage endpoint.

### `frontend/static/app.js.loadWorkspaces()` / `.recent-sessions`

Loads the complete session registry into both the native selector and the
sidebar quick list. The quick list owns a bounded six-row scroll area, so a
large registry cannot push connection and Agent settings below the viewport;
the selected session is scrolled into view after each rebuild.

### `frontend/static/app.js.switchSession()` / settings listeners

`switchSession()` calls `persistSettings()` before changing the selected
session, then calls `restoreSettings()` after the new session and connector
state have loaded. Connector changes use the same persistence helper. Settings
dialog listeners target only controls defined in `frontend/templates/index.html`;
there are no compatibility calls to removed `persistAgentSettings`,
`restoreAgentSettings`, `persistConnection`, or `openSettingsDialog` helpers.
`tests/test_workbench_assets.py` checks both the direct listener IDs and the
current helper names so a script/template drift fails before browser startup.

### `frontend/static/app.js.showSettingsSection(section)`

The settings dialog uses a persistent left navigation rather than a select
control. `showSettingsSection()` receives one category key from
`data-settings-section`, shows the matching `data-settings-panel`, and updates
each navigation button's `active` class and `aria-selected` state. It is called
by `openSettings()` and the category-button click handlers; it does not mutate
connector records or per-session Agent settings.

### `frontend/static/app.js.renderMemorySessionPicker()` / `selectedMemorySessions()`

The Agent settings pane labels memory authorization as current-session-local
and offers a searchable multi-select of other sessions. The selected IDs are
stored in the hidden `session-memory-sessions` field, persisted by
`persistSettings()`, and restored with the rest of the current session's Agent
settings. `config()` sends the same selected IDs to all four explicit
SessionMemory search/read and artifact search/open allowlists. The server adds
the current session independently, so it is not selectable in the picker.

## `llmfetcher.task_planning.TaskPlanStore`

Owns one session-local task-plan JSON file. It has no base class or subclasses.
`webapp._plan_store()` and Agent planning tools construct it; its methods
validate nested task records, atomically write complete plans, and update a
single task's status recursively.

The store serializes each instance's read-modify-write status transition with
an `RLock` and uses a unique sibling temporary file for each replacement, so
simultaneous worker tool calls cannot replace one another's temporary plan.

### `TaskPlanStore.replace(goal, summary, tasks)` / `update_status(task_id, status)`

Replace a complete nested plan or change one status respectively. Both persist
the complete plan and raise `ValueError` for invalid tasks or status values.
They are called by the planning Tool handlers and the session plan REST API.

### `create_task_planning_tools(store)`

Builds `set_task_plan` and `update_task_status` Tools for an `Agent`. The tools
call `TaskPlanStore` and return the persisted plan to the model. `webapp` adds
them to every browser-created Agent and its JavaScript renders the resulting
task tree as interactive task blocks.

### `webapp.get_session_history()` / `_read_session_history()`

Read the session context JSON written by `Agent.run()` and expose only
user/assistant display fields through the browser API. Assistant fields are
rendered through `render_markdown`; bounded persisted tool calls, arguments and
results are included as an auditable collapsed panel.
`web/static/app.js.loadHistory()` calls this endpoint after initialization and
rehydrates chat bubbles following a browser refresh.

### `webapp._session_path()` / `_context_path()` / `_build_swarm()` / `get_session_graph()`

Each browser-visible session owns one independent directory under
`workspace/<session>/`. It contains separate Agent contexts, canonical
`conversation.json`, `task-plan.json`, `events.ndjson` and `graph-view.json`;
the path is backend-only and no credential is written there. `_context_path()`
creates the `contexts/` parent directory before returning an Agent-owned JSON
path, allowing every fresh coordinator or single Agent to persist history for
the next browser run. `_build_swarm()`
creates the coordinator, attaches dynamic subagent tools, relays all graph and
Agent events into SSE plus the append-only log, and refreshes the graph view.

### `webapp._reconcile_graph_view(workspace_id, session_id, graph)`

Combines `graph-view.json`, `run-state.json`, and chronological
`events.ndjson` into the authoritative graph response. It upgrades legacy
`reported/running/queued` snapshots to precise terminals, derives
`node_states`, and adds typed `dispatch` relationships from dynamic-node
parents while keeping execution dependencies distinct. Assignment identities
also reconstruct dynamic nodes omitted by old topology snapshots.
`get_session_graph()` calls it on every read, so historical sessions require
no migration.

### `webapp._read_session_event_log()` / `_session_event_page()` / `get_session_events()`

Read the append-only `events.ndjson` trace without exposing runtime objects.
The private reader ignores malformed concurrent-write lines; the page helper
returns newest-first bounded pages with a chronological cursor. The session
events endpoint calls it for the right-hand Trace inspector, which can reload
historical records and then append live SSE events.

### `webapp._session_usage_summary()` / `get_session_usage()`

Derive session-wide and per-Agent token metrics from each durable
`agent:round.data.round_usage` delta. The aggregation deliberately ignores
cumulative usage fields, preventing prior rounds from being counted again
when an Agent performs multiple model calls. The usage endpoint is read-only
and omits incomplete model calls until their round event has been emitted.

### `webapp.start_run()` / `get_run_status()` terminal failure recovery

The run worker persists an `error` trace record before it notifies live SSE
clients, then stores the terminal status, finishing time, and readable error in
`run-state.json`. On refresh, `get_run_status()` checks the in-memory worker as
well as that durable record. A stored `running` or `force_stopping` state
without a live worker is converted once to `interrupted`, which makes service
restarts and process loss visible rather than leaving the browser to imply that
work is still running.

### `frontend/static/app.js.loadHistory()` / `loadAllAgentBehavior()`

The chat pane uses one detailed message representation for both the aggregate
`all` filter and individual Agents. Lifecycle events are confined to the
right-hand Trace inspector and never produce a second set of collapsed cards
above the transcript. The aggregate view reads canonical `conversation.json`;
an individual Agent view reads `_agent_turns_from_events()`, which reconstructs
all browser user submissions plus that Agent's model rounds, reasoning, and
completed tool calls from append-only `events.ndjson`. This avoids losing old
prompts when the Agent's model context is compacted. A legacy context file is
used only when no durable event transcript exists.
Completed aggregate results reload their persisted transcript, while a selected
coordinator result is appended immediately and reconciled on the next reload.
Transcript turn metadata labels user input as `你`, Agent replies with the
selected Agent's name; these roles are visual-only and do not change stored
data.
`get_session_graph()` exposes only the safe view snapshot to the frontend.

Single-Agent event capture supplies `coordinator` when the underlying library
event has no name. This makes the persisted lifecycle stream groupable in the
aggregate behavior UI as well as identifiable in Trace.

## `llmfetcher.rag_module_tlb`

The experimental TLB RAG package provides an Agent-driven, hierarchical
file-tree retriever. `TLBRAGHandler` owns a contextless worker `Agent`: each
`retrieve()` call asks it to walk `INDEX.md` routing files, parses the final
JSON into `TLBResult`, records a proposed intent-to-path cache entry, then
clears that worker's context. `create_tlb_rag_tool()` wraps one handler as a
normal `Tool` for an external Agent. Its private `read_file` tool resolves
paths and requires them to be descendants of the configured knowledge root,
so a sibling path sharing the same string prefix cannot escape the sandbox.

`agentStateView()` is the shared status projection used by the selector,
Inspector list, graph, and per-Agent usage cards. Usage refreshes the graph
snapshot before rendering so its lights match the persisted execution state.
Live trace evidence temporarily outranks an older
in-browser graph response; the reconciled graph supplies refresh state. Green
means running, orange queued, blue completed and awaiting acknowledgement, red
failed/interrupted, and gray idle/cancelled/acknowledged. Clicking a blue dot
stores the acknowledgement per browser session and returns it to gray.

`start()` optimistically displays a submitted user turn in every filter. When
the aggregate view receives its final SSE `result`, it calls `loadHistory()`
instead of appending a partial event payload, replacing the live lifecycle
cards and optimistic turn with the backend's newly persisted canonical order.

### `webapp.stream_events()` durable SSE replay

The browser supplies the number of event-log records it has already rendered
as `after`. Rather than treating the in-memory queue as the authoritative
stream, the endpoint tails `events.ndjson` from that offset. A session switch
or browser refresh can therefore reconnect to a running Agent without losing
events that a previous SSE generator had consumed. The frontend records the
event total returned by the aggregate history loader and uses it on the next
EventSource connection.

### `frontend/static/app.js.rehydrateSelectedView()`

Initialization, cross-session selection, and in-session Agent filter changes
all use this single recovery path. It refreshes the selectable Agent list when
needed, loads the selected filter's durable transcript/aggregate behavior, and
then restores the run status and SSE connection. This prevents a selector click
from using a weaker recovery path than a browser refresh.

The stylesheet aligns `.message.user` to the right and `.message.assistant` to
the left. This makes speaker ownership visible in both aggregate and selected
Agent transcripts without altering the stored message records.

### `webapp.start_run()` Swarm branch

When `RunConfig.enable_swarm` is selected, `start_run()` runs the session
coordinator through `AgentSwarm` instead of directly invoking one Agent.
The coordinator can dispatch workers and wait for TaskBus reports; the final
coordinator output remains the chat response. Stop requests also ask the
swarm scheduler to stop submitting new nodes while active Agents finish their
cooperative boundary.

### `webapp.migrate_legacy_state()` / `_read_session_history()` migration

The one-time migration converts legacy `.llmfetcher` workspace data into
independent `workspace/<session>/` directories, preserves the source tree in a
timestamped backup, and builds `conversation.json` from the newest context or,
when necessary, the event log. Browser refresh reads `conversation.json` as
the only authority, so it no longer depends on ambiguous context fallbacks.

### `web/static/app.js` stream isolation and result copying

Each EventSource records its originating session. Switching session closes the
old stream, reloads the selected session history/plan, and prevents an old
Agent event from appending into the new session view. Assistant bubbles
include a Clipboard API copy control for their final text content.

Creating a session calls `switchSession(session.id)`, which closes an old
session's event stream without stopping its backend work, selects the returned
ID, and reloads history, plan, and graph together. The new chat therefore
shows its empty welcome state and accepts input rather than retaining the
previous session's messages or running UI state.

`restoreRunState()` reconnects only to a live run. It renders a persistent
error block for backend `error` or `interrupted` status and also does so for a
live SSE `error` event or a rejected start/force-stop request. This retains
prior chat content while making the run failure and its backend-provided cause
visible after a refresh.

### `web/static/app.js` reasoning and run guidance

Assistant reasoning is placed in a collapsed native `details` panel, preserving
the rendered Markdown while keeping final answers readable. `setRunning()`
adds a main-panel guidance card while a run is active and removes it at
completion; the card explains trace visibility, safe stop timing and session
switch behavior. The function also moves interaction focus to the main-panel
steer composer: it replaces the new-task composer only during a run.
`appendMessage()` routes durable `steer` turns to `appendSteerMessage()`,
which presents them as right-aligned amber input cards beside original user
messages. On a live
`agent:steer_applied`, `handleEvent()` uses a stable event key to prevent
duplicate cards after an SSE reconnect. `initInspectorTabs()` falls back to
the plan view when a browser persisted the removed steer-inspector tab.

### `web/static/app.js` execution graph rendering

The Swarm configuration fields are included in connector and run payloads.
`loadGraph()` fetches the session graph view at initialization, session switch,
manual refresh, and graph lifecycle events. The Agents inspector renders only
`renderAgentTopology()` so hierarchy, task assignment, and status are not
duplicated by a second execution-graph tree. The graph snapshot still supplies
the selector, topology, usage status projection, and task assignment data. The
trace prefixes every event with its emitting Agent identity.

### `web/static/app.js` composer keyboard handling

The message textarea submits the existing composer form on an unmodified
Enter keypress. Ctrl+Enter and Alt+Enter keep the textarea's normal newline
behavior; IME composition Enter is also left untouched. The submit handler
continues to validate and start the run, so keyboard and send-button paths are
identical.

`resizeComposer()` is shared by the input and submit paths. It grows the
textarea to a capped content height while text exists, then removes its inline
height after the prompt is cleared so the composer returns to its compact CSS
size rather than retaining the previous multiline height.

### `webapp.delete_workspace()` / `_stop_then_remove_workspace()` compatibility

Implements destructive session removal through the session API while retaining
the legacy workspace handler. The REST handler requires a browser confirmation
plus an exact session-name confirmation, reserves the session
against new runs, and requests cooperative stops for every active session.
When all active runs finish, the daemon cleanup removes only that session's
directory, session holders and registry record. The built-in `default`
session is protected from deletion.

### `web/static/app.js` stale workspace deletion recovery

The delete-workspace control treats a 404 response as an idempotent stale-page
case: the selected workspace was removed by an earlier action or another
browser tab. It reloads the registry, current history, plan and graph before
showing a trace notice, instead of leaving a stale localStorage workspace ID
selected. Other error statuses remain visible to the user.
