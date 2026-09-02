# Token Burner 🔥

> v0.1.1：重绘火焰视觉——更自然的不对称焰体、多层内焰、侧舌、白热核心、地面光池与更柔和的余烬/火星。

把 Angelus 的 token 消耗速率可视化成一团火焰的插件：

> **烧得越快，火越旺；空闲时只剩余烬。**

- **独立浮动小窗口**：固定在主工作台之上的可拖动小窗（`position: fixed` 浮层），不占用主界面布局、不是内嵌卡片。
- **可弹出真正独立的窗口**：点击标题栏 `⤢` 或执行 `token-burner:popout` 命令，会打开一个 OS 管理的独立浏览器窗口（`window.html`），可脱离主界面单独存在、拖动、缩放。
- **火随速涨**：火焰高度/亮度/粒子密度/火星数量全部跟随「最近 20 秒平均 token 消耗速率」平滑变化。
- **特效**：分层贝塞尔火焰（白芯→黄→橙→红壳）、上浮粒子、火星飞溅、基底光晕、热浪扭曲、爆燃脉冲。
- **性能友好**：粒子池上限 140、Canvas DPR 上限 2、页面隐藏时冻结渲染、无逐粒子 `shadowBlur`（用预渲染光晕精灵）。

---

## 目录结构

```
plugins/token-burner/
├── manifest.json   # 插件清单（v1 契约；assets 白名单含 window.html）
├── main.py         # 惰性后端入口（不注册任何扩展点，纯前端插件）
├── plugin.js       # 前端入口：数据轮询 + 火焰引擎 + 浮动窗口 + 弹窗
├── plugin.css      # 浮动窗口与弹窗样式
├── window.html     # 独立弹窗页面（经 assets 白名单由后端提供）
└── README.md
```

## 安装方式

### 方式 A：CLI 安装（推荐，带校验与注册）

```bash
# 从本仓库（开发目录）安装
angelus plugin install ./plugins/token-burner

# 或从 zip / git 仓库安装
angelus plugin install /path/to/token-burner.zip
angelus plugin install https://github.com/you/angelus-token-burner.git
```

然后启用并加载：

```bash
angelus plugin enable token-burner
# 在 设置 → 插件 中点击「加载」（manifest 无任何权限请求，无需授权）
```

### 方式 B：目录放置 + 热发现

把 `token-burner/` 整个目录复制到插件持久目录（`<app_data>/plugins/`，可用
`ANGELUS_PLUGIN_DIR` 覆盖，通常与 `workspace/` 同级）：

```bash
cp -r plugins/token-burner "$ANGELUS_PLUGIN_DIR/token-burner"
```

然后在 设置 → 插件 中：
1. 点「加入工作台」（登记并校验 manifest，不执行代码）；
2. 选中 `token-burner` → 点「加载」（无权限提示，直接加载）；
3. 刷新页面后，浮动小窗自动出现。

> 桌面发布包会把 `plugins/` 下的示例目录复制为默认 starter 插件，本插件同样适用。

### 使用

| 操作 | 方式 |
|------|------|
| 显示/隐藏浮动窗口 | 工作台 slash 命令 `/burner: toggle`（或 `window.Angelus.dispatchCommand("token-burner:toggle")`） |
| 弹出独立窗口 | 浮动窗标题栏 `⤢`，或命令 `token-burner:popout` |
| 拖动窗口 | 按住标题栏拖动，位置自动记忆（localStorage） |
| 调参 | 编辑 `localStorage["token-burner.prefs"]`（JSON）：`windowSeconds`（速率平滑窗口，默认 20s）、`scaleTokensPerSec`（满焰阈值，默认 60 tok/s）、`pollMs`（轮询间隔）、`maxParticles`、`showReadout` |

---

## 数据来源（插件实际拿到的数据）

插件是**纯前端**实现（后端 `main.py` 惰性加载，不注册工具/钩子/路由/连接器，
`permissions: []`），只读浏览器本来就能看到的、无凭据的 Angelus API：

