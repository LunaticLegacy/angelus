# Changelog

本文件记录 Angelus 的面向用户发行说明，采用
[Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 的结构。

## [0.5.0-rc.0] - 2026-09-02

这是 `0.5.0` 的发布候选版。Angelus 与 llmfetcher 独立版本化；本版本要求
`llmfetcher >=0.4.0,<0.5.0`。

### Added

- Session 作为唯一运行时所有者的控制台 API：任务计划、Agent 图、Trace、用量
  与上下文图均可在重启后恢复。
- 统一的工具注册、权限和 Provider 物化链路；Agent 按有效 Session 策略获得
  当前可用工具。
- 声明式插件功能面板和类型化非敏感插件设置。面板 action 由宿主调用并安全地
  返回文本结果。
- External Agent Hub 的发现、协议适配与外部上下文交换基础设施。
- GZCTF v1 插件迁移：11 个命名空间 Agent 工具、私有 Cookie/下载/批处理状态，
  以及一次性密码登录面板。

### Changed

- 执行、事件流、停止控制、图编辑和右侧控制台统一以 `session_id` 为身份；移除
  workspace-run 兼容执行路径。
- 上下文恢复支持按页读取最近记录，避免恢复窗口时全量读写。
- LLM 输出使用流式 Markdown 渲染，并且只在阅读位置仍处于底部时自动跟随滚动。
- 插件入口以受控 Provider 发布工具；相对模块导入会在插件卸载时一并清理。

### Security

- 密码等敏感字段禁止进入插件持久化设置。声明式面板仅可通过
  `sensitive: true` 与 `format: "password"` 接收一次性密码，且不允许默认值。
- GZCTF Cookie、附件和自动化运行数据均保存在 Angelus 插件私有状态目录，插件
  源码目录不再承载运行时凭据。

### Upgrade notes

- 旧 GZCTF 插件需要在设置中重新扫描并重新加载。保存 `base_url` 与 `username`
  后，再通过“登录 GZCTF”面板建立 Cookie 会话；密码不会迁移或保存。
- 旧的插件 manifest 字段 `entry_type`、`tools`、`commands` 和
  `settings_actions` 不再被 v1 运行时接受，应迁移为 Provider、
  `settings_schema` 与 `frontend.panels`。

[0.5.0-rc.0]: https://github.com/LunaticLegacy/Angelus/releases/tag/v0.5.0-rc.0
