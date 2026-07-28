/**
 * Session (workspace) CRUD and list rendering.
 */

import { $, escapeHtml } from "./utils.js";
import { getState, setState } from "./state.js";
import { apiJson, apiPost, apiDelete } from "./api.js";

/* ---- data ---- */

export async function loadAll(selectedId) {
  const { sessions } = await apiJson("/api/sessions");
  if (!sessions.length) throw new Error("会话列表为空");

  /* pick the right session */
  const target =
    sessions.some((s) => s.id === selectedId) ? selectedId : sessions[0].id;

  setState({ sessionId: target, workspaceId: target });
  localStorage.llmfetcherWorkspace = target;
  localStorage.llmfetcherSession = target;

  renderSelect(sessions, target);
  renderRecent(sessions, target);

  return sessions;
}

/* ---- render ---- */

export function renderSelect(sessions, selectedId) {
  const select = $("workspace");
  select.innerHTML = sessions
    .map(
      (s) =>
        `<option value="${escapeHtml(s.id)}">${escapeHtml(s.name)}</option>`
    )
    .join("");
  select.value = selectedId;
}

export function renderRecent(sessions, selectedId) {
  const container = $("recent-sessions");
  container.innerHTML = sessions
    .slice(0, 5)
    .map(
      (s) =>
        `<button class="recent-session ${s.id === selectedId ? "active" : ""}" type="button" data-workspace-id="${escapeHtml(s.id)}">${escapeHtml(s.name)}</button>`
    )
    .join("");
}

/* ---- CRUD ---- */

export async function create(name) {
  return apiPost("/api/sessions", { name });
}

export async function remove(id, confirmation) {
  return apiDelete(`/api/sessions/${id}`, { confirmation });
}
