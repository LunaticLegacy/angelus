# src-tauri/ — Tauri Desktop Shell INDEX

Angelus 的 Tauri 2 桌面壳。它为本地 FastAPI 服务选择 loopback 端口、管理 Python sidecar 生命周期，并将 WebView 指向该服务。

| Entry | Type | Responsibility |
|---|---|---|
| `src/main.rs` | 预留本地端口、启动/回收后端进程并创建 Tauri WebView 窗口。 |
| `Cargo.toml` / `Cargo.lock` | Rust 包与锁定依赖。 |
| `tauri.conf.json` | 窗口、bundle、sidecar 资源和 CSP 配置。 |
| `build.rs` | Tauri build-time 配置入口。 |
| `binaries/` | `scripts/build-backend.sh` 生成的 Python sidecar 放置目录。 |
| `icons/` | 桌面应用图标源文件。 |

## Intent Routing

- **桌面生命周期与端口/进程管理** → `src/main.rs`
- **打包、资源或 CSP** → `tauri.conf.json`
- **构建 Python sidecar** → `../scripts/INDEX.md`
