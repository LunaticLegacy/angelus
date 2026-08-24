# src-tauri/ — Tauri Desktop Shell INDEX

Angelus 的 Tauri 2 桌面壳。它为本地 FastAPI 服务选择 loopback 端口、管理 Python sidecar 生命周期，并将 WebView 指向该服务。

| Entry | Type | Responsibility |
|---|---|---|
| `src/main.rs` | 预留本地端口、启动/回收后端进程并创建 Tauri WebView 窗口。 |
| `Cargo.toml` / `Cargo.lock` | Rust 包与锁定依赖。 |
| `tauri.conf.json` | 窗口、bundle、sidecar 资源和 CSP 配置。 |
| `build.rs` | Tauri build-time 配置入口。 |
| `binaries/` | `scripts/build-backend.mjs` / `build_backend.py` 生成的 Python sidecar 放置目录。 |
| `icons/` | 桌面应用图标源文件。 |

## Intent Routing

- **桌面生命周期与端口/进程管理** → `src/main.rs`
- **打包、资源或 CSP** → `tauri.conf.json`
- **构建 Python sidecar** → `../scripts/INDEX.md`

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [build.rs](build.rs#L1) | `main` | `None` | `()` | Implement `main` in the desktop shell. |
| [src/main.rs](src/main.rs#L19) | `drop` | `&mut self` | `()` | Implement `drop` in the desktop shell. |
| [src/main.rs](src/main.rs#L26) | `reserve_port` | `None` | `Result<u16, String>` | Implement `reserve_port` in the desktop shell. |
| [src/main.rs](src/main.rs#L39) | `backend_state_dir` | `app: &tauri::AppHandle` | `Result<PathBuf, String>` | Implement `backend_state_dir` in the desktop shell. |
| [src/main.rs](src/main.rs#L50) | `backend_command` | `app: &tauri::AppHandle, port: u16` | `Result<Command, String>` | Implement `backend_command` in the desktop shell. |
| [src/main.rs](src/main.rs#L99) | `start_backend` | `app: &tauri::AppHandle, port: u16` | `Result<Child, String>` | Implement `start_backend` in the desktop shell. |
| [src/main.rs](src/main.rs#L117) | `run` | `None` | `Result<(), Box<dyn std::error::Error>>` | Implement `run` in the desktop shell. |
| [src/main.rs](src/main.rs#L134) | `main` | `None` | `()` | Implement `main` in the desktop shell. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [src/main.rs](src/main.rs#L15) | `BackendProcess` | `See declaration` | `struct` | Represent `BackendProcess` desktop-shell state. |

<!-- END GENERATED SYMBOL MAP -->
