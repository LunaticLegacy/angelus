/**
 * Presentation frontier for the desktop client.
 *
 * This module owns shell-level concerns only: DOM lookup, theme preference,
 * and navigation between inspector surfaces. It deliberately knows nothing
 * about API payloads or backend URLs.
 */
export function element(id) { return document.getElementById(id); }

export function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  return theme;
}

export function readTheme(fallback = "dark") {
  try { return localStorage.getItem("llmfetcherTheme") || fallback; }
  catch { return fallback; }
}

export function persistTheme(theme) {
  try { localStorage.setItem("llmfetcherTheme", theme); } catch { /* private mode */ }
}

export function bindInspectorNavigation({ storageKey = "llmfetcherInspectorPanel", onChange } = {}) {
  const buttons = [...document.querySelectorAll("[data-inspector-panel]")];
  const activate = (panelId) => {
    buttons.forEach((button) => {
      const active = button.dataset.inspectorPanel === panelId;
      button.classList.toggle("active", active);
      button.setAttribute("aria-selected", String(active));
    });
    document.querySelectorAll(".inspector-panel").forEach((panel) => {
      panel.classList.toggle("active", panel.id === panelId);
    });
    try { localStorage.setItem(storageKey, panelId); } catch { /* private mode */ }
    onChange?.(panelId);
  };
  buttons.forEach((button) => button.addEventListener("click", () => activate(button.dataset.inspectorPanel)));
  activate(readStored(storageKey) || buttons[0]?.dataset.inspectorPanel);
  return { activate };
}

function readStored(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}
