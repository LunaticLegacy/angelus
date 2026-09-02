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
