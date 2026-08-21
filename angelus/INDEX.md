# angelus/ — Control Plane INDEX

Angelus 是覆盖 `llmfetcher` 的本地控制平面。它拥有浏览器 API、运行控制、会话投影、连接器凭据、跨会话记忆和插件宿主；模型调用、Agent loop、图记忆、工具与 Swarm 算法留在 `llmfetcher/` 子模块。

## Route Map

| Entry | Type | Responsibility |
|---|---|---|
| [`api/`](api/INDEX.md) | FastAPI routers | 浏览器 HTTP/SSE 路由与 SPA 根页面。 |
| [`classes/`](classes/INDEX.md) | Data models | 请求模型以及内存态运行/会话控制类。 |
| [`plugins/`](plugins/INDEX.md) | Plugin runtime | 插件发现、生命周期、权限、完整性与宿主桥接。 |
| `webapp.py` | Application assembly | 创建 FastAPI app、挂载静态资源、初始化插件管理器并注册 API。 |
| `runtime.py` | Runtime construction | 构建 Agent / Swarm、运行配置快照、按 Agent 隔离的计划与会话记忆存储；默认将 provider 文本/思考增量作为 SSE 推送、最终完整回复仍正常落盘；Swarm 分派和复活必须绑定 coordinator 计划的叶子 ID，TaskBus 生命周期自动回写叶子并派生父任务状态；每轮开始会把设置面板的上下文压缩阈值同步到所有参与 Agent 的 checkpoint；Swarm 在同一服务进程的连续用户轮次中保留实例，并会将终态图写入本地恢复快照，供后端重启后的下一轮重建；终态 worker 可经 `revive_agent` 接收新任务。 |
| `storage.py` | Durable state | 状态根目录、会话注册表、事件账本、JSON 持久化与并发保护。 |
| `history.py` | Read models | 从事件和上下文投影重建历史、归档、图和用量。 |
| `context_editing.py` | Context revisions | Agent 活动上下文的版本化编辑、原子快照、追加审计与前向恢复；归档、事件账本和远程请求快照不在其写入范围内。 |
| `connectors.py` | Credentials | 连接器 CRUD、RSA-OAEP 凭据加密与服务端解析。 |
| `session_memory.py` | Cross-session memory | 按运行级许可提供快照式会话/产物检索工具。 |
| `task_planning.py` | Plans | 会话本地 JSON 任务计划、TaskBus assignment 关联和递归父状态派生。 |
| `markdown.py` | Rendering | 受限 LRU 的安全 Markdown → HTML 渲染。 |
| `plugin_manifest.py` | Manifest validation | 手写的插件清单 v1 字段级校验。 |
| `plugin_paths.py` | Plugin locations | 与 `workspace/` 并列的持久插件目录解析，以及环境变量覆盖。 |
| `plugin_bootstrap.py` | Packaged examples | 首次启动时将发布包内的示例插件复制到持久插件目录，绝不自动执行或覆盖用户文件。 |
| `mcp_tools.py` | MCP bridge | 用官方 Python `mcp` SDK 连接服务器、发现远端工具并桥接为原生 Agent 工具。 |
| `plugin_registry.py` | Plugin registry | 原子读写 `plugins.json` 中的安装、启用与授权记录。 |
| `cli.py` | CLI | 本地 `web` / `session` / `plugin` 命令与 llmfetcher 命令委托。 |
| `__init__.py` / `__main__.py` | Package entry | 公共门面与 `python -m angelus` 入口。 |

| `provider_adapters.py` | Provider presets | Maps first-party provider presets such as Kimi Code to supported LLMFetcher backends and default endpoints. |

## Durable State Ownership

`ANGELUS_STATE_DIR` 可指定状态根目录（兼容 `LLMFETCHER_STATE_DIR`）；否则使用本地工作区。连接器与插件注册表在全局范围共享，而会话目录彼此隔离。CLI 的 `--state-dir` 会同时设置两个名称，使插件目录和注册表保持同一应用根。

| Scope | Records |
|---|---|
| Global state root | `sessions.json`、`connectors.json`、RSA 密钥对、`plugins.json` |
| Session directory | `conversation.json`、`events.ndjson`、`run-state.json`、`task-plan.json`、`graph-view.json`、`swarm-runtime.json` |
| Agent context | `contexts/<agent>.json`、其线性归档和图记忆伴随文件，以及 `contexts/revisions/<agent>/` 的不可变编辑快照与 `context-edits.ndjson` 审计账本 |

API 密钥不返回给浏览器。持久化的运行配置与 `swarm-runtime.json` 均不含密钥；直接输入的浏览器密钥只在当前请求中使用。为使动态 worker 能在服务重启后重建，`swarm-runtime.json` 会保留其本地 system prompt，因而与会话上下文同属本机私有状态。

## Intent Routing

- **HTTP 端点、SSE 或静态控制台** → `api/INDEX.md`
- **持久化、状态目录、事件账本** → `storage.py`
- **历史、归档、图或用量读模型** → `history.py`
- **Agent / Swarm 构建** → `runtime.py`
- **连接器凭据** → `connectors.py`
- **跨会话记忆授权** → `session_memory.py`
- **插件契约、注册表或运行时** → `plugin_*.py` 与 `plugins/INDEX.md`
- **请求与内存态控制模型** → `classes/INDEX.md`
