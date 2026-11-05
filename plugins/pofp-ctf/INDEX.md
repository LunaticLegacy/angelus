# pofp-ctf

Bundled current-v1 read-only plugin for a POFP CTF Markdown knowledge tree.

- `manifest.json`: strict Angelus v1 tool package metadata, declared read
  permission intent, and the optional persisted `knowledge_root` user
  parameter with a path hint.
- `main.py`: current-v1 `PluginToolContribution` provider for namespaced
  `plugin.pofp-ctf.ctf_search` and `plugin.pofp-ctf.ctf_read` tools, plus the
  manifest-declared `knowledge-search` panel action.

The setting first selects the configured root, then the legacy
`POFP_KNOWLEDGE_ROOT` environment fallback, and finally repository
`knowledge/`. The host does not expose arbitrary plugin routes or browser
code; its manifest-declared `knowledge-search` panel is rendered and invoked
by the host through the constrained plugin action API.

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [main.py](main.py#L37) | `_default_root` | `None` | `Path` | Resolve the legacy POFP knowledge-root fallback. |
| [main.py](main.py#L50) | `_configured_root` | `value: str` | `Path` | Resolve the persisted setting or retain the historic fallback root. |
| [main.py](main.py#L62) | `_safe_leaf` | `root: Path, relative: str` | `Path` | Resolve one Markdown leaf while preventing root-directory escape. |
| [main.py](main.py#L83) | `_iter_leaves` | `root: Path, direction: str` | `Iterator[Path]` | Yield sorted non-index Markdown leaves in an optional CTF direction. |
| [main.py](main.py#L115) | `PofpCtfProvider.is_available` | `None` | `bool` | Return whether the configured knowledge-root directory is readable. |
| [main.py](main.py#L123) | `PofpCtfProvider.materialize` | `session_id: str, policy: ToolPolicy, role: str` | `list[Tool]` | Build namespaced CTF tools for coordinator and worker Agents. |
| [main.py](main.py#L155) | `PofpCtfProvider.search` | `query: str, direction: str, limit: int` | `str` | Search configured CTF Markdown documents and format bounded results. |
| [main.py](main.py#L210) | `PofpCtfProvider.read` | `path: str` | `str` | Read one configured CTF Markdown document after containment checks. |
| [main.py](main.py#L242) | `PofpCtfSearchAction.__call__` | `request: PluginUiActionRequest` | `PluginUiActionResult` | Search the knowledge tree using validated declarative panel fields. |
| [main.py](main.py#L268) | `PofpCtfPlugin.setup` | `runtime: PluginRuntime` | `None` | Register CTF search and document-read tool definitions. |
| [main.py](main.py#L290) | `PofpCtfPlugin.teardown` | `None` | `None` | Release no resources because the provider owns no open handles. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [main.py](main.py#L23) | `CtfSearchHit` | `path: str, title: str, direction: str` | `object` | One searchable CTF knowledge document. |
| [main.py](main.py#L101) | `PofpCtfProvider` | `root: Path` | `object` | Materialize read-only CTF knowledge tools for Session Agents. |
| [main.py](main.py#L228) | `PofpCtfSearchAction` | `provider: PofpCtfProvider` | `object` | Serve the declarative CTF search panel without browser-side plugin code. |
| [main.py](main.py#L265) | `PofpCtfPlugin` | `None` | `object` | Publish current-v1 namespaced POFP CTF knowledge tools. |

<!-- END GENERATED SYMBOL MAP -->
