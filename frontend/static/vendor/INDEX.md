# frontend/static/vendor/ — Pinned Browser Dependencies INDEX

These files are browser-served, pinned ESM artifacts. They are copied from the
versions declared in the repository root `package.json`; their upstream license
files travel with the exact artifacts.

| Directory | Package | Version | Runtime role |
|---|---|---:|---|
| `marked/` | Marked | `15.0.12` | Parse raw Agent Markdown into HTML. |
| `dompurify/` | DOMPurify | `3.2.6` | Sanitize that parsed HTML before the workbench inserts it. |

Only `../components/markdown-renderer.js` imports these packages. They are not
general UI helpers and must not be edited locally; upgrade through npm, replace
the exact ESM artifact, retain its license, and update the version table.
