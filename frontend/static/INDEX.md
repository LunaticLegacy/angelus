# frontend/static/ — Browser Runtime INDEX

| File / directory | Responsibility |
|---|---|
| `app.js` | Main workbench state/controller: selected Session, history, settings, Session-run control, image composer wiring and Session-console inspector calls. |
| `app.css` | Workbench visual layout, dialogs, session controls and responsive styling. |
| `plugins.js` | Loads active plugin assets and renders manifest-declared, host-owned Inspector panels with validated action submissions. |
| `components/` | DOM, chat transcript, task-plan, trace, and External Agent Hub rendering helpers. |
| `vendor/` | Pinned browser ESM copies of Marked and DOMPurify, including upstream licenses. |
| `inspector/` | Historic inspector helpers; not all APIs are mounted in Phase 1. |
| `api.js`, `sessions.js`, `settings.js`, `connectors.js`, etc. | Older modular client surface retained during migration; do not introduce a second route contract through them. |

## Phase-1 Controller Route Map

| Intent | `app.js` operation | API |
|---|---|---|
| List/select/create/delete session | `loadWorkspaces`, `switchSession`, `createAndSwitchSession` | `/api/sessions` |
| Read transcript | `loadHistory`, `loadOlderMessages` | `/api/sessions/{id}/messages` |
| Connector CRUD | `loadConnectors`, `createConnector`, `saveSelectedConnector` | `/api/connectors` |
| Profile reads/writes | `restoreSettings`, `persistSettings` | `/api/settings/run-profile`, `/api/sessions/{id}/run-profile` |
| Start/stop | `start`, stop controls | `/api/runs` (`target_agent` for concrete selection) |
| Attach/send image | `createImageComposer` upload, `beginSend` | `/api/sessions/{id}/attachments/images`, `/api/runs` |
| Inspector graph/plan/trace/usage/context | `loadGraph`, `loadPlan`, `loadTrace`, `loadUsage`, context dialog | `/api/sessions/{id}/…` |

Graph removal uses the mounted contracts: Agent removal uses the path identity
route, while connection removal sends its typed source/target JSON body.
The permissions panel exposes only the registered Session-console tools; both
its category and individual Tool switches control actual model tool schemas.

