# 基于 Graph RAG 的图式上下文系统设计方案

> 目标：为 angelus（llmfetcher）重写一套更好的上下文系统。
> 方法：参考现有工程实现（Microsoft GraphRAG、LightRAG、Zep/Graphiti、HippoRAG 等）+ arxiv 图式上下文论文，设计一个可落地的 `GraphContextHandler`。
> 日期：2026-08-04

---

## 1. angelus 现有上下文系统分析

### 1.1 代码结构

```
llmfetcher/
├── context_handlers/
│   ├── base.py        # ContextHandler ABC（add_user_message / add_assistant_message /
│   │                  #   build_messages / save / load / clear_context）
│   ├── linear.py      # ContextHandlerLinear：扁平消息列表 + LLM 摘要压缩（XML 协议）
│   └── retrieved.py   # RetrievedContextHandler：linear + TLB-RAG 长期记忆
├── rag_module_tlb/    # TLB-RAG：目录树 + INDEX.md 页表 + 运行时校验的检索
└── rag_module/knowledge/  # 旧 RAG：HybridRetriever（关键词 + Chroma 向量 + 任务策略）
```

### 1.2 核心机制

| 组件 | 机制 | 关键参数 |
|---|---|---|
| `ContextHandlerLinear` | 消息按 `timeline` 单调递增；超阈值后调用 LLM 把全部消息压缩成 `<context_abstract>` + `<source_timelines>` XML | `max_context_threshold=262144` 字符，`compaction_input_char_limit=196608`，输出 8192 token，温度 0.4 |
| `RetrievedContextHandler` | 组合 linear；会话归档为 markdown（frontmatter 存 topic/task_type/entities/status/tags）；检索用 TLB-RAG 从项目/用户知识库取历史会话，作为 **user 角色**注入 | `max_retrieved_sessions=3`，触发 `first_message`/`auto`/`manual` |
| TLB-RAG (`TLBRAGHandler`) | 每查询新建 worker Agent 遍历目录树（INDEX.md 页表），用 read trace 校验模型声称，TLB 缓存（query_key→entry，mtime/size/hash 校验） | 目录树知识库，非图结构 |
| 旧 RAG (`HybridRetriever`) | 关键词 + Chroma 向量 + 任务策略融合排序 | 文档级检索，无跨文档关系 |

### 1.3 现有系统的结构性弱点

1. **压缩是"线性摘要"**：`LLMContextCompacted` 只是一段文本，丢弃了实体/关系/时间线结构。压缩后多跳关联（"之前讨论过 X 和 Y 的关系"）几乎不可恢复。
2. **检索是"文件粒度"**：TLB-RAG 检索单位是会话文件，而非实体/事实。跨会话的关联（同一实体在多会话中出现）无法被结构化表达。
3. **无时间感知**：`LLMContextCompacted` 只存 `source_timeline` 整数列表，没有实体/关系的首次/最近出现时间，无法做 recency 加权。
4. **检索触发过少**：`first_message` 只在会话开头检索一次；`auto` 在压缩后重检。会话中途的多跳知识无法动态拉取。
5. **无图结构**：INDEX.md 树是"分层"不是"图"，无法表达跨目录的多关系（person↔project↔file↔decision）。
6. **压缩与检索割裂**：压缩时没有用图摘要辅助；检索时没有用压缩产出的图。

---

## 2. 工程实现调研（开源 Graph RAG）

### 2.1 Microsoft GraphRAG（2404.16130，微软官方开源 microsoft/graphrag）

**索引 pipeline（离线、两阶段）：**
1. **Chunk**：源文档切块（默认 1200 token，15% overlap）。
2. **Entity/Relation 抽取**：LLM 从每个 chunk 抽取实体、关系、声明（claim），输出到 parquet/graphml。
3. **图构建**：实体去重（相同 canonical name 合并），关系带权重/描述/来源文档。
4. **社区检测**：Hierarchical Leiden 算法，得到多层社区（level 0 最细 → 高层全局）。
5. **社区摘要（map-reduce）**：对每个社区，先用 LLM 汇总社区内实体/关系为结构化摘要，再递归合并上层，形成层级化社区摘要。

**查询策略：**
- **Global Search**（全局问题，如"What are the main themes?"）：对所有社区摘要做 map-reduce 汇总，回答 corpus 级问题。
- **Local Search**（实体级问题）：从查询抽取实体 → 沿图扩展邻居 → 收集实体描述/关系/社区摘要 → 组装上下文。
- 还提供 **DRIFT Search**（探索性检索）和 **Dynamic Community Selection**。

