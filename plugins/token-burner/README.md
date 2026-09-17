# Token Burner 🔥 — Angelus UI plugin 0.2.0

This is the DSH-inspired rewrite of Angelus Token Burner for the **current Angelus plugin API v1**.

## What changed

The old 0.1.x implementation was treated like a historical hybrid plugin. This package is now deliberately **frontend-only**:

- `kind: "ui"`
- **no `entry`**
- **no `main.py` / Python plugin runtime**
- static assets are manifest-whitelisted
- behavioral settings use Angelus host-owned `settings_schema`
- browser `localStorage` is used only for UI state (position / collapsed / size)
- the selected Session is read only from the current workbench selection key `llmfetcherSession` (or the explicit `?session=` in the detached window)

That matches the current implementation: only `kind: "tool"` plugins execute a Python entrypoint; UI packages are declarative/browser assets.

## DSH design ideas carried over

DSH has a clean model: Session token accounting is a projection, the UI observes it, and the flame is a presentation of that projection rather than a second accounting system.

Angelus does not yet expose DSH-style browser projection hooks or a `shell.overlay` slot to third-party UI plugins, so this version maps the same idea onto the current Angelus surfaces:

| DSH concept | Angelus 0.5.x mapping |
| --- | --- |
| `tokenUsage` Session projection | `GET /api/sessions/{session_id}/usage` |
| Session `running` observable | `GET /api/runs/{session_id}/status` |
| `shell.overlay` | one isolated fixed DOM root (`data-angelus-plugin="token-burner"`) |
| profile/plugin config | manifest `settings_schema` + plugin settings API |
| projection delta → flame | cumulative Session total delta → impulse → exponential decay |

The overlay root is marked with `data-angelus-plugin`, so Angelus' frontend plugin unload path removes it. The plugin also detects removal and stops its timers.

## Burn-rate semantics

The displayed `tok/s` is an **ambient visual burn rate**, not provider streaming decode throughput.

Angelus exposes authoritative cumulative Session usage. When that cumulative total increases, Token Burner converts the delta into an impulse and then decays it smoothly. This is suitable for a telemetry toy and avoids pretending that the browser sees every provider token event.

The intensity mapping is logarithmic, so a 200 tok/s run and a 5,000 tok/s burst both remain visually useful without a hard linear saturation cliff.

## Files

```text
token-burner/
├── manifest.json
├── plugin.js
├── plugin.css
├── window.html
├── README.md
└── DESIGN.md
```

There is intentionally **no Python file**.

## Development install

Drop/replace the directory under the Angelus repository development plugin root:

```text
plugins/token-burner/
```

Then use the Workbench plugin UI:

1. Rescan plugins.
2. Register / “add to Workbench” if needed.
3. Load/enable `token-burner`.

The current plugin manager discovers manifests without importing code and only serves whitelisted frontend assets for active plugins.

## Settings

Host-persisted behavior settings:

- `poll_ms`: projection refresh interval (500–5000 ms)
- `decay_ms`: burn impulse decay time
- `rate_scale`: logarithmic full-flame reference
- `show_total`
- `show_peak`
- `idle_flame`

UI-only browser state:

- floating window position
- collapsed state
- large/small state

## Commands

Registered through `window.Angelus.registerCommand`:

- `token-burner:toggle`
- `token-burner:popout`
- `token-burner:reset-position`
- `token-burner:reload-settings`

## Future cleanup when Angelus grows a real overlay/projection bridge

The only compatibility seam that should need replacement is the browser adapter:

```text
current:
localStorage selected Session
  -> REST usage/status projection
  -> fixed DOM overlay

future:
Session projection hook
  -> tokenUsage observable
  -> official overlay slot
```

The telemetry model and flame renderer can remain unchanged.
