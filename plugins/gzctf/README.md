# gzctf — GZCTF Helper 插件

Angelus 插件：把 GZCTF 比赛平台的能力以工具形式暴露给 agent：

| 工具（完整名 `plugin.gzctf.<tool>`） | 说明 |
|---|---|
| `gzctf_login` | 登录 GZCTF 并持久化会话 Cookie，返回比赛/队伍信息 |
| `gzctf_status` | 检查本地 Cookie 与登录态（不发新登录请求） |
| `gzctf_team` | 拉取当前队伍信息（名称/分数/排名/已解题目数） |
| `gzctf_challenges` | 拉取题目列表，支持分类与关键词过滤 |
| `gzctf_challenge_info` | 拉取单题详情：描述、分数、附件 URL、连接提示 |
| `gzctf_submit_flag` | 提交 flag 并轮询判题结果（accepted/rejected/pending） |
| `gzctf_download` | 用已登录 Cookie 会话下载题目附件到插件私有目录（防路径穿越），返回本地路径与大小 |
| `gzctf_start_instance` | 启动动态题目的实例（`/instance` 优先，404/405 回退 `/container`），返回实例信息与连接提示 |
| `gzctf_batch_prepare` | 创建授权批处理运行并准备附件；不会执行题目求解。 |
| `gzctf_batch_status` | 读取一个授权批处理运行的当前状态。 |
| `gzctf_instance_acquire` | 为批处理中的动态题申请或复用实例。 |

## 安装与启用

1. 在工作台“设置 → 插件”重新扫描并选择 **GZCTF Helper**。
2. 点击“加入工作台”，确认 `network`、`http` 和私有文件写入权限后加载。
3. 在插件设置保存 `base_url` 与 `username`，重新加载插件；再使用 Inspector
   中的“登录 GZCTF”面板输入一次密码。

## 使用

所有工具都接受 `base_url`（GZCTF 站点地址，或含 `/games/{id}` 的比赛链接）。
`base_url` 与 `username` 是工作台维护的非敏感设置，工具调用时留空即回落
保存值。密码仅作为登录面板或 `gzctf_login` 工具的一次性参数，绝不写入设置、
日志或源码目录。

**注意：`password` 不能写入 settings** —— 设置门禁会拒绝 credential 形状的键
（含 password/secret/token/api_key 等，见 `_SENSITIVE_SETTINGS_KEY_PARTS`），
settings 不是第二密钥库。密码只需在每次调用中传入，或仅在 Cookie 失效后重新
登录时传入；登录成功后 Cookie 持久化在插件私有 `state_dir/cookies.txt`，
有效期内的题目/提交/下载请求无需重复传密码。

示例（比赛链接 `https://ctf.example.com/games/42`）：

```
gzctf_login    base_url="https://ctf.example.com/games/42" username="alice" password="***"
gzctf_challenges base_url="https://ctf.example.com/games/42" category="web" keyword="sql"
gzctf_challenge_info base_url="https://ctf.example.com/games/42" title="SQL Injection"
gzctf_download  base_url="https://ctf.example.com/games/42" url="/api/files/xxx.zip" dest="xxx.zip"
gzctf_start_instance base_url="https://ctf.example.com/games/42" challenge_id="7"
gzctf_submit_flag base_url="https://ctf.example.com/games/42" challenge_id="7" flag="flag{...}"
```

`gzctf_download` 的 `url` 可传相对路径（自动基于 `base_url` 拼接）或完整 URL，
`dest` 仅接受文件名（写入 `state_dir/downloads/` 下，拒绝路径穿越）；
`gzctf_start_instance` 用于动态题目，POST `/api/game/{id}/challenges/{cid}/instance`
（404/405 回退 `.../container`），返回合并后的实例 payload 与连接提示。

## 协议要点（与 ElfCTF_POFP 对齐）

- 认证：`POST /api/account/login` → `GET /api/account/profile`，题目/提交接口共用
  Cookie 会话。
- 加密：`GET /api/config` 暴露 `publicKey` 时，password / flag 用 GZCTF 前端同款
  X25519 + AES-GCM 方案加密（惰性依赖 `cryptography`；未启用加密的实例不依赖它）。
- 题目列表：`GET /api/game/{id}/details`（嵌套负载递归展平）。
- 题目详情：`GET /api/game/{id}/challenges/{cid}` 及 `detail`/`details`/`instance`/
  `container` 端点做容忍式合并。
- 附件下载：`GET` 附件 URL（Cookie 会话），写入 `state_dir/downloads/<文件名>`。
- 实例启动：`POST /api/game/{id}/challenges/{cid}/instance`（404/405 回退
  `.../container`）——真实实例验证前为最佳努力实现。
- 提交：`POST /api/game/{id}/challenges/{cid}`（404/405 回退 `.../{cid}/submit`）。
- 判题：`GET /api/game/{id}/challenges/{cid}/status/{sid}` 轮询直到
  accepted/rejected。

## 依赖

- 运行时：仅 Python 标准库（`urllib` + `http.cookiejar`）。
- 可选：`cryptography`（仅当 GZCTF 实例启用 API 加密时提交/登录需要）。
