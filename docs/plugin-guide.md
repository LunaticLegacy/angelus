# Angelus 插件开发指南（v1）

> 面向插件作者的接入教程：从「插件放在哪里」到「四个扩展点怎么写」再到「安装与权限确认」。
> API 细节与字段定义见 [plugin-api.md](plugin-api.md)；权限门与完整性校验的风险模型见 [security.md](security.md)。
> 完整的可运行示例见 [`plugins/example-tool/`](../plugins/example-tool/)（网络搜索工具：`register_tool` + `register_hook` 全链路）。

---

## 1. 插件放在哪里（两层级目录）

插件仅使用**一个持久目录**（决策 D2），与 `workspace/` 并列：

| 目录 | 生命周期 | 说明 |
|------|----------|------|
| `<app_data>/plugins` | 跨工作区共享 | `plugin_paths.plugin_dir(state_root)` 解析；可用 `ANGELUS_PLUGIN_DIR` 覆盖。 |

桌面安装包附带 `demo-hello` 与 `example-tool`。首次启动时它们被复制到这个目录供发现；不会自动注册、执行或授予权限，也不会覆盖用户已有的同名目录。
- **目录形态**：每个插件一个子目录，目录名建议与 `manifest.name` 一致，内部必须包含 `manifest.json` 与入口文件：

```
<app_data>/plugins/
└── example-tool/
    ├── manifest.json     # 插件清单（必填）
    ├── main.py           # 入口模块（entry=main）
    ├── plugin.js         # 前端资源（须列入 frontend.assets 白名单）
    └── data/             # 运行期私有目录（manager 在加载时自动创建）
```

> 加载时插件代码通过 `angelus_plugins.<name>` 命名空间导入，不会污染主命名空间；
> 插件自身的 `import` 相对导入均限定在该命名空间内（决策 D1）。

---

## 2. manifest.json 写法

最小合法清单（必填字段：`name`、`version`、`api_version`、`entry`）：

```json
{
  "name": "example-tool",
  "display_name": "Example Web Search Tool",
  "version": "0.1.0",
  "api_version": "1",
  "description": "演示插件：注册 web_search 工具并订阅工具事件钩子。",
  "author": "Angelus",
  "license": "MIT",
  "entry": "main",
  "entry_type": "module",
  "tools": ["web_search"],
  "permissions": [
    {"action": "network", "scope": "*.example.com"},
    {"action": "event.subscribe", "scope": "tool.before"}
  ],
  "frontend": {
    "assets": ["plugin.js"],
    "panels": [],
    "commands": ["example-tool:search"],
    "settings": false
  }
}
```

字段说明（完整 schema 见 `docs/plugin-api.md` 附录 A）：

| 字段 | 必填 | 约束 |
|------|------|------|
| `name` | ✅ | `^[a-z][a-z0-9_-]{1,63}$`（小写开头，可用连字符） |
| `version` | ✅ | 语义化版本 `^\d+\.\d+\.\d+$` |
| `api_version` | ✅ | 当前仅 `"1"` |
| `entry` | ✅ | 入口模块路径（`entry_type=module` 时取 `<entry>.py`；默认 `main`） |
| `entry_type` | | `module` / `function` / `package` |
| `display_name` / `description` / `author` / `license` | | 有长度上限（120 / 2000 / 200 / 200） |
| `tools` | | 声明的工具短名数组（去重） |
| `permissions` | | 权限对象数组 `{action, scope}`，`action` 枚举：`shell`、`network`、`fs.read`、`fs.write`、`env`、`http`、`connector.read`、`connector.write`、`event.subscribe` |
| `frontend.assets` | | 允许被 `/plugins/<name>/static/` 服务的文件白名单（唯一、字符串） |
| `frontend.panels` / `frontend.commands` | | 前端面板/命令注册名数组 |
| `frontend.settings` | | 布尔，是否提供设置页 |
| `dependencies` | | 依赖插件的 name→version 映射 |
| `checksum` | | `sha256:<64位hex>`，由安装流程写入（见 §6） |

> 校验器为手写实现（`angelus/plugin_manifest.py`），**不引入 jsonschema 依赖**；
> 非法字段返回**字段级结构化错误**，例如 `[{"field": "permissions[0].action", "error": "..."}]`。
> 未知顶层字段、`additionalProperties: false` 语义均会被拒绝。

---

## 3. 最小插件（入口模块）

`entry_type=module` 时，入口模块导入后取模块级变量 `angelus_plugin`，它必须是
`AngelusPlugin` 子类的实例。**所有 `register_*` 调用只能发生在 `setup()` 内**
（“先登记后生效”：setup 成功返回后，注册快照才会发布到宿主）。