**工程要点**：纯 Python + NetworkX；存储 parquet + 向量库（lancedb/azure search）；社区摘要缓存；增量更新支持；本地小模型（用便宜的 LLM 做抽取）。

### 2.2 LightRAG（2410.05779，HKUDS/LightRAG）

- **图构建**：chunk 级抽取实体 + 关系，LLM 输出 JSON，增量 upsert。
- **双层检索**：low-level（实体/关系层面，精确）与 high-level（主题/关键词层面，全局）双通道 + 关键词/向量混合。
- 轻量：单机可跑，SQLite + 向量（nano-vectordb）。
- 缺点：社区摘要不如 GraphRAG 完整；但构建成本低、增量友好。

### 2.3 Zep / Graphiti（2501.13956，getzep/graphiti）

**核心思想：时间感知知识图谱（Temporal Knowledge Graph）作为 Agent 记忆层。**

- **Bi-temporal 模型**：每条边带 `valid_at`（事实生效时间）与 `invalid_at`（失效时间），支持"事实随时间变化"的查询（"上周的配置 vs 现在的配置"）。
- **增量更新**：新对话 → 抽取事实 → 与已有实体合并（LLM 裁决 same-as）→ 更新边时间戳；支持边失效（invalid_at）。
- **搜索**：语义向量召回实体 + 图扩展 + 时间过滤；提供 `search(scope)` API。
- **评测**：Deep Memory Retrieval (DMR) 94.8% vs MemGPT 93.4%；LongMemEval 更全面。
- 这是"对话记忆图"最接近我们要做的工程。

### 2.4 HippoRAG（2405.14831）与 HippoRAG 2（2502.14802，OSU-NLP-Group）

- **海马体索引理论**：把 LLM 当作"新皮层"做抽取，知识图谱当作"索引"，PPR（Personalized PageRank）当作"海马体"关联扩散。
- **索引**：文档 → OpenIE/LLM 抽取实体与三元组 → 实体-段落二部图（passage 节点连接其内实体）。
- **检索**：查询 → 实体链接 → 在图上跑 PPR（seed = 查询实体）→ 按 PPR 分数取 top-K passage。
- **优点**：单步检索完成多跳（multi-hop），比迭代检索（IRCoT）便宜 10-30 倍。
- **HippoRAG 2**：加 passage 级深度融合 + LLM 在线重排，在 factual/sense-making/associative 三类记忆任务全面超过标准 RAG。

### 2.5 其他值得参考的工程

- **nano-graphrag / GraphRAG-Go**：轻量复刻 GraphRAG pipeline（社区检测 + 摘要），适合嵌入式/低成本部署。
- **TERAG（2509.18667）**：只保留实体+关系+少量描述，构建 token 成本降到 GraphRAG 的 3%-11%，检索用 PPR，精度达到主流方法的 80%+。
- **EcphoryRAG（2510.08958）**：实体为中心的 KG-RAG，只存核心实体+元数据（token 省 94%），检索用 cue-entity 多跳关联搜索 + 动态推断隐式关系。

---

## 3. arxiv 论文核心设计模式提炼

### 3.1 论文清单（按与本任务相关度）

| arXiv ID | 论文 | 核心贡献 | 对我们设计的启示 |
|---|---|---|---|
| 2404.16130 | **GraphRAG**（微软） | 实体KG + Leiden社区 + map-reduce社区摘要 + global/local查询 | 社区摘要是"图压缩"的现成范式；global 查询适合会话级总览 |
| 2405.14831 | **HippoRAG** | 海马体索引：实体-段落二部图 + PPR | 图+向量混合检索、单步多跳；对会话记忆很合适 |
| 2502.14802 | **HippoRAG 2** | PPR + passage深度整合 + LLM在线重排 | 检索后重排提升相关性 |
| 2410.05779 | **LightRAG** | 双层（low/high-level）检索 + 增量图构建 | 增量 upsert 适合流式对话 |
| 2501.13956 | **Zep/Graphiti** | 时间感知KG（bi-temporal）+ 增量合并 + DMR评测 | **最接近"对话记忆图"**；时间戳/失效机制必学 |
| 2310.08560 | **MemGPT** | 虚拟上下文管理：内存分层（main/archival/core）+ OS 式分页 | 触发式换页思想已被 angelus 的压缩继承；可把"归档内存"换成图 |
| 2509.18667 | **TERAG** | 极低 token 图构建（3%-11%） | 若 LLM 预算紧张，用精简抽取 schema |
| 2510.08958 | **EcphoryRAG** | cue-entity 多跳 + 隐式关系推断 | 会话检索可先用"线索实体"启动扩散 |
| 2507.23581 | **GraphRAG-R1** | RL 训练多跳检索决策 | 远期：让 agent 学会何时检索图 |
| 2506.05690 | **GraphRAG-Bench** | 系统性评测"何时该用图" | 设计评测时参考其任务分层 |
| 2408.08921 / 2501.00309 | GraphRAG 综述（两篇） | 形式化 Graph-Based Indexing / Graph-Guided Retrieval / Graph-Enhanced Generation | 术语与框架对齐 |

