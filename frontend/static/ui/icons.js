/**
 * The shell's one stroke-icon set.
 *
 * Every icon is drawn on a 24×24 grid with strokes only, so a button's colour
 * flows into its icon (`currentColor`) and nothing needs a second file, a font
 * or a network request. Markup asks for an icon by name — `data-icon="refresh"`
 * — and `hydrateIcons()` paints it, which keeps the paths here instead of
 * scattered through the template.
 *
 * Sizes come from the container's font-size (`1em`), so a control that reads
 * `font-size:var(--fs-large)` gets a large icon for free.
 */

/** Path markup per name; keys are the vocabulary markup may ask for. */
const ICONS = {
  plan: '<path d="M9 6h11M9 12h11M9 18h11"/><path d="M4.5 6h.01M4.5 12h.01M4.5 18h.01"/>',
  agents:
    '<circle cx="12" cy="5" r="2.4"/><circle cx="6" cy="18" r="2.4"/><circle cx="18" cy="18" r="2.4"/><path d="M11 7.2 7 15.8M13 7.2 17 15.8"/>',
  trace: '<path d="M3 12h3.5l2.2-5.5 3.1 11 2.2-5.5H21"/>',
  usage: '<path d="M5 20V11M12 20V4M19 20v-6"/>',
  plugin: '<path d="M12 3.2 4 7.4v9.2l8 4.2 8-4.2V7.4z"/><path d="M4 7.4l8 4.3 8-4.3M12 11.7V21"/>',
  refresh: '<path d="M20 12a8 8 0 1 1-2.6-5.9"/><path d="M20 4v4.2h-4.2"/>',
  send: '<path d="M4.5 12 20 4.5l-6.6 15-2.4-6.4z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  minus: '<path d="M5 12h14"/>',
  close: '<path d="M6.5 6.5 17.5 17.5M17.5 6.5 6.5 17.5"/>',
  sidebar: '<path d="M3.5 5.5h17v13h-17z"/><path d="M9.5 5.5v13"/>',
  search: '<circle cx="11" cy="11" r="6.2"/><path d="M15.6 15.6 20 20"/>',
  chevron: '<path d="M6.5 9.5 12 15l5.5-5.5"/>',
  external:
    '<path d="M13.5 4.5H20v6.5"/><path d="M20 4.5 11 13.5"/><path d="M18 14v4.5a1.5 1.5 0 0 1-1.5 1.5H5.5A1.5 1.5 0 0 1 4 18.5V7.5A1.5 1.5 0 0 1 5.5 6H10"/>',
  settings: '<path d="M4 7h9M17 7h3M4 17h4M12 17h8"/><path d="M15 4.5v5M10 14.5v5"/>',
  theme: '<path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z"/>',
  model: '<path d="M12 3.2 20.8 12 12 20.8 3.2 12z"/>',
  collapse: '<path d="M14.5 6.5 9 12l5.5 5.5"/>',
};

/**
 * Markup for one icon.
 *
 * @param {string} name Key in the icon set; unknown names fall back to the
 *   generic plugin glyph so a typo degrades instead of rendering nothing.
 * @returns {string} A self-contained `<svg>` sized in `em`.
 */
export function icon(name) {
  const body = ICONS[name] || ICONS.plugin;
  return (
    '<svg class="icon" viewBox="0 0 24 24" width="1em" height="1em" fill="none" ' +
    'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" ' +
    `stroke-linejoin="round" aria-hidden="true" focusable="false">${body}</svg>`
  );
}

/**
 * Paint every `data-icon` host inside a subtree.
 *
 * The icon is inserted rather than replacing the host's content, so a control
 * may keep a tooltip span beside it. Safe to call twice.
 *
 * @param {Document|Element} [root] Subtree to hydrate; defaults to the page.
 * @returns {void}
 */
export function hydrateIcons(root = document) {
  const scope = typeof root.querySelectorAll === "function" ? root : document;
  scope.querySelectorAll("[data-icon]").forEach((host) => {
    if (host.querySelector(":scope > .icon")) return;
    host.insertAdjacentHTML("afterbegin", icon(host.dataset.icon));
  });
}

/** Names the set answers for, so tooling can check a template. */
export const ICON_NAMES = Object.keys(ICONS);
