/**
 * frontend/static/plugins.js — S8 plugin frontend bridge & loader.
 *
 * Contract: docs/plugin-api.md §6 (five extension points, frontend row) and
 * the swarm execution spec S8.  Imported by main.js (the contract entry);
 * it also self-initialises on module load so the bridge is live whichever
 * entry module eventually imports it.
 *
 * Responsibilities
 * ----------------
 * 1. Startup: GET /api/plugins returns the *loadable set* — the backend only
 *    lists plugins that are registry-enabled AND manager-active, so disabled
 *    plugins are never handed to the frontend.
 * 2. window.Angelus bridge: registerPanel / registerCommand /
 *    registerSettings are the ONLY entry points plugin scripts may use to
 *    contribute UI.  Every registration is validated and namespaced per
 *    plugin, and only names of currently loaded (enabled) plugins are
 *    accepted, so a misbehaving script can never fake another plugin's UI.
 * 3. Whitelisted asset loading: for each enabled plugin we inject its
 *    conventional frontend entry — /plugins/<name>/static/plugin.js and
 *    /plugins/<name>/static/plugin.css — as <script>/<link>.  The backend
 *    answers 404 for anything not listed in manifest.frontend.assets, so
 *    only whitelisted files are ever injected: the server is the whitelist
 *    authority (the /api/plugins payload intentionally carries no manifest).
 * 4. Disabled plugins never appear in the UI: their scripts are never
 *    loaded, hence they can never register panels/commands/settings.
 * 5. The host settings page reads registerSettings metadata for active
 *    plugins, then provides a bounded JSON editor backed by the dedicated
 *    plugin-settings API. The bridge remains the only plugin UI entry point.
 */

import { apiJson } from "./api.js";

/* ================================================================
 * Constants
 * ================================================================ */

/** Conventional frontend entry assets tried for every enabled plugin.
 *
 * A plugin that ships frontend UI lists these files in
 * manifest.frontend.assets; anything else is 404'd by the backend and
 * skipped here.  plugin.js is the bridge entry script (uses
 * window.Angelus), plugin.css an optional stylesheet.
 */
const ENTRY_SCRIPTS = ["plugin.js"];
const ENTRY_STYLES = ["plugin.css"];

/** Same pattern as manifest.name — the URL/namespace source. */
const PLUGIN_NAME_RE = /^[a-z][a-z0-9_-]{1,63}$/;

/** Optional UI mount points (present in the workbench index.html). */
const TABS_SELECTOR = ".inspector-tabs";
const PANELS_SELECTOR = ".inspector-panels";

/* ================================================================
 * Bridge registries — module-private; plugin scripts can only touch
 * them through the validated window.Angelus API below.
 * ================================================================ */

const _panels = new Map();   // "plugin:id" -> panel registration
const _commands = new Map(); // "plugin:id" -> command registration
const _settings = new Map(); // "plugin"    -> settings registration

const _loadedPlugins = new Set(); // names currently enabled+loaded
let _started = false;

/* ================================================================
 * Helpers
 * ================================================================ */

function _warn(plugin, message) {
  console.warn(`[plugins] ${plugin}: ${message}`);
}

function _validName(name) {
  return typeof name === "string" && PLUGIN_NAME_RE.test(name);
}

