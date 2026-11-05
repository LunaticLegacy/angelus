import { escapeHtml } from "./dom.js";

export function renderSessionList({ select, recent, sessions, selectedId, onSelect, onOpen, onDelete, hydrateIcons }) {
  select.disabled = false;
  select.innerHTML = sessions
    .map((session) => `<option value="${escapeHtml(session.id)}">${escapeHtml(session.name)}</option>`)
    .join("");
  select.value = selectedId;

  recent.innerHTML = sessions
    .map((session) => sessionMarkup(session, selectedId))
    .join("");
  hydrateIcons(recent);

  // Bind the selectable button directly. The row listener used to rely on
  // bubbling through several nested controls, which made a click appear to
  // select the row without reliably entering the Session loading path.
  recent.querySelectorAll("[data-session-select]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      onSelect(button.dataset.sessionSelect);
    });
  });
  recent.querySelectorAll("[data-session-open]").forEach((button) => {
    button.addEventListener("click", () => onOpen(button.dataset.sessionOpen));
  });
  recent.querySelectorAll("[data-session-delete]").forEach((button) => {
    button.addEventListener("click", () => onDelete(button.dataset.sessionDelete, button.dataset.sessionName));
  });
  recent.querySelector(".active")?.scrollIntoView({ block: "nearest" });
}

function sessionMarkup(session, selectedId) {
  const id = escapeHtml(session.id);
  const name = escapeHtml(session.name);
  const active = session.id === selectedId ? "active" : "";
  const status = escapeHtml(session.status || "idle");
  return `<article class="recent-session ${active}" data-session-id="${id}" data-status="${status}"><button class="recent-session-select" type="button" data-session-select="${id}" title="切换到 ${name}"><span>${name}</span></button><div class="recent-session-actions"><button class="recent-session-action" type="button" data-session-open="${id}" title="打开该会话的工作目录" aria-label="打开该会话的工作目录" data-icon="external"></button><button class="recent-session-action danger" type="button" data-session-delete="${id}" data-session-name="${name}" title="删除该会话" aria-label="删除该会话" data-icon="trash"></button></div></article>`;
}
