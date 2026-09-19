# frontend/static/components/ — Active UI Components INDEX

由 `../app.js` 导入的当前生产 UI 组件。它们只负责 DOM 构建和局部渲染；网络调用、会话切换和全局状态仍由 `app.js` 协调。

| File | Responsibility |
|---|---|
| `dom.js` | 共用且安全的 DOM 创建、转义与格式化原语。 |
| `image-composer.js` | 会话隔离的图片草稿：上传/粘贴/拖放/移除、缩略图预览与 `attachmentImageUrl` 受限 URL 构造；运行中拒绝图片改走文字 steer。 |
| `chat-view.js` | 对话消息、steer 指令与流式转录卡片。 |
| `markdown-renderer.js` | Marked/DOMPurify-backed single Markdown projection for restored and streaming Agent output. |
| `trace-view.js` | 可展开的 Agent 生命周期与 Trace 卡片。 |
| `task-plan-view.js` | 递归任务计划标记和状态展示。 |
| `external-agent-hub-view.js` | 全局 External Agent Hub：定义配置、本机进程候选扫描、健康检查、能力/会话检查，以及 capability-gated 外部上下文包预览。 |

## Intent Routing

- **DOM 基础设施** → `dom.js`
- **图片草稿、预览与受限附件 URL** → `image-composer.js`
- **聊天和 steering 呈现** → `chat-view.js`
- **安全 Markdown 解析与流式投影** → `markdown-renderer.js`
- **Trace 呈现** → `trace-view.js`
- **任务计划呈现** → `task-plan-view.js`
- **外部 Agent 配置、本机候选扫描、只读检查与上下文包预览** → `external-agent-hub-view.js`

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [chat-view.js](chat-view.js#L15) | `createChatView` | `options: object` | `unknown` | Perform the browser runtime operation: create chat view. |
| [chat-view.js](chat-view.js#L25) | `isAtLatest` | `None` | `unknown` | Perform the browser runtime operation: is at latest. |
| [chat-view.js](chat-view.js#L36) | `updateFollowState` | `None` | `unknown` | Perform the browser runtime operation: update follow state. |
| [chat-view.js](chat-view.js#L46) | `scrollToLatestIfFollowing` | `None` | `unknown` | Perform the browser runtime operation: scroll to latest if following. |
| [chat-view.js](chat-view.js#L53) | `removeWelcome` | `None` | `unknown` | Perform the browser runtime operation: remove welcome. |
| [chat-view.js](chat-view.js#L57) | `copyResult` | `text: unknown, button: unknown` | `Promise<unknown>` | Perform the browser runtime operation: copy result. |
| [chat-view.js](chat-view.js#L74) | `legacyPythonContainerToJson` | `source: unknown` | `unknown` | Perform the browser runtime operation: legacy python container to json. |
| [chat-view.js](chat-view.js#L131) | `decodeJson` | `value: unknown` | `unknown` | Perform the browser runtime operation: decode json. |
| [chat-view.js](chat-view.js#L165) | `decodeDisplayString` | `value: unknown` | `unknown` | Perform the browser runtime operation: decode display string. |
| [chat-view.js](chat-view.js#L187) | `renderJson` | `value: unknown` | `unknown` | Perform the browser runtime operation: render json. |
| [chat-view.js](chat-view.js#L209) | `renderToolPayload` | `value: unknown, emptyText: unknown` | `unknown` | Perform the browser runtime operation: render tool payload. |
| [chat-view.js](chat-view.js#L217) | `formatDuration` | `durationMs: unknown` | `unknown` | Perform the browser runtime operation: format duration. |
| [chat-view.js](chat-view.js#L223) | `renderTools` | `tools: unknown` | `unknown` | Perform the browser runtime operation: render tools. |
| [chat-view.js](chat-view.js#L238) | `formatClock` | `timestamp: unknown` | `unknown` | Perform the browser runtime operation: format clock. |
| [chat-view.js](chat-view.js#L243) | `pad` | `value: unknown` | `unknown` | Perform the browser runtime operation: pad. |
| [chat-view.js](chat-view.js#L248) | `buildTokenStats` | `usage: unknown, modelDurationMs: unknown, timestamp: unknown, roundDurationMs: unknown` | `unknown` | Perform the browser runtime operation: build token stats. |
| [chat-view.js](chat-view.js#L250) | `n` | `value: unknown` | `unknown` | Perform the browser runtime operation: n. |
| [chat-view.js](chat-view.js#L254) | `fmt` | `value: unknown` | `unknown` | Perform the browser runtime operation: fmt. |
| [chat-view.js](chat-view.js#L295) | `buildMessage` | `message: unknown, agentName: unknown` | `unknown` | Perform the browser runtime operation: build message. |
| [chat-view.js](chat-view.js#L337) | `buildSteer` | `message: unknown` | `unknown` | Perform the browser runtime operation: build steer. |
| [chat-view.js](chat-view.js#L356) | `append` | `message: unknown, agentName: unknown` | `unknown` | Perform the browser runtime operation: append. |
| [chat-view.js](chat-view.js#L363) | `upsertSteer` | `steering: unknown` | `unknown` | Perform the browser runtime operation: upsert steer. |
| [chat-view.js](chat-view.js#L374) | `beginStream` | `agentName: unknown` | `unknown` | Perform the browser runtime operation: begin stream. |
| [chat-view.js](chat-view.js#L386) | `updateReasoningFollow` | `None` | `unknown` | Perform the browser runtime operation: update reasoning follow. |
| [chat-view.js](chat-view.js#L390) | `afterReasoningRender` | `None` | `unknown` | Perform the browser runtime operation: after reasoning render. |
| [chat-view.js](chat-view.js#L397) | `updateTool` | `tool: unknown` | `unknown` | Perform the browser runtime operation: update tool. |
| [chat-view.js](chat-view.js#L439) | `appendError` | `title: unknown, message: unknown, rawContent: unknown` | `unknown` | Perform the browser runtime operation: append error. |
| [chat-view.js](chat-view.js#L452) | `render` | `messages: unknown, assistantLabel: unknown` | `unknown` | Perform the browser runtime operation: render. |
| [dom.js](dom.js#L2) | `$` | `id: unknown` | `unknown` | Perform the browser runtime operation: $. |
| [dom.js](dom.js#L7) | `escapeHtml` | `text: unknown` | `unknown` | Perform the browser runtime operation: escape html. |
| [external-agent-hub-view.js](external-agent-hub-view.js#L13) | `createExternalAgentHubView` | `dialog: unknown, root: unknown` | `unknown` | Perform the browser runtime operation: create external agent hub view. |
| [external-agent-hub-view.js](external-agent-hub-view.js#L20) | `open` | `None` | `Promise<unknown>` | Perform the browser runtime operation: open. |
| [external-agent-hub-view.js](external-agent-hub-view.js#L26) | `close` | `None` | `unknown` | Perform the browser runtime operation: close. |
| [external-agent-hub-view.js](external-agent-hub-view.js#L31) | `refresh` | `None` | `Promise<unknown>` | Perform the browser runtime operation: refresh. |
| [external-agent-hub-view.js](external-agent-hub-view.js#L44) | `render` | `None` | `unknown` | Perform the browser runtime operation: render. |
| [external-agent-hub-view.js](external-agent-hub-view.js#L63) | `agentCard` | `agent: unknown` | `unknown` | Perform the browser runtime operation: agent card. |
| [external-agent-hub-view.js](external-agent-hub-view.js#L74) | `createView` | `None` | `unknown` | Perform the browser runtime operation: create view. |
| [external-agent-hub-view.js](external-agent-hub-view.js#L93) | `candidateSection` | `None` | `unknown` | Perform the browser runtime operation: candidate section. |
| [external-agent-hub-view.js](external-agent-hub-view.js#L112) | `discoverLocalProcesses` | `None` | `Promise<unknown>` | Perform the browser runtime operation: discover local processes. |
| [external-agent-hub-view.js](external-agent-hub-view.js#L125) | `detailView` | `agent: unknown` | `unknown` | Perform the browser runtime operation: detail view. |
| [external-agent-hub-view.js](external-agent-hub-view.js#L153) | `definitionForm` | `agent: unknown, submitLabel: unknown` | `unknown` | Perform the browser runtime operation: definition form. |
| [external-agent-hub-view.js](external-agent-hub-view.js#L196) | `readDefinition` | `form: unknown` | `unknown` | Perform the browser runtime operation: read definition. |
| [external-agent-hub-view.js](external-agent-hub-view.js#L197) | `get` | `name: unknown` | `unknown` | Perform the browser runtime operation: get. |
| [external-agent-hub-view.js](external-agent-hub-view.js#L206) | `mutate` | `prefix: unknown, operation: unknown` | `Promise<unknown>` | Perform the browser runtime operation: mutate. |
| [external-agent-hub-view.js](external-agent-hub-view.js#L216) | `loadHealth` | `agentId: unknown, view: unknown` | `Promise<unknown>` | Perform the browser runtime operation: load health. |
| [external-agent-hub-view.js](external-agent-hub-view.js#L231) | `loadCapabilities` | `agentId: unknown, container: unknown` | `Promise<unknown>` | Perform the browser runtime operation: load capabilities. |
| [external-agent-hub-view.js](external-agent-hub-view.js#L242) | `loadSessions` | `agentId: unknown, container: unknown` | `Promise<unknown>` | Perform the browser runtime operation: load sessions. |
| [external-agent-hub-view.js](external-agent-hub-view.js#L253) | `loadContexts` | `agentId: unknown, container: unknown` | `Promise<unknown>` | Perform the browser runtime operation: load contexts. |
| [external-agent-hub-view.js](external-agent-hub-view.js#L269) | `previewContext` | `agentId: unknown, contextId: unknown, container: unknown` | `Promise<unknown>` | Perform the browser runtime operation: preview context. |
| [external-agent-hub-view.js](external-agent-hub-view.js#L283) | `request` | `path: unknown, options: unknown` | `Promise<unknown>` | Perform the browser runtime operation: request. |
| [external-agent-hub-view.js](external-agent-hub-view.js#L295) | `element` | `tag: unknown, className: unknown, text: unknown` | `unknown` | Perform the browser runtime operation: element. |
| [external-agent-hub-view.js](external-agent-hub-view.js#L296) | `button` | `text: unknown, handler: unknown, className: unknown, title: unknown` | `unknown` | Perform the browser runtime operation: button. |
| [external-agent-hub-view.js](external-agent-hub-view.js#L297) | `message` | `text: unknown, className: unknown` | `unknown` | Perform the browser runtime operation: message. |
| [external-agent-hub-view.js](external-agent-hub-view.js#L298) | `heading` | `title: unknown, note: unknown` | `unknown` | Perform the browser runtime operation: heading. |
| [external-agent-hub-view.js](external-agent-hub-view.js#L299) | `section` | `title: unknown, note: unknown, loading: unknown, className: unknown` | `unknown` | Perform the browser runtime operation: section. |
| [external-agent-hub-view.js](external-agent-hub-view.js#L300) | `field` | `label: unknown, name: unknown, type: unknown, current: unknown, placeholder: unknown` | `unknown` | Perform the browser runtime operation: field. |
| [external-agent-hub-view.js](external-agent-hub-view.js#L301) | `adapterLabel` | `kind: unknown` | `unknown` | Perform the browser runtime operation: adapter label. |
| [external-agent-hub-view.js](external-agent-hub-view.js#L302) | `defaultDefinition` | `None` | `unknown` | Perform the browser runtime operation: default definition. |
| [external-agent-hub-view.js](external-agent-hub-view.js#L303) | `definitionFromCandidate` | `candidate: unknown` | `unknown` | Perform the browser runtime operation: definition from candidate. |
| [external-agent-hub-view.js](external-agent-hub-view.js#L304) | `setBusy` | `text: unknown` | `unknown` | Perform the browser runtime operation: set busy. |
| [external-agent-hub-view.js](external-agent-hub-view.js#L305) | `renderError` | `container: unknown, error: unknown` | `unknown` | Perform the browser runtime operation: render error. |
| [image-composer.js](image-composer.js#L2) | `attachmentImageUrl` | `sessionId: unknown, image: unknown` | `unknown` | Perform the browser runtime operation: attachment image url. |
| [image-composer.js](image-composer.js#L7) | `createImageComposer` | `options: object` | `unknown` | Perform the browser runtime operation: create image composer. |
| [image-composer.js](image-composer.js#L15) | `render` | `None` | `unknown` | Perform the browser runtime operation: render. |
| [image-composer.js](image-composer.js#L30) | `addFiles` | `files: unknown` | `Promise<unknown>` | Perform the browser runtime operation: add files. |
| [markdown-renderer.js](markdown-renderer.js#L26) | `isAllowedLink` | `href: unknown` | `unknown` | Perform the browser runtime operation: is allowed link. |
| [markdown-renderer.js](markdown-renderer.js#L43) | `renderMarkdown` | `source: unknown` | `unknown` | Perform the browser runtime operation: render markdown. |
| [markdown-renderer.js](markdown-renderer.js#L61) | `renderMarkdownInto` | `target: unknown, source: unknown` | `unknown` | Perform the browser runtime operation: render markdown into. |
| [markdown-renderer.js](markdown-renderer.js#L83) | `createMarkdownStream` | `target: unknown, afterRender: unknown` | `unknown` | Perform the browser runtime operation: create markdown stream. |
| [markdown-renderer.js](markdown-renderer.js#L87) | `flush` | `None` | `unknown` | Perform the browser runtime operation: flush. |
| [task-plan-view.js](task-plan-view.js#L14) | `renderTaskPlanItem` | `task: unknown, depth: unknown` | `unknown` | Perform the browser runtime operation: render task plan item. |
| [trace-view.js](trace-view.js#L9) | `createTraceView` | `None` | `unknown` | Perform the browser runtime operation: create trace view. |
| [trace-view.js](trace-view.js#L10) | `kindFor` | `event: unknown` | `unknown` | Perform the browser runtime operation: kind for. |
| [trace-view.js](trace-view.js#L17) | `formatTime` | `timestamp: unknown` | `unknown` | Perform the browser runtime operation: format time. |
| [trace-view.js](trace-view.js#L25) | `build` | `title: unknown, message: unknown, data: unknown, kind: unknown, meta: unknown` | `unknown` | Perform the browser runtime operation: build. |
| [trace-view.js](trace-view.js#L40) | `append` | `title: unknown, message: unknown, data: unknown, kind: unknown` | `unknown` | Perform the browser runtime operation: append. |
| [trace-view.js](trace-view.js#L46) | `appendEvent` | `event: unknown, position: unknown` | `unknown` | Perform the browser runtime operation: append event. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| — | — | `None` | `object` | 本索引范围不直接声明类；沿 Route Map 进入下级索引。 |

<!-- END GENERATED SYMBOL MAP -->
