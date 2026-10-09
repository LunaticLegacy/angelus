/** Composer slash-command palette: what `/` offers, and how it is chosen.
 *
 * The catalog and the matching rules live in the global `slash.js` module
 * (loaded as a plain script before the shell), so this component only renders
 * their answer and owns the keyboard and pointer interaction.
 */
import { escapeHtml } from "./dom.js";

/** Row label for one command entry or one flag descriptor. */
function label(state, match) {
  if (state.mode === "flags") return `--${match.name}=${match.value || ""}`;
  return `/${match.command}${match.args ? ` ${match.args}` : ""}`;
}

/** Stable identity of a match list, used to decide when to reset the cursor. */
function signature(state, matches) {
  if (!state) return "";
  return matches.map((match) => `${match.command || ""}${match.name || ""}`).join("|");
}

/**
 * Bind a palette to one composer input.
 *
 * @param {object} options
 * @param {HTMLTextAreaElement} options.input Composer textarea.
 * @param {HTMLElement} options.root Panel container, hidden while closed.
 * @param {(entry: object) => string} options.describeAvailability Returns a
 *   short badge for a command that cannot act right now, else an empty string.
 * @returns {{refresh: Function, handleKeydown: Function, close: Function}}
 *   `handleKeydown` reports whether it consumed the key, so the composer's own
 *   Enter-to-send handler can stay last in line.
 */
export function createSlashPalette({ input, root, describeAvailability }) {
  let state = null;
  let matches = [];
  let active = 0;
  let open = false;

  function close() {
    if (!open) return;
    open = false;
    state = null;
    matches = [];
    active = 0;
    root.hidden = true;
    root.replaceChildren();
  }

  function highlight() {
    for (const row of root.querySelectorAll("[data-index]")) {
      const selected = Number(row.dataset.index) === active;
      row.classList.toggle("active", selected);
      row.setAttribute("aria-selected", String(selected));
    }
    root.querySelector(".slash-palette-row.active")?.scrollIntoView({ block: "nearest" });
  }

  function render() {
    const parts = [];
    let group = "";
    matches.forEach((match, index) => {
      const heading = state.mode === "flags" ? `/${state.command} 参数` : String(match.group || "");
      if (heading && heading !== group) {
        group = heading;
        parts.push(`<p class="slash-palette-group">${escapeHtml(heading)}</p>`);
      }
      const badge = state.mode === "flags" ? "" : describeAvailability(match);
      const row = [
        `class="slash-palette-row${badge ? " unavailable" : ""}"`,
        `data-index="${index}"`,
        'role="option"',
        `aria-selected="false"`,
      ].join(" ");
      parts.push(
        `<button type="button" ${row}><code>${escapeHtml(label(state, match))}</code>` +
          `<span>${escapeHtml(String(match.description || ""))}</span>` +
          (badge ? `<em>${escapeHtml(badge)}</em>` : "") +
          "</button>"
      );
    });
    root.innerHTML = parts.join("");
    root.hidden = false;
    highlight();
  }

  /** Accept one match, leaving the caret ready for the next token. */
  function accept(index) {
    const match = matches[index];
    const applied = applySlashSuggestion(input.value, state, match);
    if (!applied) {
      close();
      return;
    }
    input.value = applied.value;
    input.setSelectionRange(applied.caret, applied.caret);
    input.focus();
    input.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText" }));
    refresh();
  }

  /**
   * Recompute the palette from the composer's current text and caret.
   *
   * @returns {void}
   */
  function refresh() {
    const caret = input.selectionStart ?? input.value.length;
    const next = slashPaletteState(input.value, caret);
    if (!next.open) {
      close();
      return;
    }
    if (signature(state, matches) !== signature(next, next.matches)) active = 0;
    state = next;
    matches = next.matches;
    active = Math.max(0, Math.min(active, matches.length - 1));
    open = true;
    render();
  }

  /** Enter only completes an unfinished word; a finished command still sends. */
  function enterCompletes() {
    const match = matches[active];
    if (!match) return false;
    if (state.mode === "flags") return true;
    return input.value.slice(state.replaceFrom, state.replaceTo).toLowerCase() !== `/${match.command}`;
  }

  /**
   * Handle one composer keydown.
   *
   * @param {KeyboardEvent} event
   * @returns {boolean} True when the palette consumed the event.
   */
  function handleKeydown(event) {
    if (!open) return false;
    if (event.key === "Escape") {
      event.preventDefault();
      close();
      return true;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (matches.length) {
        const step = event.key === "ArrowDown" ? 1 : -1;
        active = (active + step + matches.length) % matches.length;
        highlight();
      }
      return true;
    }
    if (event.key === "Tab" || event.key === "Enter") {
      if (event.key === "Enter" && !enterCompletes()) return false;
      event.preventDefault();
      accept(active);
      return true;
    }
    return false;
  }

  // A pointer press on a row must not blur the composer, or the caret the
  // suggestion is computed from would be gone before the click arrives.
  root.addEventListener("pointerdown", (event) => event.preventDefault());
  root.addEventListener("pointerover", (event) => {
    const row = event.target.closest?.("[data-index]");
    if (!row) return;
    active = Number(row.dataset.index);
    highlight();
  });
  root.addEventListener("click", (event) => {
    const row = event.target.closest?.("[data-index]");
    if (row) accept(Number(row.dataset.index));
  });
  input.addEventListener("input", refresh);
  input.addEventListener("click", refresh);
  input.addEventListener("blur", close);

  return { refresh, handleKeydown, close };
}
