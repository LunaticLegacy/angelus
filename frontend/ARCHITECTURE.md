# Desktop frontend boundary

The desktop client is split into two frontiers:

## Presentation frontier (`static/ui/` and `static/components/`)

Owns DOM structure, visual state, accessibility, themes, inspector navigation,
transcript rendering, composer behavior, and responsive layout. It should not
know backend URLs or parse transport envelopes.

## Runtime frontier (`static/runtime/` and `static/api.js`)

Owns REST requests, server-sent events, local persistence, session/run state,
and backend error normalization. It should expose stable methods and events to
the presentation layer rather than manipulating DOM nodes.

`static/app.js` remains the composition root while the migration is underway:
it wires the two frontiers and owns cross-feature orchestration. New features
should add transport code under `runtime/` and view code under `ui/` or
`components/`, then connect them from the composition root.

The initial boundary is implemented by:

- `runtime/backend-bridge.js`: API exports, event-stream adapter, storage adapter
- `ui/shell.js`: DOM lookup, theme persistence, inspector navigation

This keeps the current API contract intact while making a future Tauri/native
transport replaceable without reworking the interface.

## Localization

`static/i18n.js` loads locale data from `static/locales/*.json`. The selected
locale is stored as `angelusLocale`; unsupported or failed locale loads fall
back to English. Adding a language means adding a JSON file and registering its
locale code in `LOCALE_FILES`, without adding language branches to components.
