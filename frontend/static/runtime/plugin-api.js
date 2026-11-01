import { apiJson, apiPost, apiPut, request } from "./backend-bridge.js";

export async function pluginAssetAvailable(pluginName, asset) {
  try {
    const response = await request(`/plugins/${encodeURIComponent(pluginName)}/static/${encodeURIComponent(asset)}`, { method: "GET", cache: "no-store" });
    return response.ok;
  } catch {
    return false;
  }
}

export function listPluginStatuses() {
  return apiJson("/api/plugins/status");
}

export function getPluginSettings(pluginId) {
  return apiJson(`/api/plugins/${encodeURIComponent(pluginId)}/settings`);
}

export function savePluginSettings(pluginId, settings) {
  return apiPut(`/api/plugins/${encodeURIComponent(pluginId)}/settings`, settings);
}

export function changePluginLifecycle(plugin, action, options = {}) {
  const registering = action === "register";
  const loading = action === "load";
  const url = registering
    ? `/api/plugins/discovered/${encodeURIComponent(plugin.name)}/register`
    : `/api/plugins/${encodeURIComponent(plugin.id)}/${loading ? "load" : "unload"}`;
  return apiPost(url, {
    confirm: true,
    grant_permissions: Boolean(options.grantPermissions),
  });
}

export function rescanPlugins() {
  return apiPost("/api/plugins/rescan");
}
