# frontend/templates/ — HTML Templates INDEX

Single-page application shell for the Angelus workbench.

## Route Map — Leaf Files

| File | Purpose |
|------|---------|
| `index.html` | Full SPA shell: session sidebar and transcript, a main-panel live steer composer, and durable applied steering displayed beside original user messages in chat; it also contains modal settings with left navigation (global connectors; session-local Agent settings and searchable memory-session grants), new-session and connector dialogs, stop/force-stop controls, and inspector tabs (plan/Agents/trace/usage). It loads the active classic script `static/app.js` and `app.css`; it does **not** load the legacy ES modules in `static/`. |
