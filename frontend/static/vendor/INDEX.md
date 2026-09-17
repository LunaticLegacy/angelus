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

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [dompurify/purify.es.mjs](dompurify/purify.es.mjs#L59) | `unapply` | `func: unknown` | `unknown` | Perform the browser runtime operation: unapply. |
| [dompurify/purify.es.mjs](dompurify/purify.es.mjs#L76) | `unconstruct` | `func: unknown` | `unknown` | Perform the browser runtime operation: unconstruct. |
| [dompurify/purify.es.mjs](dompurify/purify.es.mjs#L92) | `addToSet` | `set: unknown, array: unknown` | `unknown` | Perform the browser runtime operation: add to set. |
| [dompurify/purify.es.mjs](dompurify/purify.es.mjs#L123) | `cleanArray` | `array: unknown` | `unknown` | Perform the browser runtime operation: clean array. |
| [dompurify/purify.es.mjs](dompurify/purify.es.mjs#L138) | `clone` | `object: unknown` | `unknown` | Perform the browser runtime operation: clone. |
| [dompurify/purify.es.mjs](dompurify/purify.es.mjs#L161) | `lookupGetter` | `object: unknown, prop: unknown` | `unknown` | Perform the browser runtime operation: lookup getter. |
| [dompurify/purify.es.mjs](dompurify/purify.es.mjs#L174) | `fallbackValue` | `None` | `unknown` | Perform the browser runtime operation: fallback value. |
| [dompurify/purify.es.mjs](dompurify/purify.es.mjs#L299) | `createDOMPurify` | `None` | `unknown` | Perform the browser runtime operation: create dom purify. |
| [dompurify/purify.es.mjs](dompurify/purify.es.mjs#L876) | `_executeHooks` | `hooks: unknown, currentNode: unknown, data: unknown` | `unknown` | Perform the browser runtime operation: execute hooks. |
| [marked/marked.esm.js](marked/marked.esm.js#L14) | `_getDefaults` | `None` | `unknown` | Perform the browser runtime operation: get defaults. |
| [marked/marked.esm.js](marked/marked.esm.js#L29) | `changeDefaults` | `newDefaults: unknown` | `unknown` | Perform the browser runtime operation: change defaults. |
| [marked/marked.esm.js](marked/marked.esm.js#L35) | `edit` | `regex: unknown, opt: unknown` | `unknown` | Perform the browser runtime operation: edit. |
| [marked/marked.esm.js](marked/marked.esm.js#L261) | `escape2` | `html2: unknown, encode: unknown` | `unknown` | Perform the browser runtime operation: escape 2. |
| [marked/marked.esm.js](marked/marked.esm.js#L273) | `cleanUrl` | `href: unknown` | `unknown` | Perform the browser runtime operation: clean url. |
| [marked/marked.esm.js](marked/marked.esm.js#L281) | `splitCells` | `tableRow: unknown, count: unknown` | `unknown` | Perform the browser runtime operation: split cells. |
| [marked/marked.esm.js](marked/marked.esm.js#L311) | `rtrim` | `str: unknown, c: unknown, invert: unknown` | `unknown` | Perform the browser runtime operation: rtrim. |
| [marked/marked.esm.js](marked/marked.esm.js#L329) | `findClosingBracket` | `str: unknown, b: unknown` | `unknown` | Perform the browser runtime operation: find closing bracket. |
| [marked/marked.esm.js](marked/marked.esm.js#L353) | `outputLink` | `cap: unknown, link2: unknown, raw: unknown, lexer2: unknown, rules: unknown` | `unknown` | Perform the browser runtime operation: output link. |
| [marked/marked.esm.js](marked/marked.esm.js#L369) | `indentCodeCompensation` | `raw: unknown, text: unknown, rules: unknown` | `unknown` | Perform the browser runtime operation: indent code compensation. |
| [marked/marked.esm.js](marked/marked.esm.js#L2067) | `parse2` | `src: unknown, options2: unknown` | `unknown` | Perform the browser runtime operation: parse 2. |
| [marked/marked.esm.js](marked/marked.esm.js#L2131) | `marked` | `src: unknown, opt: unknown` | `unknown` | Perform the browser runtime operation: marked. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| — | — | `None` | `object` | 本索引范围不直接声明类；沿 Route Map 进入下级索引。 |

<!-- END GENERATED SYMBOL MAP -->
