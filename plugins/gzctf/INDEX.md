# gzctf/ — GZCTF Helper v1 Plugin INDEX

| File | Responsibility |
|---|---|
| `manifest.json` | Current v1 tool-plugin declaration: persisted non-secret endpoint/account settings and host-rendered transient password login panel. |
| `main.py` | Namespaced GZCTF Tool provider, transient login action, authenticated HTTP helpers, attachment download, dynamic-instance, and batch orchestration logic. |
| `automation.py` | Atomic plugin-private durable state for authorized batch runs. |
| `README.md` | Legacy capability and protocol reference retained for operators. |

## Runtime boundaries

- The host imports `main.py` only after registration, permission approval, and
  explicit load. It publishes 11 `plugin.gzctf.*` Agent tools for coordinator
  and worker roles.
- `base_url` and `username` are non-secret settings. The login panel password
  is a `sensitive` transient field: it has no default and is neither persisted
  nor returned to the browser.
- Cookies, attachment downloads, and batch-run JSON live only under the
  Angelus plugin state directory, never in this source package.
