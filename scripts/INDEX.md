# scripts/ — Desktop Build Scripts INDEX

供 Tauri 桌面封装使用的 Python sidecar 入口和构建脚本。

| File | Responsibility |
|---|---|
| `backend_entry.py` | PyInstaller sidecar 入口；在 bundle 内设置前端与 starter plugins 资源根目录后启动 `angelus web`。 |
| `build-backend.mjs` | `npm run build:backend` 的无 Shell 启动器：按 `ANGELUS_PYTHON`、项目 `.venv`、系统 Python/Windows `py` 的顺序选择 Python。 |
| `build_backend.py` | 跨平台 PyInstaller 构建逻辑：收集官方 `mcp` SDK，并将前端和默认示例插件作为数据打入 sidecar，随后放入 `src-tauri/binaries/`。 |

`npm run build:backend` 不依赖 Bash、Git Bash 或 WSL。若需指定解释器，可设置 `ANGELUS_PYTHON` 为 Python 3 可执行文件路径。
