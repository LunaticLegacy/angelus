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
| `runtime.py` | Runtime construction | 构建 Agent / Swarm、运行配置快照、按 Agent 隔离的计划与会话记忆存储；所有 Shell 工具以会话绑定的外部项目目录为 `cwd`，而 checkpoint 与事件仍写入内部状态目录；provider 增量通过内存广播，最终回复正常落盘；每轮的上下文阈值先更新内存，并在 Agent 加载旧 checkpoint 后重新应用，直到安全边界才随完整上下文保存；Swarm 在同一进程连续轮次中保留实例，并写入本地恢复快照。 |
| `storage.py` | Durable state | 状态根目录、会话注册表、外部项目目录绑定、事件账本、JSON 持久化与并发保护。 |
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
| `mcp_registry.py` | MCP registry | 全局加密 server 注册表、会话角色/工具授权，以及受控 `${project_root}` 解析。 |
| `plugin_registry.py` | Plugin registry | 原子读写 `plugins.json` 中的安装、启用与授权记录。 |
| `provider_adapters.py` | Provider presets | 将 Kimi Code 等一方预设解析为 LLMFetcher 已支持的后端与默认端点。 |
| `cli.py` | CLI | 本地 `web` / `session` / `plugin` 命令与 llmfetcher 命令委托。 |
| `__init__.py` / `__main__.py` | Package entry | 公共门面与 `python -m angelus` 入口。 |

## Durable State Ownership

`ANGELUS_STATE_DIR` 可指定状态根目录（兼容 `LLMFETCHER_STATE_DIR`）；否则使用本地工作区。每个新会话在 `sessions.json` 中绑定一个用户选择的既有项目目录：Agent 的文件和 Shell 操作发生在该项目中，Angelus 的事件、checkpoint、投影与清单仍保留在内部状态目录。旧会话没有绑定字段时兼容回退到其内部目录，并可在停止状态下重新绑定。连接器与插件注册表在全局范围共享，插件 manifest 保持应用级存放，不复制进用户项目。CLI 的 `--state-dir` 会同时设置两个名称，使插件目录和注册表保持同一应用根。

