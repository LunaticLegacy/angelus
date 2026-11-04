/** Composer-scope controls: which connector, which tools, and which order the
 * context blocks of the next request compose in.
 *
 * Both values are keys of the session's run profile, which the Agent settings
 * page edits as well. This component keeps no copy of its own: it renders from
 * `readState()` and hands every change to `onConnector` / `onPermission`, so the
 * two editors can never disagree about a value.
 *
 * Both controls are chips over upward popovers rather than native selects: the
 * composer sits at the bottom of the window, where a native dropdown opens
 * downwards and off-screen, and its direction is not something CSS can fix.
 *
 * The tool panel follows the workbench reference: one card per category in a
 * grid whose column count comes from the width it gets, a category switch that
 * opens or closes every tool it owns, per-tool switches that appear only while
 * their category is on, and the system prompt the run will use.
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

/** The system prompt the next run will use, beside the toolset that governs it. */
function promptMarkup() {
  return '<label class="tool-panel-prompt"><span>系统提示词（仅下次运行生效）</span><textarea id="composer-system-prompt" rows="4" spellcheck="false"></textarea></label>';
}

/**
 * One card per category: a switch for the whole category, then its tools.
 *
 * A tool is allowed only while its category is, so a category that is off hides
 * its tools instead of showing switches that cannot take effect.
 */
function cardMarkup(state) {
  const groups = state.catalog || [];
  const categories = state.policy?.categories || {};
  const tools = state.policy?.tools || {};
  return `<div class="tool-cards">${groups
    .map((group) => {
      const on = categories[group.id] === true;
      const rows = group.tools
        .map(
          ([id, title]) => `<label class="toggle-line tool-row"><span>${escapeHtml(
            title
          )}</span><input type="checkbox" data-composer-tool="${escapeHtml(id)}"${
            tools[id] === true ? " checked" : ""
          } aria-label="${escapeHtml(title)}" /><i></i></label>`
        )
        .join("");
      return `<section class="tool-card${on ? " is-on" : ""}">
          <label class="toggle-line tool-card-head"><span>${escapeHtml(
            group.title
          )}</span><input type="checkbox" data-composer-category="${escapeHtml(group.id)}"${
            on ? " checked" : ""
          } aria-label="${escapeHtml(group.title)}" /><i></i></label>
          ${on && rows ? `<div class="tool-card-tools">${rows}</div>` : ""}
        </section>`;
    })
    .join("")}</div>`;
}

/** Human-readable size for one block row, or a dash when nothing composed. */
function charactersText(row) {
  const count = Number(row.characters || 0);
  if (!count) return "—";
  return count < 1000 ? `${count} 字` : `${(count / 1000).toFixed(1)}k 字`;
}

/** Badges that qualify a row without changing the position it occupies. */
function orderBadges(row) {
  const badges = [];
  if (row.unlisted) badges.push('<em class="order-badge">未排序</em>');
  if (row.present === false) badges.push('<em class="order-badge is-absent">本次未包含</em>');
  if (row.persisted) badges.push('<em class="order-badge is-quiet">已持久化</em>');
  return badges.join("");
}

/**
 * The context block order editor: one row per source, in the order the next
 * run will compose it.
 *
 * Rows, labels and the order itself all arrive from the backend preview, so
 * this markup never invents either. A move is only reported as two indices;
 * buttons rather than dragging because the panel must stay keyboard-reachable.
 */
function orderMarkup(order) {
  const rows = order?.rows || [];
  const busy = order?.busy === true;
  const failure = order?.error || "";
  const editable = !busy && !failure && rows.length > 1;
  const head = `<div class="tool-panel-head order-head"><strong>上下文块顺序</strong><small>改动立即写入本会话运行档案；下次运行生效</small><button type="button" class="order-reset" data-order-action="reset"${editable ? "" : " disabled"}>重置</button></div>`;
  if (failure) return `${head}<p class="tool-panel-empty order-error">${escapeHtml(failure)}</p>`;
  if (!rows.length) {
    return `${head}<p class="tool-panel-empty">${busy ? "正在读取上下文块…" : "这次运行没有可排序的上下文块。"}</p>`;
  }
  const items = rows
    .map((row, index) => {
      const label = row.label || row.source || "";
      const up = editable && index > 0;
      const down = editable && index < rows.length - 1;
      return `<li class="order-row${row.present === false ? " is-absent" : ""}">
          <span class="order-index">${index + 1}</span>
          <span class="order-label"><span>${escapeHtml(label)}</span>${orderBadges(row)}</span>
          <span class="order-size">${charactersText(row)}</span>
          <button type="button" class="order-move" data-order-action="up" data-order-index="${index}" aria-label="上移"${up ? "" : " disabled"}>↑</button>
          <button type="button" class="order-move" data-order-action="down" data-order-index="${index}" aria-label="下移"${down ? "" : " disabled"}>↓</button>
        </li>`;
    })
    .join("");
  return `${head}<ol class="order-list"${busy ? ' aria-busy="true"' : ""}>${items}</ol>`;
}

