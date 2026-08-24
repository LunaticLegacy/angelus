# frontend/ — Web UI INDEX

Angelus 前端包含两代实现：

| 代 | 目录 | 技术 | 状态 |
|---|---|---|---|
| 旧 vanilla SPA | `static/` + `templates/` | 原生 HTML + ES modules + CSS | 生产在用；Phase 2 由 `git rm -r frontend` 移除（HARD GATE：先提交 Phase 1 产物 + 回归全绿） |
| 新 React Studio | `src/` | React + TS + Vite + TanStack Query + Zustand | Phase 7 骨架；AI 短剧 Production Studio 前端 |

## Route Map

| Entry | Type | Purpose |
|-------|------|---------|
| [`static/`](static/INDEX.md) | Dir | 旧 vanilla SPA：JS modules, CSS, static assets |
| [`templates/`](templates/INDEX.md) | Dir | 旧 SPA 单页 HTML shell |
| [`src/`](src/README.md) | Dir | 新 React Studio Web（AI 短剧 Production Studio） |
| `package.json` | File | 新前端依赖与脚本（dev/build/typecheck） |
| `vite.config.ts` | File | Vite 配置（dev 代理 /api → 127.0.0.1:8765） |
| `tailwind.config.js` | File | Tailwind 配置 |
| `tsconfig.json` | File | TypeScript strict 配置 |

## 旧 vanilla SPA（生产在用）

- **No framework**: Plain HTML + vanilla ES modules + CSS
- **SSE**: EventSource for live run streaming
- **REST**: Fetch-based API calls for CRUD operations
- **Active runtime**: `templates/index.html` loads the global slash-command parser `static/slash.js` and `static/app.js` as the ES-module composition root. `app.js` owns cross-feature coordination, initializes the active plugin bridge in `static/plugins.js`, and delegates reusable DOM views to `static/components/`.
- **Legacy module split**: the older `static/*.js` and `static/inspector/*.js` modules remain unreferenced migration artifacts. They are distinct from the active `static/components/` directory and must not be changed under the assumption that they run in production.

## 新 React Studio（Phase 7 骨架）

- 消费 `/api/anime/*` 短剧领域 API（项目 → 剧集 → 场景 → 镜头 → 生成任务 → QA → 事件流）。
- 页面：项目列表 / 项目详情（剧集-场景-镜头树 + 生成/QA/通过操作）/ 生成任务（可观测/取消/重试）/ 事件流（SSE 实时）。
- 详见 [`src/README.md`](src/README.md) 与 `docs/anime/production-hosting.md`。

## Intent Routing

- **旧 SPA HTML 结构** → `templates/index.html`
- **旧 SPA 行为** → `static/app.js`
- **新 React 应用** → `src/`
- **生产托管** → `docs/anime/production-hosting.md`
