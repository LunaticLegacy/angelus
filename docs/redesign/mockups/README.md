# Redesign mockups

Static, self-contained visual references for the Angelus Agent Workbench redesign. Nothing here is loaded by the running app; these files exist only to communicate the intended look to a reader of the design document, and to serve as a build target for the real implementation. No Angelus application or frontend code is touched by these artifacts.

## Files

| File | Purpose |
| --- | --- |
| `README.md` | This index. |
| `visual-philosophy.md` | The written design movement (The Signal Ledger): colour, type, space, motion, and voice principles that the layout obeys. |
| `workbench-mockup.html` | A single self-contained HTML page that renders the full three-zone workbench at desktop width, with the redesign token system applied inline. No build step, no external assets. |

## How to view

Open `workbench-mockup.html` directly in a browser (double-click, or drag it onto a browser window). It has no dependencies and needs no server. It is designed for a desktop viewport around 1280px or wider; narrow the window to see the two reduced breakpoints described in the design document.

## What the mockup is showing

The mockup is a static portrait of one moment in a session. It shows, left to right:

- **Rail (248px):** brand plate, workspace selector, a filter field, the recent-session ledger, and a footer of shell actions.
- **Stage (fluid, min 560px):** the run header (status, tokens, duration, stop controls), the agent strip, the transcript with a live marker, and the composer with its steering hint and attachment affordances.
- **Bay (368px):** the four inspector tabs (Plan, Agents, Trace, Usage) with the Trace tab active, showing a streamed event ledger.

The values are illustrative, not live. The data shapes mirror the real API payloads described in `../frontend-redesign-v0.6.0.md` so the mockup can be lifted into the app as a presentational shell while the existing `app.js` continues to own behaviour.

## Constraints honoured

- Self-contained: one HTML file, inline CSS, system/Google-free font stack declared as a comment, inline SVG icons, no scripts required for layout.
- No dependency on, and no modification of, anything under `frontend/`.
- Bilingual-ready: copy is written so an `i18n` layer can swap strings without reflowing the layout.
