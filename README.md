# Angelus

Angelus 是 [LLMFetcher](./llmfetcher) 的部署与工作台 superproject。它把
LLMFetcher 固定为一个 Git submodule，并为本地运行数据、团队协作和版本升级
提供一个稳定的上层入口。

所有可执行实现都在 `llmfetcher/`：Python 包、Web Workbench、Agent、Swarm、
会话持久化、TLB RAG、测试和其自身文档均由该子模块维护。

## 目录与职责

```text
angelus/
├── llmfetcher/                 # 固定版本的 LLMFetcher submodule
├── workspace/                  # 本机运行数据；不提交
├── LICENSE                     # AGPL-3.0-or-later
├── LICENSING.md                # 商业授权路径说明
├── commercial-licensing.md     # 商业授权范围提示
└── .gitmodules                 # 子模块 URL 与跟踪分支
```

`workspace/` 由 Web Workbench 创建。它保存本地会话、上下文、执行图快照、
事件 Trace、任务计划和连接器配置；其中的 API key 仅保存在本机，不能提交。

## 1. 获取项目

要求：Python 3.12+、Git，以及可访问 GitHub 的 SSH 凭据（本项目的 submodule
使用 SSH URL）。

新克隆时必须初始化子模块：

```bash
git clone --recurse-submodules git@github.com:LunaticLegacy/angelus.git
cd angelus
```

如果已经克隆但 `llmfetcher/` 为空：

```bash
git submodule update --init --recursive
```

确认当前 Angelus 固定的 LLMFetcher 版本：

```bash
git submodule status
git -C llmfetcher log -1 --oneline
```

## 2. 安装

