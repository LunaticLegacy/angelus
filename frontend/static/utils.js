/** Pure utility functions — no state, no DOM, no side effects. */

export function $(id) {
  return document.getElementById(id);
}

export function escapeHtml(text) {
  const node = document.createElement("div");
  node.textContent = text ?? "";
  return node.innerHTML;
}

export async function copyResult(text, button) {
  try {
    await navigator.clipboard.writeText(text);
    button.textContent = "已复制";
    setTimeout(() => (button.textContent = "复制结果"), 1200);
  } catch {
    button.textContent = "复制失败";
  }
}

export function formatDuration(ms) {
  if (ms == null) return "—";
  const sec = Math.floor(ms / 1000);
  return `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;
}

export function formatSeconds(ms) {
  if (ms == null) return "—";
  return `${(ms / 1000).toFixed(1)}s`;
}
