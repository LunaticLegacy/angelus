# angelus/ — Control Plane INDEX

Angelus 是覆盖 `llmfetcher` 的本地控制平面。它拥有浏览器 API、运行控制、会话投影、连接器凭据、跨会话记忆和插件宿主；模型调用、Agent loop、图记忆、工具与 Swarm 算法留在 `llmfetcher/` 子模块。

## Route Map

| Entry | Type | Responsibility |
|---|---|---|
| [`api/`](api/INDEX.md) | FastAPI routers | 浏览器 HTTP/SSE 路由与 SPA 根页面。 |
| [`classes/`](classes/INDEX.md) | Data models | 请求模型以及内存态运行/会话控制类。 |
| [`event_stream/`](event_stream/INDEX.md) | SSE broadcast | 持久事件提交、有界多订阅者广播、历史交接与慢客户端磁盘补偿。 |
| [`plugins/`](plugins/INDEX.md) | Plugin runtime | 插件发现、生命周期、权限、完整性与宿主桥接。 |
| `webapp.py` | Application assembly | 创建 FastAPI app、挂载静态资源、初始化插件管理器并注册 API。 |
| `runtime.py` | Runtime construction | 构建 Agent / Swarm、运行配置快照、按 Agent 隔离的计划与会话记忆存储；provider 增量通过内存广播，最终回复正常落盘；每轮的上下文阈值先更新内存，并在 Agent 加载旧 checkpoint 后重新应用，直到安全边界才随完整上下文保存；Swarm 在同一进程连续轮次中保留实例，并写入本地恢复快照。 |
| `storage.py` | Durable state | 状态根目录、会话注册表、事件账本、JSON 持久化与并发保护。 |
| [`history/`](history/INDEX.md) | Read-model package | 从事件和上下文投影重建历史、归档、图和用量；包入口保持原导入 API。 |
| `context_editing.py` | Context revisions | Agent 活动上下文的版本化编辑、原子快照、追加审计与前向恢复；归档、事件账本和远程请求快照不在其写入范围内。 |
| `context_stats.py` | Context accounting | 以统一序列化口径估算消息、工具 schema、字符与 token 数量。 |
| `connectors.py` | Credentials | 连接器 CRUD、RSA-OAEP 凭据加密与服务端解析。 |
| `session_memory.py` | Cross-session memory | 按运行级许可提供快照式会话/产物检索工具。 |
| `task_planning.py` | Plans | 会话本地 JSON 任务计划、TaskBus assignment 关联和递归父状态派生。 |
| `markdown.py` | Rendering | 受限 LRU 的安全 Markdown → HTML 渲染。 |
| `plugin_manifest.py` | Manifest validation | 手写的插件清单 v1 字段级校验。 |
| `plugin_paths.py` | Plugin locations | 与 `workspace/` 并列的持久插件目录解析，以及环境变量覆盖。 |
| `plugin_bootstrap.py` | Packaged examples | 首次启动时将发布包内的示例插件复制到持久插件目录，绝不自动执行或覆盖用户文件。 |
| `mcp_tools.py` | MCP bridge | 用官方 Python `mcp` SDK 连接服务器、发现远端工具并桥接为原生 Agent 工具。 |
| `plugin_registry.py` | Plugin registry | 原子读写 `plugins.json` 中的安装、启用与授权记录。 |
| `provider_adapters.py` | Provider presets | 将 Kimi Code 等一方预设解析为 LLMFetcher 已支持的后端与默认端点。 |
| `cli.py` | CLI | 本地 `web` / `session` / `plugin` 命令与 llmfetcher 命令委托。 |
| `__init__.py` / `__main__.py` | Package entry | 公共门面与 `python -m angelus` 入口。 |

## Durable State Ownership

`ANGELUS_STATE_DIR` 可指定状态根目录（兼容 `LLMFETCHER_STATE_DIR`）；否则使用本地工作区。连接器与插件注册表在全局范围共享，而会话目录彼此隔离。CLI 的 `--state-dir` 会同时设置两个名称，使插件目录和注册表保持同一应用根。

| Scope | Records |
|---|---|
| Global state root | `sessions.json`、`connectors.json`、RSA 密钥对、`plugins.json` |
| Session directory | `conversation.json`、`events.ndjson`、`run-state.json`、`task-plan.json`、`graph-view.json`、`swarm-runtime.json` |
| Agent context | `contexts/<agent>.json`、主文件引用的不可变 generation 图 checkpoint、旧版图伴随文件，以及 `contexts/revisions/<agent>/` 的不可变编辑快照与 `context-edits.ndjson` 审计账本 |

API 密钥不返回给浏览器。持久化的运行配置与 `swarm-runtime.json` 均不含密钥；直接输入的浏览器密钥只在当前请求中使用。为使动态 worker 能在服务重启后重建，`swarm-runtime.json` 会保留其本地 system prompt，因而与会话上下文同属本机私有状态。

## Intent Routing

