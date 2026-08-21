# 上下文长度统计统一口径 — 变更说明

实现 `docs/context-stats-unification-spec.md`，为 F1（checkpoint 字符统计）与 F2
（远程请求预览统计）建立唯一估算入口。F3/F4（`llmfetcher` 子模块）源码未改动。

## 新增 `angelus/context_stats.py`

- `ContextLengthStats`：frozen dataclass，字段
  `messages / characters / tool_schemas / tool_schema_characters / estimated_tokens`。
- `estimate_context_length(messages, tool_schemas=None)`：纯函数。
  - 字符基准：`len(json.dumps(x, ensure_ascii=False, default=str))`（与 F3
    `llmfetcher/context_handlers/linear.py::_estimate_context_size` 同一口径）。
  - token 估算：`estimated_tokens = (characters + 3) // 4`，仅以消息字符为基数；
    tool schema 字符单独统计，不混入 token 估算。
  - 防御：非 dict 条目被跳过，畸形 checkpoint 不会导致估算崩溃。

## `angelus/history.py` 改造

1. `_agent_context_stats`（F1）
   - 消息字符统计委托给 `estimate_context_length(messages)`。
   - 返回键保持向后兼容：`messages / characters / abstract_characters /
     compacted / threshold / round / ratio`。
   - 新增键 `estimated_tokens`（= `(characters+3)//4`）与 `tool_schema_characters`
     （恒为 0，checkpoint 不含独立 tools 快照）。
2. `_agent_context_preview`（F2）
   - `RemoteRequestStats` 改为用 `estimate_context_length(messages, tool_schemas)`
     生成；`RemoteRequestStats` 字段（messages/characters/tool_schemas/
     tool_schema_characters/estimated_tokens）保持不变。
   - 语义差异：`estimated_tokens` 现基于消息字符（旧实现把 tool schema 字符也计入
     token 估算），与统一口径一致，前端无需改字段名。

## 调用方确认

- `angelus/api/sessions.py`：仅把 `_agent_context_stats` 结果作为 `context` 字段
  透传给前端（只读），不依赖字段值以外的形状变化。
- `angelus/api/compact.py`：仅读取 `before.get('messages')` 与
  `after.get('abstract_characters')`，新增键不影响。

## 测试

- 新增 `tests/test_context_stats.py`（7 个用例）：
  - 空列表 / 普通消息 / 带 tools 的 `estimate_context_length` 统计。
  - `_agent_context_stats` 含 `estimated_tokens` 且等于 `(characters+3)//4`。
  - preview `RemoteRequestStats` 字段与统一估算器一致。
- `python -m pytest tests`：332 passed（基线 325 + 新增 7）。

## 前端 `frontend/static/app.js`

- `renderContextPrompt`（F2，约 L254）不改：继续消费
  `stats.messages / stats.characters / stats.tool_schemas /
  stats.tool_schema_characters / stats.estimated_tokens`。
- `agentContextStats`（F1，约 L278）保持既有字段与文案不变：
  `characters / abstract_characters / threshold / compacted / ratio`；
  按 spec 的可选增强新增 `estimated_tokens`：
  - 新增 `const estimatedTokens = Number(ctx.estimated_tokens || 0);`
  - `estimated_tokens > 0` 时在可见文本追加 ` · 估算 N tokens`，并在 tooltip
    中追加 ` · 估算 N tokens`；为 0/缺失时不渲染任何新片段，旧 UI 完全不变。
- 未改动 `tests/test_workbench_assets.py` 断言的任何字符串。
- 验证：`python -m pytest tests` 337 passed。
