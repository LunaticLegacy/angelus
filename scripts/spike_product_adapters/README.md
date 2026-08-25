# Spike: ProductAdapter — 解析真实 claude/codex transcript

> 状态：**Spike（验证用，非生产代码）**。目标：验证「外部产品做成插件 v2 扩展点
> `register_external_product(adapter)`」的契约在真实 transcript 上成立，并产出
> 归一化 ledger 样例供 v0.5.0 设计文档引用。

## 背景决策（Q1 结论）

外部产品（claude code / codex）**不写进 angelus 核心**，而是做成插件 v2 扩展点
`register_external_product(adapter)`。分阶段：

- **Phase 0 观察**：transcript → 统一 schema → ledger（本 Spike 覆盖）
- **Phase 1 控制**：codex 无原生审批门，标注为限制
- **Phase 2 上下文历史**：把外部会话的上下文历史接入 angelus 图记忆

## 运行

```bash
python scripts/spike_product_adapters/run_spike.py
```

脚本会：
1. 扫描 `~/.claude/projects/*/*.jsonl` 与 `~/.codex/sessions/**/*.jsonl`
2. 用两个 adapter 把真实行归一化为统一 schema
3. 输出统计 + 抽样事件 + 归一化 ledger（`out/ledger.ndjson`）

## 统一 schema（归一化事件）

| 字段 | 类型 | 说明 |
|---|---|---|
| `product` | str | `claude` / `codex` |
| `session_id` | str | 产品侧会话标识 |
| `seq` | int | 会话内递增序号 |
| `ts` | float | 归一化 Unix 时间戳 |
| `kind` | str | `user` / `assistant` / `tool_call` / `tool_result` / `reasoning` / `meta` / `error` |
| `role` | str? | 消息角色（user/assistant/developer/system） |
| `content` | str? | 文本内容（截断到 2000 字符） |
| `tool` | str? | 工具名 |
| `tool_input` | dict? | 工具参数（解析后的 JSON） |
| `tool_call_id` | str? | 工具调用 id |
| `tool_output` | str? | 工具输出（截断） |
| `model` | str? | 模型标识 |
| `usage` | dict? | token 用量 |
| `error` | str? | 错误信息 |
| `raw_type` | str | 原始行 type，便于回溯 |

## 契约验证（adapter 必须满足）

每个 adapter 实现 `iter_events(path) -> Iterator[dict]`，产出上述统一 schema。
`run_spike.py` 断言：
- 每个产品至少解析出 1 条 `user` 与 1 条 `assistant` 事件；
- 所有事件字段类型符合 schema；
- 事件按 `seq` 单调递增。
