import { apiDelete, apiJson, apiPost, apiPut } from "./backend-bridge.js";

export function listConnectors() {
  return apiJson("/api/connectors");
}

export function createConnector(payload) {
  return apiPost("/api/connectors", payload);
}

export function updateConnector(id, payload) {
  return apiPut(`/api/connectors/${encodeURIComponent(id)}`, payload);
}

export function deleteConnector(id) {
  return apiDelete(`/api/connectors/${encodeURIComponent(id)}`);
}
