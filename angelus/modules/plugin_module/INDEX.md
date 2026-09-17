# plugin_module/ — Controlled Plugin Runtime INDEX

This module owns global plugin discovery, explicit registration, permission
approval, typed non-secret settings, controlled loading, and CSS theme packs.
It never creates a second tool directory: executable plugins publish only
namespaced `ToolProviderRegistration` values to `tool_module.ToolRegistry`.

| File | Responsibility |
|---|---|
| `models.py` | Dataclass contracts for manifests, user-configured parameters, declarative panels, UI actions, skins, records, and tool contributions. |
| `manifest.py` | No-import JSON manifest validator for tool, UI, and theme-pack packages. |
| `store.py` | Atomic global plugin registry and scalar settings persistence. |
| `manager.py` | Managed/local discovery, register/load/unload lifecycle, settings/panel validation, static whitelist, UI action dispatch, and ToolRegistry bridge. |

## Runtime Boundaries

- Discovery reads only `manifest.json`; it does not import plugin code. It
  scans both managed packages in `.angelus-state/plugins/packages/` and the
  repository-local `plugins/` development source root. Local packages remain
  inert until they are explicitly registered and loaded.
- Plugin settings are manifest-declared typed user parameters. They are
  persisted atomically, validated before storage, and read by a tool plugin
  with `PluginRuntime.setting(key, default)` during its next load.
- Declarative `frontend.panels` render host-owned transient form controls in
  the Inspector. A tool plugin must register every matching action during
  setup; the host validates values and renders only the returned text result.
  Panel-only `sensitive: true, format: "password"` inputs are allowed solely
  in memory: they cannot have defaults or enter persisted settings.
- A registered tool plugin executes only after a confirmed load and granted
  declared permissions.
- Theme packs never declare Python entrypoints and expose only active,
  manifest-whitelisted CSS assets.
- A ToolRegistry revision changes on plugin publication/removal, forcing the
  next Session Agent materialization to receive the correct tool set.

## Function Map

| Source | Function / method | Semantics |
|---|---|---|
| `manifest.py` | `load_manifest` | Decode and validate a package without executing it. |
| `store.py` | `PluginStore.records`, `PluginStore.put` | Atomically read or replace durable plugin registrations. |
| `manager.py` | `PluginManager.rescan`, `PluginManager.register` | Discover and record a validated package without code execution. |
| `manager.py` | `PluginManager.load`, `PluginManager.unload` | Publish/remove namespaced plugin Tool providers after explicit approval. |
| `manager.py` | `PluginManager.settings`, `PluginManager.replace_settings` | Return and validate typed scalar plugin settings. |
| `manager.py` | `PluginManager.invoke_panel` | Validate transient panel values and dispatch one active declared action. |
| `manager.py` | `PluginManager.static_asset` | Resolve only active manifest-whitelisted static files. |

## Class Map

