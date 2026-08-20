# angelus/plugins/ — Plugin Runtime INDEX

Angelus 的插件运行时：发现与 `workspace/` 并列的持久插件目录，在受控 setup 阶段收集扩展，并将工具、路由、钩子和连接器安全地桥接到宿主。插件契约见 [`../../docs/plugin-api.md`](../../docs/plugin-api.md)。

## Route Map — Leaf Files

| File | Responsibility |
|---|---|
| `__init__.py` | 稳定公共导出：运行时、基类、事件白名单和注册记录。 |
| `base.py` | `AngelusPlugin`、`PluginRuntime`、注册 API 与事件/HTTP 方法白名单。 |
| `manager.py` | 应用级目录发现、命名空间导入、加载/卸载/重载、状态机与注册发布。 |
| `security.py` | 权限门禁、安装负载 SHA-256 完整性校验与安全日志。 |
| `bridge_tools.py` | 将插件工具转换并注入 Agent 工具链。 |
| `bridge_hooks.py` | 将插件钩子映射到 `llmfetcher` 的执行事件总线。 |
| `bridge_routes.py` | 挂载插件 API、受白名单约束的静态资源、最小公开查询，以及状态/非敏感设置和经确认的运行时加载/卸载端点。 |
| `bridge_connectors.py` | 将插件注册的连接器类型合并至连接器发现流程。 |

## Boundaries

- 清单校验、目录解析与持久化注册表分别在上一级的 `plugin_manifest.py`、`plugin_paths.py` 和 `plugin_registry.py`。
- 插件只有在注册表启用、完整性校验通过且 setup 成功后才会发布扩展。
- 插件路由固定在 `/plugins/<name>/api`，静态资源只能访问清单列出的文件。