```python
# main.py
from angelus.plugins import AngelusPlugin


class HelloPlugin(AngelusPlugin):
    name = "hello"          # 应与 manifest.name 一致（不一致时以 manifest 为准）
    version = "1.0.0"

    def setup(self, runtime):
        # runtime.state_dir: <plugin_dir>/data（已创建，可写私有数据）
        runtime.logger.info("hello plugin loaded")

    def teardown(self):
        pass  # 幂等清理；异常会被 manager 吞掉并记日志


angelus_plugin = HelloPlugin()
```

---

## 4. 四类扩展点示例

### 4.1 注册工具（`register_tool`）

工具运行时的完整名称会自动加上命名空间前缀 `plugin.<name>.<tool>`，
与内建工具（shell/knowledge/swarm/obscura）天然隔离、不会冲突。
`schema` 为 JSON-Schema 风格参数声明，由 `bridge_tools.create_plugin_tools`
映射为 llmfetcher 的 `ToolParameter`（name/description/type/required/enum/default 齐全）。

```python
def setup(self, runtime):
    runtime.register_tool(
        name="web_search",
        schema={
            "description": "搜索演示索引并返回前 N 条结果",
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "limit": {"type": "integer", "description": "返回条数", "default": 5},
            },
            "required": ["query"],
        },
        handler=self._web_search,
    )

def _web_search(self, query: str, limit: int = 5, **_kwargs):
    # 离线安全：仅查内置索引；真实网络请求需宿主授予 network/http 权限
    return {"tool": "plugin.hello.web_search", "query": query, "count": 0, "results": []}
```

### 4.2 注册钩子（`register_hook`）

插件可订阅的**事件白名单**（`angelus.plugins.base.HOOK_EVENTS`）：

| 插件事件（点命名） | 内部总线事件（冒号命名） | 语义 |
|--------------------|--------------------------|------|
| `agent.started` | `agent:start` | agent 运行开始 |
| `agent.stopped` | `agent:stopped` | agent 运行被停止/中断 |
| `tool.before` | `agent:tools_requested` | 工具批次即将执行 |
| `tool.after` | `agent:tools_completed` | 工具批次执行完成 |
| `session.created` | （无原生发射点，由宿主 `notify()` 宣告） | 会话创建 |

```python
def setup(self, runtime):
    runtime.register_hook("tool.before", self._on_tool_before, priority=10)
    runtime.register_hook("tool.after", self._on_tool_after, priority=10)

def _on_tool_before(self, event):
    # event 为 llmfetcher.events.ExecutionEvent（只读，勿修改）
    # 示例：把事件快照写入私有 state_dir
    (Path(self._runtime.state_dir) / "events.jsonl").open("a", encoding="utf-8").write(
        json.dumps({"event": "tool.before", "event_type": event.event_type}) + "\n"
    )
```

- 同一事件的多个钩子按 **priority 降序**执行（同优先级保持注册顺序）。
- **失败隔离**：单个钩子抛异常会被捕获并记日志，不影响 agent/swarm 主流程，
  也不影响同事件的其他钩子（与 `test_swarm_failure_isolation.py` 语义一致）。
- 白名单外的事件名在注册时即抛 `ValueError`，整个插件进入 `blocked` 状态。

### 4.3 注册路由（`register_route`）

路由挂在 `/plugins/<name>/api` 前缀下（前缀隔离：插件路由永远不可能在
前缀之外被访问）。`method` 须在 HTTP 方法白名单内，`path` 以 `/` 开头：

```python
def setup(self, runtime):
    def info():
        return {"ok": True, "plugin": "hello"}

    runtime.register_route("GET", "/info", info)
```

启用后 `GET /plugins/hello/api/info` 返回 `{"ok": true, "plugin": "hello"}`；
`/api/info`、`/info` 等前缀之外路径一律 404。禁用插件的路由**不会挂载**。

### 4.4 注册连接器（`register_connector`）

连接器桥（`bridge_connectors.py`）是**只读路径**：插件只能注册 provider 工厂，
宿主把该 kind 并入 `GET /api/providers` 的发现结果；插件**永远读不到**已持久化的
连接器密钥（存储/解密仍走 `angelus/connectors.py`，RSA-OAEP 加密、读路径脱敏）。

```python
def setup(self, runtime):
    runtime.register_connector("search", self._search_provider_factory)

def _search_provider_factory(self):
    # 返回一个连接器/provider 实例；插件不接触凭据
    return MySearchProvider()
```

---

## 5. 前端资源与 window.Angelus 桥

- 只有列入 `frontend.assets` 白名单的文件才能通过
  `GET /plugins/<name>/static/<asset>` 被服务；`../` 穿越、符号链接逃逸、
  非白名单文件、未启用插件一律 404。
- 前端通过 `window.Angelus` 桥注册面板/命令/设置（`frontend/static/plugins.js`）：

