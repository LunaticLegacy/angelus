# AI Drama Production Studio — 生产托管指南

> 分支：`feat/v0.5.0-adapter-and-perf` · 适用：Phase 8 生产托管
> 目标：把 Angelus 后端 + React Studio 前端部署到生产环境，满足「API Key 不进浏览器、视频生成由后端调用、长任务异步化、全流程可观测」等硬性约束。

## 1. 部署拓扑

```
                         ┌─────────────────────────────┐
   Browser (React SPA)   │   Reverse Proxy (nginx)     │
   ── HTTPS ───────────► │   TLS 终止 / 静态资源 / 反代  │
                         └──────────────┬──────────────┘
                                        │ /api/*  → 127.0.0.1:8765
                                        │ /       → 静态 dist/（或后端托管）
                              ┌─────────▼─────────┐
                              │  Angelus Backend  │  uvicorn angelus.webapp:app
                              │  (FastAPI)        │  · /api/anime/* 短剧领域 API
                              └─────────┬─────────┘
                                        │ 后端持有全部密钥
                              ┌─────────▼─────────┐
                              │  Generation Queue │  异步任务：LLM / 图像 / 视频生成
                              │  + Provider 层    │  · 可观测 / 可恢复 / 可取消 / 可重试
                              └───────────────────┘
```

**关键安全边界：**
- **API Key 只存在于后端环境变量 / 密钥管理，绝不进入浏览器。**
- **视频 / 图像生成 API 一律由后端调用**（`angelus/anime/providers/*`），前端只提交任务、轮询/订阅状态。
- 前端通过 `/api/anime/*` 与后端交互；`/api/anime/providers` 只暴露 provider 名称与能力，不含密钥。

## 2. 后端部署

### 2.1 运行方式

```bash
# 生产：用 uvicorn 直接跑（等价于 `angelus web`）
uvicorn angelus.webapp:app --host 127.0.0.1 --port 8765 --workers 1
```

> 注意：`GenerationQueue` 是进程内共享队列（webapp 挂载时 `_anime_queue.start()`）。
> 当前实现为单进程模型，**生产必须 `--workers 1`**，否则多 worker 各自持有独立队列导致任务状态不一致。
> 后续如需横向扩展，需把队列与事件存储迁移到共享后端（Redis / Postgres），见 §5 演进路线。

### 2.2 systemd 单元（示例）

```ini
# /etc/systemd/system/angelus-studio.service
[Unit]
Description=Angelus AI Drama Production Studio
After=network.target

[Service]
Type=simple
User=angelus
WorkingDirectory=/opt/angelus
EnvironmentFile=/etc/angelus-studio.env
ExecStart=/opt/angelus/.venv/bin/uvicorn angelus.webapp:app --host 127.0.0.1 --port 8765 --workers 1
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

### 2.3 环境变量（`/etc/angelus-studio.env`）

```bash
# 后端密钥（仅后端可见）
LLMFETCHER_API_KEY=sk-xxxx
# 视频 / 图像生成 Provider 密钥（如适用）
VIDEO_PROVIDER_API_KEY=xxxx
# 数据根目录（项目 workspace / audit log / assets）
ANGELUS_STATE_ROOT=/var/lib/angelus-studio
```

> 任何 `*_API_KEY` 都不得出现在前端构建产物或静态资源中。

## 3. 前端部署

### 3.1 构建

```bash
cd frontend
npm ci
npm run build        # 产物输出到 frontend/dist/
```

### 3.2 托管方式（二选一）

**A. 由后端托管（推荐单机部署）**
把 `frontend/dist/` 复制到后端可访问目录，由 FastAPI 挂载为静态资源 + SPA fallback。
（当前后端已挂载 `/static`；React 应用可挂到 `/studio` 或根路径，需加 SPA history fallback。）

**B. 独立静态托管 / CDN**
把 `frontend/dist/` 部署到 nginx / S3+CloudFront / Vercel 等。
- 静态资源走 CDN，`/api/*` 通过同域反代或 CORS 指向后端。
- 生产建议同域反代（避免 CORS、便于 Cookie/鉴权）。

### 3.3 nginx 反代示例

```nginx
server {
    listen 443 ssl;
    server_name studio.example.com;
    ssl_certificate     /etc/letsencrypt/live/studio.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/studio.example.com/privkey.pem;

    # React SPA 静态资源
    root /opt/angelus/frontend/dist;
    index index.html;

    # SPA history fallback
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API 反代到后端（后端只监听 127.0.0.1）
    location /api/ {
        proxy_pass http://127.0.0.1:8765;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        # SSE 长连接
        proxy_buffering off;
        proxy_read_timeout 3600s;
    }
}
```

> SSE 端点 `/api/anime/projects/{id}/events` 与旧 runs SSE 一样要求 **`proxy_buffering off`**，否则事件流被缓冲不实时。

## 4. 可观测性与运维

- **审计日志**：所有 `anime.*` 事件写入 workspace 事件存储，前端「事件流」页可回放（`?after=N` 语义）。
- **任务可观测**：`/api/anime/projects/{id}/jobs` 暴露每个 GenerationJob 状态 / 重试次数 / 错误；失败可 `retry`，非终态可 `cancel`。
- **成本追踪**：`anime.cost.recorded` 事件 + CostRecord 模型，供 BudgetGuard 依据。
- **Artifact 落盘**：每个生成结果都成为 Asset 记录（`uri` 指向本地文件或 provider URL），导出端点聚合为成片清单 / 剧本 / 资产包 / 字幕。
- **备份**：`ANGELUS_STATE_ROOT` 下为项目 workspace（含事件、资产元数据），定期快照即可。

## 5. 演进路线（横向扩展）

| 阶段 | 变更 | 说明 |
|---|---|---|
| 单机（当前） | `--workers 1` + 进程内队列 | 满足小团队 / 单机生产 |
| 多 worker | 队列 → Redis Stream / BullMQ | 任务状态共享，支持多进程消费 |
| 多机 | 事件存储 → Postgres；资产 → 对象存储 | 支持分布式生成 worker 池 |
| 弹性 | 生成任务可投递到外部 worker（ComfyUI 等作为 generation backend） | 保持「ComfyUI 只是后端，不是产品 UI」原则 |

## 6. 安全清单（上线前检查）

- [ ] 后端只监听 `127.0.0.1`，公网流量全部经 TLS 反代
- [ ] 所有 `*_API_KEY` 仅在服务端环境变量，前端构建产物 grep 无密钥
- [ ] `/api/anime/providers` 不返回任何密钥字段
- [ ] SSE 反代 `proxy_buffering off`
- [ ] 生产 `--workers 1`（当前队列模型）
- [ ] 数据目录权限收紧（`chmod 700 /var/lib/angelus-studio`）
- [ ] 定期备份 workspace + 事件存储
