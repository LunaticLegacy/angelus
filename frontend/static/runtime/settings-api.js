import { apiDelete, apiJson, apiPost, apiPut } from "./backend-bridge.js";

export function loadRunProfile(url) {
  return apiJson(url);
}

export function saveRunProfile(url, payload) {
  return apiPut(url, payload);
}

export function deleteRunProfile(sessionId) {
  return apiDelete(`/api/sessions/${encodeURIComponent(sessionId)}/run-profile`);
}

export function loadSessionPreferences(sessionId) {
  return apiJson(`/api/sessions/${encodeURIComponent(sessionId)}/preferences`);
}

export function saveSessionPreferences(sessionId, payload) {
  return apiPut(`/api/sessions/${encodeURIComponent(sessionId)}/preferences`, payload);
}

export function loadToolRegistry() {
  return apiJson("/api/tool-registry");
}

export function loadContextHandlers() {
  return apiJson("/api/context-handlers");
}

export function loadProviders() {
  return apiJson("/api/providers");
}

export function pickWorkspaceDirectory() {
  return apiPost("/api/workspace-directory/pick");
}

export function openSessionWorkspace(sessionId) {
  return apiPost(`/api/sessions/${encodeURIComponent(sessionId)}/open-folder`);
}
