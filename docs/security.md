# Angelus 插件系统 — 安全模型（S10）

> 状态：v1 定稿（对应 `docs/plugin-swarm-execution.md` §4-S10 与 `docs/plugin-api.md` §3）
> 实现：`angelus/plugins/security.py`（权限门禁 + integrity checksum + 审计日志）
> 本文档描述插件系统的**风险模型**、v1 的安全边界与 v2 子进程隔离路线。任何安全相关决策
> 的变更（新增权限 action、放宽白名单、改变 checksum 语义）必须先更新本文档再改代码。

## MCP 凭据与项目边界

MCP server 定义属于全局应用状态，项目目录只接收运行时解析后的访问，不保存
server 配置或秘密。静态 Header、Bearer/OAuth token、OAuth client secret 和 stdio
环境变量值逐项使用本机 RSA-OAEP 密钥加密；公共 API 只返回字段名与“已配置”标记。
`${project_root}` 仅允许出现在 stdio `args`/`cwd`，URL、command、Header 和秘密字段
拒绝模板。每个会话单独授权 server、Coordinator/Worker 角色和工具白名单；旧 SSE
transport 被拒绝。MCP roots 只暴露当前会话绑定的项目根目录，不暴露状态目录。

---

## 1. 威胁模型与信任边界

插件系统引入的资产与信任假设：

| 资产 | 说明 | 保护目标 |
|------|------|----------|
| 主进程能力 | shell 执行、网络、文件系统、环境变量、connector 凭据 | 未被授予的插件**不得**触碰 |
| 用户数据 | 会话、workspace 文件、connector 元数据 | 只读/只写需显式授权 |
| 插件自身 | 安装目录下的 manifest 与入口代码 | 安装后被篡改不得被加载 |
| 审计日志 | `angelus.plugins.security` logger | 拒绝事件必须可追溯 |

信任边界（v1，D1 决策）：

1. **同进程 import**（D1 默认）：插件代码以 `angelus_plugins.<name>` 命名空间 import 进主进程，
   **与主进程同特权级**。插件一旦被加载，其 Python 代码能访问主进程能访问的一切；
2. 因此 v1 的防线**不是运行时沙箱**，而是**权限门禁**——插件只能通过 `PluginRuntime` 提供的
   注册面暴露扩展点，而扩展点背后的宿主能力（工具、钩子、路由、连接器）在真正执行前必须
   经过 `check_permission` 核对 `plugins.json` 的 `permissions_granted`；
3. **不在白名单内的能力一律拒绝并记日志，绝不静默放行**（fail closed）；
4. **未启用（disabled）的插件不 import、不执行**（S3 `load_all` 只加载 registry 中 enabled 的插件，
   S10 在运行时门禁中再次确认 `enabled is True`，双保险）。

---

## 2. D1 同进程 import 的权限边界

### 2.1 为什么 v1 选择同进程 import

MVP 阶段与内建工具（shell/swarm/knowledge 等）同权，实现简单、调试直观；子进程隔离
（真正的沙箱）成本高，列为 v2 路线（§8）。

### 2.2 边界如何成立（v1）

同进程 import 下权限边界**不能依赖 Python 层面的强制**（插件代码可 `import os` 后自行
`subprocess.run`），边界成立依赖三个正交机制：

1. **能力注册面收窄**（S3/S4–S7）：插件只能通过 `PluginRuntime.register_*` 在 `setup()`
   内注册扩展；bridge 层（`bridge_tools.py` / `bridge_hooks.py` / `bridge_routes.py` /
   `bridge_connectors.py`）是宿主能力与插件之间的唯一通道；
2. **权限门禁前置于能力执行**（S10）：bridge 层在把插件 handler 接入宿主能力（shell 工具、
   钩子总线、静态文件、connector 读取）**之前**调用 `check_permission`；未授权则拒绝并记日志；
3. **启用门**（S3+S10）：registry 未启用或启用时未授予权限的插件，其代码根本不进入执行路径。

### 2.3 已知边界与残余风险（v1 必须明示）

