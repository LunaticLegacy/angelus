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
