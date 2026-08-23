# docs/ — Documentation INDEX

架构、设计决策、安全、插件契约与研究材料。代码结构的权威语义参考是 `semantic-map.md`，而非根目录中不存在的 `CODEMAP.md`。

## Route Map — Leaf Files

| File | Purpose |
|---|---|
| `semantic-map.md` | 架构、模块 API、类层级与函数职责的代码语义参考。 |
| `graph_context_design.md` | 线性上下文、压缩归档、图检索与持久化设计。 |
| `decisions.md` | 架构与插件系统的设计决策记录。 |
| `security.md` | 连接器、Shell、运行控制、插件与数据边界的安全设计。 |
| `plugin-api.md` | 插件 manifest、运行时注册、权限与 REST 契约。 |
| `plugin-guide.md` | 插件开发、安装、启用与示例使用指南。 |
| `plugin-swarm-execution.md` | 插件系统分阶段执行规格与验收标准。 |
| `v0.5.0-adr.md` | v0.5.0 架构决策记录（Q1 外部产品接入、Q2 前端性能修复范围）。 |
| `product-adapter.md` | 插件 v2 扩展点 `register_external_product(adapter)` 契约（Spike 已验证）。 |
| `v0.5.0-spec.md` | v0.5.0 分阶段规格（Phase 0 观察 / Phase 1 控制 / Phase 2 上下文历史 + 性能修复）。 |
| `mnavrag-arxiv-draft.md` | MNavRAG：层级知识检索方法的学术论文草稿。 |
|  `assets/angelus-hero.png` · `assets/qq-group.png` | README 使用的多 Agent 执行图横幅；`qq-group.png` 为 README 底部社区 QQ 群二维码；标题图标复用 `src-tauri/icons/icon.png`。 |

## Intent Routing

- **代码架构与职责** → `semantic-map.md`
- **图记忆与归档上下文** → `graph_context_design.md`
- **设计取舍** → `decisions.md`
- **安全边界** → `security.md`
- **开发或审核插件** → `plugin-guide.md`、`plugin-api.md`、`plugin-swarm-execution.md`
- **RAG 研究材料** → `mnavrag-arxiv-draft.md`