| Source | Class | Semantics |
|---|---|---|
| `models.py` | `PluginManifest`, `PluginSettingField`, `PluginPanelField`, `PluginPanel`, `PluginTheme` | Immutable declarative package and host-rendered UI contracts. |
| `models.py` | `PluginRuntime`, `PluginToolContribution`, `PluginUiActionRequest`, `PluginUiActionResult` | Constrained setup API and typed transient action boundary. |
| `store.py` | `PluginStore` | Lock-protected registry JSON authority. |
| `manager.py` | `PluginManager` | Process-wide lifecycle and ToolRegistry integration authority. |

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [manager.py](manager.py#L42) | `PluginEntrypoint.setup` | `runtime: PluginRuntime` | `None` | Register contributions using the supplied constrained runtime. |
| [manager.py](manager.py#L52) | `PluginEntrypoint.teardown` | `None` | `None` | Release plugin-owned process resources before removal. |
| [manager.py](manager.py#L123) | `PluginManager.rescan` | `None` | `tuple[DiscoveredPlugin, ...]` | Discover managed and local development manifests without imports. |
| [manager.py](manager.py#L150) | `PluginManager.statuses` | `None` | `tuple[dict[str, object], ...]` | Project discovered and registered package states for the workbench. |
| [manager.py](manager.py#L168) | `PluginManager.active` | `None` | `tuple[dict[str, object], ...]` | Return the browser-loadable subset of active packages. |
| [manager.py](manager.py#L176) | `PluginManager.restore_enabled` | `None` | `None` | Restore previously approved enabled plugins after host startup. |
| [manager.py](manager.py#L194) | `PluginManager.register` | `name: str` | `dict[str, object]` | Persist a discovered package after validation without executing it. |
| [manager.py](manager.py#L217) | `PluginManager.load` | `plugin_id: str, grant_permissions: bool` | `dict[str, object]` | Load one registered plugin after explicit capability approval. |
| [manager.py](manager.py#L249) | `PluginManager.unload` | `plugin_id: str` | `dict[str, object]` | Stop one loaded plugin without deleting its package or settings. |
| [manager.py](manager.py#L281) | `PluginManager.settings` | `plugin_id: str` | `dict[str, object]` | Return one registered plugin's typed settings and schema. |
| [manager.py](manager.py#L301) | `PluginManager.replace_settings` | `plugin_id: str, values: Mapping[str, object]` | `dict[str, object]` | Validate and persist non-secret scalar settings for one plugin. |
| [manager.py](manager.py#L326) | `PluginManager.invoke_panel` | `plugin_id: str, panel_id: str, values: Mapping[str, object]` | `PluginUiActionResult` | Validate and dispatch one active plugin's declarative panel action. |
| [manager.py](manager.py#L369) | `PluginManager.static_asset` | `name: str, asset: str` | `Path \| None` | Resolve a manifest-whitelisted static asset without traversal. |
| [manager.py](manager.py#L386) | `PluginManager._discovery` | `name: str` | `DiscoveredPlugin` | Locate one valid discovered manifest by name. |
| [manager.py](manager.py#L403) | `PluginManager._record_by_name` | `name: str` | `PluginRecord \| None` | Find a durable record by manifest name. |
| [manager.py](manager.py#L414) | `PluginManager._manifest_for_record` | `record: PluginRecord` | `PluginManifest` | Revalidate one durable package before any active operation. |
| [manager.py](manager.py#L435) | `PluginManager._is_discovery_package` | `package_path: Path` | `bool` | Return whether a record points at a direct child of a trusted root. |
| [manager.py](manager.py#L447) | `PluginManager._load` | `manifest: PluginManifest, record: PluginRecord` | `LoadedPlugin` | Execute one approved tool plugin and atomically publish providers. |
| [manager.py](manager.py#L488) | `PluginManager._publish` | `manifest: PluginManifest, contributions: list[PluginToolContribution]` | `tuple[str, ...]` | Namespace and publish setup contributions after complete validation. |
| [manager.py](manager.py#L534) | `_PluginProvider.materialize` | `session: 'Session', policy: 'ToolPolicy', role: str, agent_name: str \| None` | `list['Tool']` | Create namespaced concrete Tools for one Agent. |
| [manager.py](manager.py#L556) | `_remove_plugin_modules` | `module_name: str` | `None` | Remove a plugin entry namespace and its relative-import children. |
| [manager.py](manager.py#L571) | `_entrypoint` | `module: ModuleType` | `PluginEntrypoint` | Extract a valid module-level plugin lifecycle object. |
| [manager.py](manager.py#L591) | `_status` | `manifest: PluginManifest, record: PluginRecord \| None, state: str, error: str` | `dict[str, object]` | Build a non-secret plugin projection for browser controls. |
| [manager.py](manager.py#L615) | `_permission_json` | `value: PluginPermission` | `dict[str, str]` | Serialize one permission to its public JSON shape. |
| [manager.py](manager.py#L627) | `_theme_json` | `value: object` | `dict[str, str]` | Serialize one typed theme without exposing package filesystem paths. |
| [manager.py](manager.py#L639) | `_panel_json` | `value: PluginPanel` | `dict[str, object]` | Serialize one declarative panel for the generic browser renderer. |
| [manager.py](manager.py#L657) | `_field_json` | `value: object` | `dict[str, object]` | Serialize one typed schema field for form rendering. |
| [manager.py](manager.py#L674) | `_settings_json` | `values: tuple[PluginSettingValue, ...]` | `dict[str, PluginSettingScalar]` | Serialize typed settings into an API object. |
| [manager.py](manager.py#L686) | `_validate_settings` | `manifest: PluginManifest, values: Mapping[str, object]` | `tuple[PluginSettingValue, ...]` | Validate a submitted object against the plugin's declared schema. |
| [manager.py](manager.py#L702) | `_validate_fields` | `declared: tuple[PluginSettingField, ...], values: Mapping[str, object], defaults: bool` | `tuple[PluginSettingValue, ...]` | Validate typed persisted or transient values against declared fields. |
| [manager.py](manager.py#L746) | `_validate_ui_actions` | `manifest: PluginManifest, actions: list[PluginUiActionRegistration]` | `tuple[PluginUiActionRegistration, ...]` | Ensure loaded code registered every and only manifest panel action. |
| [manager.py](manager.py#L773) | `_setting_type` | `value: object, kind: str` | `bool` | Check an API scalar against one schema scalar type. |
| [manifest.py](manifest.py#L32) | `load_manifest` | `package_path: Path` | `PluginManifest` | Decode one package manifest without importing plugin code. |
| [manifest.py](manifest.py#L55) | `_text` | `raw: Mapping[str, object], key: str, required: bool, maximum: int` | `str` | Read one bounded manifest text field. |
| [manifest.py](manifest.py#L76) | `_decode_manifest` | `raw: Mapping[str, object]` | `PluginManifest` | Validate supported v1 fields and assemble the immutable manifest. |
| [manifest.py](manifest.py#L145) | `_permissions` | `value: object` | `tuple[PluginPermission, ...]` | Decode requested capability pairs. |
| [manifest.py](manifest.py#L170) | `_assets` | `value: object` | `tuple[str, ...]` | Validate static assets that may be served by the host. |
| [manifest.py](manifest.py#L194) | `_themes` | `value: object, assets: tuple[str, ...], kind: object` | `tuple[PluginTheme, ...]` | Decode a theme-pack's named CSS variants. |
| [manifest.py](manifest.py#L231) | `_panels` | `value: object` | `tuple[PluginPanel, ...]` | Decode declarative plugin panels without importing package code. |
| [manifest.py](manifest.py#L274) | `_panel_fields` | `value: object` | `tuple[PluginPanelField, ...]` | Decode transient panel fields while isolating sensitive values. |
| [manifest.py](manifest.py#L341) | `_settings` | `value: object, label: str` | `tuple[PluginSettingField, ...]` | Decode the restricted scalar settings schema. |
| [manifest.py](manifest.py#L399) | `_plain` | `value: object, maximum: int` | `str` | Return a bounded optional presentation string. |
| [manifest.py](manifest.py#L419) | `_matches` | `value: object, field_type: object` | `bool` | Check one raw scalar against a declared schema type. |
| [models.py](models.py#L195) | `PluginUiActionRequest.value` | `key: str, default: PluginSettingScalar \| None` | `PluginSettingScalar \| None` | Return one validated transient field value. |
| [models.py](models.py#L301) | `PluginToolProvider.materialize` | `session_id: str, policy: ToolPolicy, role: str` | `list[Tool]` | Create concrete tools for one Session and Agent role. |
| [models.py](models.py#L348) | `PluginRuntime.register_tool_provider` | `contribution: PluginToolContribution` | `None` | Stage one Tool contribution for atomic publication after setup. |
| [models.py](models.py#L359) | `PluginRuntime.register_ui_action` | `action_id: str, handler: Callable[[PluginUiActionRequest], PluginUiActionResult]` | `None` | Stage one manifest-declared user-interface action handler. |
| [models.py](models.py#L376) | `PluginRuntime.setting` | `key: str, default: PluginSettingScalar \| None` | `PluginSettingScalar \| None` | Read one validated user-configured plugin parameter. |
| [store.py](store.py#L27) | `PluginStore.records` | `None` | `tuple[PluginRecord, ...]` | Return every persisted record in stable document order. |
| [store.py](store.py#L36) | `PluginStore.get` | `plugin_id: str` | `PluginRecord \| None` | Find one registered plugin by stable ID. |
| [store.py](store.py#L47) | `PluginStore.put` | `record: PluginRecord` | `PluginRecord` | Atomically create or replace one plugin record. |
| [store.py](store.py#L62) | `PluginStore._read` | `None` | `tuple[PluginRecord, ...]` | Decode the registered plugin document without executing packages. |
| [store.py](store.py#L79) | `PluginStore._write` | `records: tuple[PluginRecord, ...]` | `None` | Publish one complete plugin registry generation atomically. |
| [store.py](store.py#L91) | `_record` | `raw: object` | `PluginRecord` | Decode a record stored by :class:`PluginStore`. |
| [store.py](store.py#L117) | `_permissions` | `raw: object` | `tuple[PluginPermission, ...]` | Decode persisted approved plugin permissions. |
| [store.py](store.py#L139) | `_settings` | `raw: object` | `tuple[PluginSettingValue, ...]` | Decode bounded scalar settings. |
| [store.py](store.py#L164) | `_scalar` | `value: object` | `bool` | Return whether a value is a supported persisted scalar. |
| [store.py](store.py#L176) | `_record_json` | `record: PluginRecord` | `dict[str, object]` | Project a typed record into JSON-safe primitive containers. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [manager.py](manager.py#L39) | `PluginEntrypoint` | `None` | `Protocol` | Minimal executable plugin lifecycle expected by the host. |
| [manager.py](manager.py#L61) | `DiscoveredPlugin` | `manifest: PluginManifest \| None, package_path: Path, error: str` | `object` | A manifest-validated package that has not necessarily been registered. |
| [manager.py](manager.py#L76) | `LoadedPlugin` | `manifest: PluginManifest, record: PluginRecord, module_name: str, entrypoint: PluginEntrypoint \| None, provider_ids: tuple[str, ...], ui_actions: tuple[PluginUiActionRegistration, ...]` | `object` | In-process runtime state for an explicitly enabled plugin. |
| [manager.py](manager.py#L96) | `PluginManager` | `state_root: Path, tool_registry: ToolRegistry, development_root: Path \| None` | `object` | Single process authority for plugin package lifecycle and settings. |
| [manager.py](manager.py#L521) | `_PluginProvider` | `name: str, provider: object` | `object` | Adapt a package-local provider to the host Session tool protocol. |
| [manifest.py](manifest.py#L28) | `ManifestError` | `None` | `ValueError` | Raised when a plugin package fails declarative manifest validation. |
| [models.py](models.py#L18) | `PluginPermission` | `action: str, scope: str` | `object` | One capability a plugin requests before its code can be loaded. |
| [models.py](models.py#L31) | `PluginSettingField` | `key: str, value_type: Literal['string', 'integer', 'number', 'boolean'], title: str, description: str, required: bool, default: PluginSettingScalar \| None, choices: tuple[PluginSettingScalar, ...], minimum: int \| float \| None, maximum: int \| float \| None, value_format: Literal['uri', 'path', 'textarea'] \| None, placeholder: str` | `object` | One typed, non-secret field displayed in a plugin settings form. |
| [models.py](models.py#L63) | `PluginPanelField` | `key: str, value_type: Literal['string', 'integer', 'number', 'boolean'], title: str, description: str, required: bool, default: PluginSettingScalar \| None, choices: tuple[PluginSettingScalar, ...], minimum: int \| float \| None, maximum: int \| float \| None, value_format: Literal['uri', 'path', 'textarea', 'password'] \| None, placeholder: str, sensitive: bool` | `object` | One typed transient field displayed in a host-rendered plugin panel. |
| [models.py](models.py#L98) | `PluginTheme` | `id: str, title: str, asset: str, mode: Literal['dark', 'light']` | `object` | One CSS skin exposed by a theme-pack plugin. |
| [models.py](models.py#L115) | `PluginPanel` | `id: str, title: str, description: str, action: str, submit_label: str, fields: tuple[PluginPanelField, ...]` | `object` | One declarative plugin function panel rendered by the host. |
| [models.py](models.py#L136) | `PluginManifest` | `name: str, display_name: str, version: str, api_version: str, kind: PluginKind, entry: str \| None, description: str, permissions: tuple[PluginPermission, ...], assets: tuple[str, ...], settings_enabled: bool, settings_schema: tuple[PluginSettingField, ...], themes: tuple[PluginTheme, ...], panels: tuple[PluginPanel, ...]` | `object` | Validated, declarative plugin package contract. |
| [models.py](models.py#L171) | `PluginSettingValue` | `key: str, value: PluginSettingScalar` | `object` | One persisted scalar plugin setting. |
| [models.py](models.py#L184) | `PluginUiActionRequest` | `panel_id: str, values: tuple[PluginSettingValue, ...]` | `object` | Validated transient user input delivered to one plugin action. |
| [models.py](models.py#L213) | `PluginUiActionResult` | `title: str, content: str, tone: Literal['info', 'success', 'error']` | `object` | Safe textual result rendered by the host after a plugin UI action. |
| [models.py](models.py#L229) | `PluginUiActionRegistration` | `id: str, handler: Callable[[PluginUiActionRequest], PluginUiActionResult]` | `object` | One action handler explicitly registered during plugin setup. |
| [models.py](models.py#L243) | `PluginRecord` | `id: str, name: str, package_path: str, enabled: bool, permissions_granted: tuple[PluginPermission, ...], settings: tuple[PluginSettingValue, ...]` | `object` | Durable local registration state for one discovered plugin. |
| [models.py](models.py#L265) | `PluginToolCategory` | `id: str, title: str, description: str` | `object` | A plugin-owned user-visible tool category. |
| [models.py](models.py#L280) | `PluginToolDefinition` | `id: str, category_id: str, title: str, description: str, roles: frozenset[str]` | `object` | A package-local Tool definition that the host namespaces on registration. |
| [models.py](models.py#L298) | `PluginToolProvider` | `None` | `Protocol` | Plugin-owned factory for concrete llmfetcher tools. |
| [models.py](models.py#L315) | `PluginToolContribution` | `provider: PluginToolProvider, categories: tuple[PluginToolCategory, ...], definitions: tuple[PluginToolDefinition, ...]` | `object` | One plugin tool-provider registration requested during ``setup``. |
| [models.py](models.py#L330) | `PluginRuntime` | `plugin: PluginManifest, settings: tuple[PluginSettingValue, ...], state_path: str, contributions: list[PluginToolContribution], ui_actions: list[PluginUiActionRegistration]` | `object` | Constrained host object supplied to one executing plugin's setup hook. |
| [store.py](store.py#L13) | `PluginStore` | `state_root: Path` | `object` | Own global plugin registration state below the Angelus state root. |

<!-- END GENERATED SYMBOL MAP -->
