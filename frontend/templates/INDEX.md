# frontend/templates/ — HTML Templates INDEX

Single-page application shell for the Angelus workbench.

## Route Map — Leaf Files

| File | Purpose |
|------|---------|
| `index.html` | Full SPA shell: session sidebar, chat and live steer composers, modal settings with left navigation (global connectors; session-local Agent settings and searchable memory-session grants), new-session and connector dialogs, stop/force-stop controls, and inspector tabs (plan/Agents/trace/usage). It loads the active classic script `static/app.js` and `app.css`; it does **not** load the legacy ES modules in `static/`. |
