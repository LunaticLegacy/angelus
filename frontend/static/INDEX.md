# frontend/static/ — Static Assets INDEX

JavaScript modules and CSS for the Angelus workbench UI.

## Active Runtime

| Entry | Type | Purpose |
|-------|------|---------|
| `app.js` | ES-module composition root | The JavaScript entry loaded by `templates/index.html`. It coordinates session/connector settings, including native selection, rebinding and host-file-manager opening of each session's external project directory; MCP tool enablement and server definitions; runs and SSE (including server-rendered live Agent Markdown); an Agent-selectable task-plan view; and plugin status/settings plus confirmed registration/load/unload controls while delegating reusable rendering to `components/`. |
| `components/` | Active ES modules | DOM-safe components: `dom.js` provides shared DOM primitives, `chat-view.js` owns transcript cards, `trace-view.js` owns expandable Trace cards, and `task-plan-view.js` owns recursive task markup with lifecycle-owned read-only status labels. |
| `plugins.js` | Active ES module | Plugin frontend bridge: fetches the loadable plugin set, validates namespaced UI registrations, loads manifest-whitelisted assets, records settings metadata, and removes browser contributions when a plugin is unloaded. |
| `slash.js` | Active global script | DOM-free shell-style slash-command parser, also covered by `slash.test.js`. |
| `app.css` | File | Angelus mission-control visual system: calm three-zone desktop shell, readable transcript measure, project/session navigation, elevated composer, focused Inspector, light mode, reduced-motion support, and responsive two-column/mobile fallbacks. |
| `theme_light.html` | Theme reference | 独立的浅色主题视觉参考页；当前 SPA 不直接加载。 |

`index.html` deliberately cache-versions both active assets. Update those version query strings when a browser-visible change needs an immediate refresh. The active shell is branded as Angelus; its visual hierarchy keeps project navigation, transcript work, and session inspection as three independent zones while collapsing the Inspector and then stacking the sidebar at narrower breakpoints. The active connector flow includes a Kimi Code preset that fills the documented endpoint and default coding model while retaining user-defined overrides.

## Legacy Module Inventory

The following files form a prior ES-module decomposition. They are **not imported by the active composition root**, so they are useful only as migration/reference material. Do not treat their APIs or DOM assumptions as current behavior.

| Entry | Type | Purpose |
|-------|------|---------|
| `inspector/` | Dir | Legacy inspector modules; see its own INDEX for their status |
| `main.js` | ES module | Former bootstrap/wiring entry point |
| `api.js` | ES module | Former REST helper layer |
| `state.js` | ES module | Former in-memory state store |
| `chat.js` | ES module | Former chat and stream rendering layer |
| `sessions.js` | ES module | Former session-list API/UI layer |
| `connectors.js` | ES module | Former connector API layer |
| `settings.js` | ES module | Former browser-local settings layer |
| `events.js` | ES module | Former EventSource wrapper |
| `utils.js` | ES module | Former shared DOM/formatting helpers |
| `slash.test.js` | Node test | Unit coverage for the active slash-command parser; not served to the browser |

## Active Responsibilities (`app.js`)

| Function | Role |
|----------|------|
| `loadWorkspaces` | Load session registry into sidebar selector |
| `pickWorkspaceDirectory` | Ask the loopback backend to open the platform-native directory picker |
| `loadHistory` | Load the latest 200-message cursor page for the selected Agent |
| `loadAllAgentBehavior` | Render aggregate behavior from the durable transcript projection |
| `loadOlderMessages` | Prepend one older cursor page while preserving the chat viewport |
| `start` | Submit message, begin SSE stream |
| `handleEvent` | Process live SSE events |
| `appendMessage` | Render a single chat turn |
| `appendAgentBehavior` | Group agent lifecycle events into expandable block |
| `renderAgentSelector` | Build agent filter dropdown from graph evidence |
| `rehydrateSelectedView` | Restore filter state after refresh |
| `switchSession` | Persist the current settings, then restore the selected session's settings and durable views |