| 风险 | 说明 | v1 缓解 | v2 缓解（§8） |
|------|------|---------|---------------|
| 恶意插件代码 | 插件 setup/handler 内可任意 `import`、`exec`、`open` | 权限门禁 + 用户 install 时逐项确认权限；代码即信任 | 子进程沙箱 + 系统调用过滤 |
| 权限提权 | 插件利用宿主 bug 绕过门禁 | 门禁为唯一入口；审计日志留痕 | 更小攻击面 + seccomp |
| 供应链篡改 | 安装后插件被改 | **checksum 复核**（§6） | 签名/远程证明 |
| 密钥窃取 | 插件读取 connector 密钥 | `_public_connector` 脱敏 + 只读路径（§5） | 密钥永不进子进程 |

**结论**：v1 的权限边界是"信任插件作者 + 门禁拦截误用/越权调用"，不是"隔离不可信代码"。
插件安装即信任（用户显式确认权限清单），这一立场写入 v1 文档与 CLI 交互文案。

---

## 3. 权限模型

### 3.1 动作枚举（9 个，均需 scope）

| action | 含义 | 典型 scope（1–512 字符） |
|--------|------|--------------------------|
| `shell` | 执行本地 shell 命令 | 命令/目录模式 |
| `network` | 发起网络连接 | 域名/端口 |
| `fs.read` | 读取文件 | 路径前缀 |
| `fs.write` | 写入文件 | 路径前缀 |
| `env` | 读取环境变量 | 变量名 |
| `http` | HTTP 请求 | URL 模式 |
| `connector.read` | 读取连接器元数据（**不含密钥**） | provider 名 |
| `connector.write` | 写入/更新连接器 | provider 名 |
| `event.subscribe` | 订阅 agent 事件 | 事件名（白名单内） |

### 3.2 声明 vs 授予

* **声明**（`manifest.permissions`，permission 对象数组）＝ 插件**请求**的权限；
* **授予**（`plugins.json[].permissions_granted`，`"action:scope"` 字符串数组）＝ 用户**批准**的权限；
* 运行时的唯一判据是**授予**。插件声明了 `shell` 但未被授予 ⇒ 调用被拒并记日志；
  插件声明之外、被授予的权限（如 install 时勾选）同样有效——授予是权威；
* install/enable 流程（S9）以 `declared_permissions(manifest)` 生成确认清单，用户逐项批准后
  才写入 `permissions_granted`；`-y` 只跳过交互确认，不跳过门禁。

### 3.3 门禁语义（`angelus/plugins/security.py::check_permission`）

```
check_permission(plugin_id, action, scope, registry=None) -> bool
```

1. `action` 不在 9 枚举 ⇒ 拒绝（error 级日志，fail closed）；
2. `scope` 非字符串或长度不在 1..512 ⇒ 拒绝；
3. registry 中找不到插件记录（或 registry 读失败）⇒ 拒绝（`reason=not-installed` /
   `REGISTRY_LOOKUP_FAILED`）；
4. 插件未启用（`enabled is not True`）⇒ 拒绝（`reason=plugin-disabled`）；
5. `permissions_granted` 不含精确的 `"action:scope"` ⇒ 拒绝（`reason=not-granted`）。

`registry` 参数可注入（默认 `angelus.plugin_registry`），bridge/CLI/测试均可传入替代实现；
`require_permission` 提供异常语义（deny 时抛 `PermissionError`）。

---

## 4. 事件白名单（hooks）

插件可订阅的事件名（点命名，见 `docs/plugin-api.md` §5）：

`agent.started`、`agent.stopped`、`tool.before`、`tool.after`、`session.created`

* 白名单由 S3 `angelus/plugins/base.py::HOOK_EVENTS` 定义，bridge（S5）映射到内部冒号事件；
* **白名单外事件注册被拒绝**（`register_hook` 拒绝 + 日志）；
* 钩子同步调用、单个钩子异常被隔离（不击穿 agent 主流程）；
* `event.subscribe` 权限的 scope 应为白名单内事件名，由门禁与白名单双重校验。

---

## 5. connector 密钥不可读

