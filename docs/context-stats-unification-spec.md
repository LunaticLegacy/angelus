# 上下文长度统计统一口径 Spec

仓库：`/home/luna/Documents/codes/python/angelus_lunae/angelus-context-stats`（worktree，分支 `refactor/unify-context-stats`）
约束：**不改 llmfetcher 子模块源码**（F3/F4 内部实现保持原样，仅在 angelus 侧统一估算入口）。

## 背景：现存的多套统计

- **F1** `angelus/history.py::_agent_context_stats()` — 读持久化 `contexts/<agent>.json` 的字符统计（messages/characters/abstract_characters/compacted/threshold/round/ratio）。
- **F2** `angelus/history.py::_agent_context_preview()` 内 `RemoteRequestStats` — 对事件日志中最近一次远程请求快照的字符统计（messages/characters/tool_schemas/tool_schema_characters/estimated_tokens）。
- **F3** `llmfetcher/context_handlers/linear.py::_estimate_context_size()` — 运行时估算实际发送请求体字符长度，驱动压缩（不改）。
- **F4** `angelus/history.py::_session_usage_summary()` + `llmfetcher/usage_ledger.py` — 真实 token 用量账本（不改）。

## 统一口径决策

1. **唯一估算基准**：JSON 序列化后的**字符长度**（`len(json.dumps(x, ensure_ascii=False, default=str))`），与 F3 内部基准一致。
2. **唯一 token 估算系数**：`estimated_tokens = characters // 4`（等价于现有 F2 的 `(chars+3)//4`，即 ceil 除法；两者在整数语义上一致，采用 `(characters + 3) // 4` 保留向上取整）。
3. **唯一统计入口**：新增模块 `angelus/context_stats.py`，导出纯函数，供 F1/F2 共用：
   - `estimate_context_length(messages: list[dict], tool_schemas: list[dict] | None = None) -> ContextLengthStats`
   - `ContextLengthStats`（frozen dataclass）：`messages:int, characters:int, tool_schemas:int, tool_schema_characters:int, estimated_tokens:int`
4. **F1 改造**：`_agent_context_stats` 内部把消息字符统计委托给 `estimate_context_length`；返回字段**保持向后兼容**（messages/characters/abstract_characters/compacted/threshold/round/ratio），额外新增 `estimated_tokens`（基于 characters 统一导出）与 `tool_schema_characters`（默认为 0，因为 checkpoint 不含独立 tools 快照）。
5. **F2 改造**：`_agent_context_preview` 用 `estimate_context_length(messages, tool_schemas)` 构造 `RemoteRequestStats`；`RemoteRequestStats` 字段保持不变。
6. **F3/F4**：不改源码。文档注明 F3 已用同一字符基准；F4 为真实 token，不参与估算，前端需明确标注"真实用量"。

## 前端字段映射（frontend/static/app.js）

- F2 `renderContextPrompt`（第 254 行）继续用 `stats.messages/stats.characters/stats.tool_schemas/stats.tool_schema_characters/stats.estimated_tokens` —— 不变。
- F1 展示处（第 281-285 行 `context` 对象）继续用 `characters/abstract_characters/threshold/compacted/ratio` —— 不变；新增 `estimated_tokens` 可选展示（不强制，前端若已显示可加）。

## 测试要求

- 新增 `tests/test_context_stats.py`：
  - `estimate_context_length` 对空列表、普通消息、带 tools 的输入返回正确统计。
  - `_agent_context_stats` 返回键含新字段 `estimated_tokens` 且值等于 `(characters+3)//4`。
  - `RemoteRequestStats`/preview 仍返回统一字段。
- 不改 llmfetcher 子模块测试；`python -m pytest tests` 全绿（基线 325 passed）。
