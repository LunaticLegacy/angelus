# plugins/ — Plugin Examples INDEX

开发期插件示例，也是桌面发布包的默认 starter plugins。首次启动时会被复制到与 `workspace/` 并列的持久 `plugins/` 目录；仅供发现，不会自动加载或覆盖用户文件。生产插件由 `angelus/plugins/` 的运行时发现、校验与加载；具体格式见 [`../docs/plugin-guide.md`](../docs/plugin-guide.md)。

| Entry | Type | Purpose |
|---|---|---|
| `demo-hello/` | End-to-end example | 演示面板、命令、工具、钩子、路由以及可选 CSS 前端资产。 |
| `example-tool/` | Tool example | 演示网络搜索工具和 `tool.before` / `tool.after` 钩子。 |

每个示例目录的 `manifest.json` 是声明式入口；`main.py` 是 Python 实现，`plugin.js` / `plugin.css`（如存在）是被清单白名单允许的前端资源。
