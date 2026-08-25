# 上下文压缩器核验报告 (Quest 5dd873a9208e42608b3436d7cea8ee49)

仓库根: `/home/luna/Documents/codes/python/angelus_lunae/angelus`
重点文件: `llmfetcher/context_handlers/linear.py` (851 行), `workspace/default/contexts/*.json`
核验方式: 直接读取源码 + python3 实际运行验证

---

## 逐条结论

### 1. 上下文压缩器是 ContextHandlerLinear.compact() — ✅ 确认
- `llmfetcher/context_handlers/linear.py:89` `class ContextHandlerLinear(ContextHandler)`
- `linear.py:288` `def compact(self) -> bool:` — 完整实现压缩逻辑（发送消息给 LLM、解析 `<context_abstract>`、归档原始消息、清空 active buffer）。
- 触发点: `linear.py:282-286` `add_assistant_message()` 中 `if context_size > self.compress_threshold: self.compact()`。

### 2. 传入模型的文本由 _build_compaction_input() 生成 — ✅ 确认（含一处细节修正）
- `linear.py:565` `def _build_compaction_input(self) -> str:`。
- `linear.py:577-580` 把 `self.build_messages()` 的每条消息 `json.dumps(entry, ensure_ascii=False, default=str)` 序列化为 JSON 行。
- `linear.py:582-590` 从最新往旧遍历 (`reversed(serialized_entries)`)，累计 `used += len(entry)+2`，超过 `self.compaction_input_char_limit` 即 break（丢弃更旧的）。
- `linear.py:585-589` 单条超限时取尾部 `entry[-self.compaction_input_char_limit:]`。
- `linear.py:592-600` 有省略时加前缀 `"[Earlier context entries omitted due to the {limit} character compaction budget.]\n"`，最终 `prefix + "\n\n".join(retained)`。
- 默认值: `linear.py:85` `_COMPACTION_INPUT_CHAR_LIMIT = 196_608`；`linear.py:107` 构造参数默认 `compaction_input_char_limit: int = _COMPACTION_INPUT_CHAR_LIMIT`。
- **细节修正**: 输入不是"纯 JSON 行"，而是 JSON 行之间用 `\n\n` 连接，且省略提示是**前缀**（不是后缀）；"从最新往旧保留"正确，但注意 `build_messages()` 会把 abstract 以 `role:"system"` 放在最前（`linear.py:446-449`），因此输入首条通常是 abstract 摘要而非最新原始消息。

### 3. 系统提示词 _COMPACTING_SYSTEM_PROMPT 要求只输出 <context_abstract> XML — ✅ 确认
- `linear.py:53-82` `_COMPACTING_SYSTEM_PROMPT`。
- `linear.py:72-74` `"Return exactly one XML element and nothing else:\n<context_abstract>..."`。
- `linear.py:80-81` `"Do not emit Markdown fences, XML declarations, timeline metadata, or commentary outside the element."`。
- 解析端: `linear.py:603-628` `_parse_compacted_abstract()` 用正则提取 `<context_abstract>...</context_abstract>`。

### 4. context:compact_started 事件 data 只含元数据，不含输入正文 — ✅ 确认
- `linear.py:329-341`:
  ```python
  self._emit_compaction_event("context:compact_started", ...,
      {"round": round_index, "context_size": context_size,
       "compaction_input_characters": len(compaction_input),
       "compress_threshold": self.compress_threshold,
       "ratio": round(100.0*context_size/self.compress_threshold,1) if ... else 0.0})
  ```
- data 仅含 `round/context_size/compaction_input_characters/compress_threshold/ratio`，不含 `compaction_input` 正文（只传 `len(compaction_input)`）。

### 5. 压缩输入可离线重建 — ✅ 确认（已实际运行验证）
- `save()` 持久化 `compress_threshold/round/abstract/messages/archive`（`linear.py:636-647`）；`load()` 还原（`linear.py:680-733`）。
- 实际运行（python3，加载后调用 `_build_compaction_input()`）:

