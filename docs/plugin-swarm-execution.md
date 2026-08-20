# Angelus 插件系统 — Swarm 执行分解规格

> 状态：草案（待用户确认 4 个决策点；默认值见 §2，未推翻则按默认执行）
> 上游计划：P0–P6 七组任务（20/30/45/25/25/20/30 分钟，合计约 195 分钟）
> 对接基础设施：`llmfetcher/swarm_module/task_bus.py`（TaskAssignment/TaskReport）、`swarm_module/swarm.py`（AgentSwarm 执行图）、`angelus/task_planning.py`（任务树持久化）

---

## 1. 目标

把插件系统从"一个人做的一张计划"拆成**可由 AgentSwarm 并行/串行调度的最小工作单元**。每个单元满足：

1. 有且仅有一个明确的 **recipient**（角色），依赖边界写入 handoff，不共享可变内存；
2. **objective** 可独立执行、可在无其他 agent 在场时完成（依赖仅通过 artifacts 传递）；
3. **expected_artifacts** 是磁盘上的文件/端点，验收可机械核验（存在、格式合法、测试通过）；
4. 验收内容（§5）即 TaskReport 的 `findings`/`evidence` 检查单。

## 2. 决策门（swarm 首任务，coordinator 负责）

4 个待确认点按如下**默认值**执行；若用户推翻，只改 `docs/decisions.md` 一处，下游 handoff 引用该文件：

| # | 决策点 | 默认值 | 理由 |
|---|--------|--------|------|
| D1 | 插件加载模型 | **同进程 import**（命名空间 `angelus_plugins.<name>`），子进程隔离列为 v2 路线 | MVP 简单；同权限与内建工具一致 |
| D2 | 插件放置 | **应用级**：`<app_data>/plugins`，与 `workspace/` 并列 | 插件跨会话稳定，适配桌面 sidecar 的临时解压模型 |
| D3 | 桌面版设置页 | **本期不纳入**，仅保留 `/api/plugins` 后端 + 前端机制，桌面设置 UI 留 v1.1 | 缩减范围，避免 Tauri 侧改动 |
| D4 | 示例插件 | **网络搜索工具**：演示 register_tool + register_hook（搜索前后事件）全链路 | 覆盖工具与钩子两条主线 |

## 3. Swarm 拓扑

### 3.1 角色（recipient）

