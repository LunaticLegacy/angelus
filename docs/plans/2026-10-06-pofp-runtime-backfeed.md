# POFP Runtime Features Backfeed Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 POFP 中与通用 Agent runtime 相关的可观测性、持久化投影和上下文能力反哺到 Angelus，同时保持 Angelus 作为运行时源头。

**Architecture:** 只迁移 Angelus 可复用的后端能力和静态工作台接口，不迁移 CTF 知识库、POFP React/Tauri 产品层或商业保护链。每个能力按“测试 → 最小实现 → 验证 → 独立提交”推进，避开 Angelus 当前工作树中已有的未提交改动。

**Tech Stack:** Python 3.12+, FastAPI, SQLite/NDJSON 持久化、Angelus AgentSwarm、Angelus static frontend、pytest。

---

### Task 1: 建立 Angelus 当前基线

**Files:**
- Read: `angelus/modules/console_module/projection_service.py`
- Read: `angelus/modules/application_module/execution_service.py`
- Read: `angelus/api/session_console.py`
- Test: `tests/test_session_console.py`, `tests/test_run_graph_projection.py`

**Steps:** 记录当前未提交文件和测试基线；运行受影响测试；将 POFP 与 Angelus 的接口差异记录下来；只提交基线/差异文档。

### Task 2: 反哺 Agent 列表与持久化上下文投影

**Files:**
- Modify: `angelus/modules/console_module/projection_service.py`
- Modify: `angelus/api/session_console.py` only if routes are missing
- Test: `tests/test_session_console.py`

**Steps:** 先写测试证明运行时快照不完整时仍列出持久化 Worker；再实现按稳定 Agent ID 合并工作流节点与运行时节点；让 context/context-graph 在 Agent 未物化时读取持久化状态；运行聚焦测试；提交 `feat: restore durable agent projections`。

### Task 3: 反哺持久化用量与事件投影

**Files:**
- Modify: `angelus/modules/console_module/projection_service.py`
- Inspect: `angelus/modules/execution_module/journal.py`
- Test: `tests/test_session_console.py`, `tests/test_run_graph_projection.py`

**Steps:** 测试重启后的 durable usage 恢复和重复事件不重复计数；实现基于 `agent:usage` 与 `agent:internal_usage` 的持久化 reducer；保留 Agent 身份和可重放事件；运行测试；提交 `feat: make usage projection durable`。

### Task 4: 反哺上下文版本工具与权限兼容

**Files:**
- Modify: `angelus/modules/context_version_module/tool_provider.py`
- Modify: `angelus/modules/tool_module/tool_policy.py`
- Test: `tests/test_capability_migrations.py`

**Steps:** 测试工具标题、描述和旧 `context` 分类迁移；保留内部 ID，增加显示名称；将旧分类归一化为 `context_version`；运行 capability/context-store 测试；提交 `feat: expose named context version tools`。

### Task 5: Angelus 静态工作台 Agent 监视入口

**Files:**
- Modify: `frontend/static/app.js`
- Modify: `frontend/static/components/chat-view.js`
- Modify: `frontend/static/app.css`
- Test: `tests/test_session_console.py` and frontend smoke checks

**Steps:** 增加 Agent 选择/监视模型；右侧显示状态、最近事件、用量和选中 Agent 上下文；保留 coordinator 默认对话；补充加载、空状态、已移除 Agent 和错误状态；手动验证；提交 `feat: add agent monitor to static workbench`。

### Task 6: 文档与交付

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Create: `docs/runtime-observability.md`

**Steps:** 记录 coordinator 输入、工作流派发、Agent 检视和重启恢复语义；运行完整测试；检查没有引入 POFP 专用代码；提交 `docs: document runtime observability and recovery`。