* connector 凭据走既有 RSA-OAEP 加密存储（`angelus/connectors.py`），**解密只发生在服务端
  发起 run 的那一刻**（`_resolve_connector_key`）；
* 插件只能注册 provider factory（`register_connector`，S7），**不能读取已存密钥**；
* 插件可读取的 connector 元数据（`connector.read` 授权后）一律经过 `_public_connector` 脱敏：
  仅返回 `id/name/provider/model/api_url/has_api_key`，任何密钥字段不进入该视图；
  `security.redact_connector(record)` 封装该边界（本地兜底：剥离名称含
  key/secret/token/password/credential 的字段）；
* **规则**：插件拿到的 connector 信息中 `has_api_key` 只回答"有没有"，永远不回答"是什么"。

---

## 6. checksum 防篡改

### 6.1 覆盖对象与格式

* 格式 `^sha256:[0-9a-f]{64}$`（`manifest.checksum` 与 `plugins.json[].checksum` 同构）；
* **安装期**（S9 cli install / `compute_plugin_integrity`）对插件的**已安装载荷**计算：
  `sha256( canonical(manifest 去掉 checksum 字段) + "\n" + entry 文件字节 )`；
  * canonical = `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)`，
    键序与空白不敏感、**任何值的一字节变化都会改变哈希**；
  * `checksum` 字段自身从哈希输入中排除，值才能自洽地写回 manifest（无循环）；
  * 同时覆盖 manifest 与 entry ⇒ manifest 或 entry 任一改一字节即校验失败。
* 校验值同时写入 `manifest.checksum`（随插件目录自描述）与 `plugins.json[].checksum`
  （registry 交叉核对）。

### 6.2 加载前复核（`verify_plugin_integrity`）

```
verify_plugin_integrity(plugin_dir, manifest, *, expected=None) -> (ok, errors)
```

由 **manager load 在 import/setup 之前**调用（S3 预留的 verify 钩子位，见
`docs/plugin-swarm-execution.md` §4-S3"加载前复核"），cli install/重装亦调用：

1. manifest 无合法 checksum ⇒ 拒绝加载（`reason=missing-checksum`）——**未记录的插件不加载**；
2. entry 无法在插件目录内解析为文件（含路径穿越尝试）⇒ 拒绝（`reason=entry-unresolvable`）；
3. 重算载荷哈希与期望值不一致（改一字节即不相等，`hmac.compare_digest` 常数时间比较）
   ⇒ 拒绝（`reason=checksum-mismatch`），错误级日志记录 expected/actual/entry；
4. `expected` 可注入：manager 若同时持有 registry 记录，可传入 `plugins.json[].checksum`
   做第二重比对（防"manifest 被整体替换成新 checksum"式协同篡改）。

### 6.3 边界（明示）

* checksum 是**篡改检测**（防意外损坏/部分篡改/被替换后重新计算可绕过），不是防恶意
  攻击者的**防伪**——能重写 checksum 的写入者不在本模型威胁内（registry 0600、应用私有）；
* 完整防伪/签名与远程证明列入 v2 路线（§8）。

---

## 7. 白名单静态资源（S6）

* `/plugins/<name>/static/*` **只服务 `manifest.frontend.assets` 白名单内的文件**；
  白名单外的文件一律 404；
* 服务前做 **Path 规范化 + 白名单校验**：`../`、绝对路径、符号链接逃逸解析后必须仍落在
  插件目录内（与 `security._resolve_entry_path` 同款 `resolve()` + `is_relative_to` 防线）；
* 未启用插件不挂载静态资源；CSP 只放开同源自域插件路径，不放宽 `open` 等指令（S8）；
* 插件路由仅挂载于 `/plugins/<name>/api` 前缀下，前缀隔离。

---

## 8. v2 子进程隔离路线

D1 的 v2 演进：把插件从"同进程 import + 门禁"升级为"独立子进程 + IPC + 系统级隔离"。