### 3.2 提炼出的 6 个关键设计模式

**P1 — 实体-关系图作为长期记忆的索引层（HippoRAG / Zep）**
对话原文（chunk/passage）是"内容"，图是"索引"。内容可被压缩丢弃，图保留关系结构。检索时从图出发，回溯到内容。

**P2 — 社区检测 + 分层摘要 = 图感知压缩（GraphRAG）**
把"压缩 N 条消息"升级为"对图上实体簇（社区）生成摘要"。摘要按社区层级组织：细粒度社区摘要（局部事实）+ 粗粒度社区摘要（全局主题）。压缩后的抽象不再是扁平文本，而是可寻址的图摘要。

**P3 — 时间感知与事实失效（Zep/Graphiti）**
每条实体/边带 first_seen / last_seen / valid_at / invalid_at。检索按 recency 加权；被推翻的事实（"方案 A 被否决"）可标记失效，避免把过时信息注入上下文。

**P4 — PPR / 图扩散检索（HippoRAG）**
从查询实体出发跑 Personalized PageRank，把相关性沿边扩散到多跳邻居，单步完成多跳推理。比逐条向量检索更适合"跨会话关联"。

**P5 — 混合召回：关键词 + 向量 + 图 + 时间（LightRAG / HybridRetriever）**
单一召回不可靠。四路信号融合：BM25（精确术语）→ 向量（语义）→ 图 PPR（关联）→ 时间衰减（recency），最后 LLM 或规则重排。

**P6 — 虚拟上下文管理 + 分层内存（MemGPT）**
上下文窗口 = 主内存；图 + 归档 = 辅助存储。触发条件（窗口将满 / 新话题 / 检索命中）决定何时把主内存内容换入/换出。angelus 的压缩触发已实现一半（阈值），缺"话题切换触发"与"图辅助换页"。

---

## 4. 新上下文系统设计：GraphContextHandler

### 4.1 设计目标与约束

**硬约束（与现有代码兼容，直接可替换）：**
- 实现 `ContextHandler` ABC：`add_user_message` / `add_assistant_message` / `build_messages` / `save` / `load` / `clear_context`。
- `Agent.__init__(context_handler=...)` 与 `LLMFetcher.fetch(context_handler=...)` 不变。
- `LLMContext` / `LLMContextCompacted` 数据结构兼容（可加字段，向后兼容 load）。
- 离线可测：压缩/检索用注入的 `CompactionFetcher` 协议（现有测试模式沿用）。

**软目标：**
- 压缩不丢"关系"：压缩产出物从纯文本升级为"文本摘要 + 图片段"。
- 检索从"会话文件"升级为"实体/社区/时间感知"。
- 增量、低延迟：图更新不阻塞主对话（后台/批处理）。
- token 可控：图构建用精简 schema（参考 TERAG），避免每次抽取烧 token。

### 4.2 总体架构

```
┌──────────────────────────────────────────────────────────────┐
│                    Agent / LLMFetcher                         │
└──────────────────────────┬───────────────────────────────────┘
                           │ context_handler=...
┌──────────────────────────▼───────────────────────────────────┐
│              GraphContextHandler (新)                         │
│  ┌──────────────┐   ┌────────────────┐   ┌─────────────────┐ │
│  │ LinearLayer  │   │ GraphMemory    │   │ CompactionLayer │ │
│  │ (复用现有     │   │ (图存储+检索)   │   │ (图感知压缩)     │ │
│  │  linear逻辑) │   │                │   │                 │ │
│  └──────┬───────┘   └───┬────────────┘   └────────┬────────┘ │
│         │               │                         │          │
│  build_messages 组合:    │                         │          │
│  [图检索块(user) +      │                         │          │
│   abstract(system) +    │                         │          │
│   messages]             │                         │          │
└─────────────────────────┼─────────────────────────┼──────────┘
                          │                         │
        ┌─────────────────▼───────────┐   ┌─────────▼─────────┐
        │ GraphStore                  │   │ LLM (抽取/摘要/    │
        │ networkx 无向图 + 属性       │   │  检索意图/重排)     │
        │ 持久化 graph.json / sqlite  │   │  复用 LLMFetcher   │
        └─────────────────────────────┘   └───────────────────┘
```