| Scope | Records |
|---|---|
| Global state root | `sessions.json`（含会话到外部项目目录的绑定）、`connectors.json`、`mcp-servers.json`、RSA 密钥对、`plugins.json` |
| Session directory | `conversation.json`、`events.ndjson`、`run-state.json`、`task-plan.json`、`graph-view.json`、`swarm-runtime.json`、`mcp-bindings.json` |
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
| [cli.py](cli.py#L113) | `_configure_state_root` | `state_dir: str \| None` | `None` | Apply one CLI state root before importing state-owning Angelus modules. |
| [cli.py](cli.py#L133) | `_cmd_web` | `args: argparse.Namespace` | `None` | Run the optional FastAPI browser console. |
| [cli.py](cli.py#L145) | `_cmd_session` | `args: argparse.Namespace` | `None` | Create or list sessions with separated project and state directories. |
| [cli.py](cli.py#L184) | `_plugin_modules` | `None` | `Any` | Import the plugin-system support modules from the registry branch. |
| [cli.py](cli.py#L194) | `_fail` | `message: str` | `None` | Print an error to stderr and exit non-zero. |
| [cli.py](cli.py#L200) | `_is_skipped` | `path: Path, root: Path` | `bool` | True for VCS/cache/private paths that must never enter a plugin install. |
| [cli.py](cli.py#L206) | `_copy_tree` | `src: Path, dst: Path` | `None` | Recursively copy ``src`` into ``dst``, skipping VCS/cache internals. |
| [cli.py](cli.py#L219) | `_canonical_manifest_bytes` | `manifest: dict` | `bytes` | Canonical JSON bytes of the manifest with ``checksum`` excluded. |
| [cli.py](cli.py#L234) | `_resolve_entry_path` | `plugin_dir: Path, manifest: dict` | `Path \| None` | Resolve ``manifest.entry`` to an existing file inside ``plugin_dir``. |
| [cli.py](cli.py#L266) | `_compute_integrity_checksum` | `plugin_dir: Path, manifest: dict` | `str` | Install-time integrity checksum over manifest + entry (S10 contract). |
| [cli.py](cli.py#L282) | `_find_manifest_root` | `base: Path` | `Path \| None` | Locate the directory holding ``manifest.json`` under ``base``. |
| [cli.py](cli.py#L295) | `_extract_zip_safely` | `archive: zipfile.ZipFile, dest: Path` | `None` | Extract a zip archive, refusing members that escape ``dest``. |
| [cli.py](cli.py#L305) | `_stage_git` | `source: str, staging: Path` | `tuple[Path, str, str]` | Clone a git source via ``subprocess git`` and locate its manifest root. |
| [cli.py](cli.py#L321) | `_stage_source` | `source: str, staging: Path` | `tuple[Path, str, str]` | Fetch the plugin source into ``staging``. |
| [cli.py](cli.py#L356) | `_confirm_permissions` | `name: str, permissions: list[str], yes: bool` | `bool` | Interactive permission confirmation; ``-y`` skips the prompt. |
| [cli.py](cli.py#L370) | `_plugin_dir_on_disk` | `plugin_paths: Any, name: str` | `Path \| None` | Locate an installed plugin in the persistent application directory. |
| [cli.py](cli.py#L376) | `_resolve_plugin` | `registry: Any, value: str` | `dict \| None` | Resolve a plugin record by id or name. |
| [cli.py](cli.py#L384) | `_cmd_plugin` | `args: argparse.Namespace` | `None` | Dispatch the ``plugin`` subcommand. |
| [cli.py](cli.py#L399) | `_cmd_plugin_list` | `None` | `None` | List installed plugins exactly as recorded in plugins.json. |
| [cli.py](cli.py#L414) | `_cmd_plugin_install` | `args: argparse.Namespace` | `None` | Install a plugin from a local directory, a git repository or a zip. |
| [cli.py](cli.py#L490) | `_cmd_plugin_uninstall` | `args: argparse.Namespace` | `None` | Remove the persistent plugin directory and its registry record. |
| [cli.py](cli.py#L508) | `_cmd_plugin_set_enabled` | `args: argparse.Namespace, enabled: bool` | `None` | Flip and persist the enabled flag through the registry. |
| [cli.py](cli.py#L519) | `main` | `argv: list[str] \| None` | `None` | Parse CLI arguments and dispatch the selected Angelus command. |
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
| [external_agents.py](external_agents.py#L56) | `ConversionReport.to_dict` | `None` | `dict[str, Any]` | Serialize the report for manifests and API responses. |
| [external_agents.py](external_agents.py#L63) | `_private_write` | `path: Path, payload: Any` | `None` | Atomically write private JSON with owner-only permissions when possible. |
| [external_agents.py](external_agents.py#L80) | `_private_read` | `path: Path` | `list[dict[str, Any]]` | Read a private list registry, treating absent/corrupt data as empty. |
| [external_agents.py](external_agents.py#L89) | `provider_catalog` | `None` | `list[dict[str, Any]]` | Return built-in provider capability declarations and saved status. |
| [external_agents.py](external_agents.py#L121) | `save_provider` | `provider_id: str, payload: dict[str, Any]` | `dict[str, Any]` | Persist non-secret provider connection metadata. |
| [external_agents.py](external_agents.py#L150) | `runtime_provider` | `provider_id: str` | `Any` | Return a runtime adapter with saved, non-secret connection metadata. |
| [external_agents.py](external_agents.py#L184) | `canonicalize_events` | `provider: str, source: Any` | `tuple[list[dict[str, Any]], ConversionReport]` | Convert known transcript shapes into non-executing canonical events. |
| [external_agents.py](external_agents.py#L222) | `_safe_zip_members` | `archive: zipfile.ZipFile` | `list[zipfile.ZipInfo]` | Validate archive paths, link bits, counts, and uncompressed sizes. |
| [external_agents.py](external_agents.py#L241) | `build_archive` | `session_id: str` | `bytes` | Build an Angelus Session Archive v1 without exporting credentials. |
| [external_agents.py](external_agents.py#L271) | `parse_archive` | `data: bytes` | `dict[str, Any]` | Validate and parse a v1 archive entirely in memory. |
| [external_agents.py](external_agents.py#L301) | `read_session_meta` | `session_id: str` | `dict[str, Any]` | Read session provenance, defaulting old sessions to native mode. |
| [external_agents.py](external_agents.py#L311) | `write_session_meta` | `session_id: str, meta: dict[str, Any]` | `None` | Persist the additive source metadata for a newly imported/linked session. |
| [external_agents.py](external_agents.py#L316) | `import_events` | `name: str, project_path: str, provider: str, events: list[dict[str, Any]], report: ConversionReport, source_id: str` | `dict[str, Any]` | Create a new Angelus session and project canonical external events. |
| [external_agents.py](external_agents.py#L351) | `lease_link` | `link_id: str, client_instance_id: str, requested_token: str \| None` | `dict[str, Any]` | Acquire or heartbeat an exclusive 60-second external-control lease. |
| [external_providers/base.py](external_providers/base.py#L64) | `ExternalSession.to_dict` | `None` | `dict[str, Any]` | Serialize the descriptor for API responses and link persistence. |
| [external_providers/base.py](external_providers/base.py#L89) | `ExternalEvent.to_dict` | `None` | `dict[str, Any]` | Serialize the canonical public projection without raw event data. |
| [external_providers/base.py](external_providers/base.py#L108) | `ExternalAgentProvider.capabilities` | `None` | `set[ProviderCapability]` | Return actions genuinely supported by the current runtime. |
| [external_providers/base.py](external_providers/base.py#L112) | `ExternalAgentProvider.available` | `None` | `bool` | Return whether the optional local SDK/command/endpoint is usable. |
| [external_providers/base.py](external_providers/base.py#L116) | `ExternalAgentProvider.discover` | `project_path: str \| None` | `list[ExternalSession]` | Discover externally readable sessions without mutating vendor state. |
| [external_providers/base.py](external_providers/base.py#L120) | `ExternalAgentProvider.read` | `session_id: str` | `ExternalSession` | Read one external session metadata snapshot without attaching control. |
| [external_providers/base.py](external_providers/base.py#L123) | `ExternalAgentProvider.start` | `prompt: str, project_path: str, model: str \| None` | `ExternalSession` | Start an Angelus-owned external session or raise unsupported. |
| [external_providers/base.py](external_providers/base.py#L127) | `ExternalAgentProvider.resume` | `session_id: str, prompt: str` | `ExternalSession` | Continue an Angelus-owned session or raise unsupported. |
| [external_providers/base.py](external_providers/base.py#L131) | `ExternalAgentProvider.fork` | `session_id: str` | `ExternalSession` | Fork a provider session without replaying its historical tool calls. |
| [external_providers/base.py](external_providers/base.py#L135) | `ExternalAgentProvider.send` | `session_id: str, message: str` | `None` | Send a user turn to a session after the caller validates its lease. |
| [external_providers/base.py](external_providers/base.py#L139) | `ExternalAgentProvider.steer` | `session_id: str, message: str` | `None` | Deliver a provider-native steer instruction without command passthrough. |
| [external_providers/base.py](external_providers/base.py#L143) | `ExternalAgentProvider.interrupt` | `session_id: str` | `None` | Interrupt only provider work that is safe for this adapter to target. |
| [external_providers/base.py](external_providers/base.py#L147) | `ExternalAgentProvider.subscribe` | `session_id: str, cursor: str \| None` | `Iterator[ExternalEvent]` | Yield post-cursor canonical events; implementations reconnect reads only. |
| [external_providers/base.py](external_providers/base.py#L151) | `ExternalAgentProvider.diff` | `session_id: str` | `dict[str, Any]` | Return the provider's display-safe diff snapshot when supported. |
| [external_providers/base.py](external_providers/base.py#L155) | `ExternalAgentProvider.respond_approval` | `session_id: str, approval_id: str, decision: str` | `None` | Submit an allow/deny approval response after Angelus audit handling. |
| [external_providers/claude_code.py](external_providers/claude_code.py#L34) | `_content_text` | `content: Any` | `str` | Extract display text from a Claude message or content-block collection. |
| [external_providers/claude_code.py](external_providers/claude_code.py#L95) | `ClaudeCodeProvider._load_sdk` | `None` | `Any \| None` | Best-effort import the optional Claude Agent SDK without startup failure. |
| [external_providers/claude_code.py](external_providers/claude_code.py#L104) | `ClaudeCodeProvider.capabilities` | `None` | `set[ProviderCapability]` | Return fixed capabilities; controls are restricted to owned sessions. |
| [external_providers/claude_code.py](external_providers/claude_code.py#L113) | `ClaudeCodeProvider.available` | `None` | `bool` | Return whether the optional SDK or configured Claude CLI is usable. |
| [external_providers/claude_code.py](external_providers/claude_code.py#L117) | `ClaudeCodeProvider.discover` | `project_path: str \| None` | `list[ExternalSession]` | Discover local completed transcripts without opening or controlling them. |
| [external_providers/claude_code.py](external_providers/claude_code.py#L138) | `ClaudeCodeProvider.read` | `session_id: str` | `ExternalSession` | Read an owned or on-disk session without attaching to outside work. |
| [external_providers/claude_code.py](external_providers/claude_code.py#L159) | `ClaudeCodeProvider.start` | `prompt: str, project_path: str, model: str \| None` | `ExternalSession` | Start one Angelus-owned stream-json Claude Code session. |
| [external_providers/claude_code.py](external_providers/claude_code.py#L182) | `ClaudeCodeProvider.resume` | `session_id: str, prompt: str` | `ExternalSession` | Send another turn only to a live Angelus-owned Claude process. |
| [external_providers/claude_code.py](external_providers/claude_code.py#L195) | `ClaudeCodeProvider.fork` | `session_id: str` | `ExternalSession` | Create an owned fork via Claude's official resume/fork flags. |
| [external_providers/claude_code.py](external_providers/claude_code.py#L213) | `ClaudeCodeProvider.send` | `session_id: str, message: str` | `None` | Write one fixed user message to an owned CLI stream. |
| [external_providers/claude_code.py](external_providers/claude_code.py#L226) | `ClaudeCodeProvider.interrupt` | `session_id: str` | `None` | Terminate only an Angelus-owned Claude child process. |
| [external_providers/claude_code.py](external_providers/claude_code.py#L240) | `ClaudeCodeProvider.respond_approval` | `session_id: str, approval_id: str, decision: str` | `None` | Submit an allow/deny response to a pending owned stream request. |
| [external_providers/claude_code.py](external_providers/claude_code.py#L254) | `ClaudeCodeProvider.subscribe` | `session_id: str, cursor: str \| None` | `Iterator[ExternalEvent]` | Yield queued canonical events for a local owned session. |
| [external_providers/claude_code.py](external_providers/claude_code.py#L274) | `ClaudeCodeProvider._launch` | `prompt: str, directory: Path, model: str \| None, resume_id: str \| None, fork: bool` | `ExternalSession` | Spawn a CLI child, register ownership before I/O, then send first input. |
| [external_providers/claude_code.py](external_providers/claude_code.py#L302) | `ClaudeCodeProvider._owned_process` | `session_id: str` | `Any` | Return a live owned child or fail closed for discovered external sessions. |
| [external_providers/claude_code.py](external_providers/claude_code.py#L310) | `ClaudeCodeProvider._owned_session` | `session_id: str` | `ExternalSession` | Return an owned descriptor after applying the same ownership boundary. |
| [external_providers/claude_code.py](external_providers/claude_code.py#L317) | `ClaudeCodeProvider._write_stream_json` | `process: Any, payload: dict[str, Any]` | `None` | Write one JSON line to a child stdin without exposing a command channel. |
| [external_providers/claude_code.py](external_providers/claude_code.py#L328) | `ClaudeCodeProvider._read_stdout` | `session_id: str, process: Any` | `None` | Read JSONL output once and enqueue canonical events without write retries. |
| [external_providers/claude_code.py](external_providers/claude_code.py#L341) | `ClaudeCodeProvider._read_stderr` | `session_id: str, process: Any` | `None` | Convert Claude stderr lines into canonical diagnostics without leaking inputs. |
| [external_providers/claude_code.py](external_providers/claude_code.py#L351) | `ClaudeCodeProvider._queue_event` | `session_id: str, raw: dict[str, Any]` | `None` | Normalize one Claude output notification and update authoritative IDs safely. |
| [external_providers/claude_code.py](external_providers/claude_code.py#L363) | `ClaudeCodeProvider._adopt_session_id` | `temporary_id: str, session_id: str` | `None` | Alias a temporary ID while preserving its process and queued event ownership. |
| [external_providers/claude_code.py](external_providers/claude_code.py#L382) | `ClaudeCodeProvider._canonical_event` | `session_id: str, raw: dict[str, Any]` | `ExternalEvent` | Translate stream-json output to one credential-free canonical event. |
| [external_providers/claude_code.py](external_providers/claude_code.py#L421) | `ClaudeCodeProvider._transcript_session` | `transcript: Path` | `ExternalSession \| None` | Read a small transcript header/tail to construct one read-only descriptor. |
| [external_providers/codex.py](external_providers/codex.py#L121) | `CodexAppServerClient.running` | `None` | `bool` | Whether the owned child exists and has not exited. |
| [external_providers/codex.py](external_providers/codex.py#L126) | `CodexAppServerClient.stderr` | `None` | `tuple[str, ...]` | Return captured stderr lines for diagnostics without exposing stdout. |
| [external_providers/codex.py](external_providers/codex.py#L131) | `CodexAppServerClient.protocol_diagnostics` | `None` | `tuple[str, ...]` | Return malformed stdout-frame diagnostics observed by the reader. |
| [external_providers/codex.py](external_providers/codex.py#L135) | `CodexAppServerClient.add_disconnect_handler` | `handler: Callable[[BaseException \| None], Any]` | `None` | Register a callback invoked once after the child stream disconnects. |
| [external_providers/codex.py](external_providers/codex.py#L144) | `CodexAppServerClient.start` | `None` | `None` | Launch the configured App Server and begin consuming both output streams. |
| [external_providers/codex.py](external_providers/codex.py#L177) | `CodexAppServerClient.restart` | `None` | `None` | Explicitly replace the App Server process without replaying requests. |
| [external_providers/codex.py](external_providers/codex.py#L183) | `CodexAppServerClient.stop` | `None` | `None` | Close streams, fail pending callers, and terminate the owned child. |
| [external_providers/codex.py](external_providers/codex.py#L209) | `CodexAppServerClient.request` | `method: str, params: Mapping[str, Any] \| None, timeout: float \| None` | `Any` | Send one JSON-RPC request and await its matching result. |
| [external_providers/codex.py](external_providers/codex.py#L243) | `CodexAppServerClient.initialize` | `None` | `Any` | Complete Codex's one-time startup handshake before normal RPCs. |
| [external_providers/codex.py](external_providers/codex.py#L271) | `CodexAppServerClient.notify` | `method: str, params: Mapping[str, Any] \| None` | `None` | Send a notification without creating a retryable request Future. |
| [external_providers/codex.py](external_providers/codex.py#L281) | `CodexAppServerClient.next_notification` | `None` | `JSON` | Wait for the next raw notification received from Codex. |
| [external_providers/codex.py](external_providers/codex.py#L285) | `CodexAppServerClient._write` | `payload: JSON` | `None` | Serialize one complete newline-delimited JSON-RPC frame to stdin. |
| [external_providers/codex.py](external_providers/codex.py#L298) | `CodexAppServerClient._read_stdout` | `None` | `None` | Read newline-delimited stdout frames and dispatch JSON-RPC messages. |
| [external_providers/codex.py](external_providers/codex.py#L322) | `CodexAppServerClient._stdout_closed_error` | `None` | `CodexAppServerError` | Describe a terminal stdout close without exposing raw child stderr. |
| [external_providers/codex.py](external_providers/codex.py#L350) | `CodexAppServerClient._read_stderr` | `None` | `None` | Capture bounded diagnostic stderr without treating it as protocol data. |
| [external_providers/codex.py](external_providers/codex.py#L358) | `CodexAppServerClient._dispatch` | `message: JSON` | `None` | Resolve responses or route notifications and server-originated requests. |
| [external_providers/codex.py](external_providers/codex.py#L383) | `CodexAppServerClient._handle_server_request` | `message: JSON` | `None` | Answer a server request, converting handler failures into RPC errors. |
| [external_providers/codex.py](external_providers/codex.py#L397) | `CodexAppServerClient._fail_pending` | `error: BaseException` | `None` | Fail all unresolved callers after a transport-level terminal condition. |
| [external_providers/codex.py](external_providers/codex.py#L403) | `CodexAppServerClient._notify_disconnect` | `failure: BaseException \| None` | `None` | Invoke disconnect hooks while isolating one faulty hook from the rest. |
| [external_providers/codex.py](external_providers/codex.py#L438) | `CodexAsyncAppServerProvider.probe` | `None` | `JSON` | Start Codex and complete its non-mutating initialization handshake. |
| [external_providers/codex.py](external_providers/codex.py#L446) | `CodexAsyncAppServerProvider.discover` | `cursor: str \| None, limit: int` | `Any` | List Codex threads without modifying their history. |
| [external_providers/codex.py](external_providers/codex.py#L455) | `CodexAsyncAppServerProvider.read` | `external_session_id: str` | `Any` | Read one Codex thread by its opaque external id. |
| [external_providers/codex.py](external_providers/codex.py#L463) | `CodexAsyncAppServerProvider.start` | `cwd: str \| None, model: str \| None` | `Any` | Create a new Codex thread with optional public workspace/model hints. |
| [external_providers/codex.py](external_providers/codex.py#L467) | `CodexAsyncAppServerProvider.resume` | `external_session_id: str` | `Any` | Resume a previously created Codex thread when the App Server supports it. |
| [external_providers/codex.py](external_providers/codex.py#L471) | `CodexAsyncAppServerProvider.fork` | `external_session_id: str` | `Any` | Fork a Codex thread, preserving Codex's native provenance semantics. |
| [external_providers/codex.py](external_providers/codex.py#L475) | `CodexAsyncAppServerProvider.send` | `external_session_id: str, text: str, cwd: str \| None` | `Any` | Start a new turn with one text input; historical tools are never replayed. |
| [external_providers/codex.py](external_providers/codex.py#L479) | `CodexAsyncAppServerProvider.steer` | `external_session_id: str, turn_id: str, text: str` | `Any` | Steer a running turn using Codex's official turn control method. |
| [external_providers/codex.py](external_providers/codex.py#L483) | `CodexAsyncAppServerProvider.interrupt` | `external_session_id: str, turn_id: str` | `Any` | Request interruption of only the named Codex turn. |
| [external_providers/codex.py](external_providers/codex.py#L487) | `CodexAsyncAppServerProvider.diff` | `external_session_id: str` | `Any` | Retrieve the App Server diff view for a Codex thread. |
| [external_providers/codex.py](external_providers/codex.py#L491) | `CodexAsyncAppServerProvider.usage` | `external_session_id: str` | `Any` | Retrieve usage metadata when exposed by the negotiated App Server. |
| [external_providers/codex.py](external_providers/codex.py#L495) | `CodexAsyncAppServerProvider.approval` | `request_id: str, decision: str` | `Any` | Respond to a pending approval with an allow or deny decision. |
| [external_providers/codex.py](external_providers/codex.py#L506) | `CodexAsyncAppServerProvider.next_event` | `None` | `JSON` | Wait for the next canonicalized external event emitted by Codex. |
| [external_providers/codex.py](external_providers/codex.py#L510) | `CodexAsyncAppServerProvider.close` | `None` | `None` | Release the App Server process owned by this provider. |
| [external_providers/codex.py](external_providers/codex.py#L514) | `CodexAsyncAppServerProvider._on_notification` | `method: str, params: JSON` | `None` | Normalize an App Server notification while preserving vendor payload losslessly. |
| [external_providers/codex.py](external_providers/codex.py#L547) | `CodexAppServerRuntime.call` | `coroutine_factory: Callable[[CodexAppServerClient], Awaitable[Any]]` | `Any` | Run one client coroutine on the private event loop and return its result. |
| [external_providers/codex.py](external_providers/codex.py#L567) | `CodexAppServerRuntime.close` | `None` | `None` | Stop the owned child and private event loop; repeated calls are harmless. |
| [external_providers/codex.py](external_providers/codex.py#L585) | `CodexAppServerRuntime._ensure_loop` | `None` | `None` | Start the runtime thread exactly once before submitting a coroutine. |
| [external_providers/codex.py](external_providers/codex.py#L600) | `CodexAppServerRuntime._raise_bootstrap_error` | `None` | `None` | Re-raise a failed child launch/initialize as a provider-neutral error. |
| [external_providers/codex.py](external_providers/codex.py#L607) | `CodexAppServerRuntime._thread_main` | `None` | `None` | Own the event loop, launch the child, and negotiate the handshake. |
| [external_providers/codex.py](external_providers/codex.py#L629) | `CodexAppServerRuntime._bootstrap` | `None` | `None` | Launch the App Server child and complete the initialize handshake. |
| [external_providers/codex.py](external_providers/codex.py#L647) | `CodexAppServerRuntime._receive_notification` | `method: str, params: JSON` | `None` | Translate a transport notification into a bounded provider-contract event. |
| [external_providers/codex.py](external_providers/codex.py#L689) | `CodexAppServerProvider.capabilities` | `None` | `set[ProviderCapability]` | Return the fixed action set available through the Codex App Server. |
| [external_providers/codex.py](external_providers/codex.py#L693) | `CodexAppServerProvider.available` | `None` | `bool` | Return whether the configured local Codex executable can be launched. |
| [external_providers/codex.py](external_providers/codex.py#L698) | `CodexAppServerProvider.probe` | `None` | `dict[str, Any]` | Launch Codex and verify the ordered App Server handshake. |
| [external_providers/codex.py](external_providers/codex.py#L710) | `CodexAppServerProvider.discover` | `project_path: str \| None` | `list[ExternalSession]` | Discover readable Codex threads, optionally filtering by public project path. |
| [external_providers/codex.py](external_providers/codex.py#L720) | `CodexAppServerProvider.read` | `session_id: str` | `ExternalSession` | Read one Codex thread metadata snapshot without starting a turn. |
| [external_providers/codex.py](external_providers/codex.py#L728) | `CodexAppServerProvider.start` | `prompt: str, project_path: str, model: str \| None` | `ExternalSession` | Create an Angelus-owned Codex thread then send the initial user prompt. |
| [external_providers/codex.py](external_providers/codex.py#L741) | `CodexAppServerProvider.resume` | `session_id: str, prompt: str` | `ExternalSession` | Resume a Codex thread and submit one new user turn. |
| [external_providers/codex.py](external_providers/codex.py#L752) | `CodexAppServerProvider.fork` | `session_id: str` | `ExternalSession` | Fork a native Codex thread without re-executing historical work. |
| [external_providers/codex.py](external_providers/codex.py#L760) | `CodexAppServerProvider.send` | `session_id: str, message: str` | `None` | Start a turn containing exactly one text input. |
| [external_providers/codex.py](external_providers/codex.py#L772) | `CodexAppServerProvider.steer` | `session_id: str, message: str` | `None` | Steer the latest Angelus-observed active turn for a Codex thread. |
| [external_providers/codex.py](external_providers/codex.py#L787) | `CodexAppServerProvider.interrupt` | `session_id: str` | `None` | Interrupt the latest Angelus-observed active turn for a Codex thread. |
| [external_providers/codex.py](external_providers/codex.py#L799) | `CodexAppServerProvider.subscribe` | `session_id: str, cursor: str \| None` | `Any` | Yield future canonical events for ``session_id`` without replaying actions. |
| [external_providers/codex.py](external_providers/codex.py#L816) | `CodexAppServerProvider.diff` | `session_id: str` | `dict[str, Any]` | Return Codex's display-safe diff response for one thread. |
| [external_providers/codex.py](external_providers/codex.py#L824) | `CodexAppServerProvider.usage` | `session_id: str` | `dict[str, Any]` | Return public Codex token/usage data when the App Server exposes it. |
| [external_providers/codex.py](external_providers/codex.py#L832) | `CodexAppServerProvider.respond_approval` | `session_id: str, approval_id: str, decision: str` | `None` | Return a lease/audit-validated allow or deny approval decision. |
| [external_providers/codex.py](external_providers/codex.py#L844) | `CodexAppServerProvider.close` | `None` | `None` | Release the owned App Server runtime during registry/application shutdown. |
| [external_providers/codex.py](external_providers/codex.py#L848) | `CodexAppServerProvider._rpc` | `method: str, params: JSON` | `Any` | Run a fixed RPC method and preserve non-retry semantics for writes. |
| [external_providers/codex.py](external_providers/codex.py#L853) | `_records` | `value: Any` | `list[JSON]` | Extract thread records from common App Server list response envelopes. |
| [external_providers/codex.py](external_providers/codex.py#L865) | `_session_from_codex` | `record: JSON, fallback_id: str` | `ExternalSession` | Normalize a Codex thread response to the shared safe session descriptor. |
| [external_providers/codex.py](external_providers/codex.py#L875) | `_object` | `value: Any` | `JSON` | Return a shallow JSON object or an empty object for malformed params. |
| [external_providers/codex.py](external_providers/codex.py#L880) | `_without_none` | `value: Mapping[str, Any]` | `JSON` | Copy only non-``None`` parameters so optional values are not serialized as null. |
| [external_providers/codex.py](external_providers/codex.py#L885) | `_required_id` | `value: str` | `str` | Validate an opaque non-empty provider id before embedding it in an RPC object. |
| [external_providers/codex.py](external_providers/codex.py#L892) | `_required_text` | `value: str` | `str` | Validate a non-empty user-authored message without transforming its contents. |
| [external_providers/codex.py](external_providers/codex.py#L899) | `_limit` | `value: int` | `int` | Clamp a thread discovery page size to prevent unbounded provider responses. |
| [external_providers/codex.py](external_providers/codex.py#L906) | `_canonical_event_name` | `method: str, params: JSON` | `str` | Map known Codex notification categories to canonical external event names. |
| [external_providers/opencode.py](external_providers/opencode.py#L76) | `OpenCodeProvider.capabilities` | `None` | `set[ProviderCapability]` | Return only actions represented by documented OpenCode server APIs. |
| [external_providers/opencode.py](external_providers/opencode.py#L83) | `OpenCodeProvider.available` | `None` | `bool` | Probe the documented health endpoint without changing server state. |
| [external_providers/opencode.py](external_providers/opencode.py#L91) | `OpenCodeProvider.discover` | `project_path: str \| None` | `list[ExternalSession]` | List OpenCode sessions, enriching them with the status snapshot. |
| [external_providers/opencode.py](external_providers/opencode.py#L111) | `OpenCodeProvider.read` | `session_id: str` | `ExternalSession` | Read one OpenCode session metadata snapshot. |
| [external_providers/opencode.py](external_providers/opencode.py#L125) | `OpenCodeProvider.start` | `prompt: str, project_path: str, model: str \| None` | `ExternalSession` | Create an OpenCode session then deliver its first prompt asynchronously. |
| [external_providers/opencode.py](external_providers/opencode.py#L150) | `OpenCodeProvider.resume` | `session_id: str, prompt: str` | `ExternalSession` | Deliver a new prompt then return the current session descriptor. |
| [external_providers/opencode.py](external_providers/opencode.py#L155) | `OpenCodeProvider.fork` | `session_id: str` | `ExternalSession` | Fork a session at OpenCode's current message without replaying tools. |
| [external_providers/opencode.py](external_providers/opencode.py#L162) | `OpenCodeProvider.send` | `session_id: str, message: str` | `None` | Queue one user text part through OpenCode's asynchronous prompt API. |
| [external_providers/opencode.py](external_providers/opencode.py#L167) | `OpenCodeProvider.interrupt` | `session_id: str` | `None` | Request OpenCode's documented abort operation for one session. |
| [external_providers/opencode.py](external_providers/opencode.py#L171) | `OpenCodeProvider.diff` | `session_id: str` | `dict[str, Any]` | Return the current display-safe file-diff list for one session. |
| [external_providers/opencode.py](external_providers/opencode.py#L178) | `OpenCodeProvider.revert` | `session_id: str, message_id: str, part_id: str \| None` | `None` | Revert a named OpenCode message or part through the fixed API. |
| [external_providers/opencode.py](external_providers/opencode.py#L191) | `OpenCodeProvider.unrevert` | `session_id: str` | `None` | Restore OpenCode's reverted messages for one session. |
| [external_providers/opencode.py](external_providers/opencode.py#L195) | `OpenCodeProvider.respond_approval` | `session_id: str, approval_id: str, decision: str` | `None` | Map Angelus' fixed approval decisions to OpenCode permission choices. |
| [external_providers/opencode.py](external_providers/opencode.py#L208) | `OpenCodeProvider.subscribe` | `session_id: str, cursor: str \| None` | `Iterator[ExternalEvent]` | Observe OpenCode's global SSE bus with cursor reconnect and dedupe. |
| [external_providers/opencode.py](external_providers/opencode.py#L243) | `OpenCodeProvider._prompt_async` | `session_id: str, message: str, model: str \| None` | `None` | Build the documented text-part prompt shape and submit it once. |
| [external_providers/opencode.py](external_providers/opencode.py#L251) | `OpenCodeProvider._request_json` | `method: str, path: str, payload: dict[str, Any] \| None` | `Any` | Perform one bounded JSON request and translate transport errors safely. |
| [external_providers/opencode.py](external_providers/opencode.py#L273) | `OpenCodeProvider._sse_events` | `cursor: str \| None` | `Iterator[tuple[str, str, dict[str, Any]]]` | Parse one SSE response into ``(event, id, JSON payload)`` tuples. |
| [external_providers/opencode.py](external_providers/opencode.py#L305) | `OpenCodeProvider._iter_lines` | `response: Any` | `Iterator[bytes]` | Yield response lines and close a real HTTP response after iteration. |
| [external_providers/opencode.py](external_providers/opencode.py#L316) | `OpenCodeProvider._read_response` | `response: Any` | `bytes` | Read and close an urllib-style response without leaking sockets. |
| [external_providers/opencode.py](external_providers/opencode.py#L326) | `OpenCodeProvider._canonical_event` | `event_name: str, event_id: str, payload: dict[str, Any]` | `ExternalEvent \| None` | Project one OpenCode bus event while retaining sanitized raw context. |
| [external_providers/opencode.py](external_providers/opencode.py#L352) | `OpenCodeProvider._event_session_id` | `value: dict[str, Any]` | `str \| None` | Extract common OpenCode session-id field spellings from one payload. |
| [external_providers/opencode.py](external_providers/opencode.py#L360) | `OpenCodeProvider._session_from_payload` | `value: dict[str, Any], statuses: dict[str, Any]` | `ExternalSession` | Translate an OpenCode session record without exposing secret fields. |
| [external_providers/opencode.py](external_providers/opencode.py#L372) | `OpenCodeProvider._project_path` | `value: Any` | `str \| None` | Read a publicly exposed OpenCode project directory from a mapping. |
| [external_providers/opencode.py](external_providers/opencode.py#L382) | `OpenCodeProvider._url` | `path: str` | `str` | Join a fixed absolute API path to the validated endpoint root. |
| [external_providers/opencode.py](external_providers/opencode.py#L386) | `OpenCodeProvider._auth_headers` | `None` | `dict[str, str]` | Produce in-memory Basic-auth headers only when both fields exist. |
| [external_providers/opencode.py](external_providers/opencode.py#L394) | `OpenCodeProvider._validate_endpoint` | `endpoint: str, username: str \| None, password: str \| None, allow_remote: bool` | `str` | Enforce loopback-by-default and explicit authenticated remote access. |
| [external_providers/opencode.py](external_providers/opencode.py#L405) | `OpenCodeProvider._redact` | `value: Any` | `Any` | Remove credential-looking fields recursively before public/raw retention. |
| [external_providers/opencode.py](external_providers/opencode.py#L415) | `OpenCodeProvider._path_id` | `value: str` | `str` | Validate and URL-escape an opaque vendor ID as exactly one segment. |
| [external_providers/opencode.py](external_providers/opencode.py#L420) | `OpenCodeProvider._require_text` | `value: str, name: str` | `str` | Reject empty control fields before they cross the provider boundary. |
| [external_providers/opencode.py](external_providers/opencode.py#L428) | `OpenCodeProvider._title_for_prompt` | `prompt: str` | `str` | Create a bounded provider-side title without exposing extra content. |
| [external_providers/registry.py](external_providers/registry.py#L17) | `ExternalProviderRegistry.register` | `provider: ExternalAgentProvider` | `None` | Register one unique built-in provider instance. |
| [external_providers/registry.py](external_providers/registry.py#L30) | `ExternalProviderRegistry.get` | `provider_id: str` | `ExternalAgentProvider \| None` | Return one adapter by ID, or ``None`` when it is not registered. |
| [external_providers/registry.py](external_providers/registry.py#L34) | `ExternalProviderRegistry.public_catalog` | `None` | `list[dict[str, Any]]` | Return runtime-safe provider capability and availability records. |
| [external_providers/registry.py](external_providers/registry.py#L44) | `bootstrap_builtin_providers` | `None` | `ExternalProviderRegistry` | Register built-in adapters without launching their optional runtimes. |
| [markdown.py](markdown.py#L14) | `render_markdown` | `text: str` | `str` | Convert trusted-to-render model Markdown into safe display HTML. |
| [mcp_registry.py](mcp_registry.py#L22) | `_encrypt_secret` | `value: str` | `dict[str, Any]` | Envelope long UTF-8 secrets into RSA-safe encrypted chunks. |
| [mcp_registry.py](mcp_registry.py#L32) | `_decrypt_secret` | `payload: Any` | `str` | Decrypt a chunked secret while retaining old single-RSA compatibility. |
| [mcp_registry.py](mcp_registry.py#L46) | `_read_json` | `path: Path, default: Any` | `Any` | Read JSON from ``path`` and return ``default`` on invalid input. |
| [mcp_registry.py](mcp_registry.py#L59) | `_write_json` | `path: Path, payload: Any` | `None` | Atomically persist one private registry payload with mode 0600. |
| [mcp_registry.py](mcp_registry.py#L76) | `_validate_template_boundaries` | `payload: dict[str, Any]` | `None` | Reject project-root expansion outside controlled stdio args/cwd. |
| [mcp_registry.py](mcp_registry.py#L102) | `_normalize_server` | `payload: dict[str, Any], existing_id: str` | `dict[str, Any]` | Validate and normalize a global MCP server record. |
| [mcp_registry.py](mcp_registry.py#L160) | `_stored_server` | `record: dict[str, Any]` | `dict[str, Any]` | Encrypt every configured credential in one registry record. |
| [mcp_registry.py](mcp_registry.py#L174) | `_loaded_server` | `stored: dict[str, Any]` | `dict[str, Any]` | Decrypt one record for server-side connection use. |
| [mcp_registry.py](mcp_registry.py#L190) | `read_servers` | `None` | `list[dict[str, Any]]` | Return all decrypted MCP records for internal server use. |
| [mcp_registry.py](mcp_registry.py#L196) | `write_servers` | `records: list[dict[str, Any]]` | `None` | Replace the global MCP registry with encrypted records. |
| [mcp_registry.py](mcp_registry.py#L205) | `public_server` | `record: dict[str, Any]` | `dict[str, Any]` | Return browser-safe metadata and credential-presence flags. |
| [mcp_registry.py](mcp_registry.py#L219) | `binding_path` | `session_id: str` | `Path` | Return the app-state path for one session's MCP grants. |
| [mcp_registry.py](mcp_registry.py#L224) | `read_bindings` | `session_id: str` | `list[dict[str, Any]]` | Return normalized MCP grants for ``session_id``. |
| [mcp_registry.py](mcp_registry.py#L231) | `write_bindings` | `session_id: str, bindings: list[dict[str, Any]]` | `None` | Validate and persist server/role/tool grants for one session. |
| [mcp_registry.py](mcp_registry.py#L250) | `resolve_session_servers` | `session_id: str, project_root: Path` | `list[dict[str, Any]]` | Resolve authorized registry records for one run and project root. |
| [mcp_tools.py](mcp_tools.py#L32) | `_safe_name_part` | `value: str` | `str` | Implement `_safe_name_part`. |
| [mcp_tools.py](mcp_tools.py#L37) | `_model_dump` | `value: Any` | `Any` | Return SDK Pydantic models as JSON-compatible values. |
| [mcp_tools.py](mcp_tools.py#L59) | `MCPServer.from_config` | `item: dict[str, Any]` | `'MCPServer'` | Validate one decrypted registry or compatibility server mapping. |
| [mcp_tools.py](mcp_tools.py#L162) | `MCPToolBridge._approval_agent` | `server: str` | `str` | Return the sole active caller for a server, or coordinator fallback. |
| [mcp_tools.py](mcp_tools.py#L168) | `MCPToolBridge._emit` | `kind: str, server: str, data: Any` | `None` | Forward credential-free MCP runtime metadata to the host Trace. |
| [mcp_tools.py](mcp_tools.py#L176) | `MCPToolBridge._run_loop` | `None` | `None` | Own the asyncio loop used by all run-scoped MCP transports. |
| [mcp_tools.py](mcp_tools.py#L181) | `MCPToolBridge.start` | `None` | `list[Tool]` | Discover remote MCP tools and return native synchronous wrappers. |
| [mcp_tools.py](mcp_tools.py#L194) | `MCPToolBridge.tools_for` | `agent: str, allowed: set[str] \| None` | `list[Tool]` | Create wrappers attributed to one Agent and optional allowlist. |
| [mcp_tools.py](mcp_tools.py#L213) | `MCPToolBridge.close` | `None` | `None` | Close every persistent transport and stop the owning event loop. |
| [mcp_tools.py](mcp_tools.py#L231) | `MCPToolBridge.cancel_agent` | `agent: str` | `int` | Cancel in-flight MCP calls attributed to one Agent. |
| [mcp_tools.py](mcp_tools.py#L246) | `MCPToolBridge._handler` | `server_name: str, tool_name: str, agent: str` | `Any` | Build a synchronous tool handler attributed to ``agent``. |
| [mcp_tools.py](mcp_tools.py#L264) | `MCPToolBridge._open_client` | `server: MCPServer` | `Any` | Open and retain one SDK client inside the run cleanup stack. |
| [mcp_tools.py](mcp_tools.py#L350) | `MCPToolBridge._ensure_client` | `server: MCPServer` | `Any` | Return a live client, asking the stack-owning task to reconnect. |
| [mcp_tools.py](mcp_tools.py#L363) | `MCPToolBridge._own_connections` | `None` | `None` | Open and close task-bound SDK transports in the same asyncio task. |
| [mcp_tools.py](mcp_tools.py#L405) | `MCPToolBridge._discover_all` | `None` | `None` | Open each configured server once and replace the tool cache. |
| [mcp_tools.py](mcp_tools.py#L412) | `MCPToolBridge._discover_tools` | `server: MCPServer, client: Any` | `None` | Page through one live client's tools into the public-name cache. |
| [mcp_tools.py](mcp_tools.py#L446) | `MCPToolBridge.capability_snapshot` | `None` | `dict[str, Any]` | Discover tools, resources, templates, and prompts on live clients. |
| [mcp_tools.py](mcp_tools.py#L454) | `MCPToolBridge.read_resource` | `server_name: str, uri: str` | `Any` | Read one MCP resource through the persistent server connection. |
| [mcp_tools.py](mcp_tools.py#L458) | `MCPToolBridge.subscribe_resource` | `server_name: str, uri: str` | `Any` | Subscribe to one resource; later notifications enter Trace. |
| [mcp_tools.py](mcp_tools.py#L462) | `MCPToolBridge.get_prompt` | `server_name: str, name: str, arguments: dict[str, str] \| None` | `Any` | Get one MCP prompt using the persistent server connection. |
| [mcp_tools.py](mcp_tools.py#L466) | `MCPToolBridge.complete` | `server_name: str, reference: Any, argument: dict[str, str], context_arguments: dict[str, str] \| None` | `Any` | Request MCP completion for a prompt or resource template reference. |
| [mcp_tools.py](mcp_tools.py#L473) | `MCPToolBridge._submit_client_method` | `server_name: str, method: str, *args: Any` | `Any` | Run one non-tool MCP capability call on the owning event loop. |
| [mcp_tools.py](mcp_tools.py#L480) | `MCPToolBridge._client_method` | `server_name: str, method: str, *args: Any` | `Any` | Invoke a named SDK client method without automatic replay. |
| [mcp_tools.py](mcp_tools.py#L489) | `MCPToolBridge._capability_snapshot_async` | `None` | `dict[str, Any]` | Collect JSON-safe full discovery data from every live server. |
| [mcp_tools.py](mcp_tools.py#L511) | `MCPToolBridge._call` | `server_name: str, tool_name: str, arguments: dict[str, Any], agent: str` | `dict[str, Any]` | Invoke one tool once, discarding a stale client after failure. |
| [mcp_tools.py](mcp_tools.py#L555) | `create_mcp_tools` | `servers: list[dict[str, Any]], approval_handler: Any \| None, sampling_handler: Any \| None, event_handler: Any \| None` | `tuple[MCPToolBridge, list[Tool]]` | Connect configured servers and expose remote tools natively. |
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
| [runtime.py](runtime.py#L41) | `_event_payload` | `event: ExecutionEvent` | `dict[str, Any]` | Convert library events to JSON values suitable for Server-Sent Events. |
| [runtime.py](runtime.py#L62) | `_redacted_api_url` | `value: str` | `str` | Return an endpoint identity without URL credentials or query secrets. |
| [runtime.py](runtime.py#L75) | `_runtime_profile_snapshot` | `config: RunConfig, mcp_servers: list[dict[str, Any]] \| None` | `dict[str, Any]` | Build a credential-free, stable description of one run's semantics. |
| [runtime.py](runtime.py#L120) | `_enable_optional_agent_controls` | `agent: Agent` | `None` | Enable first-party streaming controls without requiring a new Agent ABI. |
| [runtime.py](runtime.py#L134) | `_build_agent` | `config: RunConfig, workspace_id: str, session_id: str, agent_name: str, active: ActiveRun \| None` | `Agent` | Create one session-owned Agent from current UI settings. |
| [runtime.py](runtime.py#L242) | `_build_http_worker_agent` | `coordinator: Agent, workspace_id: str, session_id: str, active: ActiveRun, agent_name: str, system_prompt: str` | `Agent` | Create one browser-added graph worker from the live coordinator. |
| [runtime.py](runtime.py#L316) | `_worker_memory_capabilities` | `current_session: str` | `dict[str, set[str]]` | Return the default memory grants for a browser-added graph worker. |
| [runtime.py](runtime.py#L331) | `_mcp_tools` | `active: ActiveRun \| None, agent_name: str` | `list[Any]` | Return registry-authorized MCP tools for one run Agent. |
| [runtime.py](runtime.py#L368) | `_memory_capabilities` | `config: RunConfig, current_session: str` | `dict[str, set[str]]` | Freeze the four explicit session grants for one Agent run. |
| [runtime.py](runtime.py#L384) | `_session_memory_store` | `None` | `SessionMemoryStore` | Create a store whose audit records use the normal durable event log. |
| [runtime.py](runtime.py#L388) | `_publish_plan_change` | `active: ActiveRun \| None, workspace_id: str, session_id: str, agent_name: str, event_type: str, plan: dict[str, Any]` | `None` | Persist and relay one Agent-owned plan mutation to the workbench. |
| [runtime.py](runtime.py#L410) | `_plan_store` | `workspace_id: str, session_id: str, agent_name: str` | `TaskPlanStore` | Return one Agent-owned plan store inside a browser session. |
| [runtime.py](runtime.py#L431) | `_swarm_snapshot_path` | `workspace_id: str, session_id: str` | `Any` | Return the private restart-recovery snapshot path for one Swarm. |
| [runtime.py](runtime.py#L445) | `_worker_tools_for` | `config: RunConfig, workspace_id: str, session_id: str, active: ActiveRun, agent_name: str` | `list[Any]` | Create isolated non-report tools for one dynamically created worker. |
| [runtime.py](runtime.py#L488) | `_bind_worker_context_tools` | `workspace_id: str, session_id: str, agent_name: str, worker: Agent, tools: list[Any]` | `list[Any]` | Attach live-context edit tools after a dynamic worker is constructed. |
| [runtime.py](runtime.py#L515) | `_attach_swarm_runtime_tools` | `swarm: AgentSwarm, coordinator: Agent, config: RunConfig, workspace_id: str, session_id: str, active: ActiveRun` | `None` | Install coordinator tools that create future worker Agents in ``swarm``. |
| [runtime.py](runtime.py#L571) | `_attach_swarm_observer` | `swarm: AgentSwarm, workspace_id: str, session_id: str, active: ActiveRun` | `None` | Persist and stream lifecycle events emitted by a live or restored Swarm. |
| [runtime.py](runtime.py#L601) | `_synchronize_plan_with_swarm_event` | `event: ExecutionEvent, workspace_id: str, session_id: str, active: ActiveRun` | `None` | Project an assignment-bound Swarm lifecycle event into the main plan. |
| [runtime.py](runtime.py#L644) | `_synchronize_context_threshold` | `agents: list[Agent], max_context_threshold: int` | `tuple[str, ...]` | Apply the current browser compaction threshold before one run begins. |
| [runtime.py](runtime.py#L674) | `_synchronize_swarm_context_threshold` | `swarm: AgentSwarm, config: RunConfig` | `tuple[str, ...]` | Synchronize every currently retained Swarm Agent with ``config``. |
| [runtime.py](runtime.py#L695) | `_persist_swarm_snapshot` | `swarm: AgentSwarm, workspace_id: str, session_id: str` | `None` | Write a quiescent, credential-free Swarm recovery snapshot. |
| [runtime.py](runtime.py#L727) | `_restore_swarm` | `config: RunConfig, workspace_id: str, session_id: str, active: ActiveRun` | `AgentSwarm \| None` | Rebuild a completed Swarm graph after a backend process restart. |
| [runtime.py](runtime.py#L787) | `_build_swarm` | `config: RunConfig, workspace_id: str, session_id: str, active: ActiveRun` | `AgentSwarm` | Build a coordinator-led swarm bound to one private session directory. |
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
| [storage.py](storage.py#L112) | `_write_workspaces` | `workspaces: list[dict[str, str]]` | `None` | Atomically replace the small local workspace registry. |
| [storage.py](storage.py#L126) | `_conversation_path` | `workspace_id: str, session_id: str` | `Path` | Return the authoritative display transcript for one session. |
| [storage.py](storage.py#L139) | `_run_state_path` | `workspace_id: str, session_id: str` | `Path` | Return the durable browser-facing state file for one Agent run. |
| [storage.py](storage.py#L143) | `_write_conversation` | `workspace_id: str, session_id: str, messages: list[dict[str, Any]]` | `None` | Atomically replace a session's canonical browser transcript. |
| [storage.py](storage.py#L153) | `_append_conversation_turn` | `workspace_id: str, session_id: str, turn: dict[str, Any]` | `None` | Append one display turn so refresh never depends on Agent context. |
| [storage.py](storage.py#L175) | `_workspace_exists` | `workspace_id: str` | `bool` | Return whether a workspace is registered locally. |
| [storage.py](storage.py#L180) | `_validate_project_path` | `value: str` | `Path` | Validate and canonicalize one user-selected project directory. |
| [storage.py](storage.py#L207) | `_project_path` | `workspace_id: str, session_id: str` | `Path` | Return the user-project root bound to one browser session. |
| [storage.py](storage.py#L233) | `_session_id_from_name` | `name: str, existing: set[str]` | `str` | Build a stable directory-safe session ID from a user display name. |
| [storage.py](storage.py#L255) | `_remove_workspace` | `workspace_id: str` | `None` | Remove a stopped workspace directory and its local registry entry. |
| [storage.py](storage.py#L276) | `_stop_then_remove_workspace` | `workspace_id: str, active_runs: list[ActiveRun]` | `None` | Wait for active work to reach safe stop boundaries before deletion. |
| [storage.py](storage.py#L293) | `_get_session` | `workspace_id: str, session_id: str` | `BrowserSession` | Get or create the in-memory holder for a validated browser session. |
| [storage.py](storage.py#L298) | `_session_path` | `workspace_id: str, session_id: str` | `Path` | Return the private on-disk directory that owns one browser session. |
| [storage.py](storage.py#L318) | `_context_path` | `workspace_id: str, session_id: str, agent_name: str` | `Path` | Return the validated JSON context path for one browser session. |
| [storage.py](storage.py#L341) | `_persist_json` | `path: Path, payload: dict[str, Any]` | `None` | Atomically persist JSON runtime metadata for refresh and restart recovery. |
| [storage.py](storage.py#L355) | `_append_session_event` | `workspace_id: str, session_id: str, payload: dict[str, Any]` | `int` | Append one serialized runtime event to the session's durable trace. |
| [storage.py](storage.py#L379) | `_session_event_log_size` | `workspace_id: str, session_id: str` | `int` | Return the current durable event-log byte length, or zero if absent. |
| [storage.py](storage.py#L395) | `_iter_session_event_log` | `workspace_id: str, session_id: str` | `Any` | Yield valid durable events for one browser session in write order. |
| [storage.py](storage.py#L427) | `_read_session_event_log` | `workspace_id: str, session_id: str` | `list[dict[str, Any]]` | Read valid durable events for one browser session in write order. |
| [storage.py](storage.py#L445) | `_read_session_event_log_from` | `workspace_id: str, session_id: str, offset_bytes: int` | `tuple[list[dict[str, Any]], int]` | Read durable events appended at or after a byte offset. |
| [storage.py](storage.py#L472) | `_read_session_event_records_from` | `workspace_id: str, session_id: str, offset_bytes: int, until_offset: int \| None` | `tuple[list[tuple[dict[str, Any], int]], int]` | Read durable payloads with their end offsets inside a byte range. |
| [storage.py](storage.py#L521) | `_session_event_offset_after` | `workspace_id: str, session_id: str, after: int` | `int` | Return the byte offset just past ``after`` valid durable events. |
| [storage.py](storage.py#L556) | `_read_previous_line` | `handle: Any, position: int, chunk_size: int` | `tuple[int, bytes] \| None` | Read the complete binary line immediately before a byte boundary. |
| [storage.py](storage.py#L589) | `_last_complete_line_offset` | `path: Path` | `int` | Return the byte boundary after the last newline-terminated record. |
| [storage.py](storage.py#L613) | `_session_event_page` | `workspace_id: str, session_id: str, cursor: str \| None, before: int \| None, limit: int` | `dict[str, Any]` | Return a reverse-chronological page from a session's durable trace. |
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
| [webapp.py](webapp.py#L51) | `_assemble_plugins` | `app: FastAPI` | `Any` | Wire the plugin system (swarm S2-S10) onto the console app. |
| [webapp.py](webapp.py#L93) | `main` | `None` | `None` | Run the local console with ``llmfetcher-web``. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [context_editing.py](context_editing.py#L24) | `ContextRecordRef` | `record_id: str, timeline: int, role: str, content_hash: str` | `object` | Stable identity for one editable active-context message. |
| [context_editing.py](context_editing.py#L41) | `ContextEditOperation` | `kind: EditKind, target_record_id: str \| None, content: str, role: str` | `object` | One validated mutation against a stable active-context record. |
| [context_editing.py](context_editing.py#L58) | `ContextRevision` | `revision_id: str, parent_revision_id: str \| None, agent_name: str, created_at: float, actor: str, reason: str, operations: tuple[ContextEditOperation, ...], snapshot_sha256: str, restored_from: str \| None` | `object` | Immutable audit entry and complete snapshot identity for one edit. |
| [context_editing.py](context_editing.py#L81) | `ContextEditError` | `None` | `ValueError` | Safe rejection for invalid edits, stale revisions, or unknown records. |
| [context_editing.py](context_editing.py#L111) | `ContextEditStore` | `path: str \| Path, agent_name: str` | `object` | Own immutable revisions and the active JSON checkpoint for one Agent. |
| [context_stats.py](context_stats.py#L20) | `ContextLengthStats` | `messages: int, characters: int, tool_schemas: int, tool_schema_characters: int, estimated_tokens: int` | `object` | Character and token estimate for one message/tool-schema payload. |
| [external_agents.py](external_agents.py#L37) | `ConversionReport` | `source_provider: str, target_provider: str \| None, preserved: list[str], degraded: list[str], omitted: list[str], summary_used: bool` | `object` | Describe fidelity and omissions for an import or transfer. |
| [external_providers/base.py](external_providers/base.py#L11) | `ProviderCapability` | `None` | `StrEnum` | Fixed user-visible actions supported by an external provider. |
| [external_providers/base.py](external_providers/base.py#L29) | `ProviderError` | `message: str, retryable: bool, code: str` | `RuntimeError` | Stable adapter error safe to expose as an HTTP failure detail. |
| [external_providers/base.py](external_providers/base.py#L45) | `ExternalSession` | `id: str, provider: str, title: str, status: str, project_path: str \| None, metadata: dict[str, Any]` | `object` | Safe external session descriptor returned by discovery/read operations. |
| [external_providers/base.py](external_providers/base.py#L70) | `ExternalEvent` | `type: str, provider: str, session_id: str, event_id: str, data: dict[str, Any], raw: dict[str, Any]` | `object` | Canonical event emitted by a provider subscription. |
| [external_providers/base.py](external_providers/base.py#L95) | `ExternalAgentProvider` | `id: str, label: str` | `ABC` | Private contract implemented by built-in vendor adapters. |
| [external_providers/claude_code.py](external_providers/claude_code.py#L54) | `ClaudeCodeProvider` | `command: str, history_root: Path \| str \| None, popen_factory: Callable[..., Any], sdk: Any \| None` | `ExternalAgentProvider` | Connect Angelus-owned Claude Code CLI processes and inspect transcripts. |
| [external_providers/codex.py](external_providers/codex.py#L39) | `CodexAppServerError` | `None` | `RuntimeError` | Base error raised for an unavailable or invalid Codex App Server. |
| [external_providers/codex.py](external_providers/codex.py#L43) | `CodexProtocolError` | `message: str, code: int \| None, data: Any` | `CodexAppServerError` | Raised when the server returns a JSON-RPC error or malformed response. |
| [external_providers/codex.py](external_providers/codex.py#L60) | `CodexAppServerConfig` | `command: tuple[str, ...], cwd: str \| None, environment: Mapping[str, str], request_timeout: float, terminate_timeout: float` | `object` | Configuration for a locally launched Codex App Server. |
| [external_providers/codex.py](external_providers/codex.py#L79) | `CodexAppServerClient` | `config: CodexAppServerConfig \| None, notification_handler: NotificationHandler \| None, server_request_handler: ServerRequestHandler \| None` | `object` | Own one App Server child and multiplex JSON-RPC requests over stdio. |
| [external_providers/codex.py](external_providers/codex.py#L414) | `CodexAsyncAppServerProvider` | `client: CodexAppServerClient \| None` | `object` | Provider-contract façade over :class:`CodexAppServerClient`. |
| [external_providers/codex.py](external_providers/codex.py#L523) | `CodexAppServerRuntime` | `config: CodexAppServerConfig \| None` | `object` | Run one asynchronous App Server client on a private long-lived thread. |
| [external_providers/codex.py](external_providers/codex.py#L665) | `CodexAppServerProvider` | `config: CodexAppServerConfig \| None, runtime: CodexAppServerRuntime \| None` | `ExternalAgentProvider` | Synchronous registry adapter for the Codex App Server stdio runtime. |
| [external_providers/opencode.py](external_providers/opencode.py#L28) | `OpenCodeProvider` | `endpoint: str, username: str \| None, password: str \| None, allow_remote: bool, timeout: float, opener: Callable[..., Any], sleep: Callable[[float], None], reconnect_attempts: int \| None` | `ExternalAgentProvider` | Run fixed OpenCode Server operations over HTTP and its global SSE bus. |
| [external_providers/registry.py](external_providers/registry.py#L10) | `ExternalProviderRegistry` | `None` | `object` | Own provider instances and isolate unavailable optional dependencies. |
| [mcp_tools.py](mcp_tools.py#L25) | `MCPToolError` | `None` | `RuntimeError` | Raised when MCP configuration, discovery, or invocation fails. |
| [mcp_tools.py](mcp_tools.py#L46) | `MCPServer` | `name: str, transport: str, command: str, args: tuple[str, ...], url: str, env: tuple[tuple[str, str], ...], cwd: str, headers: tuple[tuple[str, str], ...]` | `object` | One validated user-selected MCP server definition. |
| [mcp_tools.py](mcp_tools.py#L108) | `MCPToolBridge` | `servers: list[dict[str, Any]], approval_handler: Any \| None, sampling_handler: Any \| None, event_handler: Any \| None` | `object` | Keep one official SDK connection per server for the lifetime of a run. |
| [provider_adapters.py](provider_adapters.py#L52) | `KimiCodeFetcher` | `None` | `LLMFetcher` | Force Kimi Code's required temperature across all internal requests. |
| [session_memory.py](session_memory.py#L28) | `SessionMemoryError` | `None` | `ValueError` | A safe, user-facing rejection of a memory operation. |
| [session_memory.py](session_memory.py#L59) | `SessionMemoryStore` | `state_root: Path, event_logger: Callable[[str, dict[str, Any]], None] \| None` | `object` | Own manifests, handoffs, and immutable artifact bytes below one state root. |
| [task_planning.py](task_planning.py#L34) | `TaskPlanStore` | `path: str \| Path` | `object` | Own one session's task-plan JSON file and validate task-tree updates. |

<!-- END GENERATED SYMBOL MAP -->
