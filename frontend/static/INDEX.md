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
| Start/stop | `start`, stop controls | `/api/runs` |
| Attach/send image | `createImageComposer` upload, `beginSend` | `/api/sessions/{id}/attachments/images`, `/api/runs` |
| Inspector graph/plan/trace/usage/context | `loadGraph`, `loadPlan`, `loadTrace`, `loadUsage`, context dialog | `/api/sessions/{id}/…` |

Graph removal uses the mounted contracts: Agent removal uses the path identity
route, while connection removal sends its typed source/target JSON body.
The permissions panel exposes only the registered Session-console tools; both
its category and individual Tool switches control actual model tool schemas.

`app.js` must refresh `availableSessions` after creation before membership
validation; otherwise a successful POST appears as an “unknown session”.
Its SSE cursor is an event count maintained separately from the journal byte
offset used by Trace pagination, so reconnects never mix two cursor domains.
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
| [app.js](app.js#L83) | `value` | `id: unknown` | `unknown` | Perform the browser runtime operation: value. |
| [app.js](app.js#L85) | `config` | `None` | `unknown` | Perform the browser runtime operation: config. |
| [app.js](app.js#L99) | `persistedFields` | `ids: unknown` | `unknown` | Perform the browser runtime operation: persisted fields. |
| [app.js](app.js#L100) | `profileSettings` | `overrides: unknown` | `unknown` | Perform the browser runtime operation: profile settings. |
| [app.js](app.js#L112) | `profilePayload` | `overrides: unknown` | `unknown` | Perform the browser runtime operation: profile payload. |
| [app.js](app.js#L113) | `profileUrl` | `None` | `unknown` | Perform the browser runtime operation: profile url. |
| [app.js](app.js#L114) | `applyProfile` | `profile: unknown` | `unknown` | Perform the browser runtime operation: apply profile. |
| [app.js](app.js#L115) | `restoreSettings` | `None` | `Promise<unknown>` | Perform the browser runtime operation: restore settings. |
| [app.js](app.js#L116) | `persistSettings` | `None` | `Promise<unknown>` | Perform the browser runtime operation: persist settings. |
| [app.js](app.js#L117) | `bindSettingsPersistence` | `None` | `unknown` | Perform the browser runtime operation: bind settings persistence. |
| [app.js](app.js#L129) | `loadToolRegistry` | `None` | `Promise<unknown>` | Perform the browser runtime operation: load tool registry. |
| [app.js](app.js#L140) | `renderToolPermissions` | `policy: unknown` | `unknown` | Perform the browser runtime operation: render tool permissions. |
| [app.js](app.js#L167) | `setStatus` | `text: unknown, state: unknown` | `unknown` | Perform the browser runtime operation: set status. |
| [app.js](app.js#L168) | `providerLabel` | `provider: unknown` | `unknown` | Perform the browser runtime operation: provider label. |
| [app.js](app.js#L169) | `updateProviderHint` | `None` | `unknown` | Perform the browser runtime operation: update provider hint. |
| [app.js](app.js#L170) | `applyProviderPreset` | `None` | `unknown` | Perform the browser runtime operation: apply provider preset. |
| [app.js](app.js#L171) | `updateModelSummary` | `None` | `unknown` | Perform the browser runtime operation: update model summary. |
| [app.js](app.js#L173) | `selectedMemorySessions` | `None` | `unknown` | Perform the browser runtime operation: selected memory sessions. |
| [app.js](app.js#L175) | `renderMemorySessionPicker` | `None` | `unknown` | Perform the browser runtime operation: render memory session picker. |
| [app.js](app.js#L190) | `liveTools` | `data: unknown` | `unknown` | Perform the browser runtime operation: live tools. |
| [app.js](app.js#L193) | `appendMessage` | `role: unknown, content: unknown, reasoning: unknown, tools: unknown, agentName: unknown, usage: unknown, modelDurationMs: unknown, roundDurationMs: unknown, timestamp: unknown` | `unknown` | Perform the browser runtime operation: append message. |
| [app.js](app.js#L194) | `streamKey` | `agent: unknown, round: unknown` | `unknown` | Perform the browser runtime operation: stream key. |
| [app.js](app.js#L195) | `renderStreamDelta` | `agent: unknown, data: unknown` | `unknown` | Perform the browser runtime operation: render stream delta. |
| [app.js](app.js#L196) | `discardStream` | `agent: unknown, round: unknown` | `unknown` | Perform the browser runtime operation: discard stream. |
| [app.js](app.js#L198) | `appendRunErrorBlock` | `title: unknown, message: unknown, rawContent: unknown` | `unknown` | Perform the browser runtime operation: append run error block. |
| [app.js](app.js#L200) | `upsertSteering` | `record: unknown` | `unknown` | Perform the browser runtime operation: upsert steering. |
| [app.js](app.js#L203) | `messageForChat` | `message: unknown` | `unknown` | Perform the browser runtime operation: message for chat. |
| [app.js](app.js#L213) | `renderMessagesInto` | `messages: unknown, assistantLabel: unknown` | `unknown` | Perform the browser runtime operation: render messages into. |
| [app.js](app.js#L215) | `ensureLoadMoreMessagesButton` | `None` | `unknown` | Perform the browser runtime operation: ensure load more messages button. |
| [app.js](app.js#L216) | `setMessageHistoryButton` | `hasMore: unknown, text: unknown` | `unknown` | Perform the browser runtime operation: set message history button. |
| [app.js](app.js#L217) | `loadAllAgentBehavior` | `snapshot: unknown` | `Promise<unknown>` | Perform the browser runtime operation: load all agent behavior. |
| [app.js](app.js#L218) | `trace` | `title: unknown, message: unknown, data: unknown, kind: unknown` | `unknown` | Perform the browser runtime operation: trace. |
| [app.js](app.js#L219) | `tracePayload` | `event: unknown, position: unknown` | `unknown` | Perform the browser runtime operation: trace payload. |
| [app.js](app.js#L221) | `openMcpApproval` | `event: unknown` | `unknown` | Perform the browser runtime operation: open mcp approval. |
| [app.js](app.js#L223) | `answerMcpApproval` | `None` | `Promise<unknown>` | Perform the browser runtime operation: answer mcp approval. |
| [app.js](app.js#L224) | `updateHeaderMetrics` | `data: unknown` | `unknown` | Perform the browser runtime operation: update header metrics. |
| [app.js](app.js#L225) | `setRunning` | `running: unknown` | `unknown` | Perform the browser runtime operation: set running. |
| [app.js](app.js#L228) | `setSteerStatus` | `text: unknown, state: unknown` | `unknown` | Perform the browser runtime operation: set steer status. |
| [app.js](app.js#L229) | `sendSteer` | `message: unknown` | `Promise<unknown>` | Perform the browser runtime operation: send steer. |
| [app.js](app.js#L230) | `apiJson` | `path: unknown` | `Promise<unknown>` | Perform the browser runtime operation: api json. |
| [app.js](app.js#L231) | `apiPost` | `path: unknown, body: unknown` | `Promise<unknown>` | Perform the browser runtime operation: api post. |
| [app.js](app.js#L232) | `apiPut` | `path: unknown, body: unknown` | `Promise<unknown>` | Perform the browser runtime operation: api put. |
| [app.js](app.js#L234) | `setWorkspaceIndicator` | `id: unknown, status: unknown` | `unknown` | Perform the browser runtime operation: set workspace indicator. |
| [app.js](app.js#L235) | `loadWorkspaces` | `selected: unknown` | `Promise<unknown>` | Perform the browser runtime operation: load workspaces. |
| [app.js](app.js#L236) | `applyConnector` | `connector: unknown` | `unknown` | Perform the browser runtime operation: apply connector. |
| [app.js](app.js#L237) | `loadConnectors` | `selected: unknown` | `Promise<unknown>` | Perform the browser runtime operation: load connectors. |
| [app.js](app.js#L238) | `connectorPayload` | `name: unknown` | `unknown` | Perform the browser runtime operation: connector payload. |
| [app.js](app.js#L240) | `connectorFeedback` | `text: unknown, state: unknown` | `unknown` | Perform the browser runtime operation: connector feedback. |
| [app.js](app.js#L242) | `createConnector` | `name: unknown` | `Promise<unknown>` | Perform the browser runtime operation: create connector. |
| [app.js](app.js#L244) | `saveSelectedConnector` | `None` | `Promise<unknown>` | Perform the browser runtime operation: save selected connector. |
| [app.js](app.js#L246) | `openConnectorDialog` | `None` | `unknown` | Perform the browser runtime operation: open connector dialog. |
| [app.js](app.js#L247) | `openSettings` | `section: unknown` | `unknown` | Perform the browser runtime operation: open settings. |
| [app.js](app.js#L248) | `openAgentProfile` | `targetSessionId: unknown` | `Promise<unknown>` | Perform the browser runtime operation: open agent profile. |
| [app.js](app.js#L249) | `showSettingsSection` | `section: unknown` | `unknown` | Perform the browser runtime operation: show settings section. |
| [app.js](app.js#L250) | `setPluginFeedback` | `text: unknown, state: unknown` | `unknown` | Perform the browser runtime operation: set plugin feedback. |
| [app.js](app.js#L251) | `pluginStateLabel` | `state: unknown` | `unknown` | Perform the browser runtime operation: plugin state label. |
| [app.js](app.js#L252) | `pluginSettingsRegistration` | `name: unknown` | `unknown` | Perform the browser runtime operation: plugin settings registration. |
| [app.js](app.js#L253) | `pluginKey` | `plugin: unknown` | `unknown` | Perform the browser runtime operation: plugin key. |
| [app.js](app.js#L254) | `renderPluginStatusList` | `None` | `unknown` | Perform the browser runtime operation: render plugin status list. |
| [app.js](app.js#L255) | `loadPluginStatuses` | `None` | `Promise<unknown>` | Perform the browser runtime operation: load plugin statuses. |
| [app.js](app.js#L256) | `pluginPermissionLabel` | `permission: unknown` | `unknown` | Perform the browser runtime operation: plugin permission label. |
| [app.js](app.js#L257) | `pluginPermissionsNote` | `plugin: unknown` | `unknown` | Perform the browser runtime operation: plugin permissions note. |
| [app.js](app.js#L258) | `pluginLifecycleControls` | `plugin: unknown` | `unknown` | Perform the browser runtime operation: plugin lifecycle controls. |
| [app.js](app.js#L259) | `bindPluginLifecycleControls` | `plugin: unknown` | `unknown` | Perform the browser runtime operation: bind plugin lifecycle controls. |
| [app.js](app.js#L260) | `pluginThemeControls` | `plugin: unknown` | `unknown` | Perform the browser runtime operation: plugin theme controls. |
| [app.js](app.js#L261) | `renderPluginSettingsFields` | `schema: unknown, settings: unknown` | `unknown` | Perform the browser runtime operation: render plugin settings fields. |
| [app.js](app.js#L262) | `bindPluginTheme` | `plugin: unknown` | `unknown` | Perform the browser runtime operation: bind plugin theme. |
| [app.js](app.js#L263) | `renderPluginDetail` | `plugin: unknown, payload: unknown` | `unknown` | Perform the browser runtime operation: render plugin detail. |
| [app.js](app.js#L264) | `selectPluginSettings` | `key: unknown` | `Promise<unknown>` | Perform the browser runtime operation: select plugin settings. |
| [app.js](app.js#L265) | `savePluginSettings` | `event: unknown, plugin: unknown, schema: unknown` | `Promise<unknown>` | Perform the browser runtime operation: save plugin settings. |
| [app.js](app.js#L266) | `changePluginLifecycle` | `plugin: unknown, action: unknown` | `Promise<unknown>` | Perform the browser runtime operation: change plugin lifecycle. |
| [app.js](app.js#L268) | `setMcpFeedback` | `text: unknown, state: unknown` | `unknown` | Perform the browser runtime operation: set mcp feedback. |
| [app.js](app.js#L270) | `mcpKeyValues` | `id: unknown` | `unknown` | Perform the browser runtime operation: mcp key values. |
| [app.js](app.js#L272) | `updateMcpTransportFields` | `None` | `unknown` | Perform the browser runtime operation: update mcp transport fields. |
| [app.js](app.js#L274) | `resetMcpForm` | `None` | `unknown` | Perform the browser runtime operation: reset mcp form. |
| [app.js](app.js#L276) | `selectMcpServer` | `serverId: unknown` | `unknown` | Perform the browser runtime operation: select mcp server. |
| [app.js](app.js#L278) | `loadMcpConsole` | `None` | `Promise<unknown>` | Perform the browser runtime operation: load mcp console. |
| [app.js](app.js#L280) | `saveMcpBinding` | `serverId: unknown` | `Promise<unknown>` | Perform the browser runtime operation: save mcp binding. |
| [app.js](app.js#L282) | `saveMcpServer` | `event: unknown` | `Promise<unknown>` | Perform the browser runtime operation: save mcp server. |
| [app.js](app.js#L283) | `sessionApi` | `path: unknown, selectedSession: unknown` | `unknown` | Perform the browser runtime operation: session api. |
| [app.js](app.js#L284) | `planUrl` | `None` | `unknown` | Perform the browser runtime operation: plan url. |
| [app.js](app.js#L285) | `messagesUrl` | `before: unknown, selectedSession: unknown, agent: unknown` | `unknown` | Perform the browser runtime operation: messages url. |
| [app.js](app.js#L286) | `graphUrl` | `None` | `unknown` | Perform the browser runtime operation: graph url. |
| [app.js](app.js#L287) | `graphEventsUrl` | `cursor: unknown` | `unknown` | Perform the browser runtime operation: graph events url. |
| [app.js](app.js#L288) | `workflowUrl` | `None` | `unknown` | Perform the browser runtime operation: workflow url. |
| [app.js](app.js#L289) | `runNode` | `agentId: unknown` | `unknown` | Perform the browser runtime operation: run node. |
| [app.js](app.js#L290) | `agentIcon` | `agent: unknown` | `unknown` | Perform the browser runtime operation: agent icon. |
| [app.js](app.js#L291) | `acknowledgementKey` | `None` | `unknown` | Perform the browser runtime operation: acknowledgement key. |
| [app.js](app.js#L292) | `acknowledgedAgents` | `None` | `unknown` | Perform the browser runtime operation: acknowledged agents. |
| [app.js](app.js#L294) | `agentStateView` | `agentId: unknown, agents: unknown` | `unknown` | Perform the browser runtime operation: agent state view. |
| [app.js](app.js#L314) | `stateLabel` | `state: unknown` | `unknown` | Perform the browser runtime operation: state label. |
| [app.js](app.js#L316) | `stateView` | `canonical: unknown, message: unknown, agentId: unknown` | `unknown` | Perform the browser runtime operation: state view. |
| [app.js](app.js#L317) | `agentRunState` | `agentId: unknown, agents: unknown` | `unknown` | Perform the browser runtime operation: agent run state. |
| [app.js](app.js#L319) | `updateStopAvailability` | `None` | `unknown` | Perform the browser runtime operation: update stop availability. |
| [app.js](app.js#L320) | `acknowledgeAgent` | `agentId: unknown` | `unknown` | Perform the browser runtime operation: acknowledge agent. |
| [app.js](app.js#L322) | `agentCard` | `agent: unknown, selected: unknown, tone: unknown, icon: unknown, subtitle: unknown, view: unknown, title: unknown` | `unknown` | Perform the browser runtime operation: agent card. |
| [app.js](app.js#L326) | `renderAgentSelector` | `agents: unknown` | `unknown` | Perform the browser runtime operation: render agent selector. |
| [app.js](app.js#L329) | `contextNodeTone` | `type: unknown` | `unknown` | Perform the browser runtime operation: context node tone. |
| [app.js](app.js#L331) | `renderContextGraphDetail` | `graph: unknown, nodeId: unknown` | `unknown` | Perform the browser runtime operation: render context graph detail. |
| [app.js](app.js#L342) | `renderContextGraph` | `payload: unknown` | `unknown` | Perform the browser runtime operation: render context graph. |
| [app.js](app.js#L374) | `contextDialogChrome` | `tab: unknown` | `unknown` | Perform the browser runtime operation: context dialog chrome. |
| [app.js](app.js#L392) | `selectContextDialogTab` | `tab: unknown` | `unknown` | Perform the browser runtime operation: select context dialog tab. |
| [app.js](app.js#L411) | `decodePromptText` | `value: unknown` | `unknown` | Perform the browser runtime operation: decode prompt text. |
| [app.js](app.js#L413) | `readablePromptValue` | `value: unknown, indent: unknown` | `unknown` | Perform the browser runtime operation: readable prompt value. |
| [app.js](app.js#L415) | `renderContextPrompt` | `payload: unknown` | `unknown` | Perform the browser runtime operation: render context prompt. |
| [app.js](app.js#L425) | `loadContextPrompt` | `agentId: unknown` | `Promise<unknown>` | Perform the browser runtime operation: load context prompt. |
| [app.js](app.js#L427) | `renderCompactionInput` | `payload: unknown` | `unknown` | Perform the browser runtime operation: render compaction input. |
| [app.js](app.js#L436) | `loadCompactionInput` | `agentId: unknown` | `Promise<unknown>` | Perform the browser runtime operation: load compaction input. |
| [app.js](app.js#L446) | `openAgentContextInspector` | `agentId: unknown` | `Promise<unknown>` | Perform the browser runtime operation: open agent context inspector. |
| [app.js](app.js#L462) | `hasSelectedSession` | `None` | `unknown` | Perform the browser runtime operation: has selected session. |
| [app.js](app.js#L463) | `renderInspectorEmpty` | `message: unknown` | `unknown` | Perform the browser runtime operation: render inspector empty. |
| [app.js](app.js#L464) | `loadAgents` | `None` | `Promise<unknown>` | Perform the browser runtime operation: load agents. |
| [app.js](app.js#L465) | `selectAgent` | `agentId: unknown` | `Promise<unknown>` | Perform the browser runtime operation: select agent. |
| [app.js](app.js#L466) | `renderGraph` | `graph: unknown` | `unknown` | Perform the browser runtime operation: render graph. |
| [app.js](app.js#L468) | `loadGraph` | `None` | `Promise<unknown>` | Perform the browser runtime operation: load graph. |
| [app.js](app.js#L470) | `traceUrl` | `cursor: unknown` | `unknown` | Perform the browser runtime operation: trace url. |
| [app.js](app.js#L472) | `isTraceVisible` | `event: unknown` | `unknown` | Perform the browser runtime operation: is trace visible. |
| [app.js](app.js#L478) | `loadTrace` | `reset: unknown` | `Promise<unknown>` | Perform the browser runtime operation: load trace. |
| [app.js](app.js#L479) | `agentContextStats` | `agent: unknown` | `unknown` | Perform the browser runtime operation: agent context stats. |
| [app.js](app.js#L502) | `renderAgentTopology` | `agents: unknown, graph: unknown` | `unknown` | Perform the browser runtime operation: render agent topology. |
| [app.js](app.js#L517) | `loadInspectorAgents` | `None` | `Promise<unknown>` | Perform the browser runtime operation: load inspector agents. |
| [app.js](app.js#L518) | `graphEditUrl` | `None` | `unknown` | Perform the browser runtime operation: graph edit url. |
| [app.js](app.js#L520) | `graphEditFeedback` | `text: unknown, state: unknown` | `unknown` | Perform the browser runtime operation: graph edit feedback. |
| [app.js](app.js#L522) | `loadGraphEditInfo` | `None` | `Promise<unknown>` | Perform the browser runtime operation: load graph edit info. |
| [app.js](app.js#L525) | `setDisabled` | `list: unknown, disabled: unknown` | `unknown` | Perform the browser runtime operation: set disabled. |
| [app.js](app.js#L539) | `graphAddAgent` | `None` | `Promise<unknown>` | Perform the browser runtime operation: graph add agent. |
| [app.js](app.js#L548) | `graphConnect` | `None` | `Promise<unknown>` | Perform the browser runtime operation: graph connect. |
| [app.js](app.js#L557) | `graphRemoveAgent` | `None` | `Promise<unknown>` | Perform the browser runtime operation: graph remove agent. |
| [app.js](app.js#L569) | `graphDisconnect` | `None` | `Promise<unknown>` | Perform the browser runtime operation: graph disconnect. |
| [app.js](app.js#L580) | `graphSetMapper` | `None` | `Promise<unknown>` | Perform the browser runtime operation: graph set mapper. |
| [app.js](app.js#L588) | `graphSetRouter` | `None` | `Promise<unknown>` | Perform the browser runtime operation: graph set router. |
| [app.js](app.js#L597) | `usageCells` | `usage: unknown, run: unknown` | `unknown` | Perform the browser runtime operation: usage cells. |
| [app.js](app.js#L598) | `value` | `key: unknown` | `unknown` | Perform the browser runtime operation: value. |
| [app.js](app.js#L607) | `loadUsage` | `None` | `Promise<unknown>` | Perform the browser runtime operation: load usage. |
| [app.js](app.js#L608) | `selectInspectorPanel` | `panel: unknown, refresh: unknown` | `unknown` | Perform the browser runtime operation: select inspector panel. |
| [app.js](app.js#L609) | `initInspectorTabs` | `None` | `unknown` | Perform the browser runtime operation: init inspector tabs. |
| [app.js](app.js#L610) | `knownPlanAgents` | `None` | `unknown` | Perform the browser runtime operation: known plan agents. |
| [app.js](app.js#L611) | `renderPlanAgentPicker` | `None` | `unknown` | Perform the browser runtime operation: render plan agent picker. |
| [app.js](app.js#L612) | `loadPlan` | `None` | `Promise<unknown>` | Perform the browser runtime operation: load plan. |
| [app.js](app.js#L614) | `loadHistory` | `None` | `Promise<unknown>` | Perform the browser runtime operation: load history. |
| [app.js](app.js#L645) | `loadOlderMessages` | `None` | `Promise<unknown>` | Perform the browser runtime operation: load older messages. |
| [app.js](app.js#L679) | `rehydrateSelectedView` | `options: object` | `Promise<unknown>` | Perform the browser runtime operation: rehydrate selected view. |
| [app.js](app.js#L680) | `switchSession` | `selected: unknown` | `Promise<unknown>` | Perform the browser runtime operation: switch session. |
| [app.js](app.js#L681) | `start` | `message: unknown, images: unknown, targetSession: unknown` | `Promise<unknown>` | Perform the browser runtime operation: start. |
| [app.js](app.js#L700) | `showCompactStatus` | `text: unknown, state: unknown, dismissMs: unknown` | `unknown` | Perform the browser runtime operation: show compact status. |
| [app.js](app.js#L706) | `clearCompactStatus` | `None` | `unknown` | Perform the browser runtime operation: clear compact status. |
| [app.js](app.js#L708) | `debounce` | `fn: unknown, wait: unknown` | `unknown` | Perform the browser runtime operation: debounce. |
| [app.js](app.js#L719) | `pushTraceEvent` | `event: unknown` | `unknown` | Perform the browser runtime operation: push trace event. |
| [app.js](app.js#L724) | `indexTraceEvent` | `event: unknown` | `unknown` | Perform the browser runtime operation: index trace event. |
| [app.js](app.js#L730) | `rebuildTraceEventIndex` | `None` | `unknown` | Perform the browser runtime operation: rebuild trace event index. |
| [app.js](app.js#L741) | `handleEvent` | `event: unknown` | `unknown` | Perform the browser runtime operation: handle event. |
| [app.js](app.js#L768) | `finish` | `None` | `unknown` | Perform the browser runtime operation: finish. |
| [app.js](app.js#L770) | `showSlashHelp` | `None` | `unknown` | Perform the browser runtime operation: show slash help. |
| [app.js](app.js#L791) | `sessionByName` | `name: unknown` | `unknown` | Perform the browser runtime operation: session by name. |
| [app.js](app.js#L792) | `switchSessionByName` | `name: unknown` | `Promise<unknown>` | Perform the browser runtime operation: switch session by name. |
| [app.js](app.js#L793) | `deleteSessionByName` | `name: unknown` | `Promise<unknown>` | Perform the browser runtime operation: delete session by name. |
| [app.js](app.js#L794) | `runStop` | `None` | `Promise<unknown>` | Perform the browser runtime operation: run stop. |
| [app.js](app.js#L795) | `runForceStop` | `None` | `Promise<unknown>` | Perform the browser runtime operation: run force stop. |
| [app.js](app.js#L797) | `runCompact` | `agent: unknown` | `Promise<unknown>` | Perform the browser runtime operation: run compact. |
| [app.js](app.js#L814) | `handleCompactStage` | `record: unknown, startedSession: unknown` | `unknown` | Perform the browser runtime operation: handle compact stage. |
| [app.js](app.js#L838) | `dispatchSlashCommand` | `parsed: unknown` | `unknown` | Perform the browser runtime operation: dispatch slash command. |
| [app.js](app.js#L846) | `resizeComposer` | `None` | `unknown` | Perform the browser runtime operation: resize composer. |
| [app.js](app.js#L847) | `applyRunGraphEvent` | `event: unknown` | `unknown` | Perform the browser runtime operation: apply run graph event. |
| [app.js](app.js#L848) | `handleRunGraphEvent` | `event: unknown` | `unknown` | Perform the browser runtime operation: handle run graph event. |
| [app.js](app.js#L849) | `connectRunGraphEvents` | `None` | `unknown` | Perform the browser runtime operation: connect run graph events. |
| [app.js](app.js#L850) | `restoreRunState` | `None` | `Promise<unknown>` | Perform the browser runtime operation: restore run state. |
| [app.js](app.js#L880) | `pickWorkspaceDirectory` | `None` | `Promise<unknown>` | Perform the browser runtime operation: pick workspace directory. |
| [app.js](app.js#L881) | `createAndSwitchSession` | `name: unknown, projectPath: unknown` | `Promise<unknown>` | Perform the browser runtime operation: create and switch session. |
| [app.js](app.js#L969) | `loadProviders` | `None` | `Promise<unknown>` | Perform the browser runtime operation: load providers. |
| [app.js](app.js#L970) | `initializeConsole` | `None` | `Promise<unknown>` | Perform the browser runtime operation: initialize console. |
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
