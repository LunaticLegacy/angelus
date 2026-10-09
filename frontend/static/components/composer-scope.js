/** Composer-scope controls: which connector and which tools this session runs with.
 *
 * Both values are keys of the session's run profile, which the Agent settings
 * page edits as well. This component keeps no copy of its own: it renders from
 * `readState()` and hands every change to `onConnector` / `onPermission`, so the
 * two editors can never disagree about a value.
 *
 * Both controls are chips over upward popovers rather than native selects: the
 * composer sits at the bottom of the window, where a native dropdown opens
 * downwards and off-screen, and its direction is not something CSS can fix.
 */
import { escapeHtml } from "./dom.js";

/** Enabled-versus-total counts for the tool chip, e.g. ``2/6 类别 · 7/18 项``. */
function summarize(state) {
  const groups = state.catalog || [];
  if (!groups.length) return "";
  const categories = state.policy?.categories || {};
  const tools = state.policy?.tools || {};
  const onCategories = groups.filter((group) => categories[group.id] === true).length;
  const allTools = groups.flatMap((group) => group.tools.map(([id]) => id));
  const onTools = allTools.filter((id) => tools[id] === true).length;
  return `${onCategories}/${groups.length} 类别 · ${onTools}/${allTools.length} 项`;
}

/** One row per connector, marking the session's current choice. */
function connectorMarkup(state) {
  const current = state.connectorId || "";
  const rows = [{ id: "", name: "临时连接" }, ...(state.connectors || [])];
  return rows
    .map(
      (item) =>
        `<button type="button" class="connector-option${item.id === current ? " active" : ""}" data-connector-id="${escapeHtml(
          item.id
        )}"${item.id === current ? ' aria-current="true"' : ""}><span>${escapeHtml(item.name)}</span></button>`
    )
    .join("");
}

/** One checkbox list: every category, each with the tools it owns. */
function toolMarkup(state) {
  const groups = state.catalog || [];
  const categories = state.policy?.categories || {};
  const tools = state.policy?.tools || {};
  return groups
    .map(
      (group) => `<section class="tool-panel-group">
        <label class="tool-panel-master"><input type="checkbox" data-composer-category="${escapeHtml(group.id)}"${
        categories[group.id] === true ? " checked" : ""
      } /><strong>${escapeHtml(group.title)}</strong></label>
        <div class="tool-panel-tools">${group.tools
          .map(
            ([id, title, note]) => `<label class="tool-panel-tool"><span><strong>${escapeHtml(
              title
            )}</strong><small>${escapeHtml(note || "")}</small></span><input type="checkbox" data-composer-tool="${escapeHtml(
              id
            )}"${tools[id] === true ? " checked" : ""} aria-label="${escapeHtml(title)}" /></label>`
          )
          .join("")}</div>
      </section>`
    )
    .join("");
}

/**
 * Bind the composer's two scope controls into one input box.
 *
 * @param {object} options
 * @param {HTMLButtonElement} options.connectorChip Shows the session connector.
 * @param {HTMLElement} options.connectorPanel Popover listing the connectors.
 * @param {HTMLButtonElement} options.chip Tool chip, carrying the counts.
 * @param {HTMLElement} options.summary Chip's count slot.
 * @param {HTMLElement} options.panel Popover holding both permission axes.
 * @param {() => object} options.readState Returns `{connectors, connectorId,
 *   policy, catalog}` - everything a render needs, read fresh each time.
 * @param {(id: string) => void} options.onConnector Chosen connector id.
 * @param {(patch: object) => void} options.onPermission `{category|tool, enabled}`.
 * @param {() => void} [options.onOpen] Called before a popover is shown.
 * @returns {{refresh: Function, close: Function}}
 */
export function createComposerScope({
  connectorChip,
  connectorPanel,
  chip,
  summary,
  panel,
  readState,
  onConnector,
  onPermission,
  onOpen,
}) {
  let openPopover = null;

  /** Show one popover, or none, painting it as it appears. */
  function setOpen(target) {
    openPopover = target;
    connectorPanel.hidden = target !== "connector";
    connectorChip.setAttribute("aria-expanded", String(target === "connector"));
    connectorChip.classList.toggle("is-open", target === "connector");
    panel.hidden = target !== "tools";
    chip.setAttribute("aria-expanded", String(target === "tools"));
    chip.classList.toggle("is-open", target === "tools");
    connectorChip.setAttribute("aria-controls", "composer-connector-panel");
    if (!target) return;
    onOpen?.();
    // A popover is only ever filled while it is up, so opening it has to paint.
    refresh();
  }

  /** Repaint both chips and whichever popover is currently shown. */
  function refresh() {
    const state = readState() || {};
    const choices = state.connectors || [];
    const current = state.connectorId || "";
    // A stored id whose connector has gone falls back rather than showing it.
    const selected = choices.find((item) => item.id === current);
    connectorChip.innerHTML = `<span>${escapeHtml(selected?.name || "临时连接")}</span>`;
    summary.textContent = summarize(state);
    chip.title = `当前会话的工具集：${summary.textContent || "尚未注册工具"}`;
    if (openPopover === "connector") {
      connectorPanel.innerHTML = `<div class="composer-popover-head"><strong>当前会话连接器</strong><small>写入本会话运行档案</small></div>${connectorMarkup(
        state
      )}`;
    }
    if (openPopover === "tools") {
      panel.innerHTML = `<div class="tool-panel-head"><strong>当前会话工具集</strong><small>类别与单工具须同时开启；改动立即写入本会话档案</small></div><div class="tool-panel-body">${
        (state.catalog || []).length ? toolMarkup(state) : '<p class="tool-panel-empty">正在读取后端注册的工具…</p>'
      }</div>`;
    }
  }

  connectorChip.addEventListener("click", () => setOpen(openPopover === "connector" ? null : "connector"));
  chip.addEventListener("click", () => setOpen(openPopover === "tools" ? null : "tools"));
  connectorPanel.addEventListener("click", (event) => {
    const option = event.target.closest("[data-connector-id]");
    if (!option) return;
    setOpen(null);
    onConnector(option.dataset.connectorId);
  });
  panel.addEventListener("change", (event) => {
    const input = event.target;
    if (input.dataset.composerCategory) onPermission({ category: input.dataset.composerCategory, enabled: input.checked });
    else if (input.dataset.composerTool) onPermission({ tool: input.dataset.composerTool, enabled: input.checked });
  });
  // A click anywhere else, or Escape, closes without changing anything.
  document.addEventListener("pointerdown", (event) => {
    if (!openPopover) return;
    if (connectorPanel.contains(event.target) || connectorChip.contains(event.target)) return;
    if (panel.contains(event.target) || chip.contains(event.target)) return;
    setOpen(null);
  });
  document.addEventListener("keydown", (event) => {
    if (openPopover && event.key === "Escape") setOpen(null);
  });

  return { refresh, close: () => setOpen(null) };
}