| 文件 | load | round | threshold | messages | archive | abstract | 输入长度(chars) | 开头片段 |
|---|---|---|---|---|---|---|---|---|
| `workspace/default/contexts/coordinator.json` | True | 102 | 262144 | 24 | 0 | 有 | **109337** | `{"role": "system", "content": "已完成 openclaw QQ 插件修复的诊断与配置修改。背景：网关由 systemd user 服务 openclaw-gateway.service 管理（ExecStart: ...` |
| `workspace/default/contexts/turn_swarm.json` | True | 44 | 262144 | 24 | 0 | 有 | **195141** | `[Earlier context entries omitted due to the 196608 character compaction budget.]\n{"role": "tool", "content": "[stdout]\n511:  public static boolean interfloorTeleportAllowed();", ...` |

- 验证结论: 输入可离线重建，长度与开头片段如上。turn_swarm 因超限出现省略前缀；coordinator 未超限（109337 < 196608）故无前缀。
- 注意: 重建的是"当前 messages + abstract"的输入；若文件 archive 为空（如 coordinator.json），已归档的旧原始消息无法从该文件重建（见第 6 条）。

### 6. 压缩前原始消息在 messages，压缩后移入 archive，摘要存 abstract — ✅ 确认（代码层面 + 部分文件验证）
- 代码: `linear.py:405-418` `self.abstract = LLMContextCompacted(...)`; `self.archive.extend(self.messages)`; `self.messages.clear()`。
- 持久化: `linear.py:636-647` `save()` 分别写 `abstract/messages/archive`。
- **文件验证**（`workspace/token-burner/contexts/coordinator.json`，压缩已发生）:
  - `archive: 187 条`（timeline 1..187），`messages: 11 条`（timeline 188..198），`abstract: 有`（source_timeline 1..187，共 187 项）。
  - 即: 压缩前的原始消息（timeline 1..187）确实移入 archive，摘要存 abstract，压缩后的新消息留在 messages。
- **注意/修正**: `workspace/default/contexts/coordinator.json` 中 `archive: []`、`abstract.source_timeline: [1]`、messages timeline 从 79 开始——该文件经历过压缩但 archive 为空（旧格式/历史文件未保留原始消息），因此"任一文件"并不都满足 archive 非空。全仓扫描 `workspace/**/contexts/*.json` 仅 4 个文件 archive 非空（production-manager/coordinator.json 41 条、xiaohongshu-optimize/coordinator.json 66 条、token-burner/coordinator.json 187 条、pofp-agent-dev/coordinator.json 68 条）。代码行为确认无误，但 default 目录文件不能作为 archive 非空的证据。

---

## compact() 中 fetch 调用参数（实际运行验证）

源码 `linear.py:343-348`:
```python
result: LLMOutput = self.llm_handler.fetch(
    msg=compaction_input,
    system_prompt=_COMPACTING_SYSTEM_PROMPT,
    temperature=0.0,
    max_tokens=self.compaction_output_max_tokens,
    context_handler=None,
)
```

实际运行（RecordingFetcher 捕获）确认:

| 参数 | 值 |
|---|---|
| `msg` | `_build_compaction_input()` 输出（示例: `'{"role": "user", "content": "hello"}\n\n{"role": "assistant", "content": "hi"}'`） |
| `system_prompt` | `_COMPACTING_SYSTEM_PROMPT`（含 "Return exactly one XML element"） |
| `temperature` | `0.0` |
| `max_tokens` | `self.compaction_output_max_tokens` = `_COMPACTION_OUTPUT_MAX_TOKENS` = **8192**（`linear.py:84`） |
| `context_handler` | `None`（有界独立压缩，不把 handler 作为请求上下文） |
| `backend_name` | 未传（None） |
| `tools` | 未传（None） |

注意: `CompactionFetcher` 协议默认 `temperature=0.4`（`linear.py:31`），但 compact() 实际传 `0.0`。

---

## 附: 相关测试佐证
- `llmfetcher/tests/test_context_compaction.py:203-227` `test_compaction_archives_raw_messages_and_owns_provenance`: 压缩后 `handler.archive == [1,2]`、`handler.messages == []`、`abstract.source_timeline == [1,2]`。
- `llmfetcher/tests/test_context_compaction.py:229-242` `test_save_load_preserves_raw_compaction_archive`: archive 原始消息跨重启保留且不进入 build_messages。
- `tests/test_context_archive_api.py:57-77` archive 只读分页 API。
