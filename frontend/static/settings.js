/**
 * Settings panel ↔ localStorage persistence.
 *
 * The DOM element IDs use kebab-case (e.g. "max-tokens") while the API and
 * persisted JSON keys use snake_case (e.g. "max_tokens").  The lookup table
 * below keeps the mapping in one place.
 */

import { $ } from "./utils.js";
import { getState } from "./state.js";
import { apiPut } from "./api.js";

/* ---- mapping ---- */

const SETTING_IDS = [
  "provider",
  "model",
  "api-url",
  "api-key",
  "system-prompt",
  "temperature",
  "max-tokens",
  "max-rounds",
  "max-swarm-agents",
];

const BOOL_IDS = ["enable-shell", "enable-swarm"];

/* ---- helpers ---- */

function _settingsKey(workspaceId) {
  return `llmfetcherSettings:${workspaceId}`;
}

function _readConfig() {
  const val = (id) => $(id).value.trim();
  return {
    provider: val("provider"),
    model: val("model"),
    api_key: $("api-key").value,
    api_url: val("api-url"),
    system_prompt: $("system-prompt").value,
    temperature: Number($("temperature").value),
    max_tokens: Number($("max-tokens").value),
    max_rounds: Number($("max-rounds").value),
    enable_shell: $("enable-shell").checked,
    enable_swarm: $("enable-swarm").checked,
    max_swarm_agents: Number($("max-swarm-agents").value),
  };
}

/* ---- persistence ---- */

export function persistSettings() {
  const ws = getState("workspaceId");
  if (!ws) return;
  const settings = _readConfig();
  localStorage.setItem(_settingsKey(ws), JSON.stringify(settings));
}

export function restoreSettings() {
  const ws = getState("workspaceId");
  if (!ws) return;
  try {
    const raw = localStorage.getItem(_settingsKey(ws));
    if (!raw) return;
    const settings = JSON.parse(raw);
    if (!settings) return;
    SETTING_IDS.forEach((id) => {
      const key = id.replaceAll("-", "_");
      if (settings[key] !== undefined) $(id).value = settings[key];
    });
    $("enable-shell").checked = Boolean(settings.enable_shell);
    $("enable-swarm").checked = Boolean(settings.enable_swarm);
  } catch {
    /* ignore malformed localStorage */
  }
}

export function bindSettingsPersistence() {
  [...SETTING_IDS, ...BOOL_IDS].forEach((id) => {
    ["input", "change"].forEach((event) =>
      $(id).addEventListener(event, persistSettings)
    );
  });
}

/** Read current UI state as a RunConfig-compatible object. */
export function getConfig() {
  return _readConfig();
}

/* ---- model summary ---- */

export function updateModelSummary() {
  $("model-label").textContent = $("model").value.trim() || "模型配置";
  $("provider-label").textContent =
    $("provider").options[$("provider").selectedIndex]?.text ||
    "OpenAI compatible";
  $("max-tokens-output").textContent = $("max-tokens").value;
  $("temperature-output").textContent = $("temperature").value;
}

export function applyConnector(connector) {
  SETTING_IDS.forEach((id) => {
    const key = id.replaceAll("-", "_");
    if (connector[key] !== undefined) $(id).value = connector[key];
  });
  $("enable-shell").checked = Boolean(connector.enable_shell);
  $("enable-swarm").checked = Boolean(connector.enable_swarm);
}
