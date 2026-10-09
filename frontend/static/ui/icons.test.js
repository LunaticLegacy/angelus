/* Unit tests for the shell icon set. Run: node --test frontend/static/ui/icons.test.js */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

test("every icon renders one self-contained stroke-only svg", async () => {
  const { icon, ICON_NAMES } = await import("./icons.js");

  assert.ok(ICON_NAMES.length >= 15, `expected a full set, got ${ICON_NAMES.length}`);
  for (const name of ICON_NAMES) {
    const markup = icon(name);
    assert.match(markup, /^<svg class="icon" viewBox="0 0 24 24"/, name);
    assert.match(markup, /stroke="currentColor"/, name);
    assert.match(markup, /stroke-width="1\.8"/, name);
    assert.match(markup, /fill="none"/, name);
    assert.match(markup, /<\/svg>$/, name);
    // Colour has to come from the host, so no paint may be baked in.
    assert.doesNotMatch(markup, /(?:fill|stroke)="#/, name);
  }
});

test("an unknown name degrades to the generic glyph", async () => {
  const { icon } = await import("./icons.js");

  assert.equal(icon("no-such-icon"), icon("plugin"));
});

test("the set is unique and every name is a plain identifier", async () => {
  const { ICON_NAMES } = await import("./icons.js");

  assert.equal(new Set(ICON_NAMES).size, ICON_NAMES.length);
  for (const name of ICON_NAMES) assert.match(name, /^[a-z][a-z0-9-]*$/, name);
});