**模块划分（建议新目录 `llmfetcher/graph_memory/`）：**

| 模块 | 文件 | 职责 |
|---|---|---|
| 数据模型 | `models.py` | `EntityNode` / `RelationEdge` / `CommunitySummary` / `GraphHit` |
| 图存储 | `graph_store.py` | NetworkX 封装：upsert 节点/边、社区检测（Leiden/Louvain）、子图导出、时间过滤、序列化 |
| 图构建 | `builder.py` | 从对话流（LLMContext 列表）增量抽取实体/关系 → upsert；合并 same-as；时间戳维护 |
| 抽取 prompt | `extraction_prompts.py` | 精简 schema（TERAG 风格）+ 完整 schema（GraphRAG 风格）双档 |
| 图感知压缩 | `compactor.py` | 社区摘要 map-reduce；产出 `LLMContextCompacted` + 图片段（`graph_snapshot`） |
| 检索 | `retriever.py` | 混合召回：意图/实体抽取 → 向量 + PPR + 社区 + 时间衰减 → 重排 → 组装上下文块 |
| 会话句柄 | `handler.py` | `GraphContextHandler(ContextHandler)`：组合 linear + graph，触发策略 |
| 持久化 | `storage.py` | 图 + 摘要 + 会话 的 save/load（JSON/SQLite） |

### 4.3 图数据模型（核心）

```
EntityNode:
  id: str                 # 规范化实体 id（NFKC + casefold + 类型前缀，复用 normalize_query_key 思路）
  name: str               # 显示名
  entity_type: str        # person | file | concept | tool | framework | project | decision | ...
  aliases: list[str]      # 别名（same-as 合并用）
  summary: str            # 实体级摘要（可选，触发时生成）
  first_seen: int         # timeline
  last_seen: int
  freq: int               # 出现次数
  embedding: list[float] | None   # 可选向量

RelationEdge:
  source_id: str
  target_id: str
  relation: str           # "fixes" / "depends_on" / "implements" / "rejects" / "mentioned_in" ...
  weight: float           # 出现次数 / 置信度
  first_seen: int
  last_seen: int
  valid: bool             # 是否仍有效（被否决则为 False）
  evidence: list[int]     # 来源 timeline 列表（回溯原文）

CommunitySummary:          # 图感知压缩的产物
  level: int              # 社区层级（0=细粒度）
  community_id: str
  summary: str            # 社区摘要文本
  member_entity_ids: list[str]
  source_timelines: list[int]   # 覆盖的时间线（兼容现有 LLMContextCompacted.source_timeline）
  graph_snapshot: dict    # 社区子图（节点/边摘要），供注入
```

### 4.4 构建流程（增量、低开销）

**触发点**：`add_assistant_message` 末尾（与压缩检查同处），或每 N 轮批量（默认每 3 轮一次，可配置）。

```
1. 取最近 Δ 轮 LLMContext（user + assistant content，tool 结果截断）
2. LLM 抽取（精简 schema，参考 TERAG）：
   {"entities": [{"name", "type", "alias"}],
    "relations": [{"src", "dst", "relation"}]}
   —— 预算紧张时用关键词/规则兜底（文件路径、函数名正则）
3. same-as 合并：与图内已有实体做规范化匹配（别名 + 相似度）
4. upsert 节点/边：更新 first_seen/last_seen/freq/weight/evidence
5. 事实否决检测（可选，参考 Zep）：
   若消息含 "X 不再成立 / 废弃 / 否决"，将相关边 valid=False, invalid_at=now
6. 后台异步：定期（或压缩时）重跑社区检测 + 刷新社区摘要
```

**成本控制**：
- 抽取 prompt 输出 ≤ 400 token/批；
- 每批只处理新增消息（增量）；
- 抽取失败 → 静默降级为正则提取（文件名 `[\w./-]+\.\w+`、`#\w+`、函数名等），不阻塞对话。

### 4.5 检索流程（混合召回 + 图扩散）

