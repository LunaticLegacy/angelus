import { apiDelete, apiJson, apiPost, request } from "./backend-bridge.js";

function sessionPath(sessionId, suffix) {
  if (!sessionId) throw new Error("尚未选择会话");
  return `/api/sessions/${encodeURIComponent(sessionId)}${suffix}`;
}

export const getAgents = (sessionId) => apiJson(sessionPath(sessionId, "/agents"));
export const getGraph = (sessionId) => apiJson(sessionPath(sessionId, "/graph"));
export async function getGraphOptional(sessionId) {
  const response = await request(sessionPath(sessionId, "/graph"));
  if (response.status === 404) return null;
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || `${response.status} ${response.statusText}`);
  return payload;
}
export const getGraphInfo = (sessionId) => apiJson(`${sessionPath(sessionId, "/graph")}/info`);
export const getWorkflow = (sessionId) => apiJson(sessionPath(sessionId, "/workflow"));
export const getPlan = (sessionId, agent) => apiJson(`${sessionPath(sessionId, "/plan")}${agent === "coordinator" ? "" : `?agent=${encodeURIComponent(agent)}`}`);
export const getTrace = (sessionId, cursor) => apiJson(`${sessionPath(sessionId, "/events")}?limit=200${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`);
export const getUsage = (sessionId) => apiJson(sessionPath(sessionId, "/usage"));
export const getContext = (sessionId, agentId) => apiJson(sessionPath(sessionId, `/agents/${encodeURIComponent(agentId)}/context`));
/**
 * Compose the next request without sending it.
 *
 * `contextHandler` composes a handler that is not saved yet, which is what the
 * block order editor needs; omitting it composes the saved profile handler.
 */
export function previewContext(sessionId, agentId, { message = "", contextHandler = "" } = {}) {
  const body = { message };
  if (contextHandler) body.context_handler = contextHandler;
  return apiPost(sessionPath(sessionId, `/agents/${encodeURIComponent(agentId)}/context/request-preview`), body);
}
export const getCompactionInput = (sessionId, agentId) => apiJson(sessionPath(sessionId, `/agents/${encodeURIComponent(agentId)}/context/compaction-input`));
export const getCalls = (sessionId, agentId) => apiJson(sessionPath(sessionId, `/agents/${encodeURIComponent(agentId)}/calls`));
export const getContextGraph = (sessionId, agentId, refresh = false) => apiJson(`${sessionPath(sessionId, `/agents/${encodeURIComponent(agentId)}/context-graph`)}${refresh ? `?refresh=${Date.now()}` : ""}`);
export const addGraphAgent = (sessionId, payload) => apiPost(sessionPath(sessionId, "/workflow/agents"), payload);
export const connectGraphNodes = (sessionId, payload) => apiPost(sessionPath(sessionId, "/workflow/connections"), payload);
export const setGraphMapper = (sessionId, payload) => apiPost(sessionPath(sessionId, "/workflow/mapper"), payload);
export const setGraphRouter = (sessionId, payload) => apiPost(sessionPath(sessionId, "/workflow/router"), payload);
export const removeGraphAgent = (sessionId, name) => apiDelete(sessionPath(sessionId, `/workflow/agents/${encodeURIComponent(name)}`));
export const disconnectGraphNodes = (sessionId, payload) => apiDelete(sessionPath(sessionId, "/workflow/connections"), payload);
