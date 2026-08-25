# angelus/plugins/ — Plugin Runtime INDEX

Angelus 的插件运行时：发现与 `workspace/` 并列的持久插件目录，在受控 setup 阶段收集扩展，并将工具、路由、钩子和连接器安全地桥接到宿主。插件契约见 [`../../docs/plugin-api.md`](../../docs/plugin-api.md)。

## Route Map — Leaf Files

| File | Responsibility |
|---|---|
| `__init__.py` | 稳定公共导出：运行时、基类、事件白名单和注册记录。 |
| `base.py` | `AngelusPlugin`、`PluginRuntime`、注册 API 与事件/HTTP 方法白名单。 |
| `manager.py` | 应用级目录发现、命名空间导入、加载/卸载/重载、状态机与注册发布。 |
| `autoreload.py` | 开发期文件指纹轮询与去抖重载协调；生产模式不启动观察线程。 |
| `security.py` | 权限门禁、安装负载 SHA-256 完整性校验与安全日志。 |
| `bridge_tools.py` | 将插件工具转换并注入 Agent 工具链。 |
| `bridge_hooks.py` | 将插件钩子映射到 `llmfetcher` 的执行事件总线。 |
| `bridge_routes.py` | 挂载插件 API、受白名单约束的静态资源、最小公开查询，以及状态/非敏感设置和经确认的运行时加载/卸载端点。 |
| `bridge_connectors.py` | 将插件注册的连接器类型合并至连接器发现流程。 |

## Boundaries