- **HTTP 端点、SSE 或静态控制台** → `api/INDEX.md`
- **持久化、状态目录、事件账本** → `storage.py`
- **历史、归档、图或用量读模型** → `history/INDEX.md`
- **Agent / Swarm 构建** → `runtime.py`
- **连接器凭据** → `connectors.py`
- **跨会话记忆授权** → `session_memory.py`
- **插件契约、注册表或运行时** → `plugin_*.py` 与 `plugins/INDEX.md`
- **请求与内存态控制模型** → `classes/INDEX.md`

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [cli.py](cli.py#L50) | `_build_parser` | `None` | `argparse.ArgumentParser` | Build the Angelus parser: library core commands plus web/session/plugin. |
| [cli.py](cli.py#L112) | `_configure_state_root` | `state_dir: str \| None` | `None` | Apply one CLI state root before importing state-owning Angelus modules. |
| [cli.py](cli.py#L132) | `_cmd_web` | `args: argparse.Namespace` | `None` | Run the optional FastAPI browser console. |
| [cli.py](cli.py#L144) | `_cmd_session` | `args: argparse.Namespace` | `None` | Create or list browser-visible sessions and their private directories. |
| [cli.py](cli.py#L169) | `_plugin_modules` | `None` | `Any` | Import the plugin-system support modules from the registry branch. |
| [cli.py](cli.py#L179) | `_fail` | `message: str` | `None` | Print an error to stderr and exit non-zero. |
| [cli.py](cli.py#L185) | `_is_skipped` | `path: Path, root: Path` | `bool` | True for VCS/cache/private paths that must never enter a plugin install. |
| [cli.py](cli.py#L191) | `_copy_tree` | `src: Path, dst: Path` | `None` | Recursively copy ``src`` into ``dst``, skipping VCS/cache internals. |
| [cli.py](cli.py#L204) | `_canonical_manifest_bytes` | `manifest: dict` | `bytes` | Canonical JSON bytes of the manifest with ``checksum`` excluded. |
| [cli.py](cli.py#L219) | `_resolve_entry_path` | `plugin_dir: Path, manifest: dict` | `Path \| None` | Resolve ``manifest.entry`` to an existing file inside ``plugin_dir``. |
| [cli.py](cli.py#L251) | `_compute_integrity_checksum` | `plugin_dir: Path, manifest: dict` | `str` | Install-time integrity checksum over manifest + entry (S10 contract). |
| [cli.py](cli.py#L267) | `_find_manifest_root` | `base: Path` | `Path \| None` | Locate the directory holding ``manifest.json`` under ``base``. |
| [cli.py](cli.py#L280) | `_extract_zip_safely` | `archive: zipfile.ZipFile, dest: Path` | `None` | Extract a zip archive, refusing members that escape ``dest``. |
| [cli.py](cli.py#L290) | `_stage_git` | `source: str, staging: Path` | `tuple[Path, str, str]` | Clone a git source via ``subprocess git`` and locate its manifest root. |
| [cli.py](cli.py#L306) | `_stage_source` | `source: str, staging: Path` | `tuple[Path, str, str]` | Fetch the plugin source into ``staging``. |
| [cli.py](cli.py#L341) | `_confirm_permissions` | `name: str, permissions: list[str], yes: bool` | `bool` | Interactive permission confirmation; ``-y`` skips the prompt. |
| [cli.py](cli.py#L355) | `_plugin_dir_on_disk` | `plugin_paths: Any, name: str` | `Path \| None` | Locate an installed plugin in the persistent application directory. |
| [cli.py](cli.py#L361) | `_resolve_plugin` | `registry: Any, value: str` | `dict \| None` | Resolve a plugin record by id or name. |
| [cli.py](cli.py#L369) | `_cmd_plugin` | `args: argparse.Namespace` | `None` | Dispatch the ``plugin`` subcommand. |
| [cli.py](cli.py#L384) | `_cmd_plugin_list` | `None` | `None` | List installed plugins exactly as recorded in plugins.json. |
| [cli.py](cli.py#L399) | `_cmd_plugin_install` | `args: argparse.Namespace` | `None` | Install a plugin from a local directory, a git repository or a zip. |
| [cli.py](cli.py#L475) | `_cmd_plugin_uninstall` | `args: argparse.Namespace` | `None` | Remove the persistent plugin directory and its registry record. |
| [cli.py](cli.py#L493) | `_cmd_plugin_set_enabled` | `args: argparse.Namespace, enabled: bool` | `None` | Flip and persist the enabled flag through the registry. |
| [cli.py](cli.py#L504) | `main` | `argv: list[str] \| None` | `None` | Parse CLI arguments and dispatch the selected Angelus command. |
| [connectors.py](connectors.py#L19) | `_connector_key_paths` | `None` | `tuple[Path, Path]` | Return the per-store RSA private/public key paths. |
| [connectors.py](connectors.py#L24) | `_ensure_connector_keypair` | `None` | `tuple[Path, Path]` | Create a local RSA-OAEP keypair with OS-user-only permissions. |
| [connectors.py](connectors.py#L48) | `_encrypt_connector_key` | `secret: str` | `dict[str, str]` | Encrypt a normal-size API key with the local RSA public key. |
| [connectors.py](connectors.py#L62) | `_decrypt_connector_key` | `payload: Any` | `str` | Decrypt the encrypted connector key only inside the server process. |
| [connectors.py](connectors.py#L78) | `_read_connector_records` | `None` | `list[dict[str, Any]]` | Read encrypted connector records exactly as stored on disk. |
| [connectors.py](connectors.py#L88) | `_read_connectors` | `None` | `list[dict[str, Any]]` | Load and decrypt saved connector records for internal server use. |
| [connectors.py](connectors.py#L103) | `_write_connectors` | `connectors: list[dict[str, Any]]` | `None` | Atomically persist connectors with RSA-OAEP encrypted credentials. |
| [connectors.py](connectors.py#L126) | `_public_connector` | `record: dict[str, Any]` | `dict[str, Any]` | Return browser-safe connector metadata without its credential. |
| [connectors.py](connectors.py#L137) | `_resolve_connector_key` | `config: RunConfig` | `RunConfig` | Resolve a selected connector credential only for the impending run. |
| [context_editing.py](context_editing.py#L76) | `ContextRevision.to_dict` | `None` | `dict[str, Any]` | Return a JSON-compatible revision payload. |
| [context_editing.py](context_editing.py#L85) | `_lock_for` | `path: Path` | `threading.RLock` | Return the process-local lock that serializes one context file. |
| [context_editing.py](context_editing.py#L92) | `_read_json` | `path: Path` | `dict[str, Any]` | Implement `_read_json`. |
| [context_editing.py](context_editing.py#L100) | `_atomic_json` | `path: Path, value: dict[str, Any]` | `None` | Atomically write one JSON record and flush its file contents. |
| [context_editing.py](context_editing.py#L128) | `ContextEditStore._record_ref` | `message: dict[str, Any], ordinal: int` | `ContextRecordRef` | Derive a stable reference from immutable message provenance fields. |
| [context_editing.py](context_editing.py#L139) | `ContextEditStore.inspect` | `None` | `dict[str, Any]` | Return editable records and revision metadata without mutation. |
| [context_editing.py](context_editing.py#L162) | `ContextEditStore.list_revisions` | `None` | `list[dict[str, Any]]` | List immutable revision metadata newest first. |
| [context_editing.py](context_editing.py#L181) | `ContextEditStore._append_audit` | `revision: ContextRevision` | `None` | Append and flush one revision audit event. |
| [context_editing.py](context_editing.py#L197) | `ContextEditStore._write_baseline` | `raw: dict[str, Any]` | `str` | Snapshot an unedited legacy context before its first mutation. |
| [context_editing.py](context_editing.py#L226) | `ContextEditStore.apply` | `expected_revision_id: str \| None, operations: list[ContextEditOperation], actor: str, reason: str` | `dict[str, Any]` | Validate operations, snapshot the result, and atomically activate it. |
| [context_editing.py](context_editing.py#L291) | `ContextEditStore.restore` | `expected_revision_id: str \| None, revision_id: str, actor: str, reason: str` | `dict[str, Any]` | Restore a saved revision as a new forward revision without deleting history. |
| [context_editing.py](context_editing.py#L326) | `create_context_editing_tools` | `store: ContextEditStore, persist_context: Callable[[], None] \| None, reload_context: Callable[[], None] \| None` | `list[Tool]` | Create tools for inspecting, editing, and restoring one Agent context. |
| [context_stats.py](context_stats.py#L40) | `estimate_context_length` | `messages: list[dict[str, Any]], tool_schemas: list[dict[str, Any]] \| None` | `ContextLengthStats` | Estimate the serialized wire length of one provider message payload. |
| [markdown.py](markdown.py#L14) | `render_markdown` | `text: str` | `str` | Convert trusted-to-render model Markdown into safe display HTML. |
| [mcp_tools.py](mcp_tools.py#L28) | `_safe_name_part` | `value: str` | `str` | Implement `_safe_name_part`. |
| [mcp_tools.py](mcp_tools.py#L33) | `_model_dump` | `value: Any` | `Any` | Return SDK Pydantic models as JSON-compatible values. |
| [mcp_tools.py](mcp_tools.py#L54) | `MCPServer.from_config` | `item: dict[str, Any]` | `'MCPServer'` | Implement `MCPServer.from_config`. |
| [mcp_tools.py](mcp_tools.py#L102) | `MCPToolBridge.start` | `None` | `list[Tool]` | Discover remote MCP tools and return native synchronous wrappers. |
| [mcp_tools.py](mcp_tools.py#L117) | `MCPToolBridge.close` | `None` | `None` | Mark wrappers closed; SDK transports already close per operation. |
| [mcp_tools.py](mcp_tools.py#L121) | `MCPToolBridge._handler` | `server_name: str, tool_name: str` | `Any` | Implement `MCPToolBridge._handler`. |
| [mcp_tools.py](mcp_tools.py#L129) | `MCPToolBridge._client` | `server: MCPServer` | `Any` | Implement `MCPToolBridge._client`. |
| [mcp_tools.py](mcp_tools.py#L152) | `MCPToolBridge._discover_all` | `None` | `None` | Implement `MCPToolBridge._discover_all`. |
| [mcp_tools.py](mcp_tools.py#L158) | `MCPToolBridge._discover_tools` | `server: MCPServer, client: Any` | `None` | Implement `MCPToolBridge._discover_tools`. |
| [mcp_tools.py](mcp_tools.py#L180) | `MCPToolBridge._call` | `server_name: str, tool_name: str, arguments: dict[str, Any]` | `dict[str, Any]` | Implement `MCPToolBridge._call`. |
| [mcp_tools.py](mcp_tools.py#L190) | `create_mcp_tools` | `servers: list[dict[str, Any]]` | `tuple[MCPToolBridge, list[Tool]]` | Connect configured MCP servers and expose their remote tools natively. |
| [plugin_bootstrap.py](plugin_bootstrap.py#L21) | `install_bundled_plugins` | `state_root: Path \| None` | `list[str]` | Copy valid bundled plugin folders on first run without overwriting users. |
| [plugin_manifest.py](plugin_manifest.py#L71) | `_add` | `errors: list[dict[str, str]], field: str, message: str` | `None` | Implement `_add`. |
| [plugin_manifest.py](plugin_manifest.py#L75) | `_check_string` | `errors: list[dict[str, str]], data: dict[str, Any], field: str, required: bool, min_len: int \| None, max_len: int \| None, pattern: re.Pattern[str] \| None, label: str \| None` | `Any` | Validate an optional/required string field, returning its value. |
| [plugin_manifest.py](plugin_manifest.py#L105) | `_validate_string_array` | `errors: list[dict[str, str]], data: dict[str, Any], field: str, min_len: int, max_len: int, unique: bool` | `None` | Validate an array of bounded, unique strings (tools / frontend lists). |
| [plugin_manifest.py](plugin_manifest.py#L135) | `_validate_entry_type` | `errors: list[dict[str, str]], data: dict[str, Any]` | `None` | Implement `_validate_entry_type`. |
| [plugin_manifest.py](plugin_manifest.py#L143) | `_validate_permissions` | `errors: list[dict[str, str]], data: dict[str, Any]` | `None` | Validate the permissions array (permission objects with action+scope). |
| [plugin_manifest.py](plugin_manifest.py#L180) | `_validate_frontend` | `errors: list[dict[str, str]], data: dict[str, Any]` | `None` | Implement `_validate_frontend`. |
| [plugin_manifest.py](plugin_manifest.py#L196) | `_validate_dependencies` | `errors: list[dict[str, str]], data: dict[str, Any]` | `None` | Implement `_validate_dependencies`. |
| [plugin_manifest.py](plugin_manifest.py#L210) | `validate_manifest` | `data: Any` | `list[dict[str, str]]` | Validate a parsed manifest against the v1 contract. |
| [plugin_manifest.py](plugin_manifest.py#L249) | `load_manifest` | `path: Path` | `tuple[dict[str, Any] \| None, list[dict[str, str]]]` | Read, parse and validate a ``manifest.json`` file. |
| [plugin_paths.py](plugin_paths.py#L24) | `_default_app_data_root` | `state_root: Path \| None` | `Path` | Return the app-data root that owns the given workspace root. |
| [plugin_paths.py](plugin_paths.py#L40) | `plugin_dir` | `state_root: Path \| None` | `Path` | Return the app-level plugin directory, honoring ``ANGELUS_PLUGIN_DIR``. |
| [plugin_paths.py](plugin_paths.py#L52) | `workspace_plugin_dir` | `state_root: Path \| None` | `Path` | Compatibility alias for :func:`plugin_dir`. |
| [plugin_paths.py](plugin_paths.py#L60) | `global_plugin_dir` | `state_root: Path \| None` | `Path` | Compatibility alias for :func:`plugin_dir`. |
| [plugin_paths.py](plugin_paths.py#L65) | `plugin_dirs` | `state_root: Path \| None` | `tuple[Path, ...]` | Return the sole persistent plugin directory as a one-item tuple. |
| [plugin_paths.py](plugin_paths.py#L70) | `ensure_plugin_dirs` | `state_root: Path \| None` | `Path` | Create and return the persistent application-level plugin directory. |
| [plugin_registry.py](plugin_registry.py#L34) | `_registry_path` | `None` | `Path` | Return the registry file location (overridable in tests). |
| [plugin_registry.py](plugin_registry.py#L39) | `empty_registry` | `None` | `dict[str, Any]` | Return the canonical empty registry document. |
| [plugin_registry.py](plugin_registry.py#L44) | `_read_registry` | `None` | `dict[str, Any]` | Read the registry; a missing or corrupt file yields an empty registry. |
| [plugin_registry.py](plugin_registry.py#L66) | `_write_registry` | `data: dict[str, Any]` | `None` | Atomically persist the registry (``.tmp`` + ``replace()``, mode 0600). |
| [plugin_registry.py](plugin_registry.py#L84) | `list_plugins` | `None` | `list[dict[str, Any]]` | Return the installed plugin records (copy-safe). |
| [plugin_registry.py](plugin_registry.py#L90) | `get_plugin` | `plugin_id: str` | `dict[str, Any] \| None` | Return one plugin record by id, or ``None`` when absent. |
| [plugin_registry.py](plugin_registry.py#L99) | `add_plugin` | `record: dict[str, Any]` | `dict[str, Any]` | Insert a plugin record (replacing an existing record with the same id). |
| [plugin_registry.py](plugin_registry.py#L122) | `update_plugin` | `plugin_id: str, changes: dict[str, Any]` | `dict[str, Any] \| None` | Apply field updates to a plugin record; returns the updated record. |
| [plugin_registry.py](plugin_registry.py#L136) | `remove_plugin` | `plugin_id: str` | `bool` | Remove a plugin record; returns ``True`` when something was removed. |
| [plugin_registry.py](plugin_registry.py#L148) | `set_enabled` | `plugin_id: str, enabled: bool, permissions: list[str] \| None` | `dict[str, Any] \| None` | Flip the ``enabled`` flag and persist it. |
| [plugin_registry.py](plugin_registry.py#L179) | `grant_permissions` | `plugin_id: str, permissions: list[str]` | `dict[str, Any] \| None` | Merge additional ``"action:scope"`` grants into a plugin record. |
| [plugin_registry.py](plugin_registry.py#L194) | `_merge_unique` | `existing: list[str], additions: list[str]` | `list[str]` | Concatenate grant lists preserving order and uniqueness. |
| [provider_adapters.py](provider_adapters.py#L26) | `visible_provider_kinds` | `providers: Iterable[str]` | `tuple[str, ...]` | Return backend providers plus Angelus-owned adapter identifiers. |
| [provider_adapters.py](provider_adapters.py#L31) | `resolve_provider` | `provider: str, api_url: str` | `tuple[str, str]` | Translate a visible provider into its LLMFetcher backend and endpoint. |
| [provider_adapters.py](provider_adapters.py#L45) | `effective_temperature` | `provider: str, temperature: float` | `float` | Return the provider-supported sampling temperature for one request. |
| [provider_adapters.py](provider_adapters.py#L60) | `KimiCodeFetcher.fetch` | `*args: Any, **kwargs: Any` | `Any` | Implement `KimiCodeFetcher.fetch`. |
| [provider_adapters.py](provider_adapters.py#L64) | `KimiCodeFetcher.fetch_stream` | `*args: Any, **kwargs: Any` | `Any` | Implement `KimiCodeFetcher.fetch_stream`. |
| [provider_adapters.py](provider_adapters.py#L69) | `create_fetcher` | `backend: LLMBackendConfig, provider: str` | `LLMFetcher` | Build a fetcher that applies any provider-level request constraints. |
| [runtime.py](runtime.py#L40) | `_event_payload` | `event: ExecutionEvent` | `dict[str, Any]` | Convert library events to JSON values suitable for Server-Sent Events. |
| [runtime.py](runtime.py#L61) | `_redacted_api_url` | `value: str` | `str` | Return an endpoint identity without URL credentials or query secrets. |
| [runtime.py](runtime.py#L74) | `_runtime_profile_snapshot` | `config: RunConfig` | `dict[str, Any]` | Build a credential-free, stable description of one run's semantics. |
| [runtime.py](runtime.py#L117) | `_enable_optional_agent_controls` | `agent: Agent` | `None` | Enable first-party streaming controls without requiring a new Agent ABI. |
| [runtime.py](runtime.py#L131) | `_build_agent` | `config: RunConfig, workspace_id: str, session_id: str, agent_name: str, active: ActiveRun \| None` | `Agent` | Create one session-owned Agent from current UI settings. |
| [runtime.py](runtime.py#L207) | `_mcp_tools` | `config: RunConfig, active: ActiveRun \| None` | `list[Any]` | Open one SDK-backed MCP bridge and share it across every run Agent. |
| [runtime.py](runtime.py#L219) | `_memory_capabilities` | `config: RunConfig, current_session: str` | `dict[str, set[str]]` | Freeze the four explicit session grants for one Agent run. |
| [runtime.py](runtime.py#L235) | `_session_memory_store` | `None` | `SessionMemoryStore` | Create a store whose audit records use the normal durable event log. |
| [runtime.py](runtime.py#L239) | `_publish_plan_change` | `active: ActiveRun \| None, workspace_id: str, session_id: str, agent_name: str, event_type: str, plan: dict[str, Any]` | `None` | Persist and relay one Agent-owned plan mutation to the workbench. |
| [runtime.py](runtime.py#L261) | `_plan_store` | `workspace_id: str, session_id: str, agent_name: str` | `TaskPlanStore` | Return one Agent-owned plan store inside a browser session. |
| [runtime.py](runtime.py#L282) | `_swarm_snapshot_path` | `workspace_id: str, session_id: str` | `Any` | Return the private restart-recovery snapshot path for one Swarm. |
| [runtime.py](runtime.py#L296) | `_worker_tools_for` | `config: RunConfig, workspace_id: str, session_id: str, active: ActiveRun, agent_name: str` | `list[Any]` | Create isolated non-report tools for one dynamically created worker. |
| [runtime.py](runtime.py#L339) | `_bind_worker_context_tools` | `workspace_id: str, session_id: str, agent_name: str, worker: Agent, tools: list[Any]` | `list[Any]` | Attach live-context edit tools after a dynamic worker is constructed. |
| [runtime.py](runtime.py#L366) | `_attach_swarm_runtime_tools` | `swarm: AgentSwarm, coordinator: Agent, config: RunConfig, workspace_id: str, session_id: str, active: ActiveRun` | `None` | Install coordinator tools that create future worker Agents in ``swarm``. |
| [runtime.py](runtime.py#L422) | `_attach_swarm_observer` | `swarm: AgentSwarm, workspace_id: str, session_id: str, active: ActiveRun` | `None` | Persist and stream lifecycle events emitted by a live or restored Swarm. |
| [runtime.py](runtime.py#L452) | `_synchronize_plan_with_swarm_event` | `event: ExecutionEvent, workspace_id: str, session_id: str, active: ActiveRun` | `None` | Project an assignment-bound Swarm lifecycle event into the main plan. |
| [runtime.py](runtime.py#L495) | `_synchronize_context_threshold` | `agents: list[Agent], max_context_threshold: int` | `tuple[str, ...]` | Apply the current browser compaction threshold before one run begins. |
| [runtime.py](runtime.py#L525) | `_synchronize_swarm_context_threshold` | `swarm: AgentSwarm, config: RunConfig` | `tuple[str, ...]` | Synchronize every currently retained Swarm Agent with ``config``. |
| [runtime.py](runtime.py#L546) | `_persist_swarm_snapshot` | `swarm: AgentSwarm, workspace_id: str, session_id: str` | `None` | Write a quiescent, credential-free Swarm recovery snapshot. |
| [runtime.py](runtime.py#L578) | `_restore_swarm` | `config: RunConfig, workspace_id: str, session_id: str, active: ActiveRun` | `AgentSwarm \| None` | Rebuild a completed Swarm graph after a backend process restart. |
| [runtime.py](runtime.py#L638) | `_build_swarm` | `config: RunConfig, workspace_id: str, session_id: str, active: ActiveRun` | `AgentSwarm` | Build a coordinator-led swarm bound to one private session directory. |
| [session_memory.py](session_memory.py#L32) | `_atomic_json` | `path: Path, value: dict[str, Any]` | `None` | Implement `_atomic_json`. |
| [session_memory.py](session_memory.py#L48) | `_read_json` | `path: Path, default: Any` | `Any` | Implement `_read_json`. |
| [session_memory.py](session_memory.py#L55) | `_safe_text` | `value: Any, limit: int` | `str` | Implement `_safe_text`. |
| [session_memory.py](session_memory.py#L66) | `SessionMemoryStore.session_dir` | `session_id: str` | `Path` | Implement `SessionMemoryStore.session_dir`. |
| [session_memory.py](session_memory.py#L73) | `SessionMemoryStore._manifest_path` | `session_id: str, generation: int \| None` | `Path` | Implement `SessionMemoryStore._manifest_path`. |
| [session_memory.py](session_memory.py#L77) | `SessionMemoryStore._collect_evidence` | `session_id: str, artifacts: list[dict[str, Any]]` | `list[dict[str, Any]]` | Collect durable evidence that is available to a session snapshot. |
| [session_memory.py](session_memory.py#L135) | `SessionMemoryStore.snapshot` | `session_id: str` | `dict[str, Any]` | Create a new immutable manifest generation from durable session state. |
| [session_memory.py](session_memory.py#L155) | `SessionMemoryStore.get_manifest` | `session_id: str, generation: int \| None` | `dict[str, Any]` | Implement `SessionMemoryStore.get_manifest`. |
| [session_memory.py](session_memory.py#L167) | `SessionMemoryStore.register_artifact` | `session_id: str, data: bytes, logical_name: str, mime_type: str` | `dict[str, Any]` | Implement `SessionMemoryStore.register_artifact`. |
| [session_memory.py](session_memory.py#L193) | `SessionMemoryStore.cleanup_expired_copies` | `session_id: str, ttl_seconds: int` | `None` | Remove stale run-local copies left by completed or crashed runs. |
| [session_memory.py](session_memory.py#L205) | `SessionMemoryStore.create_handoff` | `source_session: str, handoff: dict[str, Any]` | `dict[str, Any]` | Implement `SessionMemoryStore.create_handoff`. |
| [session_memory.py](session_memory.py#L241) | `SessionMemoryStore.read_handoff` | `session_id: str, handoff_id: str` | `dict[str, Any]` | Implement `SessionMemoryStore.read_handoff`. |
| [session_memory.py](session_memory.py#L246) | `SessionMemoryStore._log` | `session_id: str, data: dict[str, Any]` | `None` | Implement `SessionMemoryStore._log`. |
| [session_memory.py](session_memory.py#L250) | `_read_json_line` | `line: str` | `Any` | Implement `_read_json_line`. |
| [session_memory.py](session_memory.py#L254) | `_contains_forbidden` | `value: Any` | `bool` | Implement `_contains_forbidden`. |
| [session_memory.py](session_memory.py#L261) | `create_session_memory_tools` | `store: SessionMemoryStore, current_session: str, capabilities: dict[str, set[str]], run_id: str` | `list[Tool]` | Build the six explicit retrieval tools for one run with frozen grants. |
| [session_memory.py](session_memory.py#L329) | `_artifact_matches` | `manifest: dict[str, Any], needle: str, session_id: str, store: SessionMemoryStore \| None` | `list[dict[str, Any]]` | Implement `_artifact_matches`. |
| [storage.py](storage.py#L37) | `_default_state_root` | `project_root: Path` | `Path` | Choose the local Workbench state directory for one source checkout. |
| [storage.py](storage.py#L87) | `_safe_id` | `value: str, label: str` | `str` | Validate IDs before using them in a local storage path. |
| [storage.py](storage.py#L93) | `_read_workspaces` | `None` | `list[dict[str, str]]` | Return the session registry, repairing a missing default session. |
| [storage.py](storage.py#L107) | `_write_workspaces` | `workspaces: list[dict[str, str]]` | `None` | Atomically replace the small local workspace registry. |
| [storage.py](storage.py#L113) | `_conversation_path` | `workspace_id: str, session_id: str` | `Path` | Return the authoritative display transcript for one session. |
| [storage.py](storage.py#L126) | `_run_state_path` | `workspace_id: str, session_id: str` | `Path` | Return the durable browser-facing state file for one Agent run. |
| [storage.py](storage.py#L130) | `_write_conversation` | `workspace_id: str, session_id: str, messages: list[dict[str, Any]]` | `None` | Atomically replace a session's canonical browser transcript. |
| [storage.py](storage.py#L140) | `_append_conversation_turn` | `workspace_id: str, session_id: str, turn: dict[str, Any]` | `None` | Append one display turn so refresh never depends on Agent context. |
| [storage.py](storage.py#L162) | `_workspace_exists` | `workspace_id: str` | `bool` | Return whether a workspace is registered locally. |
| [storage.py](storage.py#L166) | `_session_id_from_name` | `name: str, existing: set[str]` | `str` | Build a stable directory-safe session ID from a user display name. |
| [storage.py](storage.py#L188) | `_remove_workspace` | `workspace_id: str` | `None` | Remove a stopped workspace directory and its local registry entry. |
| [storage.py](storage.py#L209) | `_stop_then_remove_workspace` | `workspace_id: str, active_runs: list[ActiveRun]` | `None` | Wait for active work to reach safe stop boundaries before deletion. |
| [storage.py](storage.py#L226) | `_get_session` | `workspace_id: str, session_id: str` | `BrowserSession` | Get or create the in-memory holder for a validated browser session. |
| [storage.py](storage.py#L231) | `_session_path` | `workspace_id: str, session_id: str` | `Path` | Return the private on-disk directory that owns one browser session. |
| [storage.py](storage.py#L251) | `_context_path` | `workspace_id: str, session_id: str, agent_name: str` | `Path` | Return the validated JSON context path for one browser session. |
| [storage.py](storage.py#L274) | `_persist_json` | `path: Path, payload: dict[str, Any]` | `None` | Atomically persist JSON runtime metadata for refresh and restart recovery. |
| [storage.py](storage.py#L288) | `_append_session_event` | `workspace_id: str, session_id: str, payload: dict[str, Any]` | `int` | Append one serialized runtime event to the session's durable trace. |
| [storage.py](storage.py#L312) | `_session_event_log_size` | `workspace_id: str, session_id: str` | `int` | Return the current durable event-log byte length, or zero if absent. |
| [storage.py](storage.py#L328) | `_iter_session_event_log` | `workspace_id: str, session_id: str` | `Any` | Yield valid durable events for one browser session in write order. |
| [storage.py](storage.py#L360) | `_read_session_event_log` | `workspace_id: str, session_id: str` | `list[dict[str, Any]]` | Read valid durable events for one browser session in write order. |
| [storage.py](storage.py#L378) | `_read_session_event_log_from` | `workspace_id: str, session_id: str, offset_bytes: int` | `tuple[list[dict[str, Any]], int]` | Read durable events appended at or after a byte offset. |
| [storage.py](storage.py#L405) | `_read_session_event_records_from` | `workspace_id: str, session_id: str, offset_bytes: int, until_offset: int \| None` | `tuple[list[tuple[dict[str, Any], int]], int]` | Read durable payloads with their end offsets inside a byte range. |
| [storage.py](storage.py#L454) | `_session_event_offset_after` | `workspace_id: str, session_id: str, after: int` | `int` | Return the byte offset just past ``after`` valid durable events. |
| [storage.py](storage.py#L489) | `_session_event_page` | `workspace_id: str, session_id: str, before: int \| None, limit: int` | `dict[str, Any]` | Return a reverse-chronological page from a session's durable trace. |
| [task_planning.py](task_planning.py#L20) | `_lock_for_path` | `path: Path` | `threading.RLock` | Return the process-local lock shared by all stores for one plan path. |
| [task_planning.py](task_planning.py#L47) | `TaskPlanStore.read` | `None` | `dict[str, Any]` | Load the plan or return an empty plan when no file exists. |
| [task_planning.py](task_planning.py#L62) | `TaskPlanStore.replace` | `goal: str, summary: str, tasks: Iterable[Mapping[str, Any]]` | `dict[str, Any]` | Validate and atomically replace the complete task tree. |
| [task_planning.py](task_planning.py#L85) | `TaskPlanStore.update_status` | `task_id: str, status: str` | `dict[str, Any]` | Change one task status and persist the containing plan. |
| [task_planning.py](task_planning.py#L116) | `TaskPlanStore.bind_execution` | `task_id: str, assignment_id: str` | `dict[str, Any]` | Bind one dispatched Swarm assignment to a leaf task. |
| [task_planning.py](task_planning.py#L154) | `TaskPlanStore.is_bindable_leaf` | `task_id: str` | `bool` | Return whether ``task_id`` currently names a coordinator-plan leaf. |
| [task_planning.py](task_planning.py#L160) | `TaskPlanStore.update_execution_status` | `task_id: str, assignment_id: str, status: str` | `dict[str, Any]` | Apply one authoritative Swarm lifecycle state to its bound leaf. |
| [task_planning.py](task_planning.py#L185) | `TaskPlanStore._normalize_tasks` | `values: Iterable[Mapping[str, Any]]` | `list[dict[str, Any]]` | Normalize recursive task input into the persisted public contract. |
| [task_planning.py](task_planning.py#L216) | `TaskPlanStore._assert_unique_ids` | `tasks: list[dict[str, Any]]` | `None` | Reject duplicate task IDs before a plan can be bound to execution. |
| [task_planning.py](task_planning.py#L231) | `TaskPlanStore._find_task` | `tasks: list[dict[str, Any]], task_id: str` | `dict[str, Any] \| None` | Return one task from a recursive plan tree by its stable ID. |
| [task_planning.py](task_planning.py#L242) | `TaskPlanStore._reconcile_parent_statuses` | `tasks: list[dict[str, Any]]` | `None` | Derive every parent state from its direct child states. |
| [task_planning.py](task_planning.py#L263) | `TaskPlanStore._write` | `plan: Mapping[str, Any]` | `None` | Atomically write a normalized task plan to the session path. |
| [task_planning.py](task_planning.py#L271) | `create_task_planning_tools` | `store: TaskPlanStore, on_changed: Callable[[str, dict[str, Any]], None] \| None` | `list[Tool]` | Create Agent tools that let a model publish and supervise a task plan. |
| [webapp.py](webapp.py#L50) | `_assemble_plugins` | `app: FastAPI` | `Any` | Wire the plugin system (swarm S2-S10) onto the console app. |
| [webapp.py](webapp.py#L92) | `main` | `None` | `None` | Run the local console with ``llmfetcher-web``. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [context_editing.py](context_editing.py#L24) | `ContextRecordRef` | `record_id: str, timeline: int, role: str, content_hash: str` | `object` | Stable identity for one editable active-context message. |
| [context_editing.py](context_editing.py#L41) | `ContextEditOperation` | `kind: EditKind, target_record_id: str \| None, content: str, role: str` | `object` | One validated mutation against a stable active-context record. |
| [context_editing.py](context_editing.py#L58) | `ContextRevision` | `revision_id: str, parent_revision_id: str \| None, agent_name: str, created_at: float, actor: str, reason: str, operations: tuple[ContextEditOperation, ...], snapshot_sha256: str, restored_from: str \| None` | `object` | Immutable audit entry and complete snapshot identity for one edit. |
| [context_editing.py](context_editing.py#L81) | `ContextEditError` | `None` | `ValueError` | Safe rejection for invalid edits, stale revisions, or unknown records. |
| [context_editing.py](context_editing.py#L111) | `ContextEditStore` | `path: str \| Path, agent_name: str` | `object` | Own immutable revisions and the active JSON checkpoint for one Agent. |
| [context_stats.py](context_stats.py#L20) | `ContextLengthStats` | `messages: int, characters: int, tool_schemas: int, tool_schema_characters: int, estimated_tokens: int` | `object` | Character and token estimate for one message/tool-schema payload. |
| [mcp_tools.py](mcp_tools.py#L21) | `MCPToolError` | `None` | `RuntimeError` | Raised when MCP configuration, discovery, or invocation fails. |
| [mcp_tools.py](mcp_tools.py#L42) | `MCPServer` | `name: str, transport: str, command: str, args: tuple[str, ...], url: str, env: tuple[str, ...], cwd: str` | `object` | One validated user-selected MCP server definition. |
| [mcp_tools.py](mcp_tools.py#L80) | `MCPToolBridge` | `servers: list[dict[str, Any]]` | `object` | Use a fresh official SDK client context for each discovery or call. |
| [provider_adapters.py](provider_adapters.py#L52) | `KimiCodeFetcher` | `None` | `LLMFetcher` | Force Kimi Code's required temperature across all internal requests. |
| [session_memory.py](session_memory.py#L28) | `SessionMemoryError` | `None` | `ValueError` | A safe, user-facing rejection of a memory operation. |
| [session_memory.py](session_memory.py#L59) | `SessionMemoryStore` | `state_root: Path, event_logger: Callable[[str, dict[str, Any]], None] \| None` | `object` | Own manifests, handoffs, and immutable artifact bytes below one state root. |
| [task_planning.py](task_planning.py#L34) | `TaskPlanStore` | `path: str \| Path` | `object` | Own one session's task-plan JSON file and validate task-tree updates. |

<!-- END GENERATED SYMBOL MAP -->