`app.js` must refresh `availableSessions` after creation before membership
validation; otherwise a successful POST appears as an “unknown session”.
Its graph and lifecycle SSE cursors are event counts maintained separately from
the journal byte offset used by Trace pagination. Lifecycle SSE feeds model
deltas directly into chat/Trace; graph SSE remains topology-only.
On an SSE reconnect error, it checks the Session run state and closes the
browser stream once the attempt is terminal.
The MCP console is live against the mounted managed-MCP routes. It edits only
public server metadata, write-only credentials and Session bindings; SDK
transports remain backend-owned.
Plugin discovery errors are terminal in the browser lifecycle UI: an invalid
manifest can be inspected but is never offered a registration or load action.
Plugin settings are manifest-declared user parameters. The mounted editor
renders typed scalar controls, bounded choices, numeric ranges, URI fields,
path hints, and multi-line text areas before the API persists them.
Active tool plugins may also declare transient `frontend.panels`; `plugins.js`
renders their fields and submit buttons inside the Inspector, posts only
declared values to the active plugin action endpoint, and displays textual
results without accepting plugin-supplied HTML.
The Agent settings form persists reply `max_tokens` and the independent
`compaction_output_max_tokens` separately; the latter controls only context
summary responses and is applied when the next Agent lifecycle is materialized.
It also persists the 1–3600 second provider request timeout used by future
coordinator, worker, preview, compaction, and retrieval model calls.
Image drafts live in `components/image-composer.js`, isolated per Session and uploaded as raw bytes; only
`attachment_id` references are sent with a run, and the chat renderer shows durable image URLs (no inline
bytes). While a run is active the composer accepts text steering only and explicitly keeps (never drops)
image drafts for a later run. Agent Markdown is parsed and sanitized only by `components/markdown-renderer.js`;
the active `components/chat-view.js` uses it for both restored and streamed
Agent output. `chat.js` and `main.js` are legacy, unmounted modules and must
not introduce a second transcript renderer.

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
| [app.js](app.js#L16) | `applyTheme` | `theme: unknown` | `unknown` | Perform the browser runtime operation: apply theme. |
| [app.js](app.js#L25) | `initTheme` | `None` | `unknown` | Perform the browser runtime operation: init theme. |
| [app.js](app.js#L89) | `value` | `id: unknown` | `unknown` | Perform the browser runtime operation: value. |
| [app.js](app.js#L91) | `config` | `None` | `unknown` | Perform the browser runtime operation: config. |
| [app.js](app.js#L105) | `persistedFields` | `ids: unknown` | `unknown` | Perform the browser runtime operation: persisted fields. |
| [app.js](app.js#L106) | `profileSettings` | `overrides: unknown` | `unknown` | Perform the browser runtime operation: profile settings. |
| [app.js](app.js#L118) | `profilePayload` | `overrides: unknown` | `unknown` | Perform the browser runtime operation: profile payload. |
| [app.js](app.js#L119) | `profileUrl` | `None` | `unknown` | Perform the browser runtime operation: profile url. |
| [app.js](app.js#L120) | `applyProfile` | `profile: unknown` | `unknown` | Perform the browser runtime operation: apply profile. |
| [app.js](app.js#L121) | `restoreSettings` | `None` | `Promise<unknown>` | Perform the browser runtime operation: restore settings. |
| [app.js](app.js#L122) | `persistSettings` | `None` | `Promise<unknown>` | Perform the browser runtime operation: persist settings. |
| [app.js](app.js#L123) | `bindSettingsPersistence` | `None` | `unknown` | Perform the browser runtime operation: bind settings persistence. |
| [app.js](app.js#L135) | `loadToolRegistry` | `None` | `Promise<unknown>` | Perform the browser runtime operation: load tool registry. |
| [app.js](app.js#L146) | `renderToolPermissions` | `policy: unknown` | `unknown` | Perform the browser runtime operation: render tool permissions. |
| [app.js](app.js#L173) | `setStatus` | `text: unknown, state: unknown` | `unknown` | Perform the browser runtime operation: set status. |
| [app.js](app.js#L174) | `providerLabel` | `provider: unknown` | `unknown` | Perform the browser runtime operation: provider label. |
| [app.js](app.js#L175) | `updateProviderHint` | `None` | `unknown` | Perform the browser runtime operation: update provider hint. |
| [app.js](app.js#L176) | `applyProviderPreset` | `None` | `unknown` | Perform the browser runtime operation: apply provider preset. |
| [app.js](app.js#L177) | `updateModelSummary` | `None` | `unknown` | Perform the browser runtime operation: update model summary. |
| [app.js](app.js#L179) | `selectedMemorySessions` | `None` | `unknown` | Perform the browser runtime operation: selected memory sessions. |
| [app.js](app.js#L181) | `renderMemorySessionPicker` | `None` | `unknown` | Perform the browser runtime operation: render memory session picker. |
| [app.js](app.js#L196) | `liveTools` | `data: unknown` | `unknown` | Perform the browser runtime operation: live tools. |
| [app.js](app.js#L199) | `appendMessage` | `role: unknown, content: unknown, reasoning: unknown, tools: unknown, agentName: unknown, usage: unknown, modelDurationMs: unknown, roundDurationMs: unknown, timestamp: unknown` | `unknown` | Perform the browser runtime operation: append message. |
| [app.js](app.js#L200) | `streamKey` | `agent: unknown, round: unknown` | `unknown` | Perform the browser runtime operation: stream key. |
| [app.js](app.js#L201) | `renderStreamDelta` | `agent: unknown, data: unknown` | `unknown` | Perform the browser runtime operation: render stream delta. |
| [app.js](app.js#L202) | `renderStreamTool` | `agent: unknown, data: unknown, status: unknown` | `unknown` | Perform the browser runtime operation: render stream tool. |
| [app.js](app.js#L203) | `discardStream` | `agent: unknown, round: unknown` | `unknown` | Perform the browser runtime operation: discard stream. |
| [app.js](app.js#L204) | `discardAgentStreams` | `agent: unknown` | `unknown` | Perform the browser runtime operation: discard agent streams. |
| [app.js](app.js#L206) | `appendRunErrorBlock` | `title: unknown, message: unknown, rawContent: unknown` | `unknown` | Perform the browser runtime operation: append run error block. |
| [app.js](app.js#L208) | `upsertSteering` | `record: unknown` | `unknown` | Perform the browser runtime operation: upsert steering. |
| [app.js](app.js#L211) | `messageForChat` | `message: unknown` | `unknown` | Perform the browser runtime operation: message for chat. |
| [app.js](app.js#L221) | `renderMessagesInto` | `messages: unknown, assistantLabel: unknown` | `unknown` | Perform the browser runtime operation: render messages into. |
| [app.js](app.js#L223) | `ensureLoadMoreMessagesButton` | `None` | `unknown` | Perform the browser runtime operation: ensure load more messages button. |
| [app.js](app.js#L224) | `setMessageHistoryButton` | `hasMore: unknown, text: unknown` | `unknown` | Perform the browser runtime operation: set message history button. |
| [app.js](app.js#L225) | `loadAllAgentBehavior` | `snapshot: unknown` | `Promise<unknown>` | Perform the browser runtime operation: load all agent behavior. |
| [app.js](app.js#L226) | `trace` | `title: unknown, message: unknown, data: unknown, kind: unknown` | `unknown` | Perform the browser runtime operation: trace. |
| [app.js](app.js#L227) | `tracePayload` | `event: unknown, position: unknown` | `unknown` | Perform the browser runtime operation: trace payload. |
| [app.js](app.js#L229) | `openMcpApproval` | `event: unknown` | `unknown` | Perform the browser runtime operation: open mcp approval. |
| [app.js](app.js#L231) | `answerMcpApproval` | `None` | `Promise<unknown>` | Perform the browser runtime operation: answer mcp approval. |
| [app.js](app.js#L232) | `updateHeaderMetrics` | `data: unknown` | `unknown` | Perform the browser runtime operation: update header metrics. |
| [app.js](app.js#L233) | `setRunning` | `running: unknown` | `unknown` | Perform the browser runtime operation: set running. |
| [app.js](app.js#L236) | `setSteerStatus` | `text: unknown, state: unknown` | `unknown` | Perform the browser runtime operation: set steer status. |
| [app.js](app.js#L237) | `sendSteer` | `message: unknown` | `Promise<unknown>` | Perform the browser runtime operation: send steer. |
| [app.js](app.js#L238) | `apiJson` | `path: unknown` | `Promise<unknown>` | Perform the browser runtime operation: api json. |
| [app.js](app.js#L239) | `apiPost` | `path: unknown, body: unknown` | `Promise<unknown>` | Perform the browser runtime operation: api post. |
| [app.js](app.js#L240) | `apiPut` | `path: unknown, body: unknown` | `Promise<unknown>` | Perform the browser runtime operation: api put. |
| [app.js](app.js#L242) | `setWorkspaceIndicator` | `id: unknown, status: unknown` | `unknown` | Perform the browser runtime operation: set workspace indicator. |
| [app.js](app.js#L243) | `loadWorkspaces` | `selected: unknown` | `Promise<unknown>` | Perform the browser runtime operation: load workspaces. |
| [app.js](app.js#L244) | `applyConnector` | `connector: unknown` | `unknown` | Perform the browser runtime operation: apply connector. |
| [app.js](app.js#L245) | `loadConnectors` | `selected: unknown` | `Promise<unknown>` | Perform the browser runtime operation: load connectors. |
| [app.js](app.js#L246) | `connectorPayload` | `name: unknown` | `unknown` | Perform the browser runtime operation: connector payload. |
| [app.js](app.js#L248) | `connectorFeedback` | `text: unknown, state: unknown` | `unknown` | Perform the browser runtime operation: connector feedback. |
| [app.js](app.js#L250) | `createConnector` | `name: unknown` | `Promise<unknown>` | Perform the browser runtime operation: create connector. |
| [app.js](app.js#L252) | `saveSelectedConnector` | `None` | `Promise<unknown>` | Perform the browser runtime operation: save selected connector. |
| [app.js](app.js#L254) | `openConnectorDialog` | `None` | `unknown` | Perform the browser runtime operation: open connector dialog. |
| [app.js](app.js#L255) | `openSettings` | `section: unknown` | `unknown` | Perform the browser runtime operation: open settings. |
| [app.js](app.js#L256) | `openAgentProfile` | `targetSessionId: unknown` | `Promise<unknown>` | Perform the browser runtime operation: open agent profile. |
| [app.js](app.js#L257) | `showSettingsSection` | `section: unknown` | `unknown` | Perform the browser runtime operation: show settings section. |
| [app.js](app.js#L258) | `setPluginFeedback` | `text: unknown, state: unknown` | `unknown` | Perform the browser runtime operation: set plugin feedback. |
| [app.js](app.js#L259) | `pluginStateLabel` | `state: unknown` | `unknown` | Perform the browser runtime operation: plugin state label. |
| [app.js](app.js#L260) | `pluginSettingsRegistration` | `name: unknown` | `unknown` | Perform the browser runtime operation: plugin settings registration. |
| [app.js](app.js#L261) | `pluginKey` | `plugin: unknown` | `unknown` | Perform the browser runtime operation: plugin key. |
| [app.js](app.js#L262) | `renderPluginStatusList` | `None` | `unknown` | Perform the browser runtime operation: render plugin status list. |
| [app.js](app.js#L263) | `loadPluginStatuses` | `None` | `Promise<unknown>` | Perform the browser runtime operation: load plugin statuses. |
| [app.js](app.js#L264) | `pluginPermissionLabel` | `permission: unknown` | `unknown` | Perform the browser runtime operation: plugin permission label. |
| [app.js](app.js#L265) | `pluginPermissionsNote` | `plugin: unknown` | `unknown` | Perform the browser runtime operation: plugin permissions note. |
| [app.js](app.js#L266) | `pluginLifecycleControls` | `plugin: unknown` | `unknown` | Perform the browser runtime operation: plugin lifecycle controls. |
| [app.js](app.js#L267) | `bindPluginLifecycleControls` | `plugin: unknown` | `unknown` | Perform the browser runtime operation: bind plugin lifecycle controls. |
| [app.js](app.js#L268) | `pluginThemeControls` | `plugin: unknown` | `unknown` | Perform the browser runtime operation: plugin theme controls. |
| [app.js](app.js#L269) | `renderPluginSettingsFields` | `schema: unknown, settings: unknown` | `unknown` | Perform the browser runtime operation: render plugin settings fields. |
| [app.js](app.js#L270) | `bindPluginTheme` | `plugin: unknown` | `unknown` | Perform the browser runtime operation: bind plugin theme. |
| [app.js](app.js#L271) | `renderPluginDetail` | `plugin: unknown, payload: unknown` | `unknown` | Perform the browser runtime operation: render plugin detail. |
| [app.js](app.js#L272) | `selectPluginSettings` | `key: unknown` | `Promise<unknown>` | Perform the browser runtime operation: select plugin settings. |
| [app.js](app.js#L273) | `savePluginSettings` | `event: unknown, plugin: unknown, schema: unknown` | `Promise<unknown>` | Perform the browser runtime operation: save plugin settings. |
| [app.js](app.js#L274) | `changePluginLifecycle` | `plugin: unknown, action: unknown` | `Promise<unknown>` | Perform the browser runtime operation: change plugin lifecycle. |
| [app.js](app.js#L276) | `setMcpFeedback` | `text: unknown, state: unknown` | `unknown` | Perform the browser runtime operation: set mcp feedback. |
| [app.js](app.js#L278) | `mcpKeyValues` | `id: unknown` | `unknown` | Perform the browser runtime operation: mcp key values. |
| [app.js](app.js#L280) | `updateMcpTransportFields` | `None` | `unknown` | Perform the browser runtime operation: update mcp transport fields. |
| [app.js](app.js#L282) | `resetMcpForm` | `None` | `unknown` | Perform the browser runtime operation: reset mcp form. |
| [app.js](app.js#L284) | `selectMcpServer` | `serverId: unknown` | `unknown` | Perform the browser runtime operation: select mcp server. |
| [app.js](app.js#L286) | `loadMcpConsole` | `None` | `Promise<unknown>` | Perform the browser runtime operation: load mcp console. |
| [app.js](app.js#L288) | `saveMcpBinding` | `serverId: unknown` | `Promise<unknown>` | Perform the browser runtime operation: save mcp binding. |
| [app.js](app.js#L290) | `saveMcpServer` | `event: unknown` | `Promise<unknown>` | Perform the browser runtime operation: save mcp server. |
| [app.js](app.js#L291) | `sessionApi` | `path: unknown, selectedSession: unknown` | `unknown` | Perform the browser runtime operation: session api. |
| [app.js](app.js#L292) | `planUrl` | `None` | `unknown` | Perform the browser runtime operation: plan url. |
| [app.js](app.js#L293) | `messagesUrl` | `before: unknown, selectedSession: unknown, agent: unknown, limit: unknown` | `unknown` | Perform the browser runtime operation: messages url. |
| [app.js](app.js#L294) | `graphUrl` | `None` | `unknown` | Perform the browser runtime operation: graph url. |
| [app.js](app.js#L295) | `graphEventsUrl` | `cursor: unknown` | `unknown` | Perform the browser runtime operation: graph events url. |
| [app.js](app.js#L296) | `lifecycleEventsUrl` | `cursor: unknown` | `unknown` | Perform the browser runtime operation: lifecycle events url. |
| [app.js](app.js#L297) | `workflowUrl` | `None` | `unknown` | Perform the browser runtime operation: workflow url. |
| [app.js](app.js#L298) | `runNode` | `agentId: unknown` | `unknown` | Perform the browser runtime operation: run node. |
| [app.js](app.js#L299) | `agentIcon` | `agent: unknown` | `unknown` | Perform the browser runtime operation: agent icon. |
| [app.js](app.js#L300) | `acknowledgementKey` | `None` | `unknown` | Perform the browser runtime operation: acknowledgement key. |
| [app.js](app.js#L301) | `acknowledgedAgents` | `None` | `unknown` | Perform the browser runtime operation: acknowledged agents. |
| [app.js](app.js#L303) | `agentStateView` | `agentId: unknown, agents: unknown` | `unknown` | Perform the browser runtime operation: agent state view. |
| [app.js](app.js#L328) | `stateLabel` | `state: unknown` | `unknown` | Perform the browser runtime operation: state label. |
| [app.js](app.js#L330) | `stateView` | `canonical: unknown, message: unknown, agentId: unknown` | `unknown` | Perform the browser runtime operation: state view. |
| [app.js](app.js#L331) | `agentRunState` | `agentId: unknown, agents: unknown` | `unknown` | Perform the browser runtime operation: agent run state. |
| [app.js](app.js#L333) | `updateStopAvailability` | `None` | `unknown` | Perform the browser runtime operation: update stop availability. |
| [app.js](app.js#L334) | `acknowledgeAgent` | `agentId: unknown` | `unknown` | Perform the browser runtime operation: acknowledge agent. |
| [app.js](app.js#L336) | `agentCard` | `agent: unknown, selected: unknown, tone: unknown, icon: unknown, subtitle: unknown, view: unknown, title: unknown` | `unknown` | Perform the browser runtime operation: agent card. |
| [app.js](app.js#L340) | `renderAgentSelector` | `agents: unknown` | `unknown` | Perform the browser runtime operation: render agent selector. |
| [app.js](app.js#L343) | `contextNodeTone` | `type: unknown` | `unknown` | Perform the browser runtime operation: context node tone. |
| [app.js](app.js#L345) | `renderContextGraphDetail` | `graph: unknown, nodeId: unknown` | `unknown` | Perform the browser runtime operation: render context graph detail. |
| [app.js](app.js#L356) | `renderContextGraph` | `payload: unknown` | `unknown` | Perform the browser runtime operation: render context graph. |
| [app.js](app.js#L388) | `contextDialogChrome` | `tab: unknown` | `unknown` | Perform the browser runtime operation: context dialog chrome. |
| [app.js](app.js#L406) | `selectContextDialogTab` | `tab: unknown` | `unknown` | Perform the browser runtime operation: select context dialog tab. |
| [app.js](app.js#L425) | `decodePromptText` | `value: unknown` | `unknown` | Perform the browser runtime operation: decode prompt text. |
| [app.js](app.js#L427) | `readablePromptValue` | `value: unknown, indent: unknown` | `unknown` | Perform the browser runtime operation: readable prompt value. |
| [app.js](app.js#L429) | `renderContextPrompt` | `payload: unknown` | `unknown` | Perform the browser runtime operation: render context prompt. |
| [app.js](app.js#L439) | `loadContextPrompt` | `agentId: unknown` | `Promise<unknown>` | Perform the browser runtime operation: load context prompt. |
| [app.js](app.js#L441) | `renderCompactionInput` | `payload: unknown` | `unknown` | Perform the browser runtime operation: render compaction input. |
| [app.js](app.js#L450) | `loadCompactionInput` | `agentId: unknown` | `Promise<unknown>` | Perform the browser runtime operation: load compaction input. |
| [app.js](app.js#L464) | `ensureContextDialogTab` | `tab: unknown` | `unknown` | Perform the browser runtime operation: ensure context dialog tab. |
| [app.js](app.js#L472) | `openAgentContextInspector` | `agentId: unknown` | `Promise<unknown>` | Perform the browser runtime operation: open agent context inspector. |
| [app.js](app.js#L482) | `hasSelectedSession` | `None` | `unknown` | Perform the browser runtime operation: has selected session. |
| [app.js](app.js#L483) | `renderInspectorEmpty` | `message: unknown` | `unknown` | Perform the browser runtime operation: render inspector empty. |
| [app.js](app.js#L484) | `loadAgents` | `None` | `Promise<unknown>` | Perform the browser runtime operation: load agents. |
| [app.js](app.js#L485) | `selectAgent` | `agentId: unknown` | `Promise<unknown>` | Perform the browser runtime operation: select agent. |
| [app.js](app.js#L486) | `renderGraph` | `graph: unknown` | `unknown` | Perform the browser runtime operation: render graph. |
| [app.js](app.js#L488) | `loadGraph` | `None` | `Promise<unknown>` | Perform the browser runtime operation: load graph. |
| [app.js](app.js#L490) | `traceUrl` | `cursor: unknown` | `unknown` | Perform the browser runtime operation: trace url. |
| [app.js](app.js#L492) | `isTraceVisible` | `event: unknown` | `unknown` | Perform the browser runtime operation: is trace visible. |
| [app.js](app.js#L498) | `loadTrace` | `reset: unknown` | `Promise<unknown>` | Perform the browser runtime operation: load trace. |
| [app.js](app.js#L499) | `agentContextStats` | `agent: unknown` | `unknown` | Perform the browser runtime operation: agent context stats. |
| [app.js](app.js#L522) | `renderAgentTopology` | `agents: unknown, graph: unknown` | `unknown` | Perform the browser runtime operation: render agent topology. |
| [app.js](app.js#L537) | `loadInspectorAgents` | `None` | `Promise<unknown>` | Perform the browser runtime operation: load inspector agents. |
| [app.js](app.js#L538) | `graphEditUrl` | `None` | `unknown` | Perform the browser runtime operation: graph edit url. |
| [app.js](app.js#L540) | `graphEditFeedback` | `text: unknown, state: unknown` | `unknown` | Perform the browser runtime operation: graph edit feedback. |
| [app.js](app.js#L542) | `loadGraphEditInfo` | `None` | `Promise<unknown>` | Perform the browser runtime operation: load graph edit info. |
| [app.js](app.js#L545) | `setDisabled` | `list: unknown, disabled: unknown` | `unknown` | Perform the browser runtime operation: set disabled. |
| [app.js](app.js#L559) | `graphAddAgent` | `None` | `Promise<unknown>` | Perform the browser runtime operation: graph add agent. |
| [app.js](app.js#L568) | `graphConnect` | `None` | `Promise<unknown>` | Perform the browser runtime operation: graph connect. |
| [app.js](app.js#L577) | `graphRemoveAgent` | `None` | `Promise<unknown>` | Perform the browser runtime operation: graph remove agent. |
| [app.js](app.js#L589) | `graphDisconnect` | `None` | `Promise<unknown>` | Perform the browser runtime operation: graph disconnect. |
| [app.js](app.js#L600) | `graphSetMapper` | `None` | `Promise<unknown>` | Perform the browser runtime operation: graph set mapper. |
| [app.js](app.js#L608) | `graphSetRouter` | `None` | `Promise<unknown>` | Perform the browser runtime operation: graph set router. |
| [app.js](app.js#L617) | `usageCells` | `usage: unknown, run: unknown` | `unknown` | Perform the browser runtime operation: usage cells. |
| [app.js](app.js#L618) | `value` | `key: unknown` | `unknown` | Perform the browser runtime operation: value. |
| [app.js](app.js#L627) | `loadUsage` | `None` | `Promise<unknown>` | Perform the browser runtime operation: load usage. |
| [app.js](app.js#L628) | `selectInspectorPanel` | `panel: unknown, refresh: unknown` | `unknown` | Perform the browser runtime operation: select inspector panel. |
| [app.js](app.js#L629) | `initInspectorTabs` | `None` | `unknown` | Perform the browser runtime operation: init inspector tabs. |
| [app.js](app.js#L630) | `knownPlanAgents` | `None` | `unknown` | Perform the browser runtime operation: known plan agents. |
| [app.js](app.js#L631) | `renderPlanAgentPicker` | `None` | `unknown` | Perform the browser runtime operation: render plan agent picker. |
| [app.js](app.js#L632) | `loadPlan` | `None` | `Promise<unknown>` | Perform the browser runtime operation: load plan. |
| [app.js](app.js#L634) | `loadHistory` | `None` | `Promise<unknown>` | Perform the browser runtime operation: load history. |
| [app.js](app.js#L665) | `loadOlderMessages` | `None` | `Promise<unknown>` | Perform the browser runtime operation: load older messages. |
| [app.js](app.js#L699) | `rehydrateSelectedView` | `options: object` | `Promise<unknown>` | Perform the browser runtime operation: rehydrate selected view. |
| [app.js](app.js#L700) | `switchSession` | `selected: unknown` | `Promise<unknown>` | Perform the browser runtime operation: switch session. |
| [app.js](app.js#L701) | `start` | `message: unknown, images: unknown, targetSession: unknown` | `Promise<unknown>` | Perform the browser runtime operation: start. |
| [app.js](app.js#L721) | `showCompactStatus` | `text: unknown, state: unknown, dismissMs: unknown` | `unknown` | Perform the browser runtime operation: show compact status. |
| [app.js](app.js#L727) | `clearCompactStatus` | `None` | `unknown` | Perform the browser runtime operation: clear compact status. |
| [app.js](app.js#L729) | `debounce` | `fn: unknown, wait: unknown` | `unknown` | Perform the browser runtime operation: debounce. |
| [app.js](app.js#L740) | `pushTraceEvent` | `event: unknown` | `unknown` | Perform the browser runtime operation: push trace event. |
| [app.js](app.js#L745) | `indexTraceEvent` | `event: unknown` | `unknown` | Perform the browser runtime operation: index trace event. |
| [app.js](app.js#L751) | `rebuildTraceEventIndex` | `None` | `unknown` | Perform the browser runtime operation: rebuild trace event index. |
| [app.js](app.js#L762) | `handleEvent` | `event: unknown` | `unknown` | Perform the browser runtime operation: handle event. |
| [app.js](app.js#L792) | `finish` | `None` | `unknown` | Perform the browser runtime operation: finish. |
| [app.js](app.js#L794) | `showSlashHelp` | `None` | `unknown` | Perform the browser runtime operation: show slash help. |
| [app.js](app.js#L815) | `sessionByName` | `name: unknown` | `unknown` | Perform the browser runtime operation: session by name. |
| [app.js](app.js#L816) | `switchSessionByName` | `name: unknown` | `Promise<unknown>` | Perform the browser runtime operation: switch session by name. |
| [app.js](app.js#L817) | `deleteSessionByName` | `name: unknown` | `Promise<unknown>` | Perform the browser runtime operation: delete session by name. |
| [app.js](app.js#L818) | `runStop` | `None` | `Promise<unknown>` | Perform the browser runtime operation: run stop. |
| [app.js](app.js#L819) | `runForceStop` | `None` | `Promise<unknown>` | Perform the browser runtime operation: run force stop. |
| [app.js](app.js#L821) | `runCompact` | `agent: unknown` | `Promise<unknown>` | Perform the browser runtime operation: run compact. |
| [app.js](app.js#L838) | `handleCompactStage` | `record: unknown, startedSession: unknown` | `unknown` | Perform the browser runtime operation: handle compact stage. |
| [app.js](app.js#L862) | `dispatchSlashCommand` | `parsed: unknown` | `unknown` | Perform the browser runtime operation: dispatch slash command. |
| [app.js](app.js#L870) | `resizeComposer` | `None` | `unknown` | Perform the browser runtime operation: resize composer. |
| [app.js](app.js#L871) | `applyRunGraphEvent` | `event: unknown` | `unknown` | Perform the browser runtime operation: apply run graph event. |
| [app.js](app.js#L872) | `handleRunGraphEvent` | `event: unknown` | `unknown` | Perform the browser runtime operation: handle run graph event. |
| [app.js](app.js#L873) | `connectRunGraphEvents` | `None` | `unknown` | Perform the browser runtime operation: connect run graph events. |
| [app.js](app.js#L874) | `connectLifecycleEvents` | `None` | `unknown` | Perform the browser runtime operation: connect lifecycle events. |
| [app.js](app.js#L875) | `restoreRunState` | `None` | `Promise<unknown>` | Perform the browser runtime operation: restore run state. |
| [app.js](app.js#L904) | `pickWorkspaceDirectory` | `None` | `Promise<unknown>` | Perform the browser runtime operation: pick workspace directory. |
| [app.js](app.js#L905) | `createAndSwitchSession` | `name: unknown, projectPath: unknown` | `Promise<unknown>` | Perform the browser runtime operation: create and switch session. |
| [app.js](app.js#L991) | `loadProviders` | `None` | `Promise<unknown>` | Perform the browser runtime operation: load providers. |
| [app.js](app.js#L992) | `initializeConsole` | `None` | `Promise<unknown>` | Perform the browser runtime operation: initialize console. |
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
| [external-agents.js](external-agents.js#L3) | `$` | `id: unknown` | `unknown` | Perform the browser runtime operation: $. |
| [external-agents.js](external-agents.js#L6) | `request` | `path: unknown, options: unknown` | `Promise<unknown>` | Perform the browser runtime operation: request. |
| [external-agents.js](external-agents.js#L8) | `feedback` | `message: unknown, kind: unknown` | `unknown` | Perform the browser runtime operation: feedback. |
| [external-agents.js](external-agents.js#L10) | `button` | `label: unknown, handler: unknown, disabled: unknown` | `unknown` | Perform the browser runtime operation: button. |
| [external-agents.js](external-agents.js#L12) | `renderProviders` | `None` | `unknown` | Perform the browser runtime operation: render providers. |
| [external-agents.js](external-agents.js#L23) | `loadProviders` | `None` | `Promise<unknown>` | Perform the browser runtime operation: load providers. |
| [external-agents.js](external-agents.js#L25) | `autoDetectProviders` | `None` | `Promise<unknown>` | Perform the browser runtime operation: auto detect providers. |
| [external-agents.js](external-agents.js#L27) | `selectProvider` | `providerId: unknown` | `unknown` | Perform the browser runtime operation: select provider. |
| [external-agents.js](external-agents.js#L32) | `discoverSessions` | `None` | `Promise<unknown>` | Perform the browser runtime operation: discover sessions. |
| [external-agents.js](external-agents.js#L34) | `renderSessions` | `None` | `unknown` | Perform the browser runtime operation: render sessions. |
| [external-agents.js](external-agents.js#L36) | `reviewDiscoveredSession` | `session: unknown` | `unknown` | Perform the browser runtime operation: review discovered session. |
| [external-agents.js](external-agents.js#L38) | `readTranscriptFile` | `None` | `Promise<unknown>` | Perform the browser runtime operation: read transcript file. |
| [external-agents.js](external-agents.js#L40) | `previewFileImport` | `None` | `Promise<unknown>` | Perform the browser runtime operation: preview file import. |
| [external-agents.js](external-agents.js#L42) | `renderReport` | `report: unknown` | `unknown` | Perform the browser runtime operation: render report. |
| [external-agents.js](external-agents.js#L44) | `commitImport` | `None` | `Promise<unknown>` | Perform the browser runtime operation: commit import. |
| [external-agents.js](external-agents.js#L46) | `chooseImportDirectory` | `None` | `Promise<unknown>` | Perform the browser runtime operation: choose import directory. |
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
| [plugins.js](plugins.js#L146) | `unloadPlugin` | `pluginName: unknown` | `unknown` | Perform the browser runtime operation: unload plugin. |
| [plugins.js](plugins.js#L167) | `_panelContainers` | `None` | `unknown` | Perform the browser runtime operation: panel containers. |
| [plugins.js](plugins.js#L174) | `_fillPanel` | `body: unknown, render: unknown` | `unknown` | Perform the browser runtime operation: fill panel. |
| [plugins.js](plugins.js#L184) | `_renderPanel` | `registration: unknown` | `unknown` | Perform the browser runtime operation: render panel. |
| [plugins.js](plugins.js#L234) | `_panelFieldControl` | `field: unknown` | `unknown` | Perform the browser runtime operation: panel field control. |
| [plugins.js](plugins.js#L280) | `_panelFieldValue` | `field: unknown, control: unknown` | `unknown` | Perform the browser runtime operation: panel field value. |
| [plugins.js](plugins.js#L288) | `_registerDeclarativePanel` | `plugin: unknown, panel: unknown` | `unknown` | Perform the browser runtime operation: register declarative panel. |
| [plugins.js](plugins.js#L347) | `_bindPanelTabs` | `None` | `unknown` | Perform the browser runtime operation: bind panel tabs. |
| [plugins.js](plugins.js#L367) | `_createBridge` | `None` | `unknown` | Perform the browser runtime operation: create bridge. |
| [plugins.js](plugins.js#L487) | `loadPlugins` | `None` | `Promise<unknown>` | Perform the browser runtime operation: load plugins. |
| [plugins.js](plugins.js#L525) | `initPlugins` | `None` | `Promise<unknown>` | Perform the browser runtime operation: init plugins. |
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
