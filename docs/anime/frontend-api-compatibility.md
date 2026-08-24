# 前端 API 调用矩阵与兼容性分析

> 分支：`feat/v0.5.0-adapter-and-perf` · 来源：扫描 `frontend/static/app.js`、`frontend/static/plugins.js`
> 用途：AI Drama Production Studio 前端 React 重构的调用基线；旧 vanilla SPA 在 Phase 2 移除前必须先提交本文件 + 回归测试全绿（HARD GATE）。

## 1. 前端调用矩阵（app.js + plugins.js）

| # | 调用点 | 方法 | 路径 | 用途 |
|---|---|---|---|---|
| 1 | `loadWorkspaces` | GET | `/api/sessions` | 会话列表 → 侧栏选择器 |
| 2 | `loadConnectors` | GET | `/api/connectors` | 连接器列表 |
| 3 | `createConnector` | POST | `/api/connectors` | 新建连接器 |
| 4 | `saveSelectedConnector` | PUT | `/api/connectors/{id}` | 更新连接器 |
| 5 | `delete-connector` | DELETE | `/api/connectors/{id}` | 删除连接器 |
| 6 | `loadProviders` | GET | `/api/providers` | provider 下拉 |
| 7 | `loadPluginStatuses` | GET | `/api/plugins/status` | 插件状态列表 |
| 8 | `selectPluginSettings` | GET | `/api/plugins/{id}/settings` | 读取插件设置 |
| 9 | `savePluginSettings` | PUT | `/api/plugins/{id}/settings` | 保存插件设置 |
| 10 | `changePluginLifecycle` | POST | `/api/plugins/discovered/{name}/register` | 注册插件 |
| 11 | `changePluginLifecycle` | POST | `/api/plugins/{id}/load` | 加载插件 |
| 12 | `changePluginLifecycle` | POST | `/api/plugins/{id}/unload` | 卸载插件 |
| 13 | `refresh-plugins` | POST | `/api/plugins/rescan` | 热扫描插件 |
| 14 | `planUrl` | GET | `/api/sessions/{id}/plan?agent=` | 任务计划 |
| 15 | `updatePlanStatus` | PATCH | `/api/sessions/{id}/plan/tasks/{task_id}` | 更新任务状态 |
| 16 | `messagesUrl` | GET | `/api/sessions/{id}/messages?agent=&limit=` | 消息历史 |
| 17 | `graphUrl` | GET | `/api/sessions/{id}/graph` | 执行图 |
| 18 | `traceUrl` | GET | `/api/sessions/{id}/events?limit=` | 事件日志 |
| 19 | `loadContextPrompt` | GET | `/api/sessions/{id}/agents/{agent}/context` | 上下文预览 |
| 20 | `loadCompactionInput` | GET | `/api/sessions/{id}/agents/{agent}/context/compaction-input` | 压缩输入 |
| 21 | `loadAgents` | GET | `/api/sessions/{id}/agents` | Agent 列表 |
| 22 | `loadInspectorAgents` | GET | `/api/sessions/{id}/agents` + `/graph` | Inspector 拓扑 |
| 23 | `loadUsage` | GET | `/api/sessions/{id}/usage` | token 用量 |
| 24 | `start` | POST | `/api/runs` | 启动 run |
| 25 | `connectRunEvents` | SSE | `/api/workspaces/{wid}/runs/{sid}/events?after=` | 实时事件流 |
| 26 | `restoreRunState` | GET | `/api/workspaces/{wid}/runs/{sid}/status` | 恢复 run 状态 |
| 27 | `runStop` | POST | `/api/workspaces/{wid}/runs/{sid}/stop` | 协作停止 |
| 28 | `runForceStop` | POST | `/api/workspaces/{wid}/runs/{sid}/force-stop` | 强制停止 |
| 29 | `sendSteer` | POST | `/api/workspaces/{wid}/runs/{sid}/steer` | 注入 steer |
| 30 | `compact` | POST | `/api/sessions/{id}/compact` | 上下文压缩 |
| 31 | `open-workspace` | POST | `/api/sessions/{id}/open-folder` | 打开目录 |
| 32 | `new-session` | POST | `/api/sessions` | 新建会话 |
| 33 | `deleteSessionByName` | DELETE | `/api/sessions/{id}` | 删除会话 |
| 34 | `plugins.js` | GET | `/api/plugins` | 可用插件集合 |
| 35 | `plugins.js` | GET | `/plugins/{name}/static/{asset}` | 插件静态资源 |

## 2. 兼容矩阵

### KEEP（保留，新前端继续消费）

