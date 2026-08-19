/** Return the element with the supplied static template ID. */
export function $(id) {
  return document.getElementById(id);
}

/** Escape arbitrary text before placing it in an HTML template string. */
export function escapeHtml(text) {
  const node = document.createElement("div");
  node.textContent = text ?? "";
  return node.innerHTML;
}