| 维度 | v2 目标 | 落地要点 |
|------|---------|----------|
| 进程模型 | 每插件一个子进程（或受限 worker 池） | `multiprocessing`/`subprocess` 起独立解释器；宿主与插件仅经 JSON-RPC/IPC 通道 |
| 命名空间 | 插件目录作为子进程的工作根 | 子进程 `sys.path` 只含插件目录 + 受控依赖 |
| 权限执行 | 门禁下沉到 IPC 边界 | 插件请求能力 ⇒ IPC 消息 ⇒ 宿主 `check_permission` 后代理执行；子进程**无**直接系统能力 |
| 系统隔离 | 依据授予权限施加 OS 级约束 | POSIX：setuid/降权用户 + seccomp-bpf（禁 execve/open 以外的 syscall）+ rlimit（CPU/内存/文件数/进程数）；文件访问经宿主代理或 bind-mount 只读前缀 |
| 网络 | 按 `network`/`http` scope 过滤 | 子进程经宿主代理出网（或 eBPF/nftables 按 scope 限流） |
| 密钥 | 密钥永不进入子进程 | connector 解密仅宿主侧，按需把结果注入单次请求 |
| 生命周期 | 崩溃/超时/资源超限可杀 | 子进程 watchdog；插件 OOM 不拖垮宿主 |
| 兼容 | manifest/API 契约不变 | `api_version` 不因运行时模型变化而提升（§7 版本策略），新增 v2 加载器 |

**v1→v2 迁移**：`verify_plugin_integrity` 与权限门禁接口保持不变（manager load 的 verify 钩子位、
`check_permission(plugin_id, action, scope, registry)` 签名延续），桥接层改动集中在能力代理侧。

---

## 9. 日志审计（拒绝必记日志）

* logger：`angelus.plugins.security`（`logging.getLogger`，`get_logger()` 可取）；
* 行格式：`SECURITY <EVENT> k=v k=v ...`（键排序，机器可解析、grep 友好）；
* 事件表：

| 事件 | 级别 | 触发 |
|------|------|------|
| `PERMISSION_DENIED` | WARNING/ERROR | 未授权调用被拒（含 `reason=unknown-action/invalid-scope/not-installed/plugin-disabled/not-granted`） |
| `PERMISSION_GRANTED` | INFO/DEBUG | 授权放行 / 新授予落盘 |
| `INTEGRITY_DENIED` | ERROR | checksum 复核失败（含 expected/actual/entry） |
| `INTEGRITY_OK` | INFO | 复核通过（加载前） |
| `REGISTRY_LOOKUP_FAILED` / `REGISTRY_UNUSABLE` | ERROR | registry 读取异常（门禁 fail closed） |

* **铁律**：所有拒绝路径**先记日志再返回 False**，不允许静默放行/静默拒绝；
* 审计日志是取证与告警的基础：`reason` 字段区分"配置问题"（not-granted）与"攻击迹象"
  （checksum-mismatch / entry-unresolvable / traversal）。

---

## 10. 集成点速查

| 层 | 调用方 | 调用 |
|----|--------|------|
| S4 tools | `bridge_tools.py`（handler 执行前） | `check_permission(plugin, "shell"/"fs.read"/..., scope)` |
| S5 hooks | `bridge_hooks.py`（注册/触发前） | `check_permission(plugin, "event.subscribe", event)` + HOOK_EVENTS 白名单 |
| S6 routes/static | `bridge_routes.py` | 静态文件白名单 + Path 规范化；路由前缀隔离 |
| S7 connectors | `bridge_connectors.py` | `check_permission(plugin, "connector.read", provider)`；读路径 `redact_connector` |
| S3 manager | `load()` 于 import 前 | `verify_plugin_integrity(plugin_dir, manifest, expected=registry_checksum)` |
| S9 cli | install/re-install | `compute_plugin_integrity` 写 checksum；install 前 `verify_plugin_integrity` 复核 |

---

## 11. 附录：验收对照（§5-S10）

- [x] 未授权权限被拒并记日志（声明 `shell` 但未 granted ⇒ `PERMISSION_DENIED reason=not-granted`）；
- [x] manifest/entry 改一字节 ⇒ `INTEGRITY_DENIED reason=checksum-mismatch`，拒绝加载；
- [x] 本文档覆盖风险模型（§1–§7）与 v2 子进程隔离路线（§8）。
