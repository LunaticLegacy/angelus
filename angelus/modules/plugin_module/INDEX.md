# plugin_module/ — Controlled Plugin Runtime INDEX

This module owns global plugin discovery, explicit registration, permission
approval, typed non-secret settings, controlled loading, and CSS theme packs.
It never creates a second tool directory: executable plugins publish only
namespaced `ToolProviderRegistration` values to `tool_module.ToolRegistry`.

| File | Responsibility |
|---|---|
| `models.py` | Dataclass contracts for manifests, settings, skins, records, and tool contributions. |
| `manifest.py` | No-import JSON manifest validator for tool, UI, and theme-pack packages. |
| `store.py` | Atomic global plugin registry and scalar settings persistence. |
| `manager.py` | Managed/local discovery, register/load/unload lifecycle, settings validation, static whitelist, and ToolRegistry bridge. |

## Runtime Boundaries

- Discovery reads only `manifest.json`; it does not import plugin code. It
  scans both managed packages in `.angelus-state/plugins/packages/` and the
  repository-local `plugins/` development source root. Local packages remain
  inert until they are explicitly registered and loaded.
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
| `manager.py` | `PluginManager.static_asset` | Resolve only active manifest-whitelisted static files. |

## Class Map

| Source | Class | Semantics |
|---|---|---|
| `models.py` | `PluginManifest`, `PluginSettingField`, `PluginTheme` | Immutable declarative package and UI contracts. |
| `models.py` | `PluginRuntime`, `PluginToolContribution` | Constrained executable plugin setup API. |
| `store.py` | `PluginStore` | Lock-protected registry JSON authority. |
| `manager.py` | `PluginManager` | Process-wide lifecycle and ToolRegistry integration authority. |
