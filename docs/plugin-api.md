# Angelus 插件系统 API 契约（v1）

> 状态：v1 定稿（对应 swarm 执行规格附录 A/C/D，扩展点事实以代码核验为准）
> 本文档定义插件系统的**对外契约**：manifest v1、权限枚举、AngelusPlugin/PluginRuntime API、
> 五类扩展接线、api_version 版本策略，以及扩展点盘点（与代码事实一一对应）。

---

## 1. 扩展点盘点（与代码事实核对）

插件系统接入的五个既有扩展点，均以**桥接（bridge）**方式挂载，不修改 `llmfetcher/` 子模块源码：

| # | 扩展点 | 代码位置（事实） | 桥接产物 | 说明 |
|---|--------|------------------|----------|------|
| 1 | 工具工厂 | `llmfetcher/tools/__init__.py` | `angelus/plugins/bridge_tools.py` | 懒加载工厂 `_LAZY_FACTORIES`：`create_knowledge_tools`（`.knowledge_tools`）、`create_obscura_tools`（`.obscura_tools`）；立即工厂 `create_shell_tools`（`.shell_tools`）、`create_swarm_tools`（`.spawn_tools`）。`__all__` 导出全部四个。插件工具以独立工厂 `create_plugin_tools(manager)` 加入解析链 |
| 2 | agent 钩子 | `llmfetcher/events.py` + `agent.py` + `swarm_module/execution_graph.py` | `angelus/plugins/bridge_hooks.py` | `ExecutionEvent` 数据类 + `ExecutionHook = Callable[[ExecutionEvent], None]`；`Agent.add_hook()` 与 `ExecutionGraph.add_hook()` 同步调用，单个钩子异常被捕获不击穿执行。事件名内部为冒号命名空间（`agent:start`/`agent:stopped`/`agent:tools_requested`/`agent:tools_completed`/`graph:start` 等），插件白名单用点命名（见 §5） |
| 3 | 四 router | `angelus/api/__init__.py::include_api_routes` | `angelus/plugins/bridge_routes.py` | 四个 APIRouter：`connectors_router`（`api/connectors.py`）、`runs_router`（`api/runs.py`）、`sessions_router`（`api/sessions.py`）、`compact_router`（`api/compact.py`）。插件 APIRouter 挂载于 `/plugins/<name>/api` 前缀下，前缀隔离 |
| 4 | 连接器存储 | `angelus/connectors.py` | `angelus/plugins/bridge_connectors.py` | `_write_connectors()` 原子写（`.tmp` + `replace()`，0600）、`_public_connector()` 脱敏、`_encrypt_connector_key`/`_decrypt_connector_key` RSA-OAEP。Provider 发现经 `GET /api/providers`（`LLMFetcher.list_available_backend_providers()`）。插件仅能注册 provider factory，不能读取已存密钥 |
| 5 | 前端模块 | `frontend/static/`（`webapp.py` 以 `app.mount("/static", StaticFiles(...), name="static")` 挂载） | `frontend/static/plugins.js`（由 `main.js` 引入） | 模块：`api.js`、`app.css`、`app.js`、`chat.js`、`components/`、`connectors.js`、`events.js`、`inspector/`、`main.js`、`sessions.js`、`settings.js`、`slash.js`、`slash.test.js`、`state.js`、`utils.js`。入口 `main.js` 汇总全部模块；插件通过 `window.Angelus` 桥注入 |

> 核验结论：工厂名（`create_shell_tools`/`create_swarm_tools`/`create_knowledge_tools`/`create_obscura_tools`）、
> 四 router（connectors/runs/sessions/compact）、connectors.py 原子写与脱敏函数、frontend/static 模块清单均与代码一致。

---

## 2. manifest v1 契约

