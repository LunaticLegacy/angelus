(function () {
  "use strict";

  const PLUGIN = "token-burner";
  const VERSION = "0.2.0";
  const SETTINGS_URL = `/api/plugins/${PLUGIN}/settings`;
  const DEFAULTS = Object.freeze({
    poll_ms: 1200,
    decay_ms: 1750,
    rate_scale: 2600,
    show_total: true,
    show_peak: true,
    idle_flame: true,
  });
  const UI_KEY = "angelus.token-burner.ui.v2";
  const RATE_LIMIT = 50000;
  const ANIMATION_MS = 100;
  const isPopout = document.body?.classList.contains("tb-popout") === true;

  let settings = { ...DEFAULTS };
  let root = null;
  let pollTimer = null;
  let animationTimer = null;
  let destroyed = false;
  let pollInFlight = false;
  let settingsLoadedAt = 0;
  let selectedSession = null;
  let totalTokens = 0;
  let previousTotal = null;
  let previousSampleAt = 0;
  let impulseRate = 0;
  let impulseAt = performance.now();
  let displayedRate = 0;
  let peakRate = 0;
  let running = false;
  let connected = false;
  let lastRunState = "idle";

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function finite(value, fallback = 0) {
    const number = Number(value);
    return Number.isFinite(number) ? number : fallback;
  }

  function readUiState() {
    try {
      const value = JSON.parse(localStorage.getItem(UI_KEY) || "{}");
      return value && typeof value === "object" ? value : {};
    } catch (_) {
      return {};
    }
  }

  function writeUiState(patch) {
    try {
      localStorage.setItem(UI_KEY, JSON.stringify({ ...readUiState(), ...patch }));
    } catch (_) {
      // UI-only state is intentionally best-effort.
    }
  }

  function currentSessionId() {
    const pinned = new URLSearchParams(location.search).get("session");
    if (pinned && pinned.trim()) return pinned.trim();
    try {
      const value = localStorage.getItem("llmfetcherSession");
      return value && value.trim() ? value.trim() : null;
    } catch (_) {
      return null;
    }
  }

  function usageTotal(payload) {
    const usage = payload && typeof payload === "object" ? payload.usage : null;
    if (!usage || typeof usage !== "object") return null;
    const total = Number(usage.total);
    if (Number.isFinite(total) && total >= 0) return total;

    // Angelus exposes cached/reasoning as dimensions, not guaranteed-disjoint
    // billing buckets. If `total` is absent, input + output is the safest
    // non-double-counting fallback.
    const input = finite(usage.input, finite(usage.input_tokens, 0));
    const output = finite(usage.output, finite(usage.output_tokens, 0));
    const fallback = input + output;
    return fallback >= 0 ? fallback : null;
  }

  async function getJson(url) {
    const response = await fetch(url, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
      credentials: "same-origin",
    });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return response.json();
  }

  function normalizeSettings(values) {
    const source = values && typeof values === "object" ? values : {};
    return {
      poll_ms: Math.round(clamp(finite(source.poll_ms, DEFAULTS.poll_ms), 500, 5000)),
      decay_ms: Math.round(clamp(finite(source.decay_ms, DEFAULTS.decay_ms), 500, 10000)),
      rate_scale: clamp(finite(source.rate_scale, DEFAULTS.rate_scale), 50, 20000),
      show_total: source.show_total === undefined ? DEFAULTS.show_total : source.show_total === true,
      show_peak: source.show_peak === undefined ? DEFAULTS.show_peak : source.show_peak === true,
      idle_flame: source.idle_flame === undefined ? DEFAULTS.idle_flame : source.idle_flame === true,
    };
  }

  async function refreshSettings(force = false) {
    const now = Date.now();
    if (!force && now - settingsLoadedAt < 15000) return;
    try {
      const payload = await getJson(SETTINGS_URL);
      settings = normalizeSettings(payload.settings);
      settingsLoadedAt = now;
    } catch (_) {
      settings = normalizeSettings(settings);
    }
  }

  function resetSessionState(nextSession) {
    selectedSession = nextSession;
    totalTokens = 0;
    previousTotal = null;
    previousSampleAt = 0;
    impulseRate = 0;
    impulseAt = performance.now();
    displayedRate = 0;
    peakRate = 0;
    running = false;
    connected = false;
    lastRunState = nextSession ? "idle" : "no-session";
  }

  function recordUsage(total, now) {
    totalTokens = total;
    if (previousTotal === null) {
      previousTotal = total;
      previousSampleAt = now;
      return;
    }

    const delta = total - previousTotal;
    const elapsedSeconds = Math.max(0.25, (now - previousSampleAt) / 1000);
    previousTotal = total;
    previousSampleAt = now;

    // A negative delta means the selected Session/runtime projection was reset.
    if (delta < 0) {
      impulseRate = 0;
      displayedRate = 0;
      peakRate = 0;
      impulseAt = now;
      return;
    }
    if (delta === 0) return;

    // DSH-style projection impulse: cumulative usage changes are converted into
    // an instantaneous visual burn signal, then decay smoothly between samples.
    // This is deliberately an ambient rate, not provider streaming throughput.
    const rawRate = clamp(delta / elapsedSeconds, 0, RATE_LIMIT);
    impulseRate = Math.max(rawRate, displayedRate * 0.35);
    impulseAt = now;
    peakRate = Math.max(peakRate, rawRate);
  }

  async function poll() {
    if (destroyed || pollInFlight) return;
    if (!isPopout && root && !root.isConnected) {
      destroy();
      return;
    }

    pollInFlight = true;
    try {
      await refreshSettings(false);
      const session = currentSessionId();
      if (session !== selectedSession) resetSessionState(session);
      if (!session) return;

      const encoded = encodeURIComponent(session);
      const [usageResult, statusResult] = await Promise.allSettled([
        getJson(`/api/sessions/${encoded}/usage`),
        getJson(`/api/runs/${encoded}/status`),
      ]);

      if (usageResult.status === "fulfilled") {
        const total = usageTotal(usageResult.value);
        if (total !== null) {
          connected = true;
          recordUsage(total, performance.now());
        }
      } else {
        connected = false;
      }

      if (statusResult.status === "fulfilled") {
        lastRunState = String(statusResult.value?.state || "idle").toLowerCase();
        running = ["running", "stopping", "force_stopping", "force-stopping"].includes(lastRunState);
      } else {
        running = false;
        if (lastRunState === "idle") lastRunState = "unavailable";
      }
    } finally {
      pollInFlight = false;
      schedulePoll();
    }
  }

  function schedulePoll() {
    clearTimeout(pollTimer);
    if (destroyed) return;
    pollTimer = setTimeout(poll, settings.poll_ms);
  }

  function formatNumber(value) {
    const n = Math.max(0, finite(value, 0));
    if (n >= 1e9) return `${(n / 1e9).toFixed(n >= 1e10 ? 0 : 1)}b`;
    if (n >= 1e6) return `${(n / 1e6).toFixed(n >= 1e7 ? 0 : 1)}m`;
    if (n >= 1e3) return `${(n / 1e3).toFixed(n >= 1e4 ? 0 : 1)}k`;
    return Math.round(n).toLocaleString();
  }

  function formatRate(value) {
    const n = Math.max(0, finite(value, 0));
    if (n < 10) return n.toFixed(1);
    return Math.round(n).toLocaleString();
  }

  function visualTick() {
    if (destroyed) return;
    const now = performance.now();
    const age = Math.max(0, now - impulseAt);
    let desired = impulseRate * Math.exp(-age / settings.decay_ms);
    if (desired < 0.15) desired = 0;
    displayedRate += (desired - displayedRate) * 0.24;
    if (displayedRate < 0.08) displayedRate = 0;
    renderTelemetry();
    animationTimer = setTimeout(visualTick, ANIMATION_MS);
  }

  function renderTelemetry() {
    if (!root) return;
    const maxRef = Math.max(1, settings.rate_scale);
    const intensity = clamp(Math.log1p(displayedRate) / Math.log1p(maxRef), 0, 1);
    const pilot = running && settings.idle_flame ? 0.09 : 0.012;
    const visual = Math.max(intensity, pilot);
    const scale = 0.31 + visual * 0.74;

    root.style.setProperty("--tb-intensity", visual.toFixed(4));
    root.style.setProperty("--tb-flame-scale", scale.toFixed(4));
    root.style.setProperty("--tb-spark-opacity", clamp(visual * 1.2, 0.04, 1).toFixed(4));
    root.style.setProperty("--tb-panel-glow", clamp(0.12 + visual * 0.18, 0.12, 0.30).toFixed(4));
    root.style.setProperty("--tb-ambient-opacity", clamp(0.10 + visual * 0.28, 0.10, 0.38).toFixed(4));
    root.style.setProperty("--tb-saturation", (0.82 + visual * 0.70).toFixed(4));
    root.style.setProperty("--tb-ground-scale", (0.75 + visual * 0.35).toFixed(4));
    root.style.setProperty("--tb-ground-alpha", clamp(0.20 + visual * 0.42, 0.20, 0.62).toFixed(4));

    const rate = root.querySelector("[data-tb-rate]");
    const total = root.querySelector("[data-tb-total]");
    const peak = root.querySelector("[data-tb-peak]");
    const peakSep = root.querySelector(".tb-peak-sep");
    const status = root.querySelector("[data-tb-status]");

    if (rate) rate.textContent = selectedSession ? `${formatRate(displayedRate)} tok/s` : "no session";
    if (total) {
      total.hidden = !settings.show_total;
      total.textContent = `总 ${formatNumber(totalTokens)}`;
    }
    if (peak) {
      peak.hidden = !settings.show_peak;
      peak.textContent = `峰 ${formatRate(peakRate)}`;
    }
    if (peakSep) peakSep.hidden = !settings.show_peak;
    if (status) {
      status.dataset.state = running ? "running" : connected ? "idle" : "offline";
      status.title = selectedSession ? `${selectedSession} · ${lastRunState}` : "No selected Angelus Session";
    }
  }

  function flameMarkup() {
    return `
      <div class="tb-ambient" aria-hidden="true"></div>
      <div class="tb-stage" aria-hidden="true">
        <div class="tb-spark tb-spark-a"></div>
        <div class="tb-spark tb-spark-b"></div>
        <div class="tb-spark tb-spark-c"></div>
        <div class="tb-spark tb-spark-d"></div>
        <div class="tb-spark tb-spark-e"></div>
        <div class="tb-flame-wrap">
          <div class="tb-flame tb-flame-outer"></div>
          <div class="tb-flame tb-flame-mid"></div>
          <div class="tb-flame tb-flame-inner"></div>
          <div class="tb-flame tb-flame-core"></div>
        </div>
        <div class="tb-ground-glow"></div>
      </div>`;
  }

  function panelMarkup() {
    return `
      <section class="tb-panel" role="group" aria-label="Token Burner">
        <header class="tb-titlebar" data-tb-drag-handle>
          <div class="tb-title"><span class="tb-fire-icon">🔥</span><span>Token Burner</span><span class="tb-version">v${VERSION}</span></div>
          <div class="tb-controls">
            <span class="tb-status-dot" data-tb-status></span>
            <button type="button" data-tb-action="popout" title="Open detached window">↗</button>
            <button type="button" data-tb-action="large" title="Toggle size">□</button>
            <button type="button" data-tb-action="collapse" title="Collapse">×</button>
          </div>
        </header>
        <div class="tb-body">
          ${flameMarkup()}
          <footer class="tb-metrics">
            <span class="tb-metric tb-rate"><span class="tb-mini-fire">🔥</span><b data-tb-rate>0.0 tok/s</b></span>
            <span class="tb-sep">·</span>
            <span class="tb-metric" data-tb-total>总 0</span>
            <span class="tb-sep tb-peak-sep">·</span>
            <span class="tb-metric tb-peak" data-tb-peak>峰 0.0</span>
          </footer>
        </div>
      </section>
      <button class="tb-pill" type="button" data-tb-action="restore" title="Restore Token Burner">🔥</button>`;
  }

  function mount() {
    root = document.createElement("div");
    root.className = isPopout ? "tb-root tb-root-popout" : "tb-root";
    root.dataset.angelusPlugin = PLUGIN;
    root.dataset.tbCollapsed = "false";
    root.dataset.tbLarge = "false";
    root.innerHTML = panelMarkup();
    document.body.appendChild(root);

    const ui = readUiState();
    if (!isPopout) {
      root.dataset.tbCollapsed = ui.collapsed === true ? "true" : "false";
      root.dataset.tbLarge = ui.large === true ? "true" : "false";
      if (Number.isFinite(ui.left) && Number.isFinite(ui.top)) {
        root.style.left = `${ui.left}px`;
        root.style.top = `${ui.top}px`;
        root.style.right = "auto";
        root.style.bottom = "auto";
      }
      bindDrag();
    }

    root.addEventListener("click", onActionClick);
    const observer = new MutationObserver(() => {
      if (!isPopout && root && !root.isConnected) {
        observer.disconnect();
        destroy();
      }
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });
  }

  function onActionClick(event) {
    const button = event.target.closest?.("[data-tb-action]");
    if (!button) return;
    const action = button.dataset.tbAction;
    if (action === "collapse") setCollapsed(true);
    else if (action === "restore") setCollapsed(false);
    else if (action === "large") toggleLarge();
    else if (action === "popout") openPopout();
  }

  function setCollapsed(value) {
    if (!root || isPopout) return;
    root.dataset.tbCollapsed = value ? "true" : "false";
    writeUiState({ collapsed: Boolean(value) });
  }

  function toggleLarge() {
    if (!root || isPopout) return;
    const next = root.dataset.tbLarge !== "true";
    root.dataset.tbLarge = next ? "true" : "false";
    writeUiState({ large: next });
  }

  function resetPosition() {
    if (!root || isPopout) return;
    root.style.left = "auto";
    root.style.top = "auto";
    root.style.right = "22px";
    root.style.bottom = "22px";
    writeUiState({ left: null, top: null });
  }

  function bindDrag() {
    const handle = root.querySelector("[data-tb-drag-handle]");
    if (!handle) return;
    let drag = null;

    handle.addEventListener("pointerdown", (event) => {
      if (event.target.closest?.("button")) return;
      const rect = root.getBoundingClientRect();
      drag = { x: event.clientX, y: event.clientY, left: rect.left, top: rect.top };
      root.style.right = "auto";
      root.style.bottom = "auto";
      root.dataset.tbDragging = "true";
      handle.setPointerCapture?.(event.pointerId);
      event.preventDefault();
    });

    handle.addEventListener("pointermove", (event) => {
      if (!drag) return;
      const width = root.offsetWidth || 288;
      const height = root.offsetHeight || 344;
      const left = clamp(drag.left + event.clientX - drag.x, 8, Math.max(8, innerWidth - width - 8));
      const top = clamp(drag.top + event.clientY - drag.y, 8, Math.max(8, innerHeight - height - 8));
      root.style.left = `${left}px`;
      root.style.top = `${top}px`;
    });

    const finish = () => {
      if (!drag) return;
      const rect = root.getBoundingClientRect();
      writeUiState({ left: Math.round(rect.left), top: Math.round(rect.top) });
      drag = null;
      delete root.dataset.tbDragging;
    };
    handle.addEventListener("pointerup", finish);
    handle.addEventListener("pointercancel", finish);
  }

  function openPopout() {
    const session = selectedSession || currentSessionId();
    const suffix = session ? `?session=${encodeURIComponent(session)}` : "";
    const url = `/plugins/${PLUGIN}/static/window.html${suffix}`;
    window.open(url, "angelus-token-burner", "popup=yes,width=360,height=430,resizable=yes");
  }

  function toggleVisible() {
    if (!root || isPopout) return false;
    const next = root.dataset.tbCollapsed !== "true";
    setCollapsed(next);
    return !next;
  }

  function registerBridge() {
    if (isPopout || !window.Angelus) return;

    window.Angelus.registerCommand(PLUGIN, {
      id: "toggle",
      description: "Toggle the Token Burner ambient telemetry window.",
      handler: () => ({ visible: toggleVisible() }),
    });
    window.Angelus.registerCommand(PLUGIN, {
      id: "popout",
      description: "Open Token Burner in a detached same-origin window.",
      handler: () => { openPopout(); return { ok: true }; },
    });
    window.Angelus.registerCommand(PLUGIN, {
      id: "reset-position",
      description: "Reset the Token Burner floating window position.",
      handler: () => { resetPosition(); return { ok: true }; },
    });
    window.Angelus.registerCommand(PLUGIN, {
      id: "reload-settings",
      description: "Reload Token Burner host-owned plugin settings.",
      handler: () => { void refreshSettings(true); return { ok: true, scheduled: true }; },
    });
    window.Angelus.registerSettings(PLUGIN, {
      title: "Token Burner 🔥",
      description: "Ambient Session token telemetry. Behavior settings are host-persisted; position and window state remain browser-local UI state.",
    });
  }

  function destroy() {
    if (destroyed) return;
    destroyed = true;
    clearTimeout(pollTimer);
    clearTimeout(animationTimer);
  }

  async function start() {
    mount();
    registerBridge();
    await refreshSettings(true);
    resetSessionState(currentSessionId());
    renderTelemetry();
    visualTick();
    poll();

    window.addEventListener("focus", () => refreshSettings(true));
    window.addEventListener("storage", (event) => {
      if (event.key === "llmfetcherSession") poll();
    });
    window.addEventListener("beforeunload", destroy, { once: true });
  }

  start().catch((error) => {
    console.error(`[${PLUGIN}] failed to start`, error);
    destroy();
  });
})();
