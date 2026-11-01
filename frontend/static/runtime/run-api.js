import { apiJson, apiPost, request } from "./backend-bridge.js";

export const getRunStatus = (runId) => apiJson(`/api/runs/${encodeURIComponent(runId)}/status`);
export const startRun = (payload) => apiPost("/api/runs", payload);
export const controlRun = (sessionId, payload) => apiPost(`/api/runs/${encodeURIComponent(sessionId)}/control`, payload);

/** Compact emits NDJSON, so it stays a stream instead of using apiPost JSON parsing. */
export const openCompactionStream = (sessionId, agent) => request(
  `/api/sessions/${encodeURIComponent(sessionId)}/compact`,
  { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ agent }) },
);
