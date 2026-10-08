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
  const activity = document.querySelector(".activity");
  const activate = (panelId, open = true) => {
    buttons.forEach((button) => {
      const active = button.dataset.inspectorPanel === panelId;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active && open));
    });
    document.querySelectorAll(".inspector-panel").forEach((panel) => {
      panel.classList.toggle("active", panel.id === panelId);
    });
    activity?.setAttribute("data-inspector-open", String(open));
    document.body.classList.toggle("inspector-open", open);
    try { localStorage.setItem(storageKey, panelId); } catch { /* private mode */ }
    onChange?.(panelId, open);
  };
  buttons.forEach((button) => button.addEventListener("click", () => {
    const panelId = button.dataset.inspectorPanel;
    const isCurrent = button.classList.contains("active");
    const isOpen = activity?.dataset.inspectorOpen === "true";
    activate(panelId, !(isCurrent && isOpen));
  }));
  const initial = readStored(storageKey) || buttons[0]?.dataset.inspectorPanel;
  if (initial) activate(initial, false);
  return { activate };
}

function readStored(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}

function updateShellButton(button, collapsed, expandedLabel, collapsedLabel) {
  if (!button) return;
  button.setAttribute("aria-expanded", String(!collapsed));
  button.setAttribute("title", collapsed ? collapsedLabel : expandedLabel);
  button.setAttribute("aria-label", collapsed ? collapsedLabel : expandedLabel);
}

export function initShellLayout() {
  const sidebar = document.getElementById("sidebar");
  const activity = document.querySelector(".activity");
  if (!sidebar || !activity) return;

  sidebar.id = sidebar.id || "sidebar";
  activity.id = activity.id || "activity";
  const sidebarToggle = document.getElementById("toggle-sidebar") || document.createElement("button");
  sidebarToggle.id = "toggle-sidebar";
  sidebarToggle.className = "shell-toggle sidebar-toggle";
  sidebarToggle.type = "button";
  sidebarToggle.innerHTML = '<span aria-hidden="true">‹</span>';
  sidebarToggle.setAttribute("aria-controls", sidebar.id);
  if (!sidebarToggle.parentElement) sidebar.append(sidebarToggle);
  const sidebarCollapsed = readStored("angelus.sidebarCollapsed") === "true";
  document.body.classList.toggle("sidebar-collapsed", sidebarCollapsed);
  updateShellButton(sidebarToggle, sidebarCollapsed, "收起侧栏", "展开侧栏");

  sidebarToggle.addEventListener("click", () => {
    const collapsed = document.body.classList.toggle("sidebar-collapsed");
    try { localStorage.setItem("angelus.sidebarCollapsed", String(collapsed)); } catch { /* private mode */ }
    updateShellButton(sidebarToggle, collapsed, "收起侧栏", "展开侧栏");
  });
  activity.setAttribute("data-inspector-open", "false");
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && activity.dataset.inspectorOpen === "true") {
      activity.setAttribute("data-inspector-open", "false");
      document.body.classList.remove("inspector-open");
      document.querySelector("[data-inspector-panel].active")?.setAttribute("aria-pressed", "false");
    }
  });
}
