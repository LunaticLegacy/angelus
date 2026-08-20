# Angelus 插件系统 — 架构决策记录（ADR）

> 状态：定稿（D1–D4 按 swarm 执行规格 §2 默认值执行，用户未推翻）
> 本文件是插件系统四项架构决策的唯一权威记录，下游 handoff 一律引用本文件（勿重复定义）。

---

## D1 插件加载模型：同进程 import

**最终选择**：**同进程 import**，命名空间 `angelus_plugins.<name>`；子进程隔离列为 v2 路线。

- **理由**：MVP 阶段最简单；插件与内建工具在同一权限边界内运行，权限语义一致；无需进程间通信/序列化层。
- **v2 路线**：子进程隔离（sandbox）属运行时模型变更，不改变 manifest 契约；届时随 `api_version` v2 文档发布新的加载/权限语义。
- **安全含义**：同进程模型下权限校验（S10）是唯一边界，未授权权限一律拒绝并记日志，不静默放行（见 `docs/security.md`）。

## D2 插件放置：与 workspace 并列的持久目录

**最终选择**：唯一的 `<app_data>/plugins`，与 `<app_data>/workspace` 并列；可通过环境变量 `ANGELUS_PLUGIN_DIR` 覆盖。

- **路径事实**：
  - 默认：`<app_data>/plugins`，即 `STATE_ROOT`（`<app_data>/workspace`）的父目录；
  - 覆盖：`ANGELUS_PLUGIN_DIR` 存在时取该值；
  - 桌面发布包：内置的示例插件在首次启动时复制到此目录，保留用户修改且不自动执行。
- **理由**：插件跨会话稳定存在，不会随着 workspace 删除；PyInstaller one-file sidecar 的临时解压目录也不会被误作安装位置。
- 插件私有数据目录：`state_dir = <plugin_dir>/<name>/data`。

## D3 桌面版设置页：本期不纳入

**最终选择**：**本期不纳入**桌面设置 UI，仅保留后端 `GET /api/plugins` + 前端机制（`frontend/static/plugins.js` + `window.Angelus` 桥），桌面设置页留 v1.1。

- **理由**：缩减范围，避免 src-tauri（Tauri 侧）改动；无 Rust 工具链验证需求。
- **本期交付边界**：`/api/plugins` 后端端点、前端加载/注入机制、CSP 自域放行；桌面设置 UI、`frontend.settings` 注入页不在本期。

## D4 示例插件：网络搜索工具

**最终选择**：**网络搜索工具**，演示 `register_tool` + `register_hook`（搜索前后事件）全链路。

- **理由**：同时覆盖 tools 与 hooks 两条主线，是插件系统最有代表性的能力组合。
- **交付位置**：`plugins/example-tool/`（manifest + 入口 + register_tool + register_hook），须能被 S2 发现、S3 加载、S4/S5 桥接跑通（安装→启用→工具调用→钩子触发 全链路，S11 验收）。

---

## 决策变更流程

若用户后续推翻任一决策，只改本文件对应条目，并同步更新 `docs/plugin-api.md` 中受影响的契约段落；下游 handoff 引用本文件，无需逐单元重发。