It also owns settings-dialog navigation, encrypted connector CRUD calls, persistent session-status rendering, Swarm topology/Agent inspector rendering, token-ledger presentation, and initialization of the plugin UI bridge. New-session creation pauses for a platform-native directory choice; cancelling the picker cancels creation, and inactive legacy sessions may later be rebound from the sidebar. The task plan presents Agent-owned lifecycle states as fixed labels rather than browser-editable selects; summaries and descriptions preserve actual JSON line feeds with `white-space: pre-wrap`, while literal backslash escapes remain visible text. The chat retains one accessible “load older” button and uses the same locked loader when its single scroll listener reaches the top; both the controller and chat component recreate that button if an older cached renderer removed it, failures retain the cursor for retry, session/Agent/generation snapshots discard stale responses, and prepends restore the prior viewport. Trace uses reverse byte cursors and supplies its durable offset directly to SSE recovery, so initialization does not issue an extra event-count request. The dialog labels connector settings as globally shared and Agent settings as session-local. Its memory-authorisation picker searches and selects other session IDs, persists them with the current session's Agent settings, and sends them as the four run-scoped SessionMemory capability allowlists. The Agent settings include a persisted `max-retries` field: it is the additional timeout retry count, defaults to three, and is sent in every run payload. The dialog uses left-side category buttons (`data-settings-section`) and matching content panes (`data-settings-panel`); `showSettingsSection()` keeps their active and ARIA-selected states synchronized. Usage cards refresh the graph snapshot and reuse `agentStateView()` so their indicator matches the selector, Inspector and graph. The main-panel steer composer replaces the new-task composer while a run is active, while each durable applied instruction is a distinct amber, right-aligned transcript item beside original user messages. Transcript replay renders stored `steer` turns, and live `agent:steer_applied` events use a stable event key to avoid duplicate cards after an SSE reconnect. The Inspector intentionally contains only plan, Agents, Trace and usage; its stored selected-tab value falls back to plan if an older browser preference references the removed steer tab. Its normal stop remains cooperative at a model/tool boundary; its force-stop confirmation and live guidance state that the current model request is interrupted and registered Shell processes are killed. Direct event listeners must target IDs present in `templates/index.html`; `tests/test_workbench_assets.py` enforces that contract.

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [api.js](api.js#L2) | `_fetch` | `url: unknown, options: unknown` | `Promise<unknown>` | Perform the browser runtime operation: fetch. |
| [api.js](api.js#L13) | `apiJson` | `url: unknown` | `unknown` | Perform the browser runtime operation: api json. |
| [api.js](api.js#L17) | `apiPost` | `url: unknown, body: unknown` | `unknown` | Perform the browser runtime operation: api post. |
| [api.js](api.js#L25) | `apiPut` | `url: unknown, body: unknown` | `unknown` | Perform the browser runtime operation: api put. |
| [api.js](api.js#L33) | `apiPatch` | `url: unknown, body: unknown` | `unknown` | Perform the browser runtime operation: api patch. |
| [api.js](api.js#L41) | `apiDelete` | `url: unknown, body: unknown` | `unknown` | Perform the browser runtime operation: api delete. |
| [app.js](app.js#L14) | `applyTheme` | `theme: unknown` | `unknown` | Perform the browser runtime operation: apply theme. |
| [app.js](app.js#L23) | `initTheme` | `None` | `unknown` | Perform the browser runtime operation: init theme. |
| [app.js](app.js#L68) | `value` | `id: unknown` | `unknown` | Perform the browser runtime operation: value. |
| [app.js](app.js#L70) | `mcpServers` | `None` | `unknown` | Perform the browser runtime operation: mcp servers. |
| [app.js](app.js#L71) | `config` | `None` | `unknown` | Perform the browser runtime operation: config. |
| [app.js](app.js#L84) | `settingsKey` | `id: unknown` | `unknown` | Perform the browser runtime operation: settings key. |
| [app.js](app.js#L85) | `connectionDraftKey` | `id: unknown` | `unknown` | Perform the browser runtime operation: connection draft key. |
| [app.js](app.js#L86) | `persistedFields` | `ids: unknown` | `unknown` | Perform the browser runtime operation: persisted fields. |
| [app.js](app.js#L87) | `persistSettings` | `None` | `unknown` | Perform the browser runtime operation: persist settings. |
| [app.js](app.js#L88) | `restoreSettings` | `None` | `unknown` | Perform the browser runtime operation: restore settings. |
| [app.js](app.js#L89) | `bindSettingsPersistence` | `None` | `unknown` | Perform the browser runtime operation: bind settings persistence. |
| [app.js](app.js#L90) | `setStatus` | `text: unknown, state: unknown` | `unknown` | Perform the browser runtime operation: set status. |
| [app.js](app.js#L91) | `providerLabel` | `provider: unknown` | `unknown` | Perform the browser runtime operation: provider label. |
| [app.js](app.js#L92) | `updateProviderHint` | `None` | `unknown` | Perform the browser runtime operation: update provider hint. |
| [app.js](app.js#L93) | `applyProviderPreset` | `None` | `unknown` | Perform the browser runtime operation: apply provider preset. |
| [app.js](app.js#L94) | `updateModelSummary` | `None` | `unknown` | Perform the browser runtime operation: update model summary. |
| [app.js](app.js#L96) | `selectedMemorySessions` | `None` | `unknown` | Perform the browser runtime operation: selected memory sessions. |
| [app.js](app.js#L98) | `renderMemorySessionPicker` | `None` | `unknown` | Perform the browser runtime operation: render memory session picker. |
| [app.js](app.js#L102) | `liveTools` | `data: unknown` | `unknown` | Perform the browser runtime operation: live tools. |
| [app.js](app.js#L104) | `appendMessage` | `role: unknown, content: unknown, reasoning: unknown, contentHtml: unknown, reasoningHtml: unknown, tools: unknown, agentName: unknown, usage: unknown, modelDurationMs: unknown, timestamp: unknown` | `unknown` | Perform the browser runtime operation: append message. |
| [app.js](app.js#L105) | `streamKey` | `agent: unknown, round: unknown` | `unknown` | Perform the browser runtime operation: stream key. |
| [app.js](app.js#L106) | `renderStreamDelta` | `agent: unknown, data: unknown` | `unknown` | Perform the browser runtime operation: render stream delta. |
| [app.js](app.js#L107) | `discardStream` | `agent: unknown, round: unknown` | `unknown` | Perform the browser runtime operation: discard stream. |
| [app.js](app.js#L109) | `appendRunErrorBlock` | `title: unknown, message: unknown, rawContent: unknown` | `unknown` | Perform the browser runtime operation: append run error block. |
| [app.js](app.js#L111) | `appendSteerMessage` | `text: unknown, eventKey: unknown` | `unknown` | Perform the browser runtime operation: append steer message. |
| [app.js](app.js#L114) | `renderMessagesInto` | `messages: unknown, assistantLabel: unknown` | `unknown` | Perform the browser runtime operation: render messages into. |
| [app.js](app.js#L116) | `ensureLoadMoreMessagesButton` | `None` | `unknown` | Perform the browser runtime operation: ensure load more messages button. |
| [app.js](app.js#L117) | `setMessageHistoryButton` | `hasMore: unknown, text: unknown` | `unknown` | Perform the browser runtime operation: set message history button. |
| [app.js](app.js#L118) | `loadAllAgentBehavior` | `snapshot: unknown` | `Promise<unknown>` | Perform the browser runtime operation: load all agent behavior. |
| [app.js](app.js#L119) | `trace` | `title: unknown, message: unknown, data: unknown, kind: unknown` | `unknown` | Perform the browser runtime operation: trace. |
| [app.js](app.js#L120) | `tracePayload` | `event: unknown, position: unknown` | `unknown` | Perform the browser runtime operation: trace payload. |
| [app.js](app.js#L121) | `updateHeaderMetrics` | `data: unknown` | `unknown` | Perform the browser runtime operation: update header metrics. |
| [app.js](app.js#L122) | `setRunning` | `running: unknown` | `unknown` | Perform the browser runtime operation: set running. |
| [app.js](app.js#L125) | `setSteerStatus` | `text: unknown, state: unknown` | `unknown` | Perform the browser runtime operation: set steer status. |
| [app.js](app.js#L126) | `sendSteer` | `message: unknown` | `Promise<unknown>` | Perform the browser runtime operation: send steer. |
| [app.js](app.js#L127) | `apiJson` | `path: unknown` | `Promise<unknown>` | Perform the browser runtime operation: api json. |
| [app.js](app.js#L128) | `apiPost` | `path: unknown, body: unknown` | `Promise<unknown>` | Perform the browser runtime operation: api post. |
| [app.js](app.js#L130) | `setWorkspaceIndicator` | `id: unknown, status: unknown` | `unknown` | Perform the browser runtime operation: set workspace indicator. |
| [app.js](app.js#L131) | `loadWorkspaces` | `selected: unknown` | `Promise<unknown>` | Perform the browser runtime operation: load workspaces. |
| [app.js](app.js#L132) | `applyConnector` | `connector: unknown` | `unknown` | Perform the browser runtime operation: apply connector. |
| [app.js](app.js#L133) | `loadConnectors` | `selected: unknown` | `Promise<unknown>` | Perform the browser runtime operation: load connectors. |
| [app.js](app.js#L134) | `connectorPayload` | `name: unknown` | `unknown` | Perform the browser runtime operation: connector payload. |
| [app.js](app.js#L136) | `connectorFeedback` | `text: unknown, state: unknown` | `unknown` | Perform the browser runtime operation: connector feedback. |
| [app.js](app.js#L138) | `createConnector` | `name: unknown` | `Promise<unknown>` | Perform the browser runtime operation: create connector. |
| [app.js](app.js#L140) | `saveSelectedConnector` | `None` | `Promise<unknown>` | Perform the browser runtime operation: save selected connector. |
| [app.js](app.js#L142) | `openConnectorDialog` | `None` | `unknown` | Perform the browser runtime operation: open connector dialog. |
| [app.js](app.js#L143) | `openSettings` | `section: unknown` | `unknown` | Perform the browser runtime operation: open settings. |
| [app.js](app.js#L144) | `showSettingsSection` | `section: unknown` | `unknown` | Perform the browser runtime operation: show settings section. |
| [app.js](app.js#L145) | `setPluginFeedback` | `text: unknown, state: unknown` | `unknown` | Perform the browser runtime operation: set plugin feedback. |
| [app.js](app.js#L146) | `pluginStateLabel` | `state: unknown` | `unknown` | Perform the browser runtime operation: plugin state label. |
| [app.js](app.js#L147) | `pluginSettingsRegistration` | `name: unknown` | `unknown` | Perform the browser runtime operation: plugin settings registration. |
| [app.js](app.js#L148) | `pluginKey` | `plugin: unknown` | `unknown` | Perform the browser runtime operation: plugin key. |
| [app.js](app.js#L149) | `renderPluginStatusList` | `None` | `unknown` | Perform the browser runtime operation: render plugin status list. |
| [app.js](app.js#L150) | `loadPluginStatuses` | `None` | `Promise<unknown>` | Perform the browser runtime operation: load plugin statuses. |
| [app.js](app.js#L151) | `pluginPermissionsNote` | `plugin: unknown` | `unknown` | Perform the browser runtime operation: plugin permissions note. |
| [app.js](app.js#L152) | `pluginLifecycleControls` | `plugin: unknown` | `unknown` | Perform the browser runtime operation: plugin lifecycle controls. |
| [app.js](app.js#L153) | `bindPluginLifecycleControls` | `plugin: unknown` | `unknown` | Perform the browser runtime operation: bind plugin lifecycle controls. |
| [app.js](app.js#L154) | `renderPluginDetail` | `plugin: unknown, payload: unknown` | `unknown` | Perform the browser runtime operation: render plugin detail. |
| [app.js](app.js#L155) | `selectPluginSettings` | `key: unknown` | `Promise<unknown>` | Perform the browser runtime operation: select plugin settings. |
| [app.js](app.js#L156) | `savePluginSettings` | `event: unknown, plugin: unknown` | `Promise<unknown>` | Perform the browser runtime operation: save plugin settings. |
| [app.js](app.js#L157) | `changePluginLifecycle` | `plugin: unknown, action: unknown` | `Promise<unknown>` | Perform the browser runtime operation: change plugin lifecycle. |
| [app.js](app.js#L158) | `planUrl` | `None` | `unknown` | Perform the browser runtime operation: plan url. |
| [app.js](app.js#L159) | `messagesUrl` | `cursor: unknown, selectedSession: unknown, agent: unknown` | `unknown` | Perform the browser runtime operation: messages url. |
| [app.js](app.js#L160) | `graphUrl` | `None` | `unknown` | Perform the browser runtime operation: graph url. |
| [app.js](app.js#L161) | `agentIcon` | `agent: unknown` | `unknown` | Perform the browser runtime operation: agent icon. |
| [app.js](app.js#L162) | `acknowledgementKey` | `None` | `unknown` | Perform the browser runtime operation: acknowledgement key. |
| [app.js](app.js#L163) | `acknowledgedAgents` | `None` | `unknown` | Perform the browser runtime operation: acknowledged agents. |
| [app.js](app.js#L165) | `agentStateView` | `agentId: unknown, agents: unknown` | `unknown` | Perform the browser runtime operation: agent state view. |
| [app.js](app.js#L199) | `stateLabel` | `state: unknown` | `unknown` | Perform the browser runtime operation: state label. |
| [app.js](app.js#L201) | `stateView` | `canonical: unknown, message: unknown, agentId: unknown` | `unknown` | Perform the browser runtime operation: state view. |
| [app.js](app.js#L202) | `agentRunState` | `agentId: unknown, agents: unknown` | `unknown` | Perform the browser runtime operation: agent run state. |
| [app.js](app.js#L203) | `acknowledgeAgent` | `agentId: unknown` | `unknown` | Perform the browser runtime operation: acknowledge agent. |
| [app.js](app.js#L205) | `agentCard` | `agent: unknown, selected: unknown, tone: unknown, icon: unknown, subtitle: unknown, view: unknown, title: unknown` | `unknown` | Perform the browser runtime operation: agent card. |
| [app.js](app.js#L209) | `renderAgentSelector` | `agents: unknown` | `unknown` | Perform the browser runtime operation: render agent selector. |
| [app.js](app.js#L212) | `contextNodeTone` | `type: unknown` | `unknown` | Perform the browser runtime operation: context node tone. |
| [app.js](app.js#L214) | `renderContextGraphDetail` | `graph: unknown, nodeId: unknown` | `unknown` | Perform the browser runtime operation: render context graph detail. |
| [app.js](app.js#L225) | `renderContextGraph` | `payload: unknown` | `unknown` | Perform the browser runtime operation: render context graph. |
| [app.js](app.js#L251) | `selectContextDialogTab` | `tab: unknown` | `unknown` | Perform the browser runtime operation: select context dialog tab. |
| [app.js](app.js#L262) | `decodePromptText` | `value: unknown` | `unknown` | Perform the browser runtime operation: decode prompt text. |
| [app.js](app.js#L264) | `readablePromptValue` | `value: unknown, indent: unknown` | `unknown` | Perform the browser runtime operation: readable prompt value. |
| [app.js](app.js#L266) | `renderContextPrompt` | `payload: unknown` | `unknown` | Perform the browser runtime operation: render context prompt. |
| [app.js](app.js#L268) | `loadContextPrompt` | `agentId: unknown` | `Promise<unknown>` | Perform the browser runtime operation: load context prompt. |
| [app.js](app.js#L270) | `renderCompactionInput` | `payload: unknown` | `unknown` | Perform the browser runtime operation: render compaction input. |
| [app.js](app.js#L279) | `loadCompactionInput` | `agentId: unknown` | `Promise<unknown>` | Perform the browser runtime operation: load compaction input. |
| [app.js](app.js#L281) | `openContextGraph` | `agentId: unknown` | `Promise<unknown>` | Perform the browser runtime operation: open context graph. |
| [app.js](app.js#L291) | `loadAgents` | `None` | `Promise<unknown>` | Perform the browser runtime operation: load agents. |
| [app.js](app.js#L292) | `selectAgent` | `agentId: unknown` | `Promise<unknown>` | Perform the browser runtime operation: select agent. |
| [app.js](app.js#L293) | `renderGraph` | `graph: unknown` | `unknown` | Perform the browser runtime operation: render graph. |
| [app.js](app.js#L295) | `loadGraph` | `None` | `Promise<unknown>` | Perform the browser runtime operation: load graph. |
| [app.js](app.js#L297) | `traceUrl` | `cursor: unknown` | `unknown` | Perform the browser runtime operation: trace url. |
| [app.js](app.js#L299) | `isTraceVisible` | `event: unknown` | `unknown` | Perform the browser runtime operation: is trace visible. |
| [app.js](app.js#L305) | `loadTrace` | `reset: unknown` | `Promise<unknown>` | Perform the browser runtime operation: load trace. |
| [app.js](app.js#L306) | `agentContextStats` | `agent: unknown` | `unknown` | Perform the browser runtime operation: agent context stats. |
| [app.js](app.js#L329) | `renderAgentTopology` | `agents: unknown, graph: unknown` | `unknown` | Perform the browser runtime operation: render agent topology. |
| [app.js](app.js#L345) | `loadInspectorAgents` | `None` | `Promise<unknown>` | Perform the browser runtime operation: load inspector agents. |
| [app.js](app.js#L346) | `usageCells` | `usage: unknown, run: unknown` | `unknown` | Perform the browser runtime operation: usage cells. |
| [app.js](app.js#L348) | `loadUsage` | `None` | `Promise<unknown>` | Perform the browser runtime operation: load usage. |
| [app.js](app.js#L349) | `selectInspectorPanel` | `panel: unknown, refresh: unknown` | `unknown` | Perform the browser runtime operation: select inspector panel. |
| [app.js](app.js#L350) | `initInspectorTabs` | `None` | `unknown` | Perform the browser runtime operation: init inspector tabs. |
| [app.js](app.js#L351) | `knownPlanAgents` | `None` | `unknown` | Perform the browser runtime operation: known plan agents. |
| [app.js](app.js#L352) | `renderPlanAgentPicker` | `None` | `unknown` | Perform the browser runtime operation: render plan agent picker. |
| [app.js](app.js#L353) | `loadPlan` | `None` | `Promise<unknown>` | Perform the browser runtime operation: load plan. |
| [app.js](app.js#L355) | `loadHistory` | `None` | `Promise<unknown>` | Perform the browser runtime operation: load history. |
| [app.js](app.js#L385) | `loadOlderMessages` | `None` | `Promise<unknown>` | Perform the browser runtime operation: load older messages. |
| [app.js](app.js#L419) | `rehydrateSelectedView` | `options: object` | `Promise<unknown>` | Perform the browser runtime operation: rehydrate selected view. |
| [app.js](app.js#L420) | `switchSession` | `selected: unknown` | `Promise<unknown>` | Perform the browser runtime operation: switch session. |
| [app.js](app.js#L421) | `start` | `message: unknown` | `Promise<unknown>` | Perform the browser runtime operation: start. |
| [app.js](app.js#L435) | `showCompactStatus` | `text: unknown, state: unknown, dismissMs: unknown` | `unknown` | Perform the browser runtime operation: show compact status. |
| [app.js](app.js#L441) | `clearCompactStatus` | `None` | `unknown` | Perform the browser runtime operation: clear compact status. |
| [app.js](app.js#L443) | `debounce` | `fn: unknown, wait: unknown` | `unknown` | Perform the browser runtime operation: debounce. |
| [app.js](app.js#L451) | `indexTraceEvent` | `event: unknown` | `unknown` | Perform the browser runtime operation: index trace event. |
| [app.js](app.js#L457) | `rebuildTraceEventIndex` | `None` | `unknown` | Perform the browser runtime operation: rebuild trace event index. |
| [app.js](app.js#L468) | `handleEvent` | `event: unknown` | `unknown` | Perform the browser runtime operation: handle event. |
| [app.js](app.js#L488) | `finish` | `None` | `unknown` | Perform the browser runtime operation: finish. |
| [app.js](app.js#L490) | `showSlashHelp` | `None` | `unknown` | Perform the browser runtime operation: show slash help. |
| [app.js](app.js#L511) | `sessionByName` | `name: unknown` | `unknown` | Perform the browser runtime operation: session by name. |
| [app.js](app.js#L512) | `switchSessionByName` | `name: unknown` | `Promise<unknown>` | Perform the browser runtime operation: switch session by name. |
| [app.js](app.js#L513) | `deleteSessionByName` | `name: unknown` | `Promise<unknown>` | Perform the browser runtime operation: delete session by name. |
| [app.js](app.js#L514) | `runStop` | `None` | `Promise<unknown>` | Perform the browser runtime operation: run stop. |
| [app.js](app.js#L515) | `runForceStop` | `None` | `Promise<unknown>` | Perform the browser runtime operation: run force stop. |
| [app.js](app.js#L517) | `runCompact` | `agent: unknown` | `Promise<unknown>` | Perform the browser runtime operation: run compact. |
| [app.js](app.js#L531) | `handleCompactStage` | `record: unknown, startedSession: unknown` | `unknown` | Perform the browser runtime operation: handle compact stage. |
| [app.js](app.js#L555) | `dispatchSlashCommand` | `parsed: unknown` | `unknown` | Perform the browser runtime operation: dispatch slash command. |
| [app.js](app.js#L563) | `resizeComposer` | `None` | `unknown` | Perform the browser runtime operation: resize composer. |
| [app.js](app.js#L564) | `connectRunEvents` | `runId: unknown, after: unknown` | `unknown` | Perform the browser runtime operation: connect run events. |
| [app.js](app.js#L565) | `restoreRunState` | `None` | `Promise<unknown>` | Perform the browser runtime operation: restore run state. |
| [app.js](app.js#L583) | `pickWorkspaceDirectory` | `None` | `Promise<unknown>` | Perform the browser runtime operation: pick workspace directory. |
| [app.js](app.js#L584) | `createAndSwitchSession` | `name: unknown, projectPath: unknown` | `Promise<unknown>` | Perform the browser runtime operation: create and switch session. |
| [app.js](app.js#L645) | `loadProviders` | `None` | `Promise<unknown>` | Perform the browser runtime operation: load providers. |
| [app.js](app.js#L646) | `initializeConsole` | `None` | `Promise<unknown>` | Perform the browser runtime operation: initialize console. |
| [chat.js](chat.js#L12) | `removeWelcome` | `None` | `unknown` | Perform the browser runtime operation: remove welcome. |
| [chat.js](chat.js#L16) | `appendMessage` | `role: unknown, content: unknown, reasoning: unknown, contentHtml: unknown, reasoningHtml: unknown, tools: unknown` | `unknown` | Perform the browser runtime operation: append message. |
| [chat.js](chat.js#L57) | `renderTools` | `tools: unknown` | `unknown` | Perform the browser runtime operation: render tools. |
| [chat.js](chat.js#L76) | `loadHistory` | `None` | `Promise<unknown>` | Perform the browser runtime operation: load history. |
| [chat.js](chat.js#L98) | `startRun` | `message: unknown` | `Promise<unknown>` | Perform the browser runtime operation: start run. |
| [chat.js](chat.js#L123) | `setEventHandlers` | `handlers: unknown` | `unknown` | Perform the browser runtime operation: set event handlers. |
| [chat.js](chat.js#L127) | `handleEvent` | `event: unknown` | `unknown` | Perform the browser runtime operation: handle event. |
| [chat.js](chat.js#L169) | `finishRun` | `None` | `unknown` | Perform the browser runtime operation: finish run. |
| [chat.js](chat.js#L176) | `_resolveSessionId` | `None` | `unknown` | Perform the browser runtime operation: resolve session id. |
| [chat.js](chat.js#L180) | `_resolveWorkspaceId` | `None` | `unknown` | Perform the browser runtime operation: resolve workspace id. |
| [chat.js](chat.js#L186) | `initComposer` | `formEl: unknown` | `unknown` | Perform the browser runtime operation: init composer. |
| [connectors.js](connectors.js#L11) | `loadAll` | `selectedId: unknown` | `Promise<unknown>` | Perform the browser runtime operation: load all. |
| [connectors.js](connectors.js#L28) | `renderSelect` | `connectors: unknown, selectedId: unknown` | `unknown` | Perform the browser runtime operation: render select. |
| [connectors.js](connectors.js#L41) | `_payload` | `name: unknown` | `unknown` | Perform the browser runtime operation: payload. |
| [connectors.js](connectors.js#L45) | `create` | `name: unknown` | `Promise<unknown>` | Perform the browser runtime operation: create. |
| [connectors.js](connectors.js#L49) | `update` | `id: unknown, name: unknown` | `Promise<unknown>` | Perform the browser runtime operation: update. |
| [connectors.js](connectors.js#L53) | `remove` | `id: unknown` | `Promise<unknown>` | Perform the browser runtime operation: remove. |
| [events.js](events.js#L14) | `connectRun` | `workspaceId: unknown, runId: unknown, handlers: unknown` | `unknown` | Perform the browser runtime operation: connect run. |
| [events.js](events.js#L42) | `disconnect` | `None` | `unknown` | Perform the browser runtime operation: disconnect. |
| [events.js](events.js#L48) | `isConnected` | `None` | `unknown` | Perform the browser runtime operation: is connected. |
| [events.js](events.js#L52) | `currentWorkspaceId` | `None` | `unknown` | Perform the browser runtime operation: current workspace id. |
| [main.js](main.js#L84) | `switchSession` | `selected: unknown` | `Promise<unknown>` | Perform the browser runtime operation: switch session. |
| [main.js](main.js#L97) | `_reloadConnectorsKeepId` | `None` | `Promise<unknown>` | Perform the browser runtime operation: reload connectors keep id. |
| [main.js](main.js#L103) | `_restoreRunState` | `None` | `Promise<unknown>` | Perform the browser runtime operation: restore run state. |
| [main.js](main.js#L315) | `initialize` | `None` | `Promise<unknown>` | Perform the browser runtime operation: initialize. |
| [main.js](main.js#L329) | `_loadProviders` | `None` | `Promise<unknown>` | Perform the browser runtime operation: load providers. |
| [plugins.js](plugins.js#L70) | `_warn` | `plugin: unknown, message: unknown` | `unknown` | Perform the browser runtime operation: warn. |
| [plugins.js](plugins.js#L74) | `_validName` | `name: unknown` | `unknown` | Perform the browser runtime operation: valid name. |
| [plugins.js](plugins.js#L80) | `_safeId` | `value: unknown` | `unknown` | Perform the browser runtime operation: safe id. |
| [plugins.js](plugins.js#L87) | `_assertLoaded` | `plugin: unknown` | `unknown` | Perform the browser runtime operation: assert loaded. |
| [plugins.js](plugins.js#L96) | `_injectScript` | `src: unknown, pluginName: unknown` | `unknown` | Perform the browser runtime operation: inject script. |
| [plugins.js](plugins.js#L108) | `_injectStylesheet` | `src: unknown, pluginName: unknown` | `unknown` | Perform the browser runtime operation: inject stylesheet. |
| [plugins.js](plugins.js#L120) | `_pluginAssetUrl` | `pluginName: unknown, asset: unknown` | `unknown` | Perform the browser runtime operation: plugin asset url. |
| [plugins.js](plugins.js#L124) | `_loadPluginAssets` | `plugin: unknown` | `Promise<unknown>` | Perform the browser runtime operation: load plugin assets. |
| [plugins.js](plugins.js#L143) | `unloadPlugin` | `pluginName: unknown` | `unknown` | Perform the browser runtime operation: unload plugin. |
| [plugins.js](plugins.js#L164) | `_panelContainers` | `None` | `unknown` | Perform the browser runtime operation: panel containers. |
| [plugins.js](plugins.js#L171) | `_fillPanel` | `body: unknown, render: unknown` | `unknown` | Perform the browser runtime operation: fill panel. |
| [plugins.js](plugins.js#L181) | `_renderPanel` | `registration: unknown` | `unknown` | Perform the browser runtime operation: render panel. |
| [plugins.js](plugins.js#L232) | `_bindPanelTabs` | `None` | `unknown` | Perform the browser runtime operation: bind panel tabs. |
| [plugins.js](plugins.js#L252) | `_createBridge` | `None` | `unknown` | Perform the browser runtime operation: create bridge. |
| [plugins.js](plugins.js#L372) | `loadPlugins` | `None` | `Promise<unknown>` | Perform the browser runtime operation: load plugins. |
| [plugins.js](plugins.js#L407) | `initPlugins` | `None` | `Promise<unknown>` | Perform the browser runtime operation: init plugins. |
| [sessions.js](sessions.js#L10) | `loadAll` | `selectedId: unknown` | `Promise<unknown>` | Perform the browser runtime operation: load all. |
| [sessions.js](sessions.js#L30) | `renderSelect` | `sessions: unknown, selectedId: unknown` | `unknown` | Perform the browser runtime operation: render select. |
| [sessions.js](sessions.js#L41) | `renderRecent` | `sessions: unknown, selectedId: unknown` | `unknown` | Perform the browser runtime operation: render recent. |
| [sessions.js](sessions.js#L54) | `create` | `name: unknown` | `Promise<unknown>` | Perform the browser runtime operation: create. |
| [sessions.js](sessions.js#L58) | `remove` | `id: unknown, confirmation: unknown` | `Promise<unknown>` | Perform the browser runtime operation: remove. |
| [settings.js](settings.js#L32) | `_settingsKey` | `workspaceId: unknown` | `unknown` | Perform the browser runtime operation: settings key. |
| [settings.js](settings.js#L36) | `_readConfig` | `None` | `unknown` | Perform the browser runtime operation: read config. |
| [settings.js](settings.js#L38) | `val` | `id: unknown` | `unknown` | Perform the browser runtime operation: val. |
| [settings.js](settings.js#L61) | `persistSettings` | `None` | `unknown` | Perform the browser runtime operation: persist settings. |
| [settings.js](settings.js#L68) | `restoreSettings` | `None` | `unknown` | Perform the browser runtime operation: restore settings. |
| [settings.js](settings.js#L90) | `bindSettingsPersistence` | `None` | `unknown` | Perform the browser runtime operation: bind settings persistence. |
| [settings.js](settings.js#L100) | `getConfig` | `None` | `unknown` | Perform the browser runtime operation: get config. |
| [settings.js](settings.js#L105) | `updateModelSummary` | `None` | `unknown` | Perform the browser runtime operation: update model summary. |
| [settings.js](settings.js#L114) | `applyConnector` | `connector: unknown` | `unknown` | Perform the browser runtime operation: apply connector. |
| [slash.js](slash.js#L18) | `isWhitespace` | `ch: unknown` | `unknown` | Perform the browser runtime operation: is whitespace. |
| [slash.js](slash.js#L24) | `tokenize` | `input: unknown` | `unknown` | Perform the browser runtime operation: tokenize. |
| [slash.js](slash.js#L66) | `parseSlashCommand` | `line: unknown` | `unknown` | Perform the browser runtime operation: parse slash command. |
| [state.js](state.js#L21) | `getState` | `key: unknown` | `unknown` | Perform the browser runtime operation: get state. |
| [state.js](state.js#L25) | `setState` | `partial: unknown` | `unknown` | Perform the browser runtime operation: set state. |
| [state.js](state.js#L34) | `subscribe` | `key: unknown, fn: unknown` | `unknown` | Perform the browser runtime operation: subscribe. |
| [utils.js](utils.js#L2) | `$` | `id: unknown` | `unknown` | Perform the browser runtime operation: $. |
| [utils.js](utils.js#L6) | `escapeHtml` | `text: unknown` | `unknown` | Perform the browser runtime operation: escape html. |
| [utils.js](utils.js#L12) | `copyResult` | `text: unknown, button: unknown` | `Promise<unknown>` | Perform the browser runtime operation: copy result. |
| [utils.js](utils.js#L22) | `formatDuration` | `ms: unknown` | `unknown` | Perform the browser runtime operation: format duration. |
| [utils.js](utils.js#L28) | `formatSeconds` | `ms: unknown` | `unknown` | Perform the browser runtime operation: format seconds. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| — | — | `None` | `object` | 本索引范围不直接声明类；沿 Route Map 进入下级索引。 |

<!-- END GENERATED SYMBOL MAP -->
