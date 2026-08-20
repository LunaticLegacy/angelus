<div align="center">

<img src="src-tauri/icons/icon.png" alt="Angelus icon" width="96" height="96" />

# Angelus

### 可观测、可恢复、可追溯的 Agent 研究工作台

[最新版本 v0.3.0-alpha](https://github.com/LunaticLegacy/angelus/releases/tag/v0.3.0-alpha) · [项目概览](#为什么选择-angelus) · [快速开始](#快速开始) · [桌面应用](#桌面应用) · [开发](#开发与验证) · [文档导航](#文档导航)

</div>

![Angelus multi-agent execution graph](docs/assets/angelus-hero.png)

Angelus 是一个本地优先的 Agent 控制平面，面向需要可靠执行过程、明确证据链和长期任务恢复能力的研究与工程工作流。它建立在 [LLMFetcher](llmfetcher/INDEX.md) 之上，将模型调用、工具执行、协作式任务拆分与持久化状态收拢到一个可检查的工作台中。当前发布线为 `v0.3.0-alpha`。

```text
研究任务 → 任务计划 → Agent / Swarm 执行 → 工具与证据 → 可审计结论
```

## 为什么选择 Angelus

| 关注点 | Angelus 的做法 |
| --- | --- |
| 过程可见 | 实时呈现任务计划、Agent 拓扑、事件 Trace、工具调用和 Token 用量。 |
| 长任务可控 | 支持协作式停止、强制停止、持久化事件以及刷新或重启后的状态恢复。 |
| 协作可审计 | Worker 以结构化报告、证据和产物交接；原始执行记录保留用于复盘。 |
| 数据本地优先 | 会话、连接器、执行图和上下文默认保留在本机，可迁移到指定状态目录。 |
| 运行形态灵活 | 同一控制面既可作为浏览器工作台运行，也可打包为 Tauri 桌面应用。 |

## 核心能力

| 能力 | 说明 |
| --- | --- |
| 持久化会话 | 保存会话、事件账本、运行状态和兼容性对话投影。 |
| 任务计划 | 将目标拆分为可状态化、可更新、可追踪的执行单元。 |
| Agent Swarm | 协调多个具备不同职责的 Agent，并通过受限报告完成交接。 |
| 实时观测 | 通过 SSE 展示生命周期、工具调用、Trace 与用量账本。 |
| Graph / Archive Memory | 结合线性上下文、压缩归档和图检索提供长期记忆。 |
| TLB RAG | 基于 `INDEX.md` 检索树路由到最小充分的知识文件。 |
| 插件系统 | 提供受权限、完整性校验和命名空间隔离保护的工具、路由、钩子与连接器扩展点。 |
| MCP 工具 | 使用官方 Python `mcp` SDK 连接 stdio、Streamable HTTP 或兼容 SSE 服务，将发现到的远端工具直接加入 Agent。 |
| 桌面封装 | 通过 Tauri 与 Python sidecar 交付本地桌面工作台。 |

## 适用场景

- 深度研究、情报分析与报告生成
- 代码库理解、技术尽调与工程协作
- 需要证据链和执行留痕的安全分析
- 企业知识检索与受控工具调用
- 需要暂停、复盘和恢复的长时 Agent 任务

## 架构一览

```text
┌──────────── Browser / Tauri Desktop ────────────┐
│  会话 · 设置 · 计划 · Trace · Agent 图 · 用量     │
└──────────────────────┬──────────────────────────┘
                       │ FastAPI + SSE
┌──────────────────────▼──────────────────────────┐
│ Angelus control plane                            │
│ API · 运行控制 · 持久化 · 连接器 · 插件 · 会话记忆 │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│ LLMFetcher                                       │
│ 模型后端 · Agent loop · Context · Graph · Swarm · Tools │
└─────────────────────────────────────────────────┘
```

## 快速开始

### 前置条件

- Python 3.12+
- Git（用于初始化 `llmfetcher` 子模块）
- 一个可访问的模型服务及其连接器配置

### Web 工作台

```bash
git clone --recurse-submodules git@github.com:LunaticLegacy/angelus.git
cd angelus

python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows PowerShell: .\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip setuptools
python -m pip install --no-build-isolation -e ./llmfetcher
python -m pip install --no-build-isolation -e ".[test]"

angelus web --host 127.0.0.1 --port 8765
```

打开 <http://127.0.0.1:8765>，先创建连接器，再新建会话即可开始工作。

### Kimi Code 连接器

在“设置 → 连接器”的 Provider 中选择 **Kimi Code**，工作台会自动填写
`https://api.kimi.com/coding/v1` 和默认模型 `kimi-for-coding`。填入在 Kimi
Code Console 创建的 API Key 后即可保存为连接器；该 Key 与 Kimi 开放平台的
API Key 不通用。具备相应会员权限时，也可将模型改为 `k3` 或 `k3-256k`。

## 桌面应用

桌面壳会启动本地 FastAPI 控制面，并在窗口退出时回收 Python 子进程。发布构建将 Python 后端打包为 sidecar，最终用户不需要预先安装 Python。

```bash
npm install
python -m pip install -r requirements-desktop.txt
npm run dev       # 开发运行
npm run build     # 构建安装包
```

可使用 `ANGELUS_BACKEND_EXECUTABLE` 在开发时指定一个自定义后端可执行文件。构建 sidecar 可运行 `npm run build:backend`；在 Windows 上建议从 Git Bash 执行该脚本。

## 数据、权限与隐私

默认状态目录为本机 `workspace/`，也可通过 `LLMFETCHER_STATE_DIR` 指定其他磁盘、容器卷或临时目录。插件始终位于其同级的 `plugins/` 目录；桌面发布包内含 `demo-hello` 与 `example-tool` 两个示例，它们会在首次启动时复制到该持久目录，但不会自动加载或获得权限。每个会话独立保存：

| 文件或目录 | 用途 |
| --- | --- |
| `conversation.json` | 面向 UI 的兼容性对话投影 |
| `events.ndjson` | 可重放的生命周期与执行事件账本 |
| `contexts/` | Agent 上下文、压缩归档与图记忆投影 |
| `graph-view.json` | Swarm 执行图快照 |
| `task-plan.json` | 任务计划 |
| `run-state.json` | 不含凭据的运行状态与配置快照 |

```text
<应用数据>/
├── workspace/   # 会话、连接器和运行状态
└── plugins/     # 所有已发现的插件（与 workspace 并列）
```

保存的连接器 API 密钥使用 RSA-OAEP 加密；浏览器 API 不会返回密钥内容。插件仅能在明确授权、完整性校验通过且被启用后接入宿主能力。详情见 [安全设计](docs/security.md) 与 [插件 API](docs/plugin-api.md)。

### MCP 工具

在“设置 → Agent 执行”勾选“启用 MCP 工具”，填写 MCP server JSON 后，工作台会在每次运行开始前通过官方 Python `mcp` SDK 发现远端工具，并以 `mcp.<server>.<tool>` 的名称加入该次运行的所有 Agent（包括 Swarm Worker）。支持本地 `stdio`、Streamable HTTP，以及用于兼容旧服务的 SSE。

```json
[
  {
    "name": "filesystem",
    "transport": "stdio",
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "C:\\Users\\you\\Documents"],
    "env": []
  }
]
```

配置只保存在当前浏览器的本地设置中；`env` 仅接受宿主机已有的环境变量名，不接受或保存密钥值。MCP 服务器可暴露有副作用的远端能力，因此只应启用你信任的服务器与工具。

## 开发与验证

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
cargo check --manifest-path src-tauri/Cargo.toml
```

持续集成位于 [`.github/workflows/`](.github/INDEX.md)。推送 `v*` 标签会触发桌面端发布构建，并将产物上传到 Draft GitHub Release。

## 项目结构

```text
angelus/       Python 控制平面：API、运行控制、会话、存储、插件
llmfetcher/    子模块：模型后端、Agent、工具、RAG、图记忆与 Swarm
frontend/      浏览器工作台：模板、样式、ES 模块
plugins/       示例与开发期插件
scripts/       桌面 sidecar 的入口与构建脚本
src-tauri/     Tauri 桌面壳与打包配置
docs/          架构、决策、安全与插件文档
tests/         回归测试
```

完整的可检索目录树见 [INDEX.md](INDEX.md)。

## 文档导航

| 主题 | 文档 |
| --- | --- |
| 架构与代码语义 | [docs/semantic-map.md](docs/semantic-map.md) |
| 图上下文与归档检索 | [docs/graph_context_design.md](docs/graph_context_design.md) |
| 插件开发 | [docs/plugin-guide.md](docs/plugin-guide.md) · [docs/plugin-api.md](docs/plugin-api.md) |
| 安全边界 | [docs/security.md](docs/security.md) |
| 设计决策 | [docs/decisions.md](docs/decisions.md) |
| LLMFetcher | [llmfetcher/INDEX.md](llmfetcher/INDEX.md) |

## 许可证与商业授权

Angelus 采用 AGPL-3.0-or-later，同时保留商业授权路径。LLMFetcher 是独立仓库，适用其自身的版权和许可证声明。

- [LICENSE](LICENSE)
- [LICENSING.md](LICENSING.md)
- [commercial-licensing.md](commercial-licensing.md)
