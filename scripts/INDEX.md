# scripts/ — Desktop Build Scripts INDEX

供 Tauri 桌面封装使用的 Python sidecar 入口和构建脚本。

| File | Responsibility |
|---|---|
| `backend_entry.py` | PyInstaller sidecar 入口；在 bundle 内设置前端与 starter plugins 资源根目录后启动 `angelus web`。 |
| `build-backend.mjs` | `npm run build:backend` 的无 Shell 启动器：按 `ANGELUS_PYTHON`、项目 `.venv`、系统 Python/Windows `py` 的顺序选择 Python。 |
| `build_backend.py` | 跨平台 PyInstaller 构建逻辑：收集官方 `mcp` SDK，并将前端和默认示例插件作为数据打入 sidecar，随后放入 `src-tauri/binaries/`。 |
| `sync_indexes.py` | 扫描最近 `INDEX.md` 所拥有的 Python/JavaScript/Rust 源码，生成 Function/Class Map；`--check` 只检测漂移。 |
| `migrate_context_checkpoints.py` | 一次性把旧版完整 JSON context checkpoint 转为 schema 3 SQLite 行存储；之后恢复与分页只读取所需的 200 条记录。 |
| `migrate_legacy_session.py` | 将旧 `workspace/<session>` 的 coordinator context 与任务计划迁入新的 Session state；源文件保留不动。 |
| `check_versions.py` | 校验 Angelus Python、npm、Cargo 与 Tauri manifest 是否与运行时全局版本一致；llmfetcher 版本独立。 |
| `spike_product_adapters/` | Claude Code / Codex 外部产品适配器的只读 Spike、运行脚本与验证说明。 |

`npm run build:backend` 不依赖 Bash、Git Bash 或 WSL。若需指定解释器，可设置 `ANGELUS_PYTHON` 为 Python 3 可执行文件路径。

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [build_backend.py](build_backend.py#L19) | `add_data` | `source: Path, destination: str` | `str` | Return PyInstaller's platform-native source/destination argument. |
| [build_backend.py](build_backend.py#L24) | `main` | `None` | `None` | Package the backend and install the resulting sidecar for Tauri. |
| [check_versions.py](check_versions.py#L16) | `npm_version` | `pepit: str` | `str` | Convert the supported PEP 440 release-candidate form to SemVer. |
| [check_versions.py](check_versions.py#L35) | `check_versions` | `None` | `list[str]` | Return one mismatch description for every stale version manifest. |
| [check_versions.py](check_versions.py#L63) | `main` | `None` | `int` | Print version drift and return a conventional process status. |
| [eval/f1_fidelity_check.py](eval/f1_fidelity_check.py#L63) | `_sha256_file` | `path: Path` | `str` | Implement `_sha256_file`. |
| [eval/f1_fidelity_check.py](eval/f1_fidelity_check.py#L69) | `_recursive_diff` | `pre: Any, post: Any, path: str, diffs: list[tuple[str, str, str]]` | `None` | Collect field-level differences with a stable location string. |
| [eval/f1_fidelity_check.py](eval/f1_fidelity_check.py#L85) | `run_fidelity_check` | `manifest: dict[str, Any]` | `int` | Execute the F1 comparator for one run manifest; return exit code. |
| [eval/f1_fidelity_check.py](eval/f1_fidelity_check.py#L172) | `main` | `None` | `int` | Implement `main`. |
| [eval/f2_sibling_perturbation_check.py](eval/f2_sibling_perturbation_check.py#L45) | `_iter_events` | `event_log: Path` | `Any` | Implement `_iter_events`. |
| [eval/f2_sibling_perturbation_check.py](eval/f2_sibling_perturbation_check.py#L59) | `_round_sequence` | `event_log: Path, agent_name: str` | `list[int]` | Return the ordered list of round indices for one agent's agent:round events. |
| [eval/f2_sibling_perturbation_check.py](eval/f2_sibling_perturbation_check.py#L73) | `_error_rate` | `event_log: Path, agent_name: str, after: float \| None` | `float` | Fraction of an agent's rounds that carry an error/failed/stopped terminal. |
| [eval/f2_sibling_perturbation_check.py](eval/f2_sibling_perturbation_check.py#L96) | `run_perturbation_check` | `manifest: dict[str, Any]` | `int` | Execute the F2 checks for one run manifest; return exit code. |
| [eval/f2_sibling_perturbation_check.py](eval/f2_sibling_perturbation_check.py#L188) | `main` | `None` | `int` | Implement `main`. |
| [eval/f3_recovery_cost_check.py](eval/f3_recovery_cost_check.py#L35) | `run_cost_check` | `manifest: dict[str, Any]` | `int` | Execute the F3 inequality for one run manifest; return exit code. |
| [eval/f3_recovery_cost_check.py](eval/f3_recovery_cost_check.py#L94) | `main` | `None` | `int` | Implement `main`. |
| [eval/manifest.py](eval/manifest.py#L33) | `load_manifest` | `path: str \| Path` | `dict[str, Any]` | Load and structurally validate one run manifest. |
| [eval/manifest.py](eval/manifest.py#L50) | `require` | `manifest: dict[str, Any], section: str, field: str` | `Any` | Return a manifest field or raise with the section/field name. |
| [eval/manifest.py](eval/manifest.py#L58) | `resolve` | `root: str \| Path, value: str` | `Path` | Resolve a manifest path against the repo root when relative. |
| [migrate_context_checkpoints.py](migrate_context_checkpoints.py#L10) | `migrate_context` | `path: Path, raw: object \| None` | `Path` | Migrate one legacy checkpoint without loading it more than once. |
| [migrate_context_checkpoints.py](migrate_context_checkpoints.py#L66) | `main` | `None` | `int` | Migrate one file or recursively migrate a context directory. |
| [migrate_legacy_session.py](migrate_legacy_session.py#L21) | `migrate_legacy_session` | `legacy_root: Path, state_root: Path, session_id: str` | `Path` | Copy durable legacy coordinator context and task plan to one Session. |
| [migrate_legacy_session.py](migrate_legacy_session.py#L72) | `_bind_legacy_project` | `legacy_root: Path, state_root: Path, session_id: str` | `None` | Bind a recovered Session to its old project tree when it exists. |
| [migrate_legacy_session.py](migrate_legacy_session.py#L95) | `main` | `None` | `int` | Parse migration arguments, execute the copy, and print its target. |
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
| [eval/manifest.py](eval/manifest.py#L29) | `ManifestError` | `None` | `ValueError` | Raised when a run-manifest is missing or malformed. |
| [spike_product_adapters/adapters.py](spike_product_adapters/adapters.py#L61) | `ClaudeAdapter` | `None` | `object` | Parse `~/.claude/projects/<cwd-hash>/<session>.jsonl` transcript lines. |
| [spike_product_adapters/adapters.py](spike_product_adapters/adapters.py#L152) | `CodexAdapter` | `None` | `object` | Parse `~/.codex/sessions/<date>/rollout-*.jsonl` transcript lines. |
| [sync_indexes.py](sync_indexes.py#L35) | `FunctionSymbol` | `path: Path, line: int, name: str, inputs: str, output: str, semantics: str` | `object` | One searchable function or method map row. |
| [sync_indexes.py](sync_indexes.py#L56) | `ClassSymbol` | `path: Path, line: int, name: str, inputs: str, bases: str, semantics: str` | `object` | One searchable class map row. |

<!-- END GENERATED SYMBOL MAP -->