/**
 * Bind the composer's two scope controls into one input box.
 *
 * @param {object} options
 * @param {HTMLButtonElement} options.connectorChip Shows the session connector.
 * @param {HTMLElement} options.connectorPanel Popover listing the connectors.
 * @param {HTMLButtonElement} options.chip Tool chip, carrying the counts.
 * @param {HTMLElement} options.summary Chip's count slot.
 * @param {HTMLElement} options.panel Popover holding the prompt and both axes.
 * @param {() => object} options.readState Returns `{connectors, connectorId,
 *   policy, catalog, systemPrompt, order}` - everything a render needs, read
 *   fresh. `order` is `{rows, handler, error, busy}` and already sorted by the
 *   backend, so nothing here has to know what a block priority means.
 * @param {(id: string) => void} options.onConnector Chosen connector id.
 * @param {(patch: object) => void} options.onPermission `{category|tool, enabled}`.
 * @param {(text: string) => void} options.onSystemPrompt Committed prompt text.
 * @param {(from: number, to: number) => void} [options.onReorder] Move one
 *   context block from one index of the visible order to another.
 * @param {() => void} [options.onResetOrder] Drop the saved order.
 * @param {(target: string) => void} [options.onOpen] Called with the popover
 *   that is about to be shown, before it is painted.
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
  onSystemPrompt,
  onReorder,
  onResetOrder,
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
    if (!target) return;
    onOpen?.(target);
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
    chip.title = `当前会话的设置：${summary.textContent || "尚未注册工具"}`;
    if (openPopover === "connector") {
      connectorPanel.innerHTML = `<div class="composer-popover-head"><strong>当前会话连接器</strong><small>写入本会话运行档案</small></div>${connectorMarkup(
        state
      )}`;
    }
    if (openPopover === "tools") {
      // A repaint drops focus and the caret, so a prompt being typed into has
      // to survive the refresh that follows every save and every preview.
      const active = document.activeElement;
      const typing = active?.id === "composer-system-prompt"
        ? [active.selectionStart, active.selectionEnd]
        : null;
      panel.innerHTML = `<div class="tool-panel-head"><strong>本条消息的设置</strong><small>类别与单工具须同时开启；改动立即写入本会话档案</small></div>${promptMarkup()}${
        (state.catalog || []).length ? cardMarkup(state) : '<p class="tool-panel-empty">正在读取后端注册的工具…</p>'
      }${orderMarkup(state.order)}`;
      // The prompt is prose: assign it as a value rather than into markup.
      const field = panel.querySelector("#composer-system-prompt");
      if (field) {
        field.value = state.systemPrompt || "";
        if (typing) {
          field.focus();
          field.setSelectionRange(typing[0], typing[1]);
        }
      }
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
    if (input.id === "composer-system-prompt") onSystemPrompt(input.value);
    else if (input.dataset.composerCategory) onPermission({ category: input.dataset.composerCategory, enabled: input.checked });
    else if (input.dataset.composerTool) onPermission({ tool: input.dataset.composerTool, enabled: input.checked });
  });
  // A move is reported, never applied here: the caller stores the order in
  // the run profile and the next render reads it back from a fresh preview,
  // so this component keeps no order of its own that could be written stale.
  panel.addEventListener("click", (event) => {
    const control = event.target.closest("[data-order-action]");
    if (!control || control.disabled) return;
    if (control.dataset.orderAction === "reset") {
      onResetOrder?.();
      return;
    }
    const rows = readState()?.order?.rows || [];
    const from = Number(control.dataset.orderIndex);
    const to = control.dataset.orderAction === "up" ? from - 1 : from + 1;
    if (!Number.isInteger(from) || from < 0 || to < 0) return;
    if (from >= rows.length || to >= rows.length) return;
    onReorder?.(from, to);
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