建议在 Angelus 顶层创建虚拟环境，但从子模块安装包：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install setuptools
python -m pip install --no-build-isolation -e ./llmfetcher
```

可编辑安装使 `llmfetcher` CLI 与 `llmfetcher-web` 命令可用。需要本地
OpenVINO 或 ONNX Runtime 后端时，按 LLMFetcher 的依赖说明额外安装对应运行时。
`--no-build-isolation` 允许使用虚拟环境中刚安装的 `setuptools`；这对 Python
3.14 的最小 venv 或无网络环境尤其有用。

## 3. 启动 Web Workbench

Angelus 会自动把运行数据写入顶层 `workspace/`，因此旧会话在 submodule 更新后
仍会显示。正常启动不需要环境变量：

```bash
llmfetcher web --host 127.0.0.1 --port 8765
```

需要把状态放到其他磁盘、容器卷或临时目录时，才设置覆盖变量：

```bash
LLMFETCHER_STATE_DIR=/path/to/state llmfetcher-web
```

浏览器打开 <http://127.0.0.1:8765>。首次使用时：

1. 在“连接”中创建 Provider 配置，填写 provider、model、API URL（如需要）和 API key。
2. 选择或新建会话。
3. 设定最大输出 tokens、温度、Swarm 并发度与“上下文压缩阈值”。默认阈值是 262144 个字符；它是历史压缩阈值，不是模型服务商声明的上下文窗口。
4. 发送任务；需要时开启 Shell 或 Agent Swarm。Shell 工具会在当前会话的工作目录中执行，因此只应向受信任的模型开放。

连接器保存在 `workspace/connectors.json`；服务会尽可能以文件权限 0600 写入。不要把该文件复制进 issue、日志或 Git 提交。

## 4. 会话、执行和恢复

每个浏览器会话对应 `workspace/<session>/` 下的独立目录。常见文件包括：

| 文件 | 作用 |
| --- | --- |
| `conversation.json` | 按保存顺序的用户与 Agent 可见对话 |
| `contexts/*.json` | 各 Agent 的持久化上下文与工具审计数据 |
| `events.ndjson` | 可重放的生命周期 Event Trace |
| `graph-view.json` | 当前或最后一次执行图的安全快照 |
| `task-plan.json` | Agent 任务计划 |
| `run-state.json` | 当前运行或最近一次终态 |

刷新浏览器、切换会话或切换 Agent 时，前端会从这些文件重新加载历史与运行状态。运行中的 SSE 连接会从持久化事件日志续接；服务重启导致的活跃运行会显示为 `interrupted`，而不是伪装成仍在运行。

停止是协作式的：当前模型/工具步骤完成并保存后才停止。强制停止会终止已登记的工具进程；两种停止路径都会持久化已完成的上下文边界。

命令行可管理会话和启动服务：

```bash
llmfetcher session list
llmfetcher session create "研究"
llmfetcher web --host 127.0.0.1 --port 8765
```

## 5. 使用 Swarm

启用 Agent Swarm 后，coordinator 可以动态分派子 Agent。worker 以明确的任务包执行，
并通过 TaskBus 交回结构化报告；raw transcript 保留为审计数据，不会直接塞回
coordinator 的上下文。

Workbench 中的状态颜色含义：

| 颜色 | 状态 |
| --- | --- |
| 绿色 | 正在运行 |
| 橘色 | pending / 等待调度 |
| 蓝色 | 已完成，等待用户确认 |
| 红色 | 失败或中断 |
| 灰色 | 空闲、已取消或已确认 |

右侧检查器提供任务计划、Agent、Trace 和用量四个视图。总览聊天只显示 Agent 行为块与最终可见对话；选择某个 Agent 后才显示该 Agent 的推理和工具调用细节。

## 6. Python API 与 TLB RAG

从子模块目录或已安装环境中导入包：

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

TLB RAG 是实验性层级文件树检索工具：它让内部 Agent 沿 `INDEX.md` 路由文件
按层读取最少的叶节点，并将候选 intent-to-path 映射作为缓存项。它不是通用向量
数据库替代品；知识树、索引质量和模型的工具调用可靠性共同决定效果。

## 7. 测试与排错

在 submodule 内运行完整测试：

```bash
cd llmfetcher
python -m unittest discover -s tests -p 'test_*.py' -v
```

常见问题：

- `ModuleNotFoundError: llmfetcher`：确认已运行
  `python -m pip install --no-build-isolation -e ./llmfetcher`，或在 `llmfetcher/` 内执行命令。
- 由旧 Angelus 顶层迁移后出现同一错误：旧 editable 安装仍指向顶层目录。运行
  `python -m pip install setuptools`，再运行
  `python -m pip install --no-build-isolation -e ./llmfetcher`。
- submodule 目录为空：运行 `git submodule update --init --recursive`。
- Git 提示 SSH 认证失败：为 GitHub 账户配置 SSH key，或在 `.gitmodules` 中改成你有权限访问的 URL 后执行 `git submodule sync --recursive`。
- 浏览器刷新后没有本地数据：确认每次启动都设置了相同的 `LLMFETCHER_STATE_DIR`。
- 端口 8765 被占用：使用 `llmfetcher web --port <port>`。

## 8. 更新模型实现

Angelus 记录一个确定的 LLMFetcher commit，不会在普通 `git pull` 时自动移动到
submodule 的最新分支。审阅更新后显式推进它：

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

不要直接在 submodule 中改动后忘记提交；应先在 `llmfetcher` 仓库中提交并推送，
再在 Angelus 中提交更新后的 gitlink。

## 9. 许可证与素材

Angelus 顶层继承 LLMFetcher 的 AGPL-3.0-or-later 开源授权和另行签署的商业授权
路径，详见 [LICENSE](LICENSE)、[LICENSING.md](LICENSING.md) 与
[commercial-licensing.md](commercial-licensing.md)。`llmfetcher` submodule 是独立
版本库，保留自己的版权与许可证声明；Angelus 不改变或再授权其条款。

从其他项目移入图像、字体、图标或截图前，必须逐项确认素材来源和许可。删除源仓库、
归档源仓库或锁定其 Git commit 都不会自动转移版权或授予新的复用权限。
