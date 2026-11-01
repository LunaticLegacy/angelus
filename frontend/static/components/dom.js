/**
 * Return a static template element by ID, or resolve an explicit CSS selector.
 *
 * Most workbench lookups use IDs, but shell-level layout nodes such as the
 * Inspector root are class selectors. Keeping both forms behind this helper
 * prevents components from reaching into document lookup details.
 */
export function $(query) {
  if (!query) return null;
  if (query.startsWith("#") || query.startsWith(".")) {
    return document.querySelector(query);
  }
  return document.getElementById(query);
}

/** Escape arbitrary text before placing it in an HTML template string. */
export function escapeHtml(text) {
  const node = document.createElement("div");
  node.textContent = text ?? "";
  return node.innerHTML;
}
