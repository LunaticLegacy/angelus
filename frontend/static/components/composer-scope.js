/** Composer-scope controls: which connector and which tools this session runs with.
 *
 * Both values are keys of the session's run profile, which the Agent settings
 * page edits as well. This component keeps no copy of its own: it renders from
 * `readState()` and hands every change to `onConnector` / `onPermission`, so the
 * two editors can never disagree about a value.
 */
import { escapeHtml } from "./dom.js";

/** Enabled-versus-total counts for the chip, e.g. ``2/6 类别 · 7/18 项``. */
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

/** One checkbox list: every category, each with the tools it owns. */
function panelMarkup(state) {
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
 * Bind the two composer controls to one input box.
 *
 * @param {object} options
 * @param {HTMLSelectElement} options.connector Session connector selector.
 * @param {HTMLButtonElement} options.chip Opens the tool panel.
 * @param {HTMLElement} options.summary Chip's count slot.
 * @param {HTMLElement} options.panel Popover holding both permission axes.
 * @param {() => object} options.readState Returns `{connectors, connectorId,
 *   policy, catalog}` - everything a render needs, read fresh each time.
 * @param {(id: string) => void} options.onConnector Chosen connector id.
 * @param {(patch: object) => void} options.onPermission `{category|tool, enabled}`.
 * @param {() => void} [options.onOpen] Called before the panel is shown.
 * @returns {{refresh: Function, close: Function}}
 */
export function createComposerScope({ connector, chip, summary, panel, readState, onConnector, onPermission, onOpen }) {
  let open = false;

  /** Show or hide the permission popover, keeping the chip's state in step. */
  function setOpen(next) {
    open = next;
    panel.hidden = !open;
    chip.setAttribute("aria-expanded", String(open));
    chip.classList.toggle("is-open", open);
    if (open) onOpen?.();
  }

  /** Redraw the connector list, the chip's counts and the panel when it is up. */
  function refresh() {
    const state = readState() || {};
    const choices = state.connectors || [];
    const current = state.connectorId || "";
    connector.innerHTML = [
      '<option value="">临时连接</option>',
      ...choices.map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.name)}</option>`),
    ].join("");
    // A stored id whose connector has gone must not leave the wrong one showing.
    connector.value = choices.some((item) => item.id === current) ? current : "";
    summary.textContent = summarize(state);
    chip.title = `当前会话的工具集：${summary.textContent || "尚未注册工具"}`;
    if (open) panel.innerHTML = `<div class="tool-panel-head"><strong>当前会话工具集</strong><small>类别与单工具须同时开启；改动立即写入本会话档案</small></div><div class="tool-panel-body">${
      (state.catalog || []).length ? panelMarkup(state) : '<p class="tool-panel-empty">正在读取后端注册的工具…</p>'
    }</div>`;
  }

  connector.addEventListener("change", () => onConnector(connector.value));
  chip.addEventListener("click", () => setOpen(!open));
  panel.addEventListener("change", (event) => {
    const input = event.target;
    if (input.dataset.composerCategory) onPermission({ category: input.dataset.composerCategory, enabled: input.checked });
    else if (input.dataset.composerTool) onPermission({ tool: input.dataset.composerTool, enabled: input.checked });
  });
  // A click anywhere else, or Escape, closes the popover without changing it.
  document.addEventListener("pointerdown", (event) => {
    if (!open) return;
    if (panel.contains(event.target) || chip.contains(event.target)) return;
    setOpen(false);
  });
  document.addEventListener("keydown", (event) => {
    if (open && event.key === "Escape") setOpen(false);
  });

  return { refresh, close: () => setOpen(false) };
}
