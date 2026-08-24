# scripts/ — Desktop Build Scripts INDEX

供 Tauri 桌面封装使用的 Python sidecar 入口和构建脚本。

| File | Responsibility |
|---|---|
| `backend_entry.py` | PyInstaller sidecar 入口；在 bundle 内设置前端与 starter plugins 资源根目录后启动 `angelus web`。 |
| `build-backend.mjs` | `npm run build:backend` 的无 Shell 启动器：按 `ANGELUS_PYTHON`、项目 `.venv`、系统 Python/Windows `py` 的顺序选择 Python。 |
| `build_backend.py` | 跨平台 PyInstaller 构建逻辑：收集官方 `mcp` SDK，并将前端和默认示例插件作为数据打入 sidecar，随后放入 `src-tauri/binaries/`。 |
| `sync_indexes.py` | 扫描最近 `INDEX.md` 所拥有的 Python/JavaScript/Rust 源码，生成 Function/Class Map；`--check` 只检测漂移。 |
| `spike_product_adapters/` | Claude Code / Codex 外部产品适配器的只读 Spike、运行脚本与验证说明。 |

`npm run build:backend` 不依赖 Bash、Git Bash 或 WSL。若需指定解释器，可设置 `ANGELUS_PYTHON` 为 Python 3 可执行文件路径。

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [build_backend.py](build_backend.py#L19) | `add_data` | `source: Path, destination: str` | `str` | Return PyInstaller's platform-native source/destination argument. |
| [build_backend.py](build_backend.py#L24) | `main` | `None` | `None` | Package the backend and install the resulting sidecar for Tauri. |
| [spike_product_adapters/adapters.py](spike_product_adapters/adapters.py#L19) | `_iso_to_epoch` | `iso: str \| None` | `float \| None` | Convert an ISO-8601 timestamp to a Unix epoch float (best effort). |
| [spike_product_adapters/adapters.py](spike_product_adapters/adapters.py#L29) | `_truncate` | `text: str \| None, limit: int` | `str \| None` | Implement `_truncate`. |
| [spike_product_adapters/adapters.py](spike_product_adapters/adapters.py#L36) | `_extract_text` | `content: Any` | `str \| None` | Extract plain text from a content array or string. |
| [spike_product_adapters/adapters.py](spike_product_adapters/adapters.py#L66) | `ClaudeAdapter.iter_events` | `path: Path` | `Iterator[dict[str, Any]]` | Implement `ClaudeAdapter.iter_events`. |
| [spike_product_adapters/adapters.py](spike_product_adapters/adapters.py#L157) | `CodexAdapter.iter_events` | `path: Path` | `Iterator[dict[str, Any]]` | Implement `CodexAdapter.iter_events`. |
| [spike_product_adapters/adapters.py](spike_product_adapters/adapters.py#L265) | `discover_transcripts` | `None` | `dict[str, list[Path]]` | Locate real transcript files on this machine (best effort). |
| [spike_product_adapters/run_spike.py](spike_product_adapters/run_spike.py#L27) | `validate_event` | `event: dict, product: str` | `list[str]` | Implement `validate_event`. |
| [spike_product_adapters/run_spike.py](spike_product_adapters/run_spike.py#L41) | `main` | `None` | `int` | Implement `main`. |
| [sync_indexes.py](sync_indexes.py#L76) | `_clean` | `value: str, fallback: str` | `str` | Normalize source text for a single Markdown table cell. |
| [sync_indexes.py](sync_indexes.py#L90) | `_summary` | `docstring: str \| None, fallback: str` | `str` | Return the first documented semantic sentence for a symbol. |
| [sync_indexes.py](sync_indexes.py#L106) | `_annotation` | `node: ast.expr \| None, fallback: str` | `str` | Render a Python type annotation without evaluating it. |
| [sync_indexes.py](sync_indexes.py#L119) | `_python_inputs` | `node: ast.FunctionDef \| ast.AsyncFunctionDef` | `str` | Render Python parameters and types for an index row. |
| [sync_indexes.py](sync_indexes.py#L146) | `_python_symbols` | `path: Path, relative: Path` | `tuple[list[FunctionSymbol], list[ClassSymbol]]` | Extract documented Python functions, methods, and classes. |
| [sync_indexes.py](sync_indexes.py#L204) | `_javascript_symbols` | `path: Path, relative: Path` | `tuple[list[FunctionSymbol], list[ClassSymbol]]` | Extract JavaScript declarations with conservative unknown types. |
| [sync_indexes.py](sync_indexes.py#L252) | `_rust_symbols` | `path: Path, relative: Path` | `tuple[list[FunctionSymbol], list[ClassSymbol]]` | Extract Rust functions and data types from source declarations. |
| [sync_indexes.py](sync_indexes.py#L282) | `_owned_sources` | `index: Path` | `Iterable[Path]` | Yield source files owned by one nearest-index boundary. |
| [sync_indexes.py](sync_indexes.py#L312) | `_source_link` | `symbol: FunctionSymbol \| ClassSymbol` | `str` | Build a relative source link for a symbol row. |
| [sync_indexes.py](sync_indexes.py#L325) | `_render_map` | `index: Path` | `str` | Render deterministic Function Map and Class Map tables. |
| [sync_indexes.py](sync_indexes.py#L369) | `_updated_index` | `index: Path` | `str` | Replace or append one generated symbol-map section. |
| [sync_indexes.py](sync_indexes.py#L388) | `sync_indexes` | `root: Path, check: bool` | `list[Path]` | Synchronize every repository INDEX while preserving prose sections. |
| [sync_indexes.py](sync_indexes.py#L413) | `main` | `argv: list[str] \| None` | `int` | Run INDEX synchronization or its non-mutating drift check. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [spike_product_adapters/adapters.py](spike_product_adapters/adapters.py#L61) | `ClaudeAdapter` | `None` | `object` | Parse `~/.claude/projects/<cwd-hash>/<session>.jsonl` transcript lines. |
| [spike_product_adapters/adapters.py](spike_product_adapters/adapters.py#L152) | `CodexAdapter` | `None` | `object` | Parse `~/.codex/sessions/<date>/rollout-*.jsonl` transcript lines. |
| [sync_indexes.py](sync_indexes.py#L35) | `FunctionSymbol` | `path: Path, line: int, name: str, inputs: str, output: str, semantics: str` | `object` | One searchable function or method map row. |
| [sync_indexes.py](sync_indexes.py#L56) | `ClassSymbol` | `path: Path, line: int, name: str, inputs: str, bases: str, semantics: str` | `object` | One searchable class map row. |

<!-- END GENERATED SYMBOL MAP -->
