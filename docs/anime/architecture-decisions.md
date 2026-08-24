# AI Drama Production Studio — 架构决策记录 (ADR)

> 分支：`feat/v0.5.0-adapter-and-perf` · 状态：收敛完成（coordinator 收敛，两个架构 subagent 因 LLM 后端不可达失败）
> 目标：基于 Angelus 仓库重构为 AI 短剧 Production Studio，复用 Agent Runtime / LLM 调用层，不重造轮子。

## 决策点 A — 前端与旧 API 的关系

**决策：KEEP 全部旧 API，前端 React 重构后通过同一批 API 工作；旧 vanilla SPA 在 Phase 2 由 `git rm -r frontend` 移除（HARD GATE：先提交 Phase 1 产物 + 回归测试全绿）。**

- 旧 API 是 Angelus 控制面的稳定契约（connectors/runs/sessions/compact/plugins 动态路由），新前端继续消费它们。
- 新增 `/api/anime/*` 命名空间承载短剧领域 API，与旧 API 并存，互不干扰。
- 旧 `frontend/static/*` 中未引用的 legacy 模块（api.js/state.js/chat.js 等）仅作迁移参考，不迁移。

## 决策点 B — anime 包结构

**决策：新建 `angelus/anime/` 包，作为独立领域模块，依赖方向 Drama → Angelus（单向）。**

```
angelus/anime/
  __init__.py          # 公开 API 面
  models.py            # DramaProject/Episode/Scene/Shot/Asset/GenerationJob/QAReport/CostRecord
  states.py            # Shot 状态机 + 统一任务状态枚举
  storage.py           # workspace/<project>/anime/ 目录，atomic write，复用 storage._persist_json 模式
  events.py            # 事件模型 anime.*，写 audit log + SSE
  providers/
    __init__.py        # VideoGenerationProvider Protocol
    router.py          # ProviderRouter（explicit + auto fallback）
    mock.py            # MockVideoProvider（默认测试用）
    registry.py        # provider 注册表
  queue.py             # GenerationJob 队列（可观测/可恢复/可取消/可重试）
  budget.py            # BudgetGuard（WAITING_FOR_APPROVAL）
  qa.py                # QA 管线 + QAReport
  export.py            # FFmpeg 合成导出 MP4/SRT/VTT
  narrative/
    __init__.py
    outline.py         # Series Brief→Global Outline→Arc→Episode→Scene→Storyboard→Shot
    gate.py            # Narrative Gate（PASS/WARN/FAIL）
    character.py       # Character State 结构化
    foreshadowing.py   # 伏笔管理（CSV 迁移）
    audience.py        # Audience Information
  api/
    __init__.py        # include_anime_routes(app)
    projects.py        # /api/anime/projects/*
    episodes.py        # /api/anime/episodes/*
    scenes.py          # /api/anime/scenes/*
    shots.py           # /api/anime/shots/*
    jobs.py            # /api/anime/jobs/*
    qa.py              # /api/anime/qa/*
    providers.py       # /api/anime/providers/*
```

## 决策点 C — 持久化方案

**决策：local-first，`workspace/<project>/anime/` 目录；复用 Angelus `storage.py` 的原子写模式（`.tmp` + `os.replace`）与 `_safe_id` 校验。**

- 每个项目一个目录：`workspace/<project_id>/anime/{project.json, episodes/, scenes/, shots/, assets/, jobs/, qa/, costs/, events.ndjson, audit.ndjson}`
- 事件模型 `anime.*` 追加进 `events.ndjson`（与 Angelus `_append_session_event` 同构），SSE 通过 `?after=N` 回放 + 尾随。
- 不引入新数据库；JSON + ndjson 足够本地单机场景。

## 决策点 D — LLM 集成

**决策：复用 Angelus/llmfetcher 的 `LLMFetcher`/`LLMBackendConfig`/`Agent`/`AgentSwarm`，不重造。**

- 剧情编排（outline/gate/character）通过 `LLMBackendConfig(name="browser", provider, model, api_key, api_url, timeout, max_retries)` + `create_fetcher(backend, provider)` 模式调用。
- API Key 只存在于服务端进程内（connector 解密注入），**绝不进浏览器**；视频生成 API 必须后端调用。
- 不写死 API Key/模型名/临时 URL；全部来自 connector 配置或环境变量。

## 决策点 E — 任务队列

**决策：`GenerationJob` 为最小调度单元（Shot 维度），后台线程队列 + 持久化状态 + 事件流。**

- 状态机：`PENDING → QUEUED → RUNNING → SUCCEEDED/FAILED/CANCELLED/EXPIRED`
- 可观测：每个状态迁移写 `anime.job.*` 事件 + SSE
- 可恢复：重启后从 `jobs.json` 恢复未完成 job
- 可取消：`POST /api/anime/jobs/{id}/cancel`
- 可重试：`POST /api/anime/jobs/{id}/retry`（受 Retry Policy 约束）
- 每个生成结果都是 Artifact（复用 Angelus artifacts 概念）

## 决策点 F — Provider 边界

**决策：`VideoGenerationProvider` Protocol（capabilities/submit/get_task/cancel）+ `ProviderRouter`（explicit provider + auto fallback）。**

- 统一任务状态：`PENDING/QUEUED/RUNNING/SUCCEEDED/FAILED/CANCELLED/EXPIRED`
- Provider 通过 `registry.py` 注册；mock provider 为默认，真实 API 需 opt-in 环境变量。
- ComfyUI 只是 generation backend，不是产品 UI；通过 provider adapter 接入。

## 决策点 G — 前端状态架构

**决策：React+TS+Vite+Router+TanStack Query+Zustand，目录 `frontend/src/{app,api,components,features,hooks,layouts,pages,stores,types,utils}`。**

- TanStack Query：服务端状态（API 数据、轮询）
- Zustand：客户端状态（UI 状态、选择器、表单草稿）
- SSE 事件通过 hook 订阅，写入 Zustand store 或触发 query invalidation

## 决策点 H — 事件审计

**决策：`anime.*` 事件模型进 audit log + SSE；与 Angelus `events.ndjson` 同构。**

- 事件类型：`anime.project.created/updated/deleted`、`anime.shot.state_changed`、`anime.job.submitted/queued/running/succeeded/failed/cancelled/retried`、`anime.qa.passed/failed`、`anime.cost.recorded`、`anime.budget.awaiting_approval`
- SSE 端点：`GET /api/anime/events?after=N`（回放 + 尾随）

## 决策点 I — 测试策略

**决策：默认 mock，真实 API 需 opt-in 环境变量。**

- 单元测试：models/states/storage/queue/budget/gate（纯逻辑，无网络）
- 集成测试：FastAPI TestClient 打 `/api/anime/*`，用 MockVideoProvider
- 回归测试：现有 Angelus 测试套件必须全绿（HARD GATE）
- 真实 API 测试：`ANIME_REAL_PROVIDER=1` 环境变量 opt-in，默认跳过

## 决策点 J — 实施顺序

**决策：Phase 1（清单/矩阵/回归）→ Phase 2（anime 包骨架+存储+事件）→ Phase 3（Provider 层）→ Phase 4（任务队列）→ Phase 5（剧情编排迁移）→ Phase 6（QA+导出）→ Phase 7（前端 React）→ Phase 8（生产托管）→ Phase 9（测试验证）→ Phase 10（文档提交）。**

- 每 Phase 结束可独立验证；Phase 1 是 HARD GATE，完成前禁止删除 frontend。