- 清单校验、目录解析与持久化注册表分别在上一级的 `plugin_manifest.py`、`plugin_paths.py` 和 `plugin_registry.py`。
- 插件只有在注册表启用、完整性校验通过且 setup 成功后才会发布扩展。
- 插件路由固定在 `/plugins/<name>/api`，静态资源只能访问清单列出的文件。

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [autoreload.py](autoreload.py#L48) | `_enabled` | `None` | `bool` | True when ``ANGELUS_PLUGIN_AUTORELOAD`` requests background watching. |
| [autoreload.py](autoreload.py#L79) | `PluginAutoReloader.running` | `None` | `bool` | Implement `PluginAutoReloader.running`. |
| [autoreload.py](autoreload.py#L82) | `PluginAutoReloader.start` | `None` | `'PluginAutoReloader'` | Start the daemon polling thread (idempotent). |
| [autoreload.py](autoreload.py#L95) | `PluginAutoReloader.stop` | `timeout: float` | `None` | Signal the thread to stop and join it (idempotent). |
| [autoreload.py](autoreload.py#L103) | `PluginAutoReloader._run` | `None` | `None` | Implement `PluginAutoReloader._run`. |
| [autoreload.py](autoreload.py#L112) | `start_plugin_autoreload` | `rescan: Callable[[], Any], interval: float, logger: logging.Logger \| None` | `PluginAutoReloader \| None` | Start the watcher when ``ANGELUS_PLUGIN_AUTORELOAD`` is enabled. |
| [base.py](base.py#L95) | `PluginRuntime._begin_setup` | `None` | `None` | Enter the setup phase: the only phase where register_* works. |
| [base.py](base.py#L99) | `PluginRuntime._commit` | `None` | `dict[str, list[dict[str, Any]]]` | Finalize a successful setup and return the collected registrations. |
| [base.py](base.py#L116) | `PluginRuntime._abort` | `None` | `None` | Discard every collected registration after a failed setup. |
| [base.py](base.py#L124) | `PluginRuntime._shutdown` | `None` | `None` | Mark the runtime torn down (idempotent teardown bookkeeping). |
| [base.py](base.py#L132) | `PluginRuntime._ensure_setup` | `None` | `None` | Implement `PluginRuntime._ensure_setup`. |
| [base.py](base.py#L142) | `PluginRuntime.register_tool` | `name: str, schema: dict, handler: Callable` | `None` | Register a plugin tool. |
| [base.py](base.py#L167) | `PluginRuntime.register_route` | `method: str, path: str, handler: Callable` | `None` | Register a plugin route, mounted under ``/plugins/<name>/api``. |
| [base.py](base.py#L186) | `PluginRuntime.register_hook` | `event: str, handler: Callable, priority: int` | `None` | Subscribe to an agent event from the whitelist. |
| [base.py](base.py#L209) | `PluginRuntime.register_connector` | `kind: str, factory: Callable` | `None` | Register a connector provider factory (read-only path). |
| [base.py](base.py#L228) | `PluginRuntime.__repr__` | `None` | `str` | Implement `PluginRuntime.__repr__`. |
| [base.py](base.py#L246) | `AngelusPlugin.setup` | `runtime: PluginRuntime` | `None` | Called once when the plugin is loaded (inside the setup phase). |
| [base.py](base.py#L252) | `AngelusPlugin.teardown` | `None` | `None` | Release resources. Must be idempotent (may be called multiple times); the manager guards against exceptions either way. |
| [bridge_connectors.py](bridge_connectors.py#L73) | `_builtin_provider_kinds` | `None` | `tuple[str, ...]` | Provider kinds reported by the pinned ``llmfetcher`` library. |
| [bridge_connectors.py](bridge_connectors.py#L85) | `_registrations` | `manager: Any` | `dict[str, Any]` | Duck-typed access to the manager's live connector registration table. |
| [bridge_connectors.py](bridge_connectors.py#L107) | `_registration_factory` | `registration: Any` | `Optional[Callable]` | Extract the callable factory from a registration record. |
| [bridge_connectors.py](bridge_connectors.py#L121) | `get_plugin_provider_kinds` | `manager: Any` | `tuple[str, ...]` | Sorted, de-duplicated provider kinds registered by plugins. |
| [bridge_connectors.py](bridge_connectors.py#L132) | `plugin_connector_factories` | `manager: Any` | `dict[str, Callable]` | Mapping ``kind -> factory`` for all plugin connector providers. |
| [bridge_connectors.py](bridge_connectors.py#L152) | `aggregate_providers` | `manager: Any, builtin: Iterable[str] \| None` | `tuple[str, ...]` | Providers visible to ``GET /api/providers``. |
| [bridge_connectors.py](bridge_connectors.py#L174) | `resolve_connector_factory` | `kind: str, manager: Any` | `Optional[Callable]` | Look up the plugin factory registered for a provider ``kind``. |
| [bridge_connectors.py](bridge_connectors.py#L192) | `create_plugin_connector` | `kind: str, manager: Any, **kwargs: Any` | `Any` | Instantiate a plugin connector via its registered factory. |
| [bridge_hooks.py](bridge_hooks.py#L109) | `validate_event_name` | `event: str` | `str` | Return ``event`` if it is whitelisted, else raise ``ValueError``. |
| [bridge_hooks.py](bridge_hooks.py#L161) | `PluginHookBridge.attached` | `None` | `bool` | True when the dispatcher is registered on the host bus. |
| [bridge_hooks.py](bridge_hooks.py#L165) | `PluginHookBridge.attach` | `host: Any` | `None` | Register the dispatcher with the host's ``add_hook``. |
| [bridge_hooks.py](bridge_hooks.py#L191) | `PluginHookBridge.detach` | `None` | `None` | Stop dispatching bus events (idempotent). |
| [bridge_hooks.py](bridge_hooks.py#L215) | `PluginHookBridge._dispatch` | `event: Any` | `None` | ``ExecutionHook`` entry point: route one bus event to plugins. |
| [bridge_hooks.py](bridge_hooks.py#L224) | `PluginHookBridge._invoke` | `dot_event: str, event: Any` | `None` | Run every registration for one whitelisted dot event, isolating each handler so one failure never affects the others nor the caller. |
| [bridge_hooks.py](bridge_hooks.py#L247) | `PluginHookBridge._registrations_for` | `event: str` | `list[HookRegistrationLike]` | HookRegistration list for one event, priority-descending. |
| [bridge_hooks.py](bridge_hooks.py#L270) | `PluginHookBridge.notify` | `event: str, source: str, agent_name: str, message: str, data: Any` | `Any` | Synthesize and dispatch a whitelisted event the bus does not emit. |
| [bridge_hooks.py](bridge_hooks.py#L307) | `attach_plugin_hooks` | `manager: Any, host: Any, logger: Optional[logging.Logger]` | `PluginHookBridge` | Create a :class:`PluginHookBridge` for ``manager`` and attach it. |
| [bridge_routes.py](bridge_routes.py#L79) | `_http_methods` | `None` | `frozenset[str]` | Canonical HTTP verb whitelist (``angelus.plugins.base.HTTP_METHODS``). |
| [bridge_routes.py](bridge_routes.py#L88) | `_is_active` | `record: Any` | `bool` | True when the manager record is loaded (state == PluginState.ACTIVE). |
| [bridge_routes.py](bridge_routes.py#L101) | `_settings_are_safe` | `value: Any, depth: int` | `bool` | Accept bounded JSON settings while rejecting credential-shaped keys. |
| [bridge_routes.py](bridge_routes.py#L138) | `_EmptyRegistry.list_plugins` | `None` | `list[dict[str, Any]]` | Implement `_EmptyRegistry.list_plugins`. |
| [bridge_routes.py](bridge_routes.py#L141) | `_EmptyRegistry.get_plugin` | `plugin_id: str` | `dict[str, Any] \| None` | Implement `_EmptyRegistry.get_plugin`. |
| [bridge_routes.py](bridge_routes.py#L145) | `_resolve_registry` | `registry: Any \| None` | `Any` | Implement `_resolve_registry`. |
| [bridge_routes.py](bridge_routes.py#L176) | `PluginBridge.mount` | `app: FastAPI` | `None` | Attach the plugin REST/static surface to ``app``. |
| [bridge_routes.py](bridge_routes.py#L209) | `PluginBridge._registry_by_name` | `None` | `dict[str, dict[str, Any]]` | Implement `PluginBridge._registry_by_name`. |
| [bridge_routes.py](bridge_routes.py#L216) | `PluginBridge._loadable` | `None` | `Iterator[tuple[Any, dict[str, Any]]]` | ``(manager record, registry item)`` for enabled+active plugins. |
| [bridge_routes.py](bridge_routes.py#L228) | `PluginBridge._public_entry` | `item: dict[str, Any]` | `dict[str, Any]` | Copy exactly the appendix-D list fields (no manifest/credentials). |
| [bridge_routes.py](bridge_routes.py#L232) | `PluginBridge._list_plugins` | `None` | `dict[str, Any]` | Implement `PluginBridge._list_plugins`. |
| [bridge_routes.py](bridge_routes.py#L237) | `PluginBridge._get_plugin` | `plugin_id: str` | `dict[str, Any]` | Implement `PluginBridge._get_plugin`. |
| [bridge_routes.py](bridge_routes.py#L248) | `PluginBridge._plugin_status` | `None` | `dict[str, Any]` | Return the complete discovered-plugin status for the settings UI. |
| [bridge_routes.py](bridge_routes.py#L263) | `PluginBridge.rescan` | `None` | `dict[str, Any]` | Re-scan the plugin directories and reconcile live plugins. |
| [bridge_routes.py](bridge_routes.py#L286) | `PluginBridge._rescan_plugins` | `None` | `dict[str, Any]` | HTTP handler for ``POST /api/plugins/rescan``. |
| [bridge_routes.py](bridge_routes.py#L295) | `PluginBridge._requested_permissions` | `manifest: dict[str, Any]` | `list[str]` | Return canonical manifest permissions without importing plugin code. |
| [bridge_routes.py](bridge_routes.py#L304) | `PluginBridge._status_entry` | `record: Any, item: dict[str, Any]` | `dict[str, Any]` | Non-secret lifecycle metadata for the local management surface. |
| [bridge_routes.py](bridge_routes.py#L328) | `PluginBridge._management_record` | `plugin_id: str` | `tuple[Any, dict[str, Any]]` | Resolve a discovered, registry-installed plugin for lifecycle control. |
| [bridge_routes.py](bridge_routes.py#L340) | `PluginBridge._register_discovered_plugin` | `name: str, payload: dict[str, Any]` | `dict[str, Any]` | Add one already-discovered local plugin to the local registry. |
| [bridge_routes.py](bridge_routes.py#L381) | `PluginBridge._load_plugin` | `plugin_id: str, payload: dict[str, Any]` | `dict[str, Any]` | Confirm, optionally grant declared permissions, then load one plugin. |
| [bridge_routes.py](bridge_routes.py#L419) | `PluginBridge._unload_plugin` | `plugin_id: str, payload: dict[str, Any]` | `dict[str, Any]` | Confirm and tear down a plugin without deleting its installed files. |
| [bridge_routes.py](bridge_routes.py#L436) | `PluginBridge._settings_record` | `plugin_id: str` | `tuple[Any, dict[str, Any]]` | Implement `PluginBridge._settings_record`. |
| [bridge_routes.py](bridge_routes.py#L449) | `PluginBridge._get_plugin_settings` | `plugin_id: str` | `dict[str, Any]` | Read one plugin's non-secret persisted settings. |
| [bridge_routes.py](bridge_routes.py#L460) | `PluginBridge._put_plugin_settings` | `plugin_id: str, settings: dict[str, Any]` | `dict[str, Any]` | Persist JSON settings without accepting credential-like values. |
| [bridge_routes.py](bridge_routes.py#L478) | `PluginBridge._static_asset` | `name: str, asset: str` | `FileResponse` | Implement `PluginBridge._static_asset`. |
| [bridge_routes.py](bridge_routes.py#L484) | `PluginBridge._resolve_static_asset` | `name: str, asset: str` | `Path \| None` | Resolve ``asset`` inside the plugin dir under the whitelist. |
| [bridge_routes.py](bridge_routes.py#L519) | `PluginBridge._mount_plugin_routers` | `app: FastAPI` | `None` | Attach one prefixed ``APIRouter`` per plugin with published routes. |
| [bridge_routes.py](bridge_routes.py#L568) | `PluginBridge._active_plugin_dependency` | `plugin: str` | `Any` | Build a request-time guard for an already-mounted plugin route. |
| [bridge_routes.py](bridge_routes.py#L578) | `PluginBridge._unmount_plugin_routers` | `plugin: str` | `None` | Remove routes owned by a stopped plugin so stale handlers cannot run. |
| [bridge_routes.py](bridge_routes.py#L593) | `_normalise_asset_key` | `entry: str` | `str` | Normalise a whitelist entry to the same key space as resolved paths. |
| [bridge_routes.py](bridge_routes.py#L601) | `include_plugin_routes` | `app: FastAPI, manager: Any, registry: Any \| None` | `PluginBridge` | Mount the plugin REST/static surface onto the main app (S6 entry). |
| [bridge_tools.py](bridge_tools.py#L59) | `create_plugin_tools` | `manager: Any \| None` | `list[Tool]` | Create one :class:`~llmfetcher.llm_types.Tool` per published plugin tool. |
| [bridge_tools.py](bridge_tools.py#L105) | `_registration_to_tool` | `registration: Any, default_name: str \| None` | `Tool \| None` | Map one ``ToolRegistration`` onto a llmfetcher ``Tool`` (duck-typed). |
| [bridge_tools.py](bridge_tools.py#L160) | `_schema_to_tool_schema` | `schema: dict[str, Any]` | `ToolSchema` | Map a plugin ``register_tool`` schema onto :class:`ToolSchema`. |
| [bridge_tools.py](bridge_tools.py#L216) | `_to_parameter` | `name: str, prop: dict[str, Any], required: bool` | `ToolParameter` | Build one :class:`ToolParameter` from a JSON-Schema property dict. |
| [manager.py](manager.py#L83) | `PluginRecord.loadable` | `None` | `bool` | Implement `PluginRecord.loadable`. |
| [manager.py](manager.py#L97) | `ToolRegistration.full_name` | `None` | `str` | Implement `ToolRegistration.full_name`. |
| [manager.py](manager.py#L205) | `PluginManager.workspace_dir` | `None` | `Path` | Implement `PluginManager.workspace_dir`. |
| [manager.py](manager.py#L209) | `PluginManager.global_dir` | `None` | `Path` | Implement `PluginManager.global_dir`. |
| [manager.py](manager.py#L212) | `PluginManager.discover` | `None` | `list[PluginRecord]` | Scan both tiers and (re)build the discovered record set. |
| [manager.py](manager.py#L285) | `PluginManager.load` | `name: str, reload: bool` | `PluginRecord` | Import and ``setup()`` one plugin; returns its record. |
| [manager.py](manager.py#L354) | `PluginManager.reload` | `name: str` | `PluginRecord` | Tear down and load a plugin fresh (modules purged, setup re-run). |
| [manager.py](manager.py#L358) | `PluginManager.teardown` | `name: str` | `PluginRecord \| None` | Run ``teardown()``, unpublish registrations and purge modules. |
| [manager.py](manager.py#L367) | `PluginManager.enable` | `name: str, permissions: list[str] \| None` | `PluginRecord` | Persist ``enabled=true`` in the registry, then load the plugin. |
| [manager.py](manager.py#L393) | `PluginManager.disable` | `name: str` | `PluginRecord \| None` | Tear the plugin down and persist ``enabled=false`` in the registry. |
| [manager.py](manager.py#L402) | `PluginManager.load_all` | `None` | `list[PluginRecord]` | Load every discovered plugin that is enabled in the registry. |
| [manager.py](manager.py#L419) | `PluginManager.rescan` | `None` | `dict[str, Any]` | Re-scan the plugin directories and reconcile live plugins. |
| [manager.py](manager.py#L475) | `PluginManager.get_tools` | `None` | `dict[str, ToolRegistration]` | Published tools keyed by their namespaced ``plugin.<name>.<tool>``. |
| [manager.py](manager.py#L479) | `PluginManager.get_routes` | `None` | `list[RouteRegistration]` | Implement `PluginManager.get_routes`. |
| [manager.py](manager.py#L482) | `PluginManager.get_hooks` | `event: str \| None` | `dict[str, list[HookRegistration]] \| list[HookRegistration]` | Return hooks for one event (priority-desc) or all events. |
| [manager.py](manager.py#L490) | `PluginManager.get_connectors` | `None` | `dict[str, ConnectorRegistration]` | Implement `PluginManager.get_connectors`. |
| [manager.py](manager.py#L493) | `PluginManager.plugin` | `name: str` | `PluginRecord \| None` | Implement `PluginManager.plugin`. |
| [manager.py](manager.py#L496) | `PluginManager.plugins` | `None` | `list[PluginRecord]` | Implement `PluginManager.plugins`. |
| [manager.py](manager.py#L500) | `PluginManager.get_status` | `None` | `list[dict[str, Any]]` | Status snapshot for ``/api/plugins`` and CLI reporting. |
| [manager.py](manager.py#L520) | `PluginManager._ensure_discovered` | `None` | `None` | Implement `PluginManager._ensure_discovered`. |
| [manager.py](manager.py#L524) | `PluginManager._require_loadable` | `name: str` | `PluginRecord` | Implement `PluginManager._require_loadable`. |
| [manager.py](manager.py#L535) | `PluginManager._manifest_loader` | `None` | `Any` | Implement `PluginManager._manifest_loader`. |
| [manager.py](manager.py#L542) | `PluginManager._registry_module` | `None` | `Any` | Implement `PluginManager._registry_module`. |
| [manager.py](manager.py#L549) | `PluginManager._registry_lookup` | `name: str` | `dict[str, Any] \| None` | Implement `PluginManager._registry_lookup`. |
| [manager.py](manager.py#L560) | `PluginManager._ensure_namespace` | `None` | `types.ModuleType` | Create the ``angelus_plugins`` namespace package in ``sys.modules``. |
| [manager.py](manager.py#L576) | `PluginManager._import_entry` | `record: PluginRecord` | `types.ModuleType` | Import the plugin entry module under ``angelus_plugins.<name>``. |
| [manager.py](manager.py#L628) | `PluginManager._resolve_plugin` | `module: types.ModuleType, record: PluginRecord` | `AngelusPlugin` | Implement `PluginManager._resolve_plugin`. |
| [manager.py](manager.py#L655) | `PluginManager._build_runtime` | `record: PluginRecord` | `PluginRuntime` | Implement `PluginManager._build_runtime`. |
| [manager.py](manager.py#L668) | `PluginManager._publish` | `name: str, snapshot: dict[str, list[dict[str, Any]]]` | `None` | Apply a successful setup snapshot to the live tables. |
| [manager.py](manager.py#L706) | `PluginManager._unpublish` | `name: str` | `None` | Implement `PluginManager._unpublish`. |
| [manager.py](manager.py#L727) | `PluginManager._teardown_locked` | `name: str` | `PluginRecord \| None` | Implement `PluginManager._teardown_locked`. |
| [manager.py](manager.py#L749) | `PluginManager._purge_modules` | `name: str` | `None` | Drop every module of this plugin from ``sys.modules`` so a later load imports a fresh copy (no stale registrations, no duplicates). |
| [security.py](security.py#L84) | `get_logger` | `None` | `logging.Logger` | Return the module logger (``angelus.plugins.security``). |
| [security.py](security.py#L92) | `_default_registry` | `None` | `Any` | Lazily import the real S2 registry module (importable standalone). |
| [security.py](security.py#L99) | `_audit` | `level: int, event: str, **fields: Any` | `None` | Emit a structured audit line: ``SECURITY <EVENT> k=v k=v ...``. |
| [security.py](security.py#L108) | `format_grant` | `action: str, scope: str` | `str` | Render a grant as the canonical ``"action:scope"`` string. |
| [security.py](security.py#L113) | `declared_permissions` | `manifest: dict[str, Any]` | `frozenset[str]` | Return the ``"action:scope"`` set a manifest *declares*. |
| [security.py](security.py#L133) | `granted_permissions` | `plugin_id: str, registry: Any` | `frozenset[str]` | Return the ``permissions_granted`` set for a plugin record. |
| [security.py](security.py#L149) | `_lookup_record` | `plugin_id: str, registry: Any` | `dict[str, Any] \| None` | Resolve a plugin record by id, falling back to a name scan. |
| [security.py](security.py#L192) | `check_permission` | `plugin_id: str, action: str, scope: str, registry: Any` | `bool` | Gate one plugin capability call against ``permissions_granted``. |
| [security.py](security.py#L276) | `require_permission` | `plugin_id: str, action: str, scope: str, registry: Any` | `None` | Like :func:`check_permission` but raises ``PermissionError`` on denial. |
| [security.py](security.py#L293) | `grant_permission` | `plugin_id: str, action: str, scope: str, registry: Any` | `dict[str, Any] \| None` | Validate and persist one ``"action:scope"`` grant. |
| [security.py](security.py#L330) | `compute_checksum` | `path: Path \| str` | `str` | Return ``"sha256:<hex>"`` of a single file's bytes. |
| [security.py](security.py#L336) | `verify_checksum` | `path: Path \| str, expected: str \| None` | `bool` | Return ``True`` when the file's sha256 equals ``expected``. |
| [security.py](security.py#L350) | `_canonical_manifest_bytes` | `manifest: dict[str, Any]` | `bytes` | Canonical JSON bytes of the manifest with ``checksum`` excluded. |
| [security.py](security.py#L364) | `_resolve_entry_path` | `plugin_dir: Path \| str, manifest: dict[str, Any]` | `Path \| None` | Resolve ``manifest.entry`` to an existing file inside ``plugin_dir``. |
| [security.py](security.py#L399) | `compute_plugin_integrity` | `plugin_dir: Path \| str, manifest: dict[str, Any]` | `str` | Compute the install-time integrity checksum for a plugin. |
| [security.py](security.py#L424) | `verify_plugin_integrity` | `plugin_dir: Path \| str, manifest: dict[str, Any], expected: str \| None` | `tuple[bool, list[str]]` | Verify a plugin's manifest + entry are untouched since install. |
| [security.py](security.py#L521) | `redact_connector` | `record: dict[str, Any]` | `dict[str, Any]` | Return browser-safe connector metadata without credentials. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [autoreload.py](autoreload.py#L54) | `PluginAutoReloader` | `rescan: Callable[[], Any], interval: float, logger: logging.Logger \| None` | `object` | Daemon polling thread that periodically rescans the plugin bridge. |
| [base.py](base.py#L47) | `PluginError` | `None` | `Exception` | Raised for plugin lifecycle errors (missing plugin, bad entry, ...). |
| [base.py](base.py#L56) | `PluginRuntime` | `name: str, state_dir: Path \| str, settings: dict[str, Any] \| None, logger: logging.Logger \| None` | `object` | Setup-time registration surface handed to ``AngelusPlugin.setup()``. |
| [base.py](base.py#L235) | `AngelusPlugin` | `name: str, version: str` | `object` | Base class plugins subclass to become loadable by ``PluginManager``. |
| [bridge_hooks.py](bridge_hooks.py#L96) | `HookRegistrationLike` | `plugin: str, event: str, handler: Callable[[Any], None], priority: int` | `Protocol` | Structural view of the manager's ``HookRegistration`` records. |
| [bridge_hooks.py](bridge_hooks.py#L125) | `PluginHookBridge` | `manager: Any, host: Any, logger: Optional[logging.Logger]` | `object` | Route agent-bus execution events to plugin hooks. |
| [bridge_routes.py](bridge_routes.py#L135) | `_EmptyRegistry` | `None` | `object` | Stand-in registry so the bridge works before S2 lands (empty view). |
| [bridge_routes.py](bridge_routes.py#L158) | `PluginBridge` | `manager: Any, registry: Any \| None` | `object` | Routes + static mounting for one ``PluginManager``. |
| [manager.py](manager.py#L56) | `PluginState` | `None` | `str, enum.Enum` | Lifecycle state of a discovered/loaded plugin. |
| [manager.py](manager.py#L68) | `PluginRecord` | `name: str, plugin_dir: Path, tier: str, manifest: dict[str, Any] \| None, version: str, state: PluginState, plugin: AngelusPlugin \| None, runtime: PluginRuntime \| None, error: str \| None, errors: list[dict[str, str]]` | `object` | One discovered plugin and its in-memory lifecycle state. |
| [manager.py](manager.py#L88) | `ToolRegistration` | `plugin: str, name: str, schema: dict[str, Any], handler: Callable` | `object` | Published plugin tool (live name ``plugin.<plugin>.<tool>``). |
| [manager.py](manager.py#L102) | `RouteRegistration` | `plugin: str, method: str, path: str, handler: Callable` | `object` | Published plugin route (mounted under ``/plugins/<name>/api``). |
| [manager.py](manager.py#L112) | `HookRegistration` | `plugin: str, event: str, handler: Callable, priority: int` | `object` | Published plugin hook for a whitelisted agent event. |
| [manager.py](manager.py#L122) | `ConnectorRegistration` | `plugin: str, kind: str, factory: Callable` | `object` | Published plugin connector provider factory. |
| [manager.py](manager.py#L130) | `PluginManager` | `state_root: Path \| str \| None, workspace_dir: Path \| str \| None, global_dir: Path \| str \| None, registry: Any, logger: logging.Logger \| None` | `object` | Owns plugin discovery, namespaced loading and the lifecycle state machine for every plugin visible in the current workspace. |

<!-- END GENERATED SYMBOL MAP -->
