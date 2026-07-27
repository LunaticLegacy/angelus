# Angelus

> 面向专业研究工作流的 Agent 轨迹追溯工作台。

Angelus 让多 Agent 的研究过程不仅能运行，也能被检查、停止、恢复和复盘。它面向
构建或监督研究型 Agent 的开发者与团队：当一个结论由多个 Agent、工具调用和任务交接
共同产生时，你应当能够回答“它为什么得出这个结论、证据来自哪里、过程在哪里中断”。

```text
研究任务 → 任务分解 → 专家 Agent / 工具执行 → 结构化报告交接 → 综合结论
    │                                                                     │
    └──────── 会话、事件、执行图、用量与上下文均可持久化和回放 ────────────┘
```

Angelus 是 [LLMFetcher](./llmfetcher) 的部署与工作台 superproject。
完整实现位于 `llmfetcher/` Git submodule：Python 包、Web Workbench、Agent、
Swarm、持久化、TLB RAG、测试及底层技术文档均在其中维护。Angelus 负责锁定一个
可复现版本，并保存不进入 Git 的本地运行状态。

## 适合谁

- 构建深度研究、情报分析、安全分析、代码分析或知识检索 Agent 的工程师；
- 需要多 Agent 分工、证据交接、长任务恢复与结果审计的团队；
- 不满足于“模型给出了一个答案”，而需要检查执行轨迹和结论来源的人。

它不是面向普通聊天用户的通用 AI 客户端，也不试图替代向量数据库或所有 Agent
框架。它专注于：**让专业 Agent 工作流可观测、可恢复、可追溯。**

## 核心能力

| 能力 | 解决的问题 |
| --- | --- |
| 持久化会话 | 刷新页面或重启服务后，用户消息、Agent 回复和执行状态仍可恢复。 |
| Agent 轨迹 | 记录生命周期事件、任务计划、工具批次、执行图和逐 Agent 用量。 |
| 可控中断 | 协作式停止会保存已完成边界；强制停止会记录终态并清理已登记工具进程。 |
| Swarm 交接 | coordinator 分派 worker；worker 通过 TaskBus 返回结构化报告，而非污染 coordinator 上下文的 raw transcript。 |
| 本地优先 | 连接器、API key 与会话数据保存在本机 `workspace/`，不写入 Git。 |
| 实验性 TLB RAG | 通过 `INDEX.md` 层级路由读取最小充分文件集，适合结构化知识树。 |

## 快速开始

**要求：** Python 3.12+、Git，以及可访问 GitHub 的 SSH 凭据。子模块使用 SSH URL。

```bash
git clone --recurse-submodules git@github.com:LunaticLegacy/angelus.git
cd angelus

python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools
python -m pip install --no-build-isolation -e ./llmfetcher

llmfetcher web --host 127.0.0.1 --port 8765
```

打开 <http://127.0.0.1:8765>，创建 Provider 连接器，选择模型并新建会话，即可开始。
如果 `8765` 已被占用，改用 `llmfetcher web --port 8766`。

> Python 3.14 的最小 venv 可能不自带 `setuptools`。`--no-build-isolation` 让可编辑
> 安装复用当前虚拟环境的构建工具，适合无网络或受代理限制的环境。

### 首次配置

1. 在 Workbench 的“连接”区域创建 Provider 配置，填写 provider、model、可选 API URL 和 API key。
2. 选择或新建会话。
3. 调整最大输出 tokens、温度、Swarm 并发度和上下文压缩阈值。
4. 发送任务；需要协作时启用 Agent Swarm。

上下文压缩阈值默认是 262144 个字符。它控制历史何时压缩，并非模型服务商声明的
context window。Shell 工具只应向受信任模型开放；它的工作目录受限于当前会话目录。

## 运行数据与轨迹

Angelus 会自动使用顶层 `workspace/`。因此升级或重新安装 `llmfetcher` submodule 后，
已有会话仍会显示。若需要把数据置于其他磁盘、容器卷或临时目录，可覆盖：

```bash
LLMFETCHER_STATE_DIR=/path/to/state llmfetcher-web
```

每个会话独立保存于 `workspace/<session>/`：

| 文件 | 内容 |
| --- | --- |
| `conversation.json` | 按保存顺序的用户与 Agent 可见对话 |
| `contexts/*.json` | 各 Agent 的持久化上下文与工具审计数据 |
| `events.ndjson` | 可重放的生命周期 Event Trace |
| `graph-view.json` | 当前或最近一次运行的安全执行图快照 |
| `task-plan.json` | 任务分解与状态 |
| `run-state.json` | 活跃运行或最近一次终态 |