```javascript
(function () {
  "use strict";
  if (!window.Angelus) { console.warn("bridge unavailable"); return; }
  window.Angelus.registerCommand("hello", {
    id: "search",
    description: "调用插件工具（演示命令）",
    handler: function (args) {
      return { ok: true, query: (args && args[0]) || "plugin" };
    },
  });
})();
```

命令名会被命名空间化为 `hello:search`。

若 manifest 声明 `frontend.settings: true`，工作台“设置 → 插件”会显示该插件的状态与 JSON 设置编辑器。`registerSettings(plugin, { title, description })` 可提供页面标题和说明；设置会持久化到本机 `plugins.json`，不能包含 API Key、token、password 或 secret 等凭据形字段。Python 插件会在下次加载时从 `runtime.settings` 读取这些值。页面中的已发现插件都可以选中；若显示“加入工作台”，该操作只登记当前已发现的本地目录并校验完整性，不执行代码。登记后可加载/卸载：加载前必须确认执行插件代码，若存在尚未授予的 manifest 权限，还会单独显示并确认这些权限；卸载会 teardown 并移除前端贡献，但不会删除插件文件或配置。

---

## 6. 安装、启用与权限确认流程

CLI 命令（`angelus plugin ...`，见 `docs/plugin-api.md` 附录 C）：

```
angelus plugin list                     # 与 plugins.json 一致
angelus plugin install <source> [-y] [--global]
angelus plugin uninstall <id-or-name>
angelus plugin enable <id-or-name>
angelus plugin disable <id-or-name>
```

1. **安装**：`angelus plugin install ./path/to/plugin`（`<source>` 支持本地目录/git/zip）。
   - 先校验 manifest；计算 `manifest`（不含 checksum）与入口文件的 sha256 完整性值。
   - 若清单声明了 `checksum` 且与计算值不符 → **拒绝安装**（防篡改，见 security.md）。
   - 交互式逐条确认清单声明的 `permissions`（`network:*.example.com`、`event.subscribe:tool.before` 等）；
     传 `-y` 跳过确认、一次性全授。
   - 安装记录写入 `plugins.json`（原子写：`.tmp` + `replace()`，0600），
     `source` 为 `local`/`git`/`zip`，初始 `enabled=false`。
2. **启用**：`angelus plugin enable <id-or-name>`。
   - 首次启用把安装时授予的权限写入 `permissions_granted` 并持久化；
     后续启用**不会覆盖**已授予的权限。
   - 启用即加载：`setup()` 成功 → `active`；失败 → `blocked`（进程不受影响）。
3. **禁用/卸载**：`disable` 执行 `teardown()` 并把 `enabled` 翻回 false；
   `uninstall` 删除插件目录并清理注册表项。

工作台中的“卸载插件”对应运行时 `disable`（保留文件），而非 CLI 的 `uninstall`（删除文件）；这样可以安全地重新加载、检查状态或调整设置。

> 未授权权限在调用时被权限门拦下（`angelus.plugins.security.check_permission`），
> 并记录日志；示例插件声明但未授予 `network` 时，远程搜索路径不会执行。

---

## 7. 调试与常见问题

| 现象 | 原因与排查 |
|------|-----------|
| `plugin list` 显示 `error` 状态 | manifest 非法：用 `validate_manifest` 查看字段级错误（缺 name/version/entry、permissions 非法、未知字段等） |
| 启用后状态 `blocked` | `setup()` 抛异常（错误信息含异常类型与消息）；常见于注册了白名单外钩子事件 |
| 工具调用时找不到 `plugin.<name>.<tool>` | 确认 `setup()` 内调用了 `register_tool`，且插件状态为 `active`（`get_status()` 查看） |
| 静态资源 404 | 文件未列入 `frontend.assets` 白名单；或插件未启用；或路径含 `../`/`./` 前缀（白名单键已归一化，直接写 `assets/logo.txt` 即可） |
| 钩子不触发 | 确认事件在白名单内；`tool.before` 对应内部事件 `agent:tools_requested`；`session.created` 需要宿主主动 `notify()` |
| 重复加载导致注册重复 | 正常不会发生：重复 `load()` 去重、`reload()` 先 teardown 再重新导入（模块被清出 `sys.modules`） |

---

## 8. 完整示例

跟着 [`plugins/example-tool/`](../plugins/example-tool/) 走一遍
**安装 → 启用 → 工具调用 → 钩子触发** 全链路：

1. `angelus plugin install plugins/example-tool`（或复制到 `<app_data>/plugins/` 后在工作台中登记）；
2. `angelus plugin enable example-tool`；
3. 在 agent 工具链中调用 `plugin.example-tool.web_search`（`query` 必填，`limit` 默认 5）；
4. 每次工具调用前后，`tool.before`/`tool.after` 钩子把事件快照写入
   `<plugin_dir>/data/events.jsonl`（离线可用，默认查内置演示索引）。
