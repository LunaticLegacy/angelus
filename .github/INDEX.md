# .github/ — Automation INDEX

仓库自动化工作流。

| File | Trigger and responsibility |
|---|---|
| `workflows/ci.yml` | Pull Request 与主分支推送的基础测试、检查和 Python 包验证。 |
| `workflows/desktop-release.yml` | `v*` 标签触发的 Linux / Windows 桌面包构建与 Draft Release 上传。 |