刷新、切换会话或切换 Agent 时，前端从这些持久化文件恢复视图。SSE 会从事件日志续接；
服务丢失的运行会显示为 `interrupted`，不会被误报为仍在执行。

Workbench 中，绿色表示运行中，橘色表示 pending，蓝色表示已完成且等待确认，红色表示
失败/中断，灰色表示空闲、取消或已确认。右侧检查器提供任务计划、Agent、Trace 和用量；
总览隐藏工具细节，只显示行为块与可见对话，选中具体 Agent 后再显示其工具和推理细节。

## Swarm：从任务到可审计结论

启用 Agent Swarm 后，coordinator 可以动态分派子 Agent。每个 worker 收到明确任务包，
通过 TaskBus 回传结构化结论、证据、产物和待解决问题；raw transcript 仅保留作审计，
不会直接注入 coordinator 的上下文。

这使轨迹能按以下路径复盘：

```text
谁收到何种任务 → 何时调用什么工具 → 产生什么结构化报告 →
报告被谁消费 → 最终结论如何形成
```

停止是协作式的：当前模型与工具步骤完成、结果持久化后才结束。强制停止会终止已登记的
工具进程；两种方式都会保留已经完成的上下文边界。

## CLI 与测试

```bash
# 会话管理
llmfetcher session list
llmfetcher session create "研究"

# 在 LLMFetcher 子模块中运行完整测试
cd llmfetcher
python -m unittest discover -s tests -p 'test_*.py' -v
```

### 常见问题

- **`ModuleNotFoundError: llmfetcher`**：旧 editable 安装可能仍指向 Angelus 顶层。执行：
  ```bash
  python -m pip install setuptools
  python -m pip install --no-build-isolation -e ./llmfetcher
  ```
- **`llmfetcher/` 为空**：执行 `git submodule update --init --recursive`。
- **SSH 认证失败**：为 GitHub 配置 SSH key；或修改 `.gitmodules` 后执行
  `git submodule sync --recursive`。
- **看不到旧会话**：通常是启动进程使用了不同的 `LLMFETCHER_STATE_DIR`；检查它是否指向期望目录。

## 使用 TLB RAG

TLB RAG 是实验性的层级文件树检索工具。它将 `INDEX.md` 视为路由表，内部 Agent 按层
读取必要的索引和叶文件，并生成候选 intent-to-path 缓存项。它适合已有清晰目录结构的
知识库，不是通用向量数据库替代品。

```python
from llmfetcher import Agent, LLMBackendConfig, LLMFetcher
from llmfetcher.rag_module_tlb import create_tlb_rag_tool

fetcher = LLMFetcher([
    LLMBackendConfig(
        name="primary",
        provider="openai",
        model="your-model",
        api_key="...",
        api_url="https://api.openai.com/v1",
    )
])
agent = Agent(llm_fetcher=fetcher, system_prompt="Answer with evidence.")
agent.add_tool(create_tlb_rag_tool("./knowledge", fetcher))
print(agent.run("Locate the deployment guide.").content)
```

## 更新 LLMFetcher

Angelus 固定一个确定的 LLMFetcher commit；普通 `git pull` 不会自动推进 submodule。
审阅更新后显式执行：

```bash
git -C llmfetcher fetch origin
git -C llmfetcher switch main
git -C llmfetcher pull --ff-only
git add llmfetcher
git commit -m "chore: update llmfetcher submodule"
git push
```

如需回到 Angelus 锁定版本：

```bash
git submodule update --init --recursive
```

对子模块做修改时，应先在 LLMFetcher 仓库中提交并推送，再在 Angelus 中提交更新后的
gitlink。

## 许可证与素材

Angelus 继承 LLMFetcher 的 AGPL-3.0-or-later 开源授权与另行签署的商业授权路径，
详见 [LICENSE](LICENSE)、[LICENSING.md](LICENSING.md) 和
[commercial-licensing.md](commercial-licensing.md)。`llmfetcher` 是独立版本库，
保留自身版权和许可证声明；Angelus 不改变或再授权其条款。

导入图像、字体、图标或截图前，应逐项确认来源、版权人与许可。删除、归档或锁定源仓库
不会自动转移版权或授予新的复用权限。
