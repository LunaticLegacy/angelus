# frontend/src — Angelus Studio Web (React)

AI 短剧 Production Studio 的新前端骨架（Phase 7）。React + TypeScript + Vite + TanStack Query + Zustand。

## 技术栈

| 层 | 选型 |
|---|---|
| 框架 | React 18 + TypeScript (strict) |
| 构建 | Vite 5 |
| 数据获取 | TanStack Query（服务端状态 / 缓存 / 失效） |
| 全局状态 | Zustand（UI 选择状态 + SSE 事件流） |
| 路由 | react-router-dom v6 |
| 样式 | Tailwind CSS |

## 目录结构

```
src/
  app/          # 应用装配：QueryProvider、路由 App
  api/          # API 客户端（client.ts 封装 fetch；anime.ts 领域 API）
  components/   # 复用组件（StatusBadge 等）
  features/     # 领域功能模块（预留）
  hooks/        # 自定义 hooks（useAnimeEvents 订阅 SSE）
  layouts/      # 布局（StudioLayout 侧栏 + 主区）
  pages/        # 页面（Projects / ProjectDetail / Jobs / Events）
  stores/       # Zustand stores（studio.ts）
  types/        # 领域类型（与 angelus/anime/models.py + states.py 对应）
  utils/        # 工具（format 等）
```

## 开发 / 构建

```bash
npm install
npm run dev        # Vite dev server，/api 代理到 http://127.0.0.1:8765
npm run typecheck  # tsc --noEmit
npm run build      # 产物输出到 dist/
```

## 与后端的关系

- 消费 `/api/anime/*` 领域 API（见 `docs/anime/api-inventory.md`）。
- SSE 事件流：`/api/anime/projects/{id}/events?after=N`（回放 + 尾随）。
- API Key 不进浏览器；生成任务由后端队列异步执行，前端轮询/订阅状态。
- 旧 vanilla SPA（`frontend/static` + `frontend/templates`）在 Phase 2 由 `git rm -r frontend` 移除前仍保留。
