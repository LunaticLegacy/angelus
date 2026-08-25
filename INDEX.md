# Angelus — Root INDEX

Angelus 是建立在 `llmfetcher` 子模块之上的本地优先 Agent 控制平面：它提供浏览器与桌面工作台、持久化会话、受控运行、插件扩展和可审计的协作执行。

## Route Map

| Entry | Type | Purpose |
|---|---|---|
| [`angelus/`](angelus/INDEX.md) | Python package | 控制平面：FastAPI、运行时、存储、连接器、会话记忆和插件宿主 |
| [`llmfetcher/`](llmfetcher/INDEX.md) | Git submodule | 模型后端、Agent loop、上下文、图记忆、工具、Swarm 与 TLB RAG |
| [`frontend/`](frontend/INDEX.md) | Web UI | SPA 模板、样式与 JavaScript 模块 |
| [`src-tauri/`](src-tauri/INDEX.md) | Desktop shell | Tauri 桌面壳、sidecar 生命周期与打包配置 |
| [`plugins/`](plugins/INDEX.md) | Plugin examples | 插件契约的示例实现与前端资产 |
| [`scripts/`](scripts/INDEX.md) | Build scripts | Python sidecar 入口和 PyInstaller 构建脚本 |
| [`tests/`](tests/INDEX.md) | Test suite | 控制平面、记忆、插件、RAG 与工作台回归测试 |
| [`docs/`](docs/INDEX.md) | Documentation | 架构、设计决策、安全、插件与研究文档 |
| [`.github/`](.github/INDEX.md) | CI configuration | 持续集成与桌面发布工作流 |
| `pyproject.toml` | Build config | Python 包元数据、运行依赖和测试 extra |
| `requirements.txt` | Requirements | 便捷的 Python 运行依赖清单 |
| `requirements-desktop.txt` | Requirements | Tauri Python sidecar 的 PyInstaller 依赖 |
| `package.json` | Node config | Tauri CLI、开发、打包与 sidecar 构建脚本 |
| `package-lock.json` | Node lockfile | 锁定 Tauri CLI 的 Node 依赖解析结果 |
| `README.md` | Project guide | 项目概览、安装、运行、架构和文档入口 |
| `MANIFEST.in` | Packaging | Python 源码分发清单 |
| `.gitignore` / `.gitmodules` | Repository config | 忽略规则与 `llmfetcher` 子模块登记 |
| `LICENSE` / `LICENSING.md` / `commercial-licensing.md` | Licensing | AGPL 文本、授权政策与商业授权条款 |

`workspace/`、`.venv/`、`.pytest_cache/` 和 `angelus.egg-info/` 都是本地运行或构建产物，不是源代码检索入口。

## Quick Intent Routing

- **HTTP API、SSE、浏览器入口** → `angelus/api/` 与 `angelus/webapp.py`
- **会话、事件账本、状态目录** → `angelus/storage.py`、`angelus/history.py`
- **Agent / Swarm 构建** → `angelus/runtime.py`；算法实现见 `llmfetcher/`
- **插件宿主、权限和注册表** → `angelus/plugins/`、`angelus/plugin_*.py`
- **前端工作台** → `frontend/INDEX.md` → `frontend/static/INDEX.md`
- **桌面端生命周期与打包** → `src-tauri/INDEX.md`、`scripts/INDEX.md`
- **图记忆、归档检索、上下文压缩** → `llmfetcher/graph_memory/`、`llmfetcher/context_handlers/`
- **Swarm 实现** → `llmfetcher/swarm_module/`
- **内置工具** → `llmfetcher/tools/`
- **测试覆盖** → `tests/INDEX.md`
- **架构语义参考** → `docs/semantic-map.md`
