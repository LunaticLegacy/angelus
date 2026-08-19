# Angelus

### 可观测、可恢复、可追溯的 Agent 研究工作台

Angelus 是一套面向专业研究团队的本地优先 Agent 控制平面。

它不只是“让模型回答问题”，而是把一次复杂研究变成一条可以检查、暂停、恢复和复盘的证据链：

```text
研究任务 → 任务拆解 → 多 Agent 协作 → 工具执行 → 证据交接 → 可审计结论
```

当研究由多个 Agent、工具调用和长时间运行共同完成时，Angelus 帮你回答：

- 谁执行了什么任务？
- 结论依据了哪些证据？
- 任务在哪里中断？
- 如何从上次边界安全恢复？

## 为什么是 Angelus

### 让 Agent 工作过程可见

实时查看任务计划、Agent 拓扑、事件 Trace、工具调用和 Token 用量。总览保持清晰，深入检查时再展开具体 Agent 的执行细节。

### 让长任务可控

支持协作式停止、强制停止、断点恢复和会话持久化。页面刷新、服务重启或运行中断，不会让研究轨迹消失。

### 让多 Agent 协作可审计

Coordinator 将明确的任务包交给 Worker，Worker 返回结构化报告、证据、产物和待解决问题；原始 Transcript 保留用于审计，不会直接污染主 Agent 上下文。

### 本地优先，数据归你

会话、连接器、事件日志、执行图和上下文默认保存在本机 `workspace/`。适合研究机构、企业内网、敏感资料和需要完整留痕的工作流。

### 从浏览器到桌面应用

既可以作为本地 Web 控制台运行，也可以通过 Tauri 打包为 Windows、macOS 和 Linux 桌面应用。Python Agent 运行时与现有前端保持一致，迁移成本低。

## 适用场景

- 深度研究与情报分析
- 代码库理解与技术尽调
- 安全分析与事件调查
- 企业知识检索与报告生成
- 需要证据链、过程审计和长任务恢复的 Agent 产品

## 产品能力

| 能力 | 你得到的结果 |
| --- | --- |
| 持久化会话 | 对话、运行状态和历史在刷新或重启后仍可恢复 |
| 任务计划 | 把复杂目标拆成可跟踪、可更新的执行单元 |
| Agent Swarm | 让多个专长 Agent 协同工作并结构化交接 |
| 实时 Trace | 回放生命周期事件、工具调用和状态变化 |
| 受控 Shell | 在限定工作目录内执行工具，并支持安全停止 |
| 用量审计 | 按 Agent 记录模型调用与 Token 消耗 |
| TLB RAG | 按 `INDEX.md` 层级路由读取最小充分知识文件 |
| 桌面封装 | Tauri + Python sidecar，离线运行本地控制面 |

## 立即运行

### Web 控制台

要求：Python 3.12+、Git，以及可访问所选模型服务的网络环境。

```bash
git clone --recurse-submodules git@github.com:LunaticLegacy/angelus.git
cd angelus

python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools
python -m pip install --no-build-isolation -e ./llmfetcher
python -m pip install --no-build-isolation -e ".[test]"

angelus web --host 127.0.0.1 --port 8765
```

打开 <http://127.0.0.1:8765>，创建连接器并新建会话即可开始。

### Tauri 桌面版

桌面壳会自动启动本地 FastAPI 控制面，并在退出时回收 Python 子进程。发布版使用 PyInstaller sidecar，因此最终用户无需预装 Python。

```bash
npm install
python -m pip install -r requirements-desktop.txt
npm run dev       # 开发运行
npm run build     # 构建安装包
```

开发时可通过 `ANGELUS_BACKEND_EXECUTABLE` 指定自定义后端可执行文件。

## 持续集成与发布

GitHub Actions 已配置在 `.github/workflows/desktop-release.yml`：

- 每次推送 `v*` 标签时，自动构建 Linux、Windows、macOS Intel 和 macOS Apple Silicon 安装包；
- 构建产物自动上传到 GitHub Release，并以 Draft 形式等待发布确认；
- Pull Request 和主分支推送继续由基础 CI 执行测试、编译检查和 Python 包构建。

创建发布版本：

```bash
git tag v0.1.0
git push origin v0.1.0
```

Linux 本地构建 AppImage 需要 `linuxdeploy`、`patchelf` 和 WebKitGTK 开发包；CI 已自动安装这些依赖。若只需本地 Debian/RPM 包，可按 Tauri CLI 的 `--bundles deb,rpm` 选项构建。

## 数据与隐私

每个会话独立保存在 `workspace/<session>/`，包括：

- `conversation.json`：可见对话
- `events.ndjson`：可重放事件流
- `contexts/`：Agent 上下文与工具审计数据
- `graph-view.json`：执行图快照
- `task-plan.json`：任务计划
- `run-state.json`：运行状态

可通过 `LLMFETCHER_STATE_DIR` 将数据迁移到其他磁盘、容器卷或临时目录。

## 开发与测试

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
cargo check --manifest-path src-tauri/Cargo.toml
```

## 项目结构

```text
angelus/       Python 控制平面、会话、运行时和 API
llmfetcher/    模型后端、Agent、工具契约与 RAG 基础库
frontend/      Web 工作台界面
src-tauri/     Tauri 桌面壳与 Python sidecar 配置
tests/         控制平面与运行时回归测试
```

## 许可证与商业授权

Angelus 采用 AGPL-3.0-or-later，并保留商业授权路径。LLMFetcher 是独立版本库，拥有其自身的版权和许可证声明。

- [LICENSE](LICENSE)
- [LICENSING.md](LICENSING.md)
- [commercial-licensing.md](commercial-licensing.md)

如果你正在构建需要可解释执行链的 Agent 产品，欢迎通过 Issue 或 Pull Request 与我们交流。