```
触发：first_message（沿用）/ auto（压缩后）/ manual / 新增"话题切换检测"
      （可选：query 与最近话题 embedding 相似度 < 阈值 → 触发检索）

1. 意图/实体抽取（LLM，轻量）：从当前 user 消息抽 seed entities + 关键词
2. 四路召回：
   a. 向量：seed 实体 embedding → 最近邻实体（复用 Chroma 或纯 numpy 余弦）
   b. 图扩散：seed 实体在图上跑 Personalized PageRank（networkx.pagerank，
      personalization={seed:1.0}），取 top-K 实体
   c. 关键词：BM25 命中实体 name/alias/summary
   d. 时间：按 last_seen 时间衰减系数 λ 加权（如 score *= exp(-λ·age)）
3. 融合：加权和（可配置 w_vec/w_ppr/w_kw/w_time，默认 0.3/0.4/0.2/0.1）
4. 关联扩展：取 top-K 实体的 1-hop 邻居 + 所属社区摘要（level 0 为主）
5. 重排（可选）：LLM 按相关性给候选排序，截断到 max_graph_hits（默认 5 实体 + 3 社区）
6. 组装上下文块（user 角色，保留现有 <retrieved_memory> 风格）：
   <graph_memory authority="historical" trust="mixed">
     [实体卡: name/type/summary/last_seen/freq]
     [关系卡: src -relation-> dst (最近出现时间)]
     [社区卡: community summary]
   </graph_memory>
```

**注入位置**：作为 `user` 角色消息放在最前（与现有 `RetrievedContextHandler.build_messages` 一致，避免低信任历史数据覆盖 system 指令）。

### 4.6 图感知压缩流程（升级现有 compact）

```
1. 触发：_estimate_context_size() > max_context_threshold（沿用现有阈值机制）
2. 输入：当前 messages + 图（而非仅文本 transcript）
3. 步骤：
   a. 对 messages 做增量图更新（见 4.4），确保图已包含本批内容
   b. 社区检测（Leiden，level 0）
   c. map：对每个社区，LLM 生成社区摘要（输入=社区内实体/关系/相关消息片段）
   d. reduce：可选，把 level 0 摘要合并为 level 1 全局摘要
   e. 产出 LLMContextCompacted：
        abstract_msg   = 全局摘要 + 关键社区摘要拼接（保持 <context_abstract> 兼容格式）
        source_timeline= 被压缩消息的 timeline（沿用）
        tags           = 本批高频实体名
      新增：社区摘要 + 图快照存到 GraphMemory（不入 abstract 文本，省 token）
4. 压缩后 messages.clear()，后续检索可从图快照恢复跨会话关联
```

**兼容性**：`save/load` 时，`abstract` 字段仍为原格式（文本 + timeline），图数据独立存 `graph.json`，load 时分别恢复。旧文件（无图）可正常加载。

### 4.7 触发策略汇总

| 事件 | 动作 |
|---|---|
| `add_user_message`（首个） | 检索一次（first_message 模式） |
| `add_assistant_message`（每 N 轮） | 增量图更新（异步/低开销） |
| 上下文超阈值 | 图感知压缩（4.6） |
| 压缩完成（auto 模式） | 触发一次检索（重新定位长期记忆） |
| （可选）话题切换 | 检索一次 |
| `clear_context` | 清 linear + 会话级图引用（长期图可保留） |

### 4.8 与现有代码的集成点

1. **新文件**：`llmfetcher/context_handlers/graph.py`（`GraphContextHandler`），内部持有 `ContextHandlerLinear` 实例（复用其消息管理、阈值、序列化）+ `GraphMemory`。
2. **图存储**：`llmfetcher/graph_memory/graph_store.py`，用 `networkx`（若不允许新增依赖，可自写邻接表 dict；后续可换 sqlite + 图算法）。
3. **抽取/摘要**：复用 `CompactionFetcher` 协议（`fetch(msg, system_prompt, temperature, max_tokens, context_handler=None)`），与现有 `_RecordingCompactor` 测试模式兼容。
4. **注入格式**：复用 `_render_retrieved_memory` 的 `<retrieved_memory>` 风格，新增 `<graph_memory>` 块；角色保持 `user`。
5. **持久化**：`save(path)` 额外写 `path + ".graph.json"`；`load` 恢复。
6. **旧模块过渡**：TLB-RAG 可保留作为"文件级兜底检索"，图检索作为"实体级主检索"，二者按命中率路由（A/B）。

### 4.9 评测方案

