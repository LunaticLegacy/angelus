# frontend/static/components/ — Active UI Components INDEX

由 `../app.js` 导入的当前生产 UI 组件。它们只负责 DOM 构建和局部渲染；网络调用、会话切换和全局状态仍由 `app.js` 协调。

| File | Responsibility |
|---|---|
| `dom.js` | 共用且安全的 DOM 创建、转义与格式化原语。 |
| `chat-view.js` | 对话消息、steer 指令与流式转录卡片。 |
| `trace-view.js` | 可展开的 Agent 生命周期与 Trace 卡片。 |
| `task-plan-view.js` | 递归任务计划标记和状态展示。 |

## Intent Routing

- **DOM 基础设施** → `dom.js`
- **聊天和 steering 呈现** → `chat-view.js`
- **Trace 呈现** → `trace-view.js`
- **任务计划呈现** → `task-plan-view.js`

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [chat-view.js](chat-view.js#L13) | `createChatView` | `options: object` | `unknown` | Perform the browser runtime operation: create chat view. |
| [chat-view.js](chat-view.js#L14) | `removeWelcome` | `None` | `unknown` | Perform the browser runtime operation: remove welcome. |
| [chat-view.js](chat-view.js#L17) | `copyResult` | `text: unknown, button: unknown` | `Promise<unknown>` | Perform the browser runtime operation: copy result. |
| [chat-view.js](chat-view.js#L34) | `legacyPythonContainerToJson` | `source: unknown` | `unknown` | Perform the browser runtime operation: legacy python container to json. |
| [chat-view.js](chat-view.js#L91) | `decodeJson` | `value: unknown` | `unknown` | Perform the browser runtime operation: decode json. |
| [chat-view.js](chat-view.js#L125) | `decodeDisplayString` | `value: unknown` | `unknown` | Perform the browser runtime operation: decode display string. |
| [chat-view.js](chat-view.js#L147) | `renderJson` | `value: unknown` | `unknown` | Perform the browser runtime operation: render json. |
| [chat-view.js](chat-view.js#L169) | `renderToolPayload` | `value: unknown, emptyText: unknown` | `unknown` | Perform the browser runtime operation: render tool payload. |
| [chat-view.js](chat-view.js#L177) | `formatDuration` | `durationMs: unknown` | `unknown` | Perform the browser runtime operation: format duration. |
| [chat-view.js](chat-view.js#L183) | `renderTools` | `tools: unknown` | `unknown` | Perform the browser runtime operation: render tools. |
| [chat-view.js](chat-view.js#L198) | `formatClock` | `epochSeconds: unknown` | `unknown` | Perform the browser runtime operation: format clock. |
| [chat-view.js](chat-view.js#L201) | `pad` | `value: unknown` | `unknown` | Perform the browser runtime operation: pad. |
| [chat-view.js](chat-view.js#L206) | `buildTokenStats` | `usage: unknown, modelDurationMs: unknown, timestamp: unknown, durationMs: unknown` | `unknown` | Perform the browser runtime operation: build token stats. |
| [chat-view.js](chat-view.js#L208) | `n` | `value: unknown` | `unknown` | Perform the browser runtime operation: n. |
| [chat-view.js](chat-view.js#L209) | `fmt` | `value: unknown` | `unknown` | Perform the browser runtime operation: fmt. |
| [chat-view.js](chat-view.js#L236) | `buildMessage` | `message: unknown, agentName: unknown` | `unknown` | Perform the browser runtime operation: build message. |
| [chat-view.js](chat-view.js#L258) | `buildSteer` | `text: unknown` | `unknown` | Perform the browser runtime operation: build steer. |
| [chat-view.js](chat-view.js#L265) | `append` | `message: unknown, agentName: unknown` | `unknown` | Perform the browser runtime operation: append. |
| [chat-view.js](chat-view.js#L272) | `beginStream` | `agentName: unknown` | `unknown` | Perform the browser runtime operation: begin stream. |
| [chat-view.js](chat-view.js#L292) | `appendError` | `title: unknown, message: unknown, rawContent: unknown` | `unknown` | Perform the browser runtime operation: append error. |
| [chat-view.js](chat-view.js#L305) | `render` | `messages: unknown, assistantLabel: unknown` | `unknown` | Perform the browser runtime operation: render. |
| [dom.js](dom.js#L2) | `$` | `id: unknown` | `unknown` | Perform the browser runtime operation: $. |
| [dom.js](dom.js#L7) | `escapeHtml` | `text: unknown` | `unknown` | Perform the browser runtime operation: escape html. |
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