| 角色 | 负责单元 | 核心产出 |
|------|----------|----------|
| `coordinator` | S0（决策门）、合并 | decisions.md、总验收 |
| `spec` | S1（契约） | docs/plugin-api.md、docs/decisions.md |
| `registry` | S2（目录+注册表） | plugin_paths.py、manifest 校验、plugins.json 原子写 |
| `runtime-core` | S3（PluginManager 核心） | PluginManager、AngelusPlugin 基类、运行时隔离 |
| `runtime-tools` | S4（工具接入） | 动态工具注册到 llmfetcher 工具链 |
| `runtime-hooks` | S5（钩子接入） | agent 事件钩子总线接入 |
| `runtime-routes` | S6（路由/静态挂载） | /plugins/<name>/static/*、插件路由 |
| `runtime-connectors` | S7（连接器接入） | register_connector → connectors.py 存储 |
| `frontend` | S8（前端机制） | plugins.js、window.Angelus 桥、CSP |
| `cli` | S9（分发与 CLI） | `angelus plugin list/install/...` |
| `security` | S10（安全权限） | permissions 确认流、checksum、security.md |
| `qa` | S11（测试文档示例） | tests、docs/plugin-guide.md、example-tool |

### 3.2 执行图（AgentSwarm edges）

```
coordinator ──► spec(S1) ──► registry(S2) ──► runtime-core(S3)
                                                  │
             runtime-tools(S4) ◄──┘  (S3 split)
             runtime-hooks(S5) ◄──┘
             runtime-routes(S6) ◄──┘
             runtime-connectors(S7) ◄──┘
                                                  │  (S4..S7 gather)
             frontend(S8) ◄──┘   cli(S9) ◄──┘   security(S10) ◄──┘
                                                  │  (S8..S10 gather)
             qa(S11) ◄──┘
             coordinator ◄──┘ (merge, 总验收)
```

即：`coordinator→spec`、`spec→registry`、`registry→runtime-core`、`runtime-core→{tools,hooks,routes,connectors}`（split）、`{tools,hooks,routes,connectors}→{frontend,cli,security}`（gather 后 split）、`{frontend,cli,security}→qa`、`qa→coordinator`。

### 3.3 TaskAssignment 映射规则

每个单元 S* 实例化为 `TaskAssignment`：

```python
TaskAssignment(
    task_id="S3",                       # 稳定 id，与本文档一致
    recipient="runtime-core",           # §3.1 角色
    reply_to="coordinator",
    objective=<见 §4 objective 字段>,
    handoff=<见 §4 handoff 字段>,        # 有界状态，仅引用 artifacts 路径
    expected_artifacts=<见 §4 artifacts>,
)
```

## 4. 单元分解（objective / handoff / artifacts）

### S1 — 契约（P0） · recipient=`spec` · 依赖：无 · 估时 20min

- **objective**：盘点现有扩展点（llmfetcher/tools/ 工厂、agent 钩子、angelus/api/ 四 router、connectors.py、frontend/static/ 模块），撰写 `docs/plugin-api.md`（含 manifest v1 契约、权限枚举、AngelusPlugin API、版本策略）与 `docs/decisions.md`（记录 §2 四项确认结果）。
- **handoff**：`决策默认值见 §2；扩展点清单见 §1 背景；契约必须覆盖 tools/hooks/routes/connectors/frontend 五类扩展。`
- **artifacts**：`docs/plugin-api.md`、`docs/decisions.md`
- **验收**：见 §5-S1。

### S2 — 目录与注册表（P1） · recipient=`registry` · 依赖：S1 · 估时 30min

- **objective**：实现插件目录解析 `angelus/plugin_paths.py`（`<app_data>/plugins`，与 workspace 并列，可通过 `ANGELUS_PLUGIN_DIR` 覆盖）；实现 `manifest.json` 校验器（按附录 A schema，不新增 jsonschema 依赖，手写校验并返回结构化错误）；实现 `plugins.json` 注册表（仿 connectors.py 原子写：`with_suffix(".tmp")` + `replace()`，字段见附录 B），首次启用写入 permissions_granted。
- **handoff**：`manifest schema 见 docs/plugin-api.md 附录 A；原子写模式参照 angelus/connectors.py:_write_connectors；依赖清单无 jsonschema，禁止新增大依赖。`
- **artifacts**：`angelus/plugin_paths.py`、`angelus/plugin_manifest.py`、`angelus/plugin_registry.py`、`tests/test_plugin_registry.py`（骨架可后补）
- **验收**：见 §5-S2。

### S3 — PluginManager 核心（P2 前半） · recipient=`runtime-core` · 依赖：S1、S2 · 估时 25min

- **objective**：实现 `angelus/plugins/manager.py`：发现（扫描应用级目录、读注册表）、加载（`importlib` 以 `angelus_plugins.<name>` 命名空间隔离 import）、生命周期（setup/teardown，异常不击穿主进程）、启用/禁用状态机；实现 `angelus/plugins/base.py`：`AngelusPlugin` 基类 + `PluginRuntime`（暴露 register_tool/register_route/register_hook/register_connector 与 state_dir、logger、settings）。
- **handoff**：`命名空间 angelus_plugins.<name>；setup 抛异常则标记 blocked 并回滚注册；teardown 幂等；所有注册表先登记后生效。`
- **artifacts**：`angelus/plugins/__init__.py`、`angelus/plugins/manager.py`、`angelus/plugins/base.py`
- **验收**：见 §5-S3。

### S4 — 工具接入（P2 后半） · recipient=`runtime-tools` · 依赖：S3 · 估时 8min

- **objective**：把 PluginManager 收集的插件工具合并进工具解析链——在 `llmfetcher/tools/__init__.py` 的懒加载机制旁提供 `angelus/plugins/bridge_tools.py`，返回 `create_plugin_tools(manager)` 工厂；插件工具名加 `plugin.<name>.<tool>` 前缀防冲突；Tool schema 由插件 manifest 的 tools 声明 + register_tool 的 ToolParameter 构造。
- **handoff**：`参考 llmfetcher/tools/__init__.py 的 _LAZY_FACTORIES 模式；不要改 llmfetcher 源码（子模块），只在 angelus 侧桥接。`
- **artifacts**：`angelus/plugins/bridge_tools.py`
- **验收**：见 §5-S4。

### S5 — 钩子接入 · recipient=`runtime-hooks` · 依赖：S3 · 估时 7min

- **objective**：在 `angelus/plugins/bridge_hooks.py` 中把插件 register_hook 接到 agent 事件总线（llmfetcher/events.py 的 ExecutionHook 体系，参照既有 send_event 隔离失败语义：单个钩子异常不崩 agent）；事件名白名单 v1：`agent.started`、`agent.stopped`、`tool.before`、`tool.after`、`session.created`。
- **handoff**：`钩子同步调用、单钩子失败隔离；事件名白名单见 objective；不能改 llmfetcher 源码。`
- **artifacts**：`angelus/plugins/bridge_hooks.py`
- **验收**：见 §5-S5。

### S6 — 路由与静态挂载 · recipient=`runtime-routes` · 依赖：S3 · 估时 10min

- **objective**：在 angelus 主 app 挂载 `/plugins/<name>/static/*`（仅服务 manifest.frontend.assets 白名单内文件，防路径穿越），并挂载插件注册的 APIRouter（前缀 `/plugins/<name>/api`）；实现 `GET /api/plugins`（列表，含 enabled/version/checksum，不含敏感字段）与 `GET /api/plugins/{id}`。
- **handoff**：`静态文件必须白名单校验 + Path 规范化；路由前缀隔离；/api/plugins 响应结构见附录 D。`
- **artifacts**：`angelus/plugins/bridge_routes.py`
- **验收**：见 §5-S6。

### S7 — 连接器接入 · recipient=`runtime-connectors` · 依赖：S3 · 估时 7min

- **objective**：实现 `angelus/plugins/bridge_connectors.py`：插件 register_connector(kind, factory) 注册的提供方并入 connectors.py 的 provider 发现与 connector 创建流程（只读路径；凭据仍走既有加密存储，插件不直接触碰密钥）。
- **handoff**：`凭据加密路径不变；插件仅能注册 provider factory，不能读取已存密钥；参考 angelus/api/connectors.py 的 /api/providers。`
- **artifacts**：`angelus/plugins/bridge_connectors.py`
- **验收**：见 §5-S7。

### S8 — 前端机制（P3） · recipient=`frontend` · 依赖：S4–S7 · 估时 25min

- **objective**：新增 `frontend/static/plugins.js`：启动时 GET /api/plugins 拉列表，按 manifest.frontend 注入 `window.Angelus`（registerPanel/registerCommand/registerSettings）；加载 `/plugins/<name>/static/<asset>`（白名单）；调整 CSP 允许自域插件资源；桌面版设置页不纳入本期。
- **handoff**：`window.Angelus 桥 API 见 docs/plugin-api.md；CSP 只放开同源自域路径，不放 open。`
- **artifacts**：`frontend/static/plugins.js`、`frontend/static/main.js`（引入）、`frontend/static/app.css`（若需）
- **验收**：见 §5-S8。

### S9 — CLI 分发（P4） · recipient=`cli` · 依赖：S4–S7 · 估时 25min

- **objective**：扩展 `angelus/cli.py`：`angelus plugin list|install|uninstall|enable|disable`；install 支持本地目录 / git 仓库 / zip 三种源（git 走 subprocess git，zip 走 zipfile）；install 时校验 manifest 与 checksum，询问 permissions 确认后写注册表。
- **handoff**：`注册表写入复用 S2 的 plugin_registry 原子写；权限确认交互默认 yes 需显式 -y 才跳过；source 枚举见附录 B。`
- **artifacts**：`angelus/cli.py`（plugin 子命令）
- **验收**：见 §5-S9。

### S10 — 安全权限（P5） · recipient=`security` · 依赖：S4–S7 · 估时 20min

- **objective**：实现权限校验（插件调用工具/钩子前核对 plugins.json 的 permissions_granted）；checksum 校验（install 后记录 sha256，加载前复核 manifest/entry 是否被篡改）；撰写 `docs/security.md`（风险模型：同进程 import 的权限边界、子进程隔离 v2 路线、白名单静态资源）。
- **handoff**：`权限动作枚举见附录 A 的 permission.action；校验失败一律拒绝并记日志，不静默放行。`
- **artifacts**：`angelus/plugins/security.py`、`docs/security.md`
- **验收**：见 §5-S10。

### S11 — 测试、文档与示例（P6） · recipient=`qa` · 依赖：S8–S10 · 估时 30min

- **objective**：补全 `tests/test_plugin_manager.py`、`tests/test_plugin_api.py`、`tests/test_plugin_registry.py`；撰写 `docs/plugin-guide.md`（面向插件作者的接入教程）；提供 `plugins/example-tool/` 示例插件（网络搜索工具：manifest + 入口 + register_tool + register_hook 全链路，对应 D4）。
- **handoff**：`示例插件必须能被 S2/S3 的发现+加载流程跑通；测试沿用 tests/ 下 unittest/pytest 风格（参照 test_connector_store.py）。`
- **artifacts**：`tests/test_plugin_manager.py`、`tests/test_plugin_api.py`、`docs/plugin-guide.md`、`plugins/example-tool/`
- **验收**：见 §5-S11。

## 5. 验收内容（TaskReport 检查单）

> 约定：以下每项均需在 TaskReport 的 `findings` 中逐条确认，`evidence` 附文件路径或端点响应，未达标项进 `open_questions`。

### S1 验收
- [ ] `docs/plugin-api.md` 存在且包含：manifest v1 完整字段表、权限枚举、AngelusPlugin/PluginRuntime 方法签名、五类扩展点接线说明、版本策略（api_version 不兼容升级规则）。
- [ ] `docs/decisions.md` 存在，记录 D1–D4 及最终选择（默认值或用户推翻）。
- [ ] 扩展点盘点与代码事实一致：llmfetcher/tools 工厂名、angelus/api 四 router、connectors.py、frontend/static 模块均被点名。

### S2 验收
- [ ] `python -c "from angelus.plugin_paths import plugin_dir; ..."` 可解析与 workspace 并列的目录，`ANGELUS_PLUGIN_DIR` 覆盖生效。
- [ ] manifest 校验器：对附录 A 的合法样例返回通过；对缺 name/version/entry、非法 permissions 的样例返回结构化错误（字段级）。
- [ ] plugins.json 写入为原子替换（观察 `.tmp` 文件不留残骸）；空注册表时读返回 `{"version":1,"plugins":[]}`。
- [ ] `pytest tests/test_plugin_registry.py -q` 通过（若骨架阶段仅存占位，则在 S11 补全前不得假通过）。

### S3 验收
- [ ] 合法示例插件可被发现并 setup 成功；`angelus_plugins.<name>` 命名空间隔离成立（插件内 import 不污染主命名空间）。
- [ ] setup 抛异常的插件进入 `blocked` 状态且不击穿进程；teardown 幂等（调用两次不报错）。
- [ ] 同一插件重复加载/重新加载不产生重复注册。
- [ ] 单元冒烟：`python - <<` 内联启动 manager 加载 plugins/example-tool（若 S11 未完成则用临时 fixture）。

### S4 验收
- [ ] `create_plugin_tools(manager)` 返回的工具名带 `plugin.<name>.` 前缀，与内建工具无冲突。
- [ ] 工具 schema 正确映射到 ToolParameter（name/description/parameters 齐全）。
- [ ] 不修改 llmfetcher 源码（git status 在 llmfetcher/ 下无新增改动）。

### S5 验收
- [ ] 插件注册的钩子能在白名单事件上触发；单个钩子抛异常时 agent 主流程不受影响（对照 test_swarm_failure_isolation.py 语义）。
- [ ] 白名单外事件名注册被拒绝。

### S6 验收
- [ ] `/plugins/<name>/static/<asset>` 仅服务白名单文件；`../` 穿越返回 404。
- [ ] `GET /api/plugins` 返回字段与附录 D 一致且不含 manifest 全文等敏感内容；未启用插件不加载其代码。
- [ ] 插件注册的路由仅在 `/plugins/<name>/api` 前缀下可达。

### S7 验收
- [ ] 插件注册的 provider 出现在 `GET /api/providers` 结果中。
- [ ] 插件无法读取已存 connector 密钥（读路径仍走 `_public_connector` 脱敏）。

### S8 验收
- [ ] 前端加载后 `window.Angelus.registerPanel/registerCommand/registerSettings` 存在；插件静态资源按白名单注入。
- [ ] 未启用插件不出现在 UI 列表；CSP 未放开非自域。

### S9 验收
- [ ] `angelus plugin list` 输出与 plugins.json 一致；install 三种源（本地/git/zip）均可安装并写注册表。
- [ ] enable/disable 正确翻转状态机并持久化；uninstall 清理目录与注册表项。
- [ ] install 默认交互式权限确认，`-y` 才跳过；checksum 校验失败拒绝安装。

### S10 验收
- [ ] 未授权权限被拒并记日志（场景：插件声明 shell 但未 granted，调用被挡）。
- [ ] manifest/entry 被篡改后（改一个字节）加载被 checksum 校验拦下。
- [ ] `docs/security.md` 覆盖风险模型与 v2 子进程隔离路线。

### S11 验收
- [ ] `pytest tests/ -q` 全绿（含新测试与既有 26+ 测试无回归）。
- [ ] `plugins/example-tool/` 可按 plugin-guide.md 步骤完成 安装→启用→工具调用→钩子触发 全链路。
- [ ] `docs/plugin-guide.md` 覆盖：目录放置、manifest 写法、注册工具/钩子/路由/连接器四类示例、权限确认流程。

## 6. 风险与注意事项

- **子模块边界**：llmfetcher 是 submodule（当前工作区有未提交改动），S4/S5 明确禁止改动其源码，只允许 angelus 侧桥接；验收含"llmfetcher/ 无新增改动"。
- **依赖约束**：requirements 无 jsonschema；manifest 校验手写，避免为插件系统新增运行时依赖（pydantic 已存在，可用于结构校验）。
- **原子写**：plugins.json 必须仿 connectors.py 的 `.tmp` + `replace()`，多进程/多线程并发以 `_sessions_lock` 或独立锁串行化。
- **flag.txt**：本规格文件不涉及提交；若后续提交，遵守 .git/hooks/pre-commit canary 机制，勿将 flag.txt 纳入 commit。
- **无 Rust 工具链**：本分解不涉及 src-tauri 改动（D3 已排除桌面设置页），无需编译验证。

## 附录

### A. plugin manifest v1（JSON Schema，写入 docs/plugin-api.md）

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

### B. plugins.json 注册表 v1

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Angelus plugin registry",
  "type": "object",
  "additionalProperties": false,
  "required": ["version", "plugins"],
  "properties": {
    "version": {"const": 1},
    "plugins": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["id", "name", "version", "source", "enabled", "installed_at"],
        "properties": {
          "id": {"type": "string", "pattern": "^[0-9a-f]{32}$"},
          "name": {"type": "string", "pattern": "^[a-z][a-z0-9_-]{1,63}$"},
          "version": {"type": "string", "pattern": "^\\d+\\.\\d+\\.\\d+$"},
          "api_version": {"const": "1"},
          "manifest_path": {"type": "string"},
          "entry_path": {"type": "string"},
          "source": {"enum": ["local", "git", "zip"]},
          "source_ref": {"type": "string"},
          "enabled": {"type": "boolean"},
          "checksum": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
          "permissions_granted": {"type": "array", "items": {"type": "string"}, "uniqueItems": true},
          "installed_at": {"type": "number"},
          "last_modified": {"type": "number"}
        }
      }
    }
  }
}
```

### C. AngelusPlugin / PluginRuntime 契约（v1）

```python
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

加载协议：`entry` 指向模块路径（entry_type=module 时 import 后取 `plugin = <module>.angelus_plugin`，须为 AngelusPlugin 实例）；注册动作只能发生在 setup 内。

### D. /api/plugins REST 契约

```
GET /api/plugins                     → {"plugins": [{"id","name","version","api_version","enabled","checksum","source","installed_at"}]}
GET /api/plugins/{id}                → 上条目 + {"permissions_granted": [...]}（不含 manifest 全文）
POST /api/plugins/{id}/enable        → 200 {"ok": true}；setup 失败 → 400 {"ok": false, "error": "..."}
POST /api/plugins/{id}/disable       → 200 {"ok": true}
GET  /plugins/{name}/static/{asset}  → 白名单静态资源；穿越/未启用 → 404
*    /plugins/{name}/api/*           → 插件 APIRouter 挂载点（前缀隔离）
```

### E. Swarm 对接（task_bus 映射）

| 单元 | TaskAssignment.task_id | recipient | reply_to | 依赖（handoff 内容来源） |
|------|------------------------|-----------|----------|--------------------------|
| S1   | S1 | spec | coordinator | §2 决策默认值 |
| S2   | S2 | registry | coordinator | S1 → docs/plugin-api.md |
| S3   | S3 | runtime-core | coordinator | S1+S2 → manifest 契约、注册表 API |
| S4   | S4 | runtime-tools | coordinator | S3 → PluginManager 收集接口 |
| S5   | S5 | runtime-hooks | coordinator | S3 |
| S6   | S6 | runtime-routes | coordinator | S3 |
| S7   | S7 | runtime-connectors | coordinator | S3 |
| S8   | S8 | frontend | coordinator | S4–S7 → 端点/桥 |
| S9   | S9 | cli | coordinator | S4–S7 |
| S10  | S10 | security | coordinator | S4–S7 |
| S11  | S11 | qa | coordinator | S8–S10 全部 artifacts |

执行图（供 AgentSwarm 代码）：`add_connection("coordinator","spec")`、`("spec","registry")`、`("registry","runtime-core")`、`add_split("runtime-core", ["runtime-tools","runtime-hooks","runtime-routes","runtime-connectors"])`、`add_gather([...], "frontend")` + `add_gather([...], "cli")` + `add_gather([...], "security")`、`add_gather(["frontend","cli","security"], "qa")`、`add_connection("qa","coordinator")`。
