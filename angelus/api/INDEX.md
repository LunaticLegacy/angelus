# angelus/api/ — Browser API INDEX

FastAPI 路由层。路由只负责 HTTP/SSE 边界、请求验证与响应编排；持久化、运行构建和历史重建分别位于上一级包的 `storage.py`、`runtime.py` 和 `history.py`。

## Route Map — Leaf Files

| File | Responsibility |
|---|---|
| `__init__.py` | `include_api_routes(app)`：注册所有路由并提供 SPA 根页面。 |
| `connectors.py` | 供应商列表与连接器 CRUD；桥接已启用插件的连接器类型。 |
| `runs.py` | 运行启动、状态、SSE、协作式停止、强制停止和运行中 steer 指令。 |
| `sessions.py` | 工作区、会话历史、按 Agent 查询的计划、归档、图、用量、产物与跨会话记忆授权 API。 |
| `compact.py` | 手动上下文压缩，以及面向浏览器的阶段性进度流。 |

## Intent Routing

- **连接器 / Provider** → `connectors.py`
- **运行、停止、SSE 或 steering** → `runs.py`
- **会话、计划、图、归档、用量或记忆授权** → `sessions.py`
- **手动压缩** → `compact.py`
- **挂载路由或 SPA 根路径** → `__init__.py`
