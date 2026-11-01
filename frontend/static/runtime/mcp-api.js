import { apiDelete, apiJson, apiPost, apiPut } from "./backend-bridge.js";

function sessionPath(sessionId, suffix) {
  if (!sessionId) throw new Error("尚未选择会话");
  return `/api/sessions/${encodeURIComponent(sessionId)}${suffix}`;
}

export function listMcpServers() {
  return apiJson("/api/mcp/servers");
}

export function listMcpBindings(sessionId) {
  return apiJson(sessionPath(sessionId, "/mcp-bindings"));
}

export function saveMcpBindings(sessionId, bindings) {
  return apiPut(sessionPath(sessionId, "/mcp-bindings"), { bindings });
}

export function saveMcpServer(id, payload) {
  return id ? apiPut(`/api/mcp/servers/${encodeURIComponent(id)}`, payload) : apiPost("/api/mcp/servers", payload);
}

export function deleteMcpServer(id) {
  return apiDelete(`/api/mcp/servers/${encodeURIComponent(id)}`);
}

export function probeMcpServer(id) {
  return apiPost(`/api/mcp/servers/${encodeURIComponent(id)}/probe`);
}

export function connectMcpOauth(id, redirectUri) {
  return apiPost(`/api/mcp/servers/${encodeURIComponent(id)}/oauth/connect`, { redirect_uri: redirectUri });
}

export function disconnectMcpOauth(id) {
  return apiPost(`/api/mcp/servers/${encodeURIComponent(id)}/oauth/disconnect`);
}