/** Sanitise a plugin-supplied id into a safe DOM id fragment. */
function _safeId(value) {
  return String(value ?? "")
    .replace(/[^A-Za-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/** Only plugins that are actually loaded (enabled) may register UI. */
function _assertLoaded(plugin) {
  if (_loadedPlugins.has(plugin)) return true;
  _warn(plugin, "拒绝注册：插件未启用或未加载（不在 /api/plugins 返回的可用集合中）");
  return false;
}

/* ================================================================
 * Asset injection — whitelist enforced by the backend (404 = skip)
 * ================================================================ */

function _injectScript(src, pluginName) {
  return new Promise((resolve) => {
    const el = document.createElement("script");
    el.src = src;
    el.async = false;
    el.dataset.angelusPlugin = pluginName;
    el.addEventListener("load", () => resolve(true));
    el.addEventListener("error", () => resolve(false));
    document.head.appendChild(el);
  });
}

function _injectStylesheet(src, pluginName) {
  return new Promise((resolve) => {
    const el = document.createElement("link");
    el.rel = "stylesheet";
    el.href = src;
    el.dataset.angelusPlugin = pluginName;
    el.addEventListener("load", () => resolve(true));
    el.addEventListener("error", () => resolve(false));
    document.head.appendChild(el);
  });
}

function _pluginAssetUrl(pluginName, asset) {
  return `/plugins/${encodeURIComponent(pluginName)}/static/${encodeURIComponent(asset)}`;
}

async function _loadPluginAssets(plugin) {
  // Theme packs are CSS-only declarative bundles. Their selected skin is
  // loaded by the Settings UI; never probe them for executable plugin.js.
  if (plugin.kind === "theme_pack") return;
  for (const asset of ENTRY_SCRIPTS) {
    const ok = await _injectScript(_pluginAssetUrl(plugin.name, asset), plugin.name);
    if (!ok) {
      _warn(plugin.name, `前端入口 ${asset} 不在白名单或加载失败，已跳过`);
    }
  }
  for (const asset of ENTRY_STYLES) {
    await _injectStylesheet(_pluginAssetUrl(plugin.name, asset), plugin.name);
  }
}

/** Remove the host-owned browser contributions of a stopped plugin.
 *
 * Python teardown remains the authority for runtime resources.  This only
 * clears script/link tags and UI registrations owned by the workbench so a
 * subsequently reloaded plugin receives a clean browser-side activation.
 */
export function unloadPlugin(pluginName) {
  if (!_validName(pluginName)) return;
  _loadedPlugins.delete(pluginName);
  for (const [key, panel] of _panels) {
    if (panel.plugin !== pluginName) continue;
    document.querySelector(`[data-inspector-panel="plugin-${pluginName}-${panel.id}"]`)?.remove();
    document.getElementById(`plugin-${pluginName}-${panel.id}`)?.remove();
    _panels.delete(key);
  }
  for (const [key, command] of _commands) {
    if (command.plugin === pluginName) _commands.delete(key);
  }
  _settings.delete(pluginName);
  document.querySelectorAll("[data-angelus-plugin]").forEach((element) => {
    if (element.dataset.angelusPlugin === pluginName) element.remove();
  });
}

/* ================================================================
 * Panel rendering into the workbench inspector
 * ================================================================ */

function _panelContainers() {
  return {
    tabs: document.querySelector(TABS_SELECTOR),
    panels: document.querySelector(PANELS_SELECTOR),
  };
}

function _fillPanel(body, render) {
  if (typeof render === "function") {
    render(body);
  } else if (typeof render === "string") {
    body.innerHTML = render;
  } else if (typeof Element !== "undefined" && render instanceof Element) {
    body.appendChild(render);
  }
}

function _renderPanel(registration) {
  const { tabs, panels } = _panelContainers();
  if (!tabs || !panels) return; // host has no inspector UI — keep registry only
  const panelId = `plugin-${registration.plugin}-${registration.id}`;

  if (!document.getElementById(panelId)) {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.inspectorPanel = panelId;
    button.textContent = registration.title;
    tabs.appendChild(button);

    const section = document.createElement("section");
    section.id = panelId;
    section.className = "inspector-panel";
    section.dataset.pluginPanel = registration.plugin;

    const heading = document.createElement("div");
    heading.className = "section-title";
    const inner = document.createElement("div");
    const eyebrow = document.createElement("p");
    eyebrow.className = "eyebrow";
    eyebrow.textContent = "PLUGIN";
    const title = document.createElement("h3");
    title.textContent = registration.title;
    inner.append(eyebrow, title);
    heading.appendChild(inner);
    section.appendChild(heading);

    const body = document.createElement("div");
    body.className = "plugin-panel-body";
    section.appendChild(body);
    panels.appendChild(section);

    registration._body = body;
  }

  const body = registration._body || document.getElementById(panelId)?.querySelector(".plugin-panel-body");
  if (body && !registration._rendered) {
    try {
      _fillPanel(body, registration.render);
    } catch (error) {
      _warn(registration.plugin, `面板 ${registration.id} 渲染失败：${error.message}`);
    }
    registration._rendered = true;
  }
}

/** Delegated tab switching so plugin-added tabs work without touching the
 *  host's own tab binding (idempotent with the host's toggle logic). */
function _bindPanelTabs() {
  const tabs = document.querySelector(TABS_SELECTOR);
  if (!tabs || tabs.dataset.pluginsBound) return;
  tabs.dataset.pluginsBound = "1";
  tabs.addEventListener("click", (event) => {
    const button = event.target.closest?.("[data-inspector-panel]");
    if (!button) return;
    const panelId = button.dataset.inspectorPanel;
    document
      .querySelectorAll("[data-inspector-panel]")
      .forEach((btn) => btn.classList.toggle("active", btn === button));
    document
      .querySelectorAll(".inspector-panel")
      .forEach((panel) => panel.classList.toggle("active", panel.id === panelId));
  });
}

/* ================================================================
 * window.Angelus bridge — the safe registration surface
 * ================================================================ */

function _createBridge() {
  return Object.freeze({
    /**
     * Register a plugin inspector panel.
     * spec: { id, title, render } — render is a function(bodyEl),
     * an HTML string, or a DOM Element.  The DOM id is namespaced as
     * `plugin-<name>-<id>`.
     */
    registerPanel(plugin, spec) {
      if (!_validName(plugin) || !_assertLoaded(plugin)) return { ok: false };
      if (!spec || typeof spec !== "object") {
        _warn(plugin, "registerPanel: spec 必须为对象");
        return { ok: false, error: "spec must be an object" };
      }
      const id = _safeId(spec.id);
      const title = typeof spec.title === "string" ? spec.title.trim() : "";
      if (!id || !title) {
        _warn(plugin, "registerPanel: 需要非空 spec.id 与 spec.title");
        return { ok: false, error: "spec.id and spec.title are required" };
      }
      const render = spec.render;
      const renderOk =
        typeof render === "function" ||
        typeof render === "string" ||
        (typeof Element !== "undefined" && render instanceof Element);
      if (!renderOk) {
        _warn(plugin, "registerPanel: spec.render 必须是函数、HTML 字符串或 Element");
        return { ok: false, error: "spec.render must be a function, string or Element" };
      }
      const key = `${plugin}:${id}`;
      const registration = { plugin, id, title, render, key };
      _panels.set(key, registration);
      _renderPanel(registration);
      return { ok: true };
    },

    /**
     * Register a plugin command.  spec: { id, handler, description }.
     * The dispatch key is namespaced `plugin:id` so it can never collide
     * with built-in slash commands; handler is called as
     * handler(args, flags) — see dispatchCommand().
     */
    registerCommand(plugin, spec) {
      if (!_validName(plugin) || !_assertLoaded(plugin)) return { ok: false };
      if (!spec || typeof spec !== "object") {
        _warn(plugin, "registerCommand: spec 必须为对象");
        return { ok: false, error: "spec must be an object" };
      }
      const id = _safeId(spec.id);
      if (!id) {
        _warn(plugin, "registerCommand: 需要非空 spec.id");
        return { ok: false, error: "spec.id is required" };
      }
      if (typeof spec.handler !== "function") {
        _warn(plugin, "registerCommand: spec.handler 必须是函数");
        return { ok: false, error: "spec.handler must be a function" };
      }
      const key = `${plugin}:${id}`;
      _commands.set(key, {
        plugin,
        id,
        key,
        description:
          typeof spec.description === "string" ? spec.description : "",
        handler: spec.handler,
      });
      return { ok: true };
    },

    /**
     * Register plugin settings metadata for the host settings page.
     * spec may provide title and description; persisted values remain under
     * host control and are never handed to arbitrary browser code directly.
     */
    registerSettings(plugin, spec) {
      if (!_validName(plugin) || !_assertLoaded(plugin)) return { ok: false };
      if (!spec || typeof spec !== "object") {
        _warn(plugin, "registerSettings: spec 必须为对象");
        return { ok: false, error: "spec must be an object" };
      }
      _settings.set(plugin, { plugin, ...spec });
      return { ok: true };
    },

    /* ---- read-only introspection for host integration ---- */

    getRegisteredPanels() {
      return [..._panels.values()];
    },
    getRegisteredCommands() {
      return [..._commands.values()];
    },
    getRegisteredSettings() {
      return [..._settings.values()];
    },

    /** Invoke a registered plugin command by its `plugin:id` key. */
    dispatchCommand(key, args = [], flags = {}) {
      const command = _commands.get(String(key));
      if (!command) return { ok: false, error: `unknown command ${key}` };
      try {
        return { ok: true, result: command.handler(args, flags) };
      } catch (error) {
        _warn(command.plugin, `命令 ${key} 执行失败：${error.message}`);
        return { ok: false, error: error.message };
      }
    },
  });
}

if (!window.Angelus) {
  window.Angelus = _createBridge();
}

/* ================================================================
 * Loading sequence
 * ================================================================ */

/** Fetch the loadable plugin set and activate every enabled plugin. */
export async function loadPlugins() {
  let plugins = [];
  try {
    const payload = await apiJson("/api/plugins");
    plugins = Array.isArray(payload?.plugins) ? payload.plugins : [];
  } catch (error) {
    _warn("bridge", `GET /api/plugins 失败：${error.message}`);
    return [];
  }

  // Defensive: the backend already returns only enabled+active plugins,
  // but never trust the wire for UI visibility.
  const enabled = plugins.filter(
    (p) => p && typeof p === "object" && _validName(p.name) && p.enabled === true
  );
  const enabledNames = new Set(enabled.map((plugin) => plugin.name));
  [..._loadedPlugins].forEach((name) => {
    if (!enabledNames.has(name)) unloadPlugin(name);
  });

  for (const plugin of enabled) {
    try {
      if (_loadedPlugins.has(plugin.name)) continue;
      // Mark as loaded BEFORE injecting so synchronous register* calls
      // inside the plugin script pass the enabled-only gate.
      _loadedPlugins.add(plugin.name);
      await _loadPluginAssets(plugin);
    } catch (error) {
      _warn(plugin.name, `前端激活失败：${error.message}`);
    }
  }
  return enabled;
}

/** Idempotent entry point — never throws, never blocks the workbench. */
export async function initPlugins() {
  if (_started) return;
  _started = true;
  _bindPanelTabs();
  try {
    await loadPlugins();
  } catch (error) {
    _warn("bridge", `插件初始化失败：${error.message}`);
  }
}

/* Self-initialise on import so the bridge and loader are live regardless
 * of which entry module (main.js today, app.js after the merge) loads this
 * file.  initPlugins() is idempotent. */
if (typeof document !== "undefined") {
  initPlugins();
}
