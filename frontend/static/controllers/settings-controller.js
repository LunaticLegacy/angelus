import {
  loadContextHandlers,
  loadRunProfile,
  loadSessionPreferences,
  loadToolRegistry,
  saveRunProfile,
} from "../runtime/settings-api.js";

/** Coordinate settings resources without owning settings markup. */
export function createSettingsController({
  getProfileUrl,
  getProfilePayload,
  applyProfile,
  applySessionConnector,
  onContextHandlers,
}) {
  async function restore() {
    const profile = await loadRunProfile(getProfileUrl());
    applyProfile(profile);
    const target = applySessionConnector ? await applySessionConnector(profile) : null;
    return { profile, target };
  }

  async function persist(overrides = {}) {
    const profile = await saveRunProfile(getProfileUrl(), getProfilePayload(overrides));
    applyProfile(profile);
    return profile;
  }

  async function loadTools() {
    return loadToolRegistry();
  }

  async function loadContextCatalog() {
    const payload = await loadContextHandlers();
    onContextHandlers?.(payload);
    return payload;
  }

  async function loadPreferences(sessionId) {
    return loadSessionPreferences(sessionId);
  }

  return { restore, persist, loadTools, loadContextCatalog, loadPreferences };
}
