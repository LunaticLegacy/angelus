/**
 * Connector CRUD and select rendering.
 */

import { $, escapeHtml } from "./utils.js";
import { getState, setState } from "./state.js";
import { apiJson, apiPost, apiPut, apiDelete } from "./api.js";
import { getConfig } from "./settings.js";

/* ---- data ---- */

export async function loadAll(selectedId) {
  const { connectors } = await apiJson("/api/connectors");
  const target = connectors.some((c) => c.id === selectedId)
    ? selectedId
    : "";

  setState({ connectorId: target });
  localStorage.llmfetcherConnector = target;

  renderSelect(connectors, target);

  const connector = connectors.find((c) => c.id === target);
  return { connectors, connector };
}

/* ---- render ---- */

export function renderSelect(connectors, selectedId) {
  const select = $("connector");
  select.innerHTML = `<option value="">未保存的临时连接</option>${connectors
    .map(
      (c) =>
        `<option value="${escapeHtml(c.id)}">${escapeHtml(c.name)}</option>`
    )
    .join("")}`;
  select.value = selectedId;
}

/* ---- CRUD ---- */

function _payload(name) {
  return { name, ...getConfig() };
}

export async function create(name) {
  return apiPost("/api/connectors", _payload(name));
}

export async function update(id, name) {
  return apiPut(`/api/connectors/${id}`, _payload(name));
}

export async function remove(id) {
  return apiDelete(`/api/connectors/${id}`);
}