| 路径 | 说明 |
|---|---|
| `/api/sessions` GET/POST/DELETE | 会话 CRUD |
| `/api/sessions/{id}/plan` GET/PATCH | 任务计划 |
| `/api/sessions/{id}/messages` GET | 消息历史 |
| `/api/sessions/{id}/graph` GET | 执行图 |
| `/api/sessions/{id}/events` GET | 事件日志 |
| `/api/sessions/{id}/usage` GET | 用量 |
| `/api/sessions/{id}/agents` GET | Agent 列表 |
| `/api/sessions/{id}/agents/{agent}/context*` GET/POST | 上下文 |
| `/api/sessions/{id}/compact` POST | 压缩 |
| `/api/sessions/{id}/open-folder` POST | 打开目录 |
| `/api/runs` POST | 启动 run |
| `/api/workspaces/{wid}/runs/{sid}/events` SSE | 事件流 |
| `/api/workspaces/{wid}/runs/{sid}/status` GET | run 状态 |
| `/api/workspaces/{wid}/runs/{sid}/stop` POST | 停止 |
| `/api/workspaces/{wid}/runs/{sid}/force-stop` POST | 强制停止 |
| `/api/workspaces/{wid}/runs/{sid}/steer` POST | steer |
| `/api/providers` GET | provider 列表 |
| `/api/connectors` GET/POST/PUT/DELETE | 连接器 CRUD |
| `/api/plugins*` GET/POST/PUT | 插件管理 |
| `/plugins/{name}/static/*` GET | 插件静态资源 |

### REPLACE（被 /api/anime/* 替代，旧 API 保留但新前端不再调用）

| 旧路径 | 新路径 | 说明 |
|---|---|---|
| （无直接对应） | `/api/anime/projects/*` | 短剧项目 CRUD（新领域） |
| （无直接对应） | `/api/anime/episodes/*` | 剧集管理 |
| （无直接对应） | `/api/anime/scenes/*` | 场景管理 |
| （无直接对应） | `/api/anime/shots/*` | 镜头管理（最小调度单元） |
| （无直接对应） | `/api/anime/jobs/*` | 生成任务队列 |
| （无直接对应） | `/api/anime/qa/*` | QA 管线 |
| （无直接对应） | `/api/anime/providers/*` | 视频生成 provider |
| （无直接对应） | `/api/anime/events` SSE | 短剧事件流 |

### WRAP（包装复用，不重造）

| 复用对象 | 说明 |
|---|---|
| `LLMFetcher`/`LLMBackendConfig`/`create_fetcher` | 剧情编排 LLM 调用 |
| `Agent`/`AgentSwarm` | 多 Agent 编排 |
| `storage._persist_json` | 原子写 |
| `storage._safe_id` | ID 校验 |
| connector RSA-OAEP 加密 | API Key 存储 |
| SSE `?after=N` 回放+尾随 | 事件流模式 |

### DEPRECATE（标记废弃，暂不删除）

| 路径 | 说明 |
|---|---|
| `/api/workspaces/{wid}/sessions/{sid}/archive` | 归档（新前端用 events 替代） |
| `/api/sessions/{id}/steers` | steer 记录（保留 API，前端弱化） |

### UNUSED（legacy 前端模块，不迁移）

| 文件 | 说明 |
|---|---|
| `frontend/static/api.js` | 旧 REST helper |
| `frontend/static/state.js` | 旧状态存储 |
| `frontend/static/chat.js` | 旧聊天渲染 |
| `frontend/static/sessions.js` | 旧会话层 |
| `frontend/static/connectors.js` | 旧连接器层 |
| `frontend/static/settings.js` | 旧设置层 |
| `frontend/static/events.js` | 旧 EventSource 包装 |
| `frontend/static/utils.js` | 旧工具函数 |
| `frontend/static/main.js` | 旧入口 |
| `frontend/static/inspector/` | 旧 inspector 模块 |

### PLUGIN-DYNAMIC（保留，插件系统能力）

| 路径 | 说明 |
|---|---|
| `/api/plugins` GET | 插件列表 |
| `/api/plugins/status` GET | 状态 |
| `/api/plugins/rescan` POST | 热扫描 |
| `/api/plugins/discovered/{name}/register` POST | 注册 |
| `/api/plugins/{id}/load` POST | 加载 |
| `/api/plugins/{id}/unload` POST | 卸载 |
| `/api/plugins/{id}/settings` GET/PUT | 设置 |
| `/api/plugins/{id}` GET | 详情 |
| `/plugins/{name}/static/{asset}` GET | 静态资源 |
| `/plugins/{name}/api/*` GET | 插件自定义 API |

## 3. 结论

- 旧 API 全部 **KEEP**，新前端继续消费；`/api/anime/*` 为新增命名空间，不冲突。
- 前端 React 重构后，`frontend/static/` 中 UNUSED 模块随 `git rm -r frontend` 移除（Phase 2，HARD GATE 之后）。
- 插件系统能力（PLUGIN-DYNAMIC）完整保留，不破坏 Angelus 原有 Plugin 能力。
