# Angelus 现有 API 清单 (API Inventory)

> 分支：`feat/v0.5.0-adapter-and-perf` · 生成方式：扫描 `angelus/api/*.py` 与 `angelus/plugins/bridge_routes.py` 的路由装饰器
> 用途：AI Drama Production Studio 重构的基线契约；新 `/api/anime/*` 命名空间与这些 API 并存。
> 机器可读版本：`docs/anime/api-inventory.json`

## 1. 根路由

| 方法 | 路径 | 来源 | 说明 |
|---|---|---|---|
| GET | `/` | `angelus/api/__init__.py` | 返回 `frontend/templates/index.html`（vanilla SPA shell） |

## 2. connectors 路由（`angelus/api/connectors.py`，5 个）

| 方法 | 路径 | 状态码 | 说明 |
|---|---|---|---|
| GET | `/api/providers` | 200 | 列出可用 provider kinds（含插件聚合） |
| GET | `/api/connectors` | 200 | 列出已保存连接器（永不返回 api_key） |
| POST | `/api/connectors` | 201 | 创建连接器（RSA-OAEP 加密存储） |
| PUT | `/api/connectors/{connector_id}` | 200 | 更新连接器 |
| DELETE | `/api/connectors/{connector_id}` | 204 | 删除连接器 |

## 3. runs 路由（`angelus/api/runs.py`，6 个）

| 方法 | 路径 | 状态码 | 说明 |
|---|---|---|---|
| POST | `/api/runs` | 200 | 启动 Agent run（daemon 线程） |
| GET | `/api/workspaces/{workspace_id}/runs/{session_id}/status` | 200 | 查询 run 状态（run-state.json） |
| GET | `/api/workspaces/{workspace_id}/runs/{session_id}/events` | SSE | 事件流（`?after=N` 回放+尾随） |
| POST | `/api/workspaces/{workspace_id}/runs/{session_id}/stop` | 200 | 协作式停止 |
| POST | `/api/workspaces/{workspace_id}/runs/{session_id}/force-stop` | 200 | 强制停止（中断模型请求+杀 Shell 进程） |
| POST | `/api/workspaces/{workspace_id}/runs/{session_id}/steer` | 200 | 注入 steer 指令 |

## 4. sessions 路由（`angelus/api/sessions.py`，约 30 个）

### 4.1 工作区/会话 CRUD

| 方法 | 路径 | 状态码 | 说明 |
|---|---|---|---|
| GET | `/api/workspaces` | 200 | 列出工作区 |
| POST | `/api/workspaces` | 201 | 创建工作区 |
| DELETE | `/api/workspaces/{workspace_id}` | 200 | 删除工作区 |
| GET | `/api/sessions` | 200 | 列出会话 |
| POST | `/api/sessions` | 201 | 创建会话 |
| DELETE | `/api/sessions/{session_id}` | 200 | 删除会话 |
| GET | `/api/workspace-root` | 200 | 查询工作区根路径 |

### 4.2 会话内容

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/workspaces/{workspace_id}/sessions/{session_id}/plan` | 任务计划 |
| GET | `/api/sessions/{session_id}/plan` | 任务计划（按 session_id） |
| PUT | `/api/workspaces/{workspace_id}/sessions/{session_id}/plan` | 替换任务计划 |
| PATCH | `/api/workspaces/{workspace_id}/sessions/{session_id}/plan/tasks/{task_id}` | 更新任务状态 |
| PATCH | `/api/sessions/{session_id}/plan/tasks/{task_id}` | 更新任务状态（按 session_id） |
| GET | `/api/workspaces/{workspace_id}/sessions/{session_id}/messages` | 消息历史 |
| GET | `/api/sessions/{session_id}/messages` | 消息历史（按 session_id） |
| GET | `/api/workspaces/{workspace_id}/sessions/{session_id}/archive` | 归档 |
| GET | `/api/sessions/{session_id}/archive` | 归档（按 session_id） |
| GET | `/api/sessions/{session_id}/events` | 事件日志（分页） |
| GET | `/api/sessions/{session_id}/steers` | steer 记录 |
| GET | `/api/sessions/{session_id}/usage` | token 用量 |

### 4.3 Agent 上下文

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/sessions/{session_id}/agents` | 列出 agents |
| GET | `/api/sessions/{session_id}/agents/{agent_name}/context-graph` | 上下文图 |
| GET | `/api/sessions/{session_id}/agents/{agent_name}/context` | 上下文预览 |
| GET | `/api/sessions/{session_id}/agents/{agent_name}/context/compaction-input` | 压缩输入预览 |
| GET | `/api/sessions/{session_id}/agents/{agent_name}/context/editable` | 可编辑上下文 |
| POST | `/api/sessions/{session_id}/agents/{agent_name}/context/edit` | 编辑上下文 |
| POST | `/api/sessions/{session_id}/agents/{agent_name}/context/restore` | 恢复上下文 |

### 4.4 图视图

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/workspaces/{workspace_id}/sessions/{session_id}/graph` | 执行图 |
| GET | `/api/sessions/{session_id}/graph` | 执行图（按 session_id） |

### 4.5 其他

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/sessions/{session_id}/open-folder` | 打开工作区目录 |
| GET | `/api/sessions/{session_id}/memory/capabilities` | 记忆能力 |
| POST | `/api/sessions/{session_id}/artifacts` | 注册 artifact |
| GET | `/api/sessions/{session_id}/artifacts` | 列出 artifacts |
| GET | `/api/sessions/{session_id}/handoffs` | 列出 handoffs |
| GET | `/api/sessions/{session_id}/handoffs/{handoff_id}` | 读取 handoff |
| POST | `/api/sessions/{session_id}/handoffs` | 创建 handoff |

## 5. compact 路由（`angelus/api/compact.py`，1 个）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/sessions/{session_id}/compact` | 触发上下文压缩（SSE 流式） |

## 6. 插件动态路由（`angelus/plugins/bridge_routes.py`，PLUGIN-DYNAMIC）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/plugins` | 插件列表（附录-D 字段白名单） |
| GET | `/api/plugins/status` | 插件状态 |
| POST | `/api/plugins/rescan` | 热发现新插件目录 |
| POST | `/api/plugins/discovered/{name}/register` | 注册已发现插件 |
| POST | `/api/plugins/{plugin_id}/load` | 加载插件（需 confirm + grant_permissions） |
| POST | `/api/plugins/{plugin_id}/unload` | 卸载插件 |
| GET | `/api/plugins/{plugin_id}/settings` | 读取插件设置（敏感键过滤） |
| PUT | `/api/plugins/{plugin_id}/settings` | 保存插件设置 |
| GET | `/api/plugins/{plugin_id}` | 插件详情 |
| GET | `/plugins/{name}/static/{asset:path}` | 插件静态资源（白名单+路径归一化） |
| GET | `/plugins/{name}/api/*` | 插件自定义 API（per-plugin APIRouter，verb 白名单） |

## 7. 统计

- 静态路由总数：约 42 个（connectors 5 + runs 6 + sessions 约 30 + compact 1）
- 插件动态路由：11 个固定 + 每插件动态
- 根路由：1 个

## 8. 与 /api/anime/* 的关系

- 旧 API 全部 **KEEP**（详见 `frontend-api-compatibility.md`）
- 新 `/api/anime/*` 命名空间独立挂载，不修改旧路由
- 复用模式：`_persist_json` 原子写、`_safe_id` 校验、SSE `?after=N` 回放+尾随、connector 加密解密、LLMFetcher/LLMBackendConfig
