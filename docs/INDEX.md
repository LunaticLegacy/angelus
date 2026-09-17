# docs/ — Documentation INDEX

架构、设计决策、安全、插件契约与研究材料。代码结构的权威语义参考是 `semantic-map.md`，而非根目录中不存在的 `CODEMAP.md`。

## Route Map — Leaf Files

| File | Purpose |
|---|---|
| `semantic-map.md` | 架构、模块 API、类层级与函数职责的代码语义参考。 |
| `current-code-architecture-mermaid.md` | 基于当前工作树的 Mermaid 架构、依赖、类/方法/字段、函数和全局变量语义图；明确现行与未挂载路径。 |
| `session-console-backend-design.md` | 右侧任务控制台的后端优先设计、Session 所有权边界与 API 契约。 |
| `context-stats-unification-spec.md` | 上下文长度统计统一口径、字段契约与迁移验收规格。 |
| `context-stats-change-notes.md` | 上下文统计统一工作的实现变更与验证记录。 |
| `graph_context_design.md` | 线性上下文、压缩归档、图检索与持久化设计。 |
| `decisions.md` | 架构与插件系统的设计决策记录。 |
| `security.md` | 连接器、Shell、运行控制、插件与数据边界的安全设计。 |
| `plugin-api.md` | 插件 manifest、运行时注册、权限与 REST 契约。 |
| `plugin-guide.md` | 插件开发、安装、启用与示例使用指南。 |
| `plugin-panel-manifest.md` | 当前 v1 声明式插件功能面板、受控输入和 action handler 契约。 |
| `plugin-swarm-execution.md` | 插件系统分阶段执行规格与验收标准。 |
| `v0.5.0-adr.md` | v0.5.0 架构决策记录（Q1 外部产品接入、Q2 前端性能修复范围）。 |
| `product-adapter.md` | 插件 v2 扩展点 `register_external_product(adapter)` 契约（Spike 已验证）。 |
| `v0.5.0-spec.md` | v0.5.0 分阶段规格（Phase 0 观察 / Phase 1 控制 / Phase 2 上下文历史 + 性能修复）。 |
| `mnavrag-arxiv-draft.md` | MNavRAG：层级知识检索方法的学术论文草稿。 |
|  `assets/angelus-hero.png` · `assets/qq-group.png` | README 使用的多 Agent 执行图横幅；`qq-group.png` 为 README 底部社区 QQ 群二维码；标题图标复用 `src-tauri/icons/icon.png`。 |

## Intent Routing

- **代码架构与职责** → `semantic-map.md`
- **当前可运行控制面架构（Mermaid）** → `current-code-architecture-mermaid.md`
- **任务控制台后端迁移** → `session-console-backend-design.md`
- **图记忆与归档上下文** → `graph_context_design.md`
- **设计取舍** → `decisions.md`
- **安全边界** → `security.md`
- **开发或审核插件** → `plugin-guide.md`、`plugin-api.md`、`plugin-panel-manifest.md`、`plugin-swarm-execution.md`
- **RAG 研究材料** → `mnavrag-arxiv-draft.md`
- **原生识图（native vision）实现与官方来源** → `.modular/vision-design.md` 与下方「官方来源注记」

## 官方来源注记 — Native vision input（2026-09-17）

本仓库的原生识图输入按 `../.modular/vision-design.md` 的 5 步蓝图实现；provider wire
格式严格遵循官方文档，且**不依赖任何付费实网请求**即可验证传输契约（测试以
`MagicMock` SDK / 假传输核对请求 payload，见 `../tests/test_native_vision_payload.py`）。

| Provider | 官方来源 | 本仓库 wire 形态 |
|---|---|---|
| OpenAI Chat Completions | https://developers.openai.com/api/docs/guides/images-vision | `{"type":"image_url","image_url":{"url":"data:<mime>;base64,…","detail":"auto\|low\|high"}}`，纯文本块在前 |
| Anthropic Messages | https://platform.claude.com/docs/en/build-with-claude/vision | `{"type":"image","source":{"type":"base64","media_type":"<mime>","data":…}}` |

实现落点：`llmfetcher/multimodal.py`（引用校验 / marker / wire block）、
`llmfetcher/fetcher_handlers/{openai,anthropic}.py`（wire 转换与不支持后端拒绝）、
`angelus/modules/attachment_module` 与 `angelus/api/attachments.py`（图片字节唯一所有者）、
`frontend/static/components/image-composer.js`（前端 composer / renderer）。

契约要点：仅 `openai`/`anthropic` 接受原生图片，其余 provider 抛
`ValueError("... does not support native image inputs")`；图片字节只存在于 provider
请求边界，journal/checkpoint/preview/snapshot/summary 仅保留持久引用与
`[image: <attachment_id> (<mime>)]` marker。

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| — | — | `None` | `None` | 本索引范围不直接拥有可执行函数；沿 Route Map 进入下级索引。 |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| — | — | `None` | `object` | 本索引范围不直接声明类；沿 Route Map 进入下级索引。 |

<!-- END GENERATED SYMBOL MAP -->