插件根目录必须包含 `manifest.json`，完整 JSON Schema 如下（写入校验器实现，见 `angelus/plugin_manifest.py`）：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://angelus.local/schema/plugin-manifest/v1",
  "title": "Angelus plugin manifest",
  "type": "object",
  "additionalProperties": false,
  "required": ["name", "version", "api_version", "entry"],
  "properties": {
    "name": {"type": "string", "pattern": "^[a-z][a-z0-9_-]{1,63}$"},
    "display_name": {"type": "string", "maxLength": 120},
    "version": {"type": "string", "pattern": "^\\d+\\.\\d+\\.\\d+$"},
    "api_version": {"const": "1"},
    "description": {"type": "string", "maxLength": 2000},
    "author": {"type": "string", "maxLength": 200},
    "license": {"type": "string", "maxLength": 200},
    "entry": {"type": "string", "minLength": 1, "maxLength": 512},
    "entry_type": {"enum": ["module", "function", "package"]},
    "tools": {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 128}, "uniqueItems": true},
    "permissions": {"type": "array", "items": {"$ref": "#/$defs/permission"}, "uniqueItems": true},
    "frontend": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "assets": {"type": "array", "items": {"type": "string"}, "uniqueItems": true},
        "panels": {"type": "array", "items": {"type": "string"}, "uniqueItems": true},
        "commands": {"type": "array", "items": {"type": "string"}, "uniqueItems": true},
        "settings": {"type": "boolean", "default": false}
      }
    },
    "dependencies": {
      "type": "object",
      "additionalProperties": false,
      "patternProperties": {
        "^[a-z][a-z0-9_-]*$": {"type": "string", "pattern": "^\\d+\\.\\d+\\.\\d+$"}
      }
    },
    "checksum": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}
  },
  "$defs": {
    "permission": {
      "type": "object",
      "additionalProperties": false,
      "required": ["action", "scope"],
      "properties": {
        "action": {"enum": ["shell", "network", "fs.read", "fs.write", "env", "http", "connector.read", "connector.write", "event.subscribe"]},
        "scope": {"type": "string", "minLength": 1, "maxLength": 512}
      }
    }
  }
}
```

### 2.1 字段表（v1）

| 字段 | 类型 | 必填 | 约束 | 说明 |
|------|------|------|------|------|
| `name` | string | ✅ | `^[a-z][a-z0-9_-]{1,63}$` | 插件唯一名，同时是 import 命名空间 `angelus_plugins.<name>` 与 URL 前缀 `/plugins/<name>` 的来源 |
| `display_name` | string | – | ≤120 | UI 展示名 |
| `version` | string | ✅ | `^\d+\.\d+\.\d+$`（semver） | 插件版本 |
| `api_version` | string | ✅ | 恒为 `"1"` | 契约版本，见 §7 |
| `description` | string | – | ≤2000 | 描述 |
| `author` / `license` | string | – | ≤200 | 元数据 |
| `entry` | string | ✅ | 1–512 | 加载入口（`entry_type=module` 时为模块路径） |
| `entry_type` | enum | – | `module`/`function`/`package` | 默认 `module` |
| `tools` | string[] | – | 唯一 | 声明的工具名清单（供 schema 预检） |
| `permissions` | permission[] | – | 唯一 | 权限声明，见 §3 |
| `frontend.assets` | string[] | – | 唯一 | 可被 `/plugins/<name>/static/*` 服务的白名单文件 |
| `frontend.panels` / `frontend.commands` | string[] | – | 唯一 | 面板/命令注册键 |
| `frontend.settings` | boolean | – | 默认 `false` | 是否注入设置 UI |
| `dependencies` | object | – | 键 `^[a-z][a-z0-9_-]*$`，值 semver | 对其他插件的最低版本约束 |
| `checksum` | string | – | `^sha256:[0-9a-f]{64}$` | 安装期写入，加载前复核（见 S10） |

校验器为**手写实现**（不引入 jsonschema 依赖），对缺失必填字段、非法 pattern/enum、
`additionalProperties` 越界等返回**字段级结构化错误**（`{"field": ..., "error": ...}` 列表）。

---

## 3. 权限枚举

权限动作（`permission.action`）共 9 个，均需 `scope`（范围字符串，1–512）：

| action | 含义 | 典型 scope |
|--------|------|-----------|
| `shell` | 执行本地 shell 命令 | 命令/目录模式 |
| `network` | 发起网络连接 | 域名/端口 |
| `fs.read` | 读取文件 | 路径前缀 |
| `fs.write` | 写入文件 | 路径前缀 |
| `env` | 读取环境变量 | 变量名 |
| `http` | HTTP 请求 | URL 模式 |
| `connector.read` | 读取连接器元数据（**不含密钥**） | provider 名 |
| `connector.write` | 写入/更新连接器 | provider 名 |
| `event.subscribe` | 订阅 agent 事件 | 事件名（白名单内） |

权限授予记录在 `plugins.json` 的 `permissions_granted`（`"action:scope"` 字符串数组）。
未授予的权限**一律拒绝并记日志，不静默放行**（见 S10）。

---

## 4. AngelusPlugin / PluginRuntime API（v1）

```python
# angelus/plugins/base.py
from pathlib import Path
from typing import Any, Callable
import logging

class PluginRuntime:
    name: str                      # 插件名（与 manifest.name 一致）
    state_dir: Path                # <plugin_dir>/<name>/data，插件私有可写区
    settings: dict                 # 注册表持久化的插件配置（只读视图）
    logger: logging.Logger         # 命名 angelus.plugins.<name>

    def register_tool(self, name: str, schema: dict, handler: Callable) -> None: ...
    def register_route(self, method: str, path: str, handler: Callable) -> None: ...
    def register_hook(self, event: str, handler: Callable, *, priority: int = 0) -> None: ...
    def register_connector(self, kind: str, factory: Callable) -> None: ...

class AngelusPlugin:
    name: str
    version: str
    def setup(self, runtime: PluginRuntime) -> None: ...
    def teardown(self) -> None: ...
```

### 4.1 加载协议

- `entry` 指向模块路径；`entry_type=module` 时 import 后取 `plugin = <module>.angelus_plugin`，须为 `AngelusPlugin` 实例。
- 所有 `register_*` 动作**只能发生在 `setup()` 内**；setup 抛异常则插件进入 `blocked` 状态并回滚已注册项，不击穿主进程。
- `teardown()` 必须幂等（调用两次不报错）。
- import 使用 `angelus_plugins.<name>` 命名空间隔离，插件内 import 不污染主命名空间。
- 同名插件重复加载/重新加载不产生重复注册。

### 4.2 方法签名明细

| 方法 | 签名 | 语义 |
|------|------|------|
| `register_tool` | `(name: str, schema: dict, handler: Callable) -> None` | 注册一个插件工具；运行时工具名为 `plugin.<name>.<tool>`（防与内建工具冲突）；`schema` 为 JSON Schema 风格的参数声明，映射到 ToolParameter（name/description/parameters） |
| `register_route` | `(method: str, path: str, handler: Callable) -> None` | 注册一个插件路由；最终挂载于 `/plugins/<name>/api<path>` 前缀下 |
| `register_hook` | `(event: str, handler: Callable, *, priority: int = 0) -> None` | 注册事件钩子；`event` 必须命中 §5 白名单，否则拒绝；priority 越大越先执行 |
| `register_connector` | `(kind: str, factory: Callable) -> None` | 注册连接器 provider factory（只读路径，见 §6） |

---

## 5. 事件钩子（hooks）白名单 v1

插件面向的事件名（点命名），桥接层映射到内部冒号命名事件：

| 插件事件名 | 内部事件（事实） | 触发时机 |
|-----------|------------------|----------|
| `agent.started` | `agent:start` / `agent:submitted` | agent 启动 |
| `agent.stopped` | `agent:stopped` | agent 停止 |
| `tool.before` | `agent:tools_requested` | 工具调用前 |
| `tool.after` | `agent:tools_completed` | 工具调用后 |
| `session.created` | 会话创建（由 angelus 侧发出） | 新会话建立 |

- 白名单外事件名注册被**拒绝**（`register_hook` 抛 ValueError 或返回错误）。
- 钩子同步调用；单个钩子异常被捕获并记日志，不影响 agent 主流程（对齐 `llmfetcher/events.py` 的 `ExecutionHook` 语义与 `test_swarm_failure_isolation.py`）。

---

## 6. 五类扩展接线

| 扩展类 | 接入点 | 插件侧 API | 桥接实现 | 隔离/安全 |
|--------|--------|-----------|----------|-----------|
| **tools** | `llmfetcher/tools/__init__.py` 工厂解析链 | `register_tool(name, schema, handler)` | `angelus/plugins/bridge_tools.py::create_plugin_tools(manager)` | 工具名加 `plugin.<name>.` 前缀；不修改 llmfetcher 源码 |
| **hooks** | `llmfetcher/events.py` 的 ExecutionHook 体系（`Agent.add_hook` / `ExecutionGraph.add_hook`） | `register_hook(event, handler, *, priority=0)` | `angelus/plugins/bridge_hooks.py` | 白名单过滤；单钩子失败隔离 |
| **routes** | `angelus/api/__init__.py::include_api_routes` 装配点 | `register_route(method, path, handler)` | `angelus/plugins/bridge_routes.py` | 前缀 `/plugins/<name>/api` 隔离；静态资源白名单 + Path 规范化防穿越 |
| **connectors** | `angelus/connectors.py` provider 发现 + `GET /api/providers` | `register_connector(kind, factory)` | `angelus/plugins/bridge_connectors.py` | 只读路径；凭据仍走 RSA-OAEP 加密存储，插件不能读取已存密钥（读路径走 `_public_connector` 脱敏） |
| **frontend** | `frontend/static/` 模块体系（入口 `main.js`） | `window.Angelus.registerPanel/registerCommand/registerSettings` | `frontend/static/plugins.js`（由 `main.js` 引入） | 仅加载启用插件；静态资源白名单；CSP 仅放开同源自域插件路径 |

### 6.1 REST 端点（附录 D 事实化）

```
GET /api/plugins                     → {"plugins": [{"id","name","version","api_version","enabled","checksum","source","installed_at"}]}
GET /api/plugins/{id}                → 上条目 + {"permissions_granted": [...]}（不含 manifest 全文）
POST /api/plugins/{id}/enable        → 200 {"ok": true}；setup 失败 → 400 {"ok": false, "error": "..."}
POST /api/plugins/{id}/disable       → 200 {"ok": true}
GET  /plugins/{name}/static/{asset}  → 白名单静态资源；穿越/未启用 → 404
*    /plugins/{name}/api/*           → 插件 APIRouter 挂载点（前缀隔离）
```

---

## 7. api_version 版本策略

- `manifest.api_version` 恒为 `"1"`（`const`），对应本文档 §2/§4 契约的**不变量**：字段表、权限枚举、AngelusPlugin/PluginRuntime 签名、五类接线方式。
- **兼容规则**：
  1. 同一主版本内只允许**增量变更**（新增可选字段、新增权限 action、新增白名单事件），旧插件仍可加载；
  2. 任何**破坏性变更**（必填字段变更、方法签名变更、删除权限 action、事件语义变更）必须提升 `api_version`（v2 等）；
  3. 加载器对 `api_version` 不在支持集合内的 manifest **拒绝加载**并给出明确错误；
  4. `plugins.json` 注册表自带 `version`（当前 `1`），注册表格式变更同样遵循增量/破坏二分。
- 子进程隔离（D1 的 v2 路线）属运行时模型变更，不改变 manifest 契约，但会引入新的加载/权限语义，届时随 v2 文档发布。

---

## 8. 目录放置（D2 事实化）

两级目录（`ANGELUS_PLUGIN_DIR` 可覆盖全局级）：

| 层级 | 路径 | 生命周期 |
|------|------|----------|
| 会话级 | `<workspace>/plugins`（`STATE_ROOT`，即 `workspace/`） | 随工作区 |
| 全局级 | `<app_data>/plugins`（仿 `_default_state_root` 的 workspace 模型；`ANGELUS_PLUGIN_DIR` 覆盖时取该值） | 跨工作区 |

插件私有数据目录 `state_dir = <plugin_dir>/<name>/data`。