**离线单元测试（沿用现有测试风格，注入假 fetcher）：**
- 图构建：给定消息序列 → 断言实体/边 upsert、same-as 合并、时间戳更新正确。
- 检索：构造小图 → 断言 PPR 排序、时间衰减、社区注入正确。
- 压缩：假 compactor 返回固定 XML → 断言 abstract/timeline/graph_snapshot 落盘与恢复。
- 触发：阈值/首消息/压缩后重检触发次数正确。
- 持久化：save/load 往返一致；旧格式文件兼容。

**指标（离线可跑）：**
| 指标 | 说明 |
|---|---|
| 检索命中率 | 注入的图块与 ground-truth 实体重叠率（参考 DMR 风格） |
| 压缩信息保持率 | 压缩前后关键实体/关系是否仍可被检索到（召回率） |
| 多跳 QA 准确率 | 在 HotpotQA / 2WikiMultiHop 子集或自建会话集上测试 |
| token 成本 | 每 100 轮对话的抽取/摘要 token 消耗（目标 ≤ 现有压缩的 1.5 倍） |
| 延迟 | 图更新/检索 p50/p95（不阻塞主对话 ≥ 50ms） |

**基准参照**：DMR（Zep 94.8% vs MemGPT 93.4%）、LongMemEval、GraphRAG-Bench 任务分层（fact retrieval / complex reasoning / contextual summarization）。

---

## 5. 落地路线图

| 阶段 | 内容 | 产出 | 预估 |
|---|---|---|---|
| **P0** | `graph_memory/models.py` + `graph_store.py`（NetworkX 封装、upsert、序列化、时间过滤、Leiden/Louvain 社区） | 图存储内核 + 单测 | 1-2 天 |
| **P1** | `builder.py` + 抽取 prompt（精简 schema）；接入 `add_assistant_message` 增量更新；正则兜底 | 对话 → 图 打通 + 单测 | 1-2 天 |
| **P2** | `retriever.py`：实体抽取 → PPR + 向量 + 关键词 + 时间衰减融合 → `<graph_memory>` 注入；`GraphContextHandler` 组装 | 检索可用 + 单测 | 2-3 天 |
| **P3** | `compactor.py`：社区检测 → map-reduce 摘要 → 图快照；改造 `compact()` | 图感知压缩 + 兼容测试 | 2-3 天 |
| **P4** | 持久化（graph.json / sqlite）、触发策略（话题切换）、重排；与 TLB-RAG 共存路由 | 完整 handler + 回归 | 2 天 |
| **P5** | 评测（检索命中/压缩保持/多跳 QA/token/延迟）+ 调参（λ、权重、阈值） | 评测报告 + 参数配置 | 2-3 天 |

**依赖**：`networkx`（社区检测可先用内置 `greedy_modularity_communities`，后续换 `leidenalg`）；可选 `numpy`（余弦）。其余全部复用 angelus 现有 `LLMFetcher`/`CompactionFetcher`。

---

## 6. 参考资源

### 论文（arXiv）
- GraphRAG: From Local to Global（2404.16130）
- HippoRAG（2405.14831）／ HippoRAG 2（2502.14802）
- LightRAG（2410.05779）
- Zep: A Temporal Knowledge Graph Architecture for Agent Memory（2501.13956）
- MemGPT（2310.08560）
- TERAG（2509.18667）
- EcphoryRAG（2510.08958）
- GraphRAG-R1（2507.23581）
- GraphRAG-Bench（2506.05690）
- Graph Retrieval-Augmented Generation: A Survey（2408.08921 / 2501.00309）

### 工程
- microsoft/graphrag（官方：索引 pipeline + Leiden + 社区摘要 + global/local/drift search）
- HKUDS/LightRAG（双层检索、增量 upsert、SQLite）
- getzep/graphiti（时间感知 KG 记忆层，DMR/LongMemEval 评测）
- OSU-NLP-Group/HippoRAG（PPR 检索）
- guanidin/graphrag-go / nano-graphrag（轻量复刻）

---

## 7. 一句话总结

把 angelus 现有的"线性压缩 + 文件级 TLB 检索"升级为 **"图式长期记忆"**：
**构建时**用 LLM 增量抽取实体/关系进图（TERAG 精简 schema 控成本），
**压缩时**用社区检测 + map-reduce 生成可寻址的图摘要（GraphRAG 范式），
**检索时**用 向量 + PPR 扩散 + 关键词 + 时间衰减 四路融合（HippoRAG + Zep 范式），
最终以 `GraphContextHandler` 实现 `ContextHandler` ABC，**无侵入替换现有 handler**，旧 TLB-RAG 保留为文件级兜底。
