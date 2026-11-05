import {
  changePluginLifecycle,
  getPluginSettings,
  listPluginStatuses,
  rescanPlugins,
  savePluginSettings,
} from "../runtime/plugin-api.js";

/** Own plugin data and lifecycle calls while the view supplies presentation. */
export function createPluginController({
  getStatuses,
  setStatuses,
  getSelectedKey,
  setSelectedKey,
  keyForPlugin,
  labelPermission,
  confirm,
  loadPluginAssets,
  unloadPluginAsset,
  onChanged,
}) {
  async function loadStatuses() {
    const payload = await listPluginStatuses();
    const statuses = Array.isArray(payload?.plugins) ? payload.plugins : [];
    setStatuses(statuses);
    if (!statuses.some((plugin) => keyForPlugin(plugin) === getSelectedKey())) {
      setSelectedKey(statuses[0] ? keyForPlugin(statuses[0]) : "");
    }
    return statuses;
  }

  async function settings(pluginId) {
    return getPluginSettings(pluginId);
  }

  async function saveSettings(pluginId, settings) {
    return savePluginSettings(pluginId, settings);
  }

  async function changeLifecycle(plugin, action) {
    if (!plugin) return null;
    const registering = action === "register";
    const loading = action === "load";
    if (!registering && !plugin.id) return null;

    const requested = Array.isArray(plugin.permissions_requested) ? plugin.permissions_requested : [];
    const granted = new Set((plugin.permissions_granted || []).map(labelPermission));
    const missing = requested.filter((permission) => !granted.has(labelPermission(permission)));
    if (!confirm(plugin, action, missing)) return null;

    const payload = await changePluginLifecycle(plugin, action, {
      grantPermissions: loading && missing.length > 0,
    });
    if (registering) setSelectedKey(payload.plugin?.id || plugin.name);
    if (loading) await loadPluginAssets();
    else if (!registering) unloadPluginAsset(plugin.name);
    await loadStatuses();
    onChanged?.(plugin, action);
    return payload;
  }

  async function rescan() {
    const summary = await rescanPlugins();
    await loadPluginAssets();
    const statuses = await loadStatuses();
    return { summary, statuses };
  }

  return { loadStatuses, settings, saveSettings, changeLifecycle, rescan };
}
