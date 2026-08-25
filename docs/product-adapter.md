# ProductAdapter 契约（插件 v2 扩展点）

> 状态：**草案，Spike 已验证**（`scripts/spike_product_adapters/`，94,273 条真实事件归一化通过）
> 本文档定义插件 v2 扩展点 `register_external_product(adapter)` 的对外契约。
> 具体产品适配器（claude/codex）由插件提供，**不写进 angelus 核心**。

---

## 1. 定位

angelus 核心只定义契约，不感知任何具体外部产品。插件通过
`AngelusPlugin.register_external_product(adapter)` 注册一个适配器，把外部产品的
transcript / 控制接口归一化为 angelus 统一事件流。

```
外部产品 transcript ──► ProductAdapter.iter_events() ──► 统一 schema 事件
外部产品 CLI/hooks  ──► ProductAdapter.drive()/control() ──► 驱动/控制
```

## 2. 统一 schema（归一化事件）

Spike 已验证的字段（`scripts/spike_product_adapters/README.md` 为权威样例）：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `product` | str | ✅ | `claude` / `codex`（插件注册名） |
| `session_id` | str | ✅ | 产品侧会话标识 |
| `seq` | int | ✅ | 会话内递增序号（**每个产出事件唯一**） |
| `ts` | float | ✅ | 归一化 Unix 时间戳（ISO-8601 → epoch） |
| `kind` | str | ✅ | `user` / `assistant` / `tool_call` / `tool_result` / `reasoning` / `meta` / `error` |
| `role` | str? | | user / assistant / developer / system / tool |
| `content` | str? | | 文本内容（截断到 2000 字符） |
| `tool` | str? | | 工具名 |
| `tool_input` | dict? | | 工具参数（解析后的 JSON） |
| `tool_call_id` | str? | | 工具调用 id |
| `tool_output` | str? | | 工具输出（截断） |
| `model` | str? | | 模型标识 |
| `usage` | dict? | | token 用量 |
| `error` | str? | | 错误信息 |
| `raw_type` | str | ✅ | 原始行 type，便于回溯 |

**契约不变量**：
- `seq` 单调递增（每个产出事件唯一，一条原始行可产出多条事件）；
- 至少能解析出 `user` 与 `assistant` 事件（Spike 断言）；
- 未知/畸形行**跳过不抛异常**，保证观察永不击穿。

## 3. Adapter 接口

```python
class ProductAdapter(Protocol):
    product: str  # 唯一产品标识，如 "claude" / "codex"

    def iter_events(self, path: Path) -> Iterator[dict]: ...
    # 把一条 transcript 文件归一化为统一 schema 事件流。

    # Phase 1 控制（可选，未实现则标注 capability 限制）：
    def drive(self, session_id: str, message: str) -> None: ...
    def control(self, session_id: str, action: str) -> None: ...
    # Phase 2 上下文历史（可选）：
    def context_history(self, session_id: str) -> list[dict]: ...
```

## 4. 能力声明与限制

| 能力 | claude code | codex | 说明 |
|---|---|---|---|
| 观察（读 transcript） | ✅ | ✅ | Phase 0 |
| 驱动（注入指令） | ✅ `claude -p --input-format=stream-json` | ✅ `codex exec/resume/queue` | Phase 1 |
| 审批门（暂停/恢复） | ✅ hooks + `--include-hook-events` | ⚠️ **无原生审批门** | Phase 1 限制 |
| 实时事件流 | ✅ stream-json（含 hook events） | ⚠️ 无原生流式 JSON，靠轮询 jsonl | Phase 1 限制 |
| 上下文历史 | ✅ | ✅ | Phase 2 |

**限制必须显式声明**：适配器在 `capabilities` 字段中声明支持的能力；angelus 对未声明
能力不提供 UI 入口，避免「看起来能控制、实际做不到」。

## 5. 与插件 api_version v2 的关系

- `register_external_product` 是插件 v2 新增扩展点，随 `api_version: "2"` 发布；
- v1 插件（五类既有接线）不受影响，加载器按 `api_version` 分流；
- 权限枚举扩展：新增 `external_product:read`（观察）与 `external_product:control`（驱动/控制），
  未授权权限一律拒绝（沿用 S10 安全模型）。

## 6. Spike 证据

- 脚本：`scripts/spike_product_adapters/`（`adapters.py` + `run_spike.py` + 单测 `tests/test_spike_product_adapters.py`）
- 实测：claude 4 文件、codex 273 文件；归一化 94,273 条事件，契约断言 PASS。
- 关键格式事实：
  - claude assistant 行：`message.content[]` 含 `text` / `tool_use` / `thinking`；`isApiErrorMessage` 标记错误。
  - codex `response_item.payload.type`：`message`（role 区分 user/assistant/developer）、`reasoning`、`function_call`（arguments 为 JSON 字符串）、`function_call_output`。