1. **`GET /api/sessions/{session_id}/usage`**（主数据源）
   返回会话级累计 token 统计（`usage.total` 等，含每 Agent 明细）。插件每 2 秒
   轮询一次，取**滑动窗口内累计值的斜率**作为燃烧速率：
   `rate = (total_now − total_early) / (t_now − t_early)`（默认 20s 窗口），
   再经 EWMA（α=0.35）平滑。**不用瞬时值**，火焰不会乱抖。
2. **`GET /api/sessions/{session_id}/events?limit=30`**（辅助信号）
   读取持久事件日志中最近 `agent:round` / `agent:complete` / `agent:start`，
   按指数衰减折算成「近期活跃度」。速率为 0 时火焰仍能保持在温热状态，
   每完成一轮就喷一次火星脉冲。

数据局限（如实说明）：`usage` 端点在模型调用**完成一轮后**才更新；流式生成
**过程中**没有 REST 可见的实时用量（`agent:stream_delta` 仅走 SSE、不入持久日志）。
因此火焰节奏是「一轮完成 → 燃烧脉冲 + 速率上升；轮间靠活动度保温」，而不是
逐 token 实时跳动。若要逐 token 实时，需要宿主开放 run 级 SSE 事件给插件
（v1 契约目前不提供该数据面）。

session 的解析与工作台一致：`URL ?session=` → `localStorage.llmfetcherSession` →
`llmfetcherWorkspace` → `"default"`。

## 独立窗口的实现方式（为什么这么选）

调研结论：**v1 插件契约没有 Tauri 侧窗/原生窗口 API**；`window.Angelus` 桥只提供
`registerPanel / registerCommand / registerSettings`，且面板是工作台 inspector 的
内嵌 tab（正是需求排除的「内嵌卡片」）。因此按契约能力内可实现的最强方案是：

1. **主界面内浮动小窗（默认）**：`position: fixed` + 高 z-index + 标题栏指针拖动，
   视觉与交互上「脱离主界面布局」独立存在、可任意拖动、可隐藏；
2. **真·独立窗口（弹窗模式）**：`window.html` 列入 `frontend.assets` 白名单后由
   后端同源服务，`window.open()` 打开一个**独立浏览器/系统窗口**——完全脱离主
   界面，可单独拖动/缩放，可关掉主工作台继续看火。同源，因此共享同一套 API 与
   localStorage 配置。

若后续 Angelus 插件契约新增原生窗口能力（如 Tauri 侧窗），可在保持现有
manifest 不变的前提下，把 `openPopout()` 替换为原生窗口调用。

## 火焰效果说明

| 信号 | 表现 |
|------|------|
| 速率 ≈ 0（空闲） | 只剩余烬：底部一小团暗红光晕 + 极少量慢速粒子，永不熄灭 |
| 速率上升 | 火焰高度（24→142px）与宽度、亮度、粒子发射率（~1.5/s→~95/s）同步增长 |
| 一轮完成 | 爆燃脉冲 `burst=1`，连续喷出 2–3 条火星拖尾 |
| 速率满阈值（默认 60 tok/s） | 满焰：白芯 + 黄/橙/红四层贝塞尔火焰 + 强光晕 + 热浪扭曲 |
| 数据中断 >8s | 速率指数衰减回余烬，避免假火焰 |

所有平滑都在三层完成：窗口斜率平均（20s）→ 轮询级 EWMA → 帧级指数逼近
（`dt*2.4`），保证观感流畅不抽搐。

## 兼容性

- 要求 Angelus 插件系统 v1（`api_version: "1"`），与 `demo-hello`、
  `angelus-control-plane-ui-v0.2.2` 同一契约。
- 无 Python 依赖、无权限请求；纯浏览器标准 API（fetch / canvas / pointer events）。
- 性能：单 canvas、粒子池上限、DPR≤2、`document.hidden` 冻结，低端机也可流畅运行。
