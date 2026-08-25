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
