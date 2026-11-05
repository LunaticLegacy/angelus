import { escapeHtml } from "./dom.js";

export function renderConnectorSelect(select, connectors, selectedId) {
  select.innerHTML = `<option value="">未保存的临时连接</option>${connectors
    .map((connector) => `<option value="${escapeHtml(connector.id)}">${escapeHtml(connector.name)}</option>`)
    .join("")}`;
  select.value = selectedId;
}
