# frontend/templates/ — HTML Templates INDEX

Single-page application shell for the Angelus workbench, including the Kimi Code connector option and its explanatory key hint.

## Route Map — Leaf Files

| File | Purpose |
|------|---------|
| `index.html` | Full SPA shell: session sidebar and transcript, a main-panel live steer composer, and durable applied steering displayed beside original user messages in chat; it also contains modal settings with left navigation (global connectors; session-local Agent settings, MCP enablement/server definitions, and searchable memory-session grants; plugin lifecycle status and persisted plugin settings), new-session and connector dialogs, stop/force-stop controls, and inspector tabs (plan/Agents/trace/usage). It loads `static/app.css`, the active global `static/slash.js` parser, and the ES-module composition root `static/app.js`; it does **not** import the legacy modules in `static/`. |
