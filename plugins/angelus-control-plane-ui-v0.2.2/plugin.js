/**
 * Angelus Control Plane UI v0.2.2
 *
 * Target: LunaticLegacy/angelus :: feat/v0.5.0-adapter-and-perf
 *
 * This remains a frontend-only skin/observability plugin.  It deliberately
 * consumes Angelus' durable REST event log instead of cloning Agent runtime
 * state, and leaves all run/session/tool execution authority in the host.
 */
(function () {
  "use strict";

  const PLUGIN = "control-plane-ui";
  const VERSION = "0.2.2";
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

  if (!$(`script[data-angelus-plugin="${PLUGIN}"]`)) return;
  if ($(`[data-cpui-root="${PLUGIN}"]`)) return;

  const main = $(".main-panel");
  const sidebar = $(".sidebar");
  const activity = $(".activity");
  const composer = $("#composer");
  const messageInput = $("#message");
  const workspaceSelect = $("#workspace");

  if (!main || !sidebar || !activity || !composer || !messageInput || !workspaceSelect) {
    console.warn(`[${PLUGIN}] host workbench selectors are unavailable`);
    return;
  }

  document.body.classList.add("cpui-enabled");
  document.body.dataset.cpuiView = "timeline";
  document.body.dataset.cpuiVersion = VERSION;

  const state = {
    view: "timeline",
    sessionId: currentSessionId(),
    timelineEvents: [],
    timelineTotal: 0,
    timelineLoadedAt: 0,
    statsEvents: [],
    statsRange: "1h",
    statsAgent: localStorage.cpuiStatsAgent || "all",
    statsLoadedAt: 0,
    refreshTimer: null,
    slash: {
      open: false,
      selected: 0,
      items: [],
      mode: "commands",
      querySeq: 0,
    },
    overlay: null,
  };

  function currentSessionId() {
    return String(workspaceSelect.value || localStorage.llmfetcherSession || localStorage.llmfetcherWorkspace || "default");
  }

  function esc(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function pluginElement(tag, className = "") {
    const el = document.createElement(tag);
    if (className) el.className = className;
    el.dataset.angelusPlugin = PLUGIN;
    return el;
  }

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }

  function finite(value, fallback = 0) {
    const number = Number(value);
    return Number.isFinite(number) ? number : fallback;
  }

  function formatDuration(ms) {
    const value = finite(ms, -1);
    if (value < 0) return "—";
    if (value < 1000) return `${Math.round(value)}ms`;
    if (value < 60_000) return `${(value / 1000).toFixed(value < 10_000 ? 2 : 1)}s`;
    const minutes = Math.floor(value / 60_000);
    const seconds = Math.round((value % 60_000) / 1000);
    return `${minutes}m ${seconds}s`;
  }

  function formatClock(epochSeconds, withDate = false) {
    const value = finite(epochSeconds, 0);
    if (!value) return "—";
    const date = new Date(value * 1000);
    const options = withDate
      ? { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }
      : { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false };
    return new Intl.DateTimeFormat(undefined, options).format(date);
  }

  function formatNumber(value, digits = 0) {
    const n = finite(value, 0);
    return n.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits });
  }

  function eventKey(event, index = 0) {
    const data = event?.data && typeof event.data === "object" ? event.data : {};
    const calls = Array.isArray(data.tool_calls) ? data.tool_calls.map((call) => call?.call_id || call?.name || "").join(",") : "";
    return [
      event?.event || "",
      event?.type || "",
      event?.agent || "",
      finite(event?.timestamp, 0).toFixed(6),
      data.round ?? "",
      calls,
      index,
    ].join("|");
  }

  async function apiJson(path) {
    const response = await fetch(path, { headers: { Accept: "application/json" } });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload?.detail || `${response.status} ${response.statusText}`);
    return payload;
  }

  /**
   * Read durable events newest-first until the requested cutoff is crossed.
   * The server already bounds pages to 500 records, so this remains friendly
   * to the current event-log API while supporting long-running sessions.
   */
  async function loadEventsSince(sessionId, cutoffSeconds = 0, maxPages = 160) {
    let before = null;
    let pages = 0;
    let total = 0;
    const collected = [];
    const seen = new Set();

    while (pages < maxPages) {
      const query = new URLSearchParams({ limit: "500" });
      if (before !== null) query.set("before", String(before));
      const payload = await apiJson(`/api/sessions/${encodeURIComponent(sessionId)}/events?${query}`);
      total = finite(payload.total, total);
      const events = Array.isArray(payload.events) ? payload.events : [];
      if (!events.length) break;

      let crossed = false;
      for (const event of events) {
        const timestamp = finite(event?.timestamp, 0);
        if (cutoffSeconds && timestamp && timestamp < cutoffSeconds) {
          crossed = true;
          continue;
        }
        const key = eventKey(event);
        if (seen.has(key)) continue;
        seen.add(key);
        collected.push(event);
      }

      before = payload.next_before ?? null;
      pages += 1;
      if (crossed || before === null) break;
    }

    collected.sort((a, b) => finite(a.timestamp, 0) - finite(b.timestamp, 0));
    return { events: collected, total };
  }

  async function loadLatestRunEvents(sessionId, maxPages = 80) {
    let before = null;
    let pages = 0;
    let total = 0;
    const collected = [];
    let foundStart = false;
    while (pages < maxPages && !foundStart) {
      const query = new URLSearchParams({ limit: "500" });
      if (before !== null) query.set("before", String(before));
      const payload = await apiJson(`/api/sessions/${encodeURIComponent(sessionId)}/events?${query}`);
      total = finite(payload.total, total);
      const events = Array.isArray(payload.events) ? payload.events : [];
      if (!events.length) break;
      for (const event of events) {
        collected.push(event);
        if (event?.event === "run_started") {
          foundStart = true;
          break;
        }
      }
      before = payload.next_before ?? null;
      pages += 1;
      if (before === null) break;
    }
    collected.sort((a, b) => finite(a.timestamp, 0) - finite(b.timestamp, 0));
    return { events: collected, total };
  }

  function lastRunWindow(events) {
    if (!events.length) return [];
    let startIndex = -1;
    for (let i = events.length - 1; i >= 0; i -= 1) {
      if (events[i]?.event === "run_started") {
        startIndex = i;
        break;
      }
    }
    if (startIndex < 0) {
      const newest = finite(events.at(-1)?.timestamp, Date.now() / 1000);
      return events.filter((event) => finite(event.timestamp, newest) >= newest - 3600);
    }
    return events.slice(startIndex);
  }

  // -------------------------------------------------------------------------
  // Shell and view navigation
  // -------------------------------------------------------------------------

  const rail = pluginElement("nav", "cpui-rail");
  rail.dataset.cpuiRoot = PLUGIN;
  rail.setAttribute("aria-label", "Angelus Control Plane navigation");
  rail.innerHTML = `
    <button class="cpui-mark" type="button" title="Angelus" aria-label="Angelus">A</button>
    <div class="cpui-rail-group">
      <button class="cpui-rail-button active" type="button" data-cpui-view="timeline" title="Timeline">▶</button>
      <button class="cpui-rail-button" type="button" data-cpui-view="transcript" title="Transcript">▤</button>
      <button class="cpui-rail-button" type="button" data-cpui-view="agents" title="Agents">⑂</button>
      <button class="cpui-rail-button" type="button" data-cpui-view="plan" title="Plan">✓</button>
      <button class="cpui-rail-button" type="button" data-cpui-view="statistics" title="Statistics">∿</button>
    </div>
    <div class="cpui-rail-spacer"></div>
    <button class="cpui-rail-button" type="button" data-cpui-action="settings" title="Settings">⚙</button>
  `;
  document.body.prepend(rail);

  const viewbar = pluginElement("nav", "cpui-viewbar");
  viewbar.setAttribute("aria-label", "Run views");
  viewbar.innerHTML = `
    <div class="cpui-view-title"><strong>RUN</strong><span>CONTROL PLANE</span></div>
    <div class="cpui-view-tabs" role="tablist">
      <button class="active" type="button" role="tab" aria-selected="true" data-cpui-view="timeline">Timeline</button>
      <button type="button" role="tab" aria-selected="false" data-cpui-view="transcript">Transcript</button>
      <button type="button" role="tab" aria-selected="false" data-cpui-view="agents">Agents</button>
      <button type="button" role="tab" aria-selected="false" data-cpui-view="plan">Plan</button>
      <button type="button" role="tab" aria-selected="false" data-cpui-view="statistics">Statistics</button>
    </div>
  `;
  main.insertBefore(viewbar, $("#agent-row", main) || $("#chat", main));

  const commandLabel = pluginElement("div", "cpui-command-label");
  commandLabel.innerHTML = `<span>COMMAND</span><small>Ask / steer current run</small>`;
  composer.prepend(commandLabel);

  const timelineSurface = pluginElement("section", "cpui-stage-surface cpui-timeline-surface");
  timelineSurface.id = "cpui-timeline-surface";
  timelineSurface.setAttribute("aria-label", "Agent execution timeline");
  main.appendChild(timelineSurface);

  const statisticsSurface = pluginElement("section", "cpui-stage-surface cpui-statistics-surface");
  statisticsSurface.id = "cpui-statistics-surface";
  statisticsSurface.setAttribute("aria-label", "Session statistics");
  main.appendChild(statisticsSurface);

  const slashConsole = pluginElement("section", "cpui-slash-console");
  slashConsole.id = "cpui-slash-console";
  slashConsole.hidden = true;
  slashConsole.setAttribute("aria-label", "Slash command console");
  main.appendChild(slashConsole);

  function setView(view) {
    if (!["timeline", "transcript", "agents", "plan", "statistics"].includes(view)) return;
    state.view = view;
    document.body.dataset.cpuiView = view;
    $$(`[data-angelus-plugin="${PLUGIN}"] [data-cpui-view]`).forEach((button) => {
      const active = button.dataset.cpuiView === view;
      button.classList.toggle("active", active);
      if (button.getAttribute("role") === "tab") button.setAttribute("aria-selected", active ? "true" : "false");
    });
    if (view === "timeline") refreshTimeline(false);
    if (view === "statistics") refreshStatistics(false);
  }

  document.addEventListener("click", (event) => {
    const viewButton = event.target.closest?.(`[data-angelus-plugin="${PLUGIN}"] [data-cpui-view]`);
    if (viewButton) {
      setView(viewButton.dataset.cpuiView);
      return;
    }
    const actionButton = event.target.closest?.(`[data-angelus-plugin="${PLUGIN}"] [data-cpui-action]`);
    if (actionButton?.dataset.cpuiAction === "settings") $("#open-settings")?.click();
  });

  // -------------------------------------------------------------------------
  // Timeline: per-Agent swimlanes with TOOL / MODEL / INPUT sublanes
  // -------------------------------------------------------------------------

  function timelineSpans(events) {
    const spans = [];
    const inputs = [];
    const agents = new Set(["coordinator"]);

    for (const event of events) {
      const timestamp = finite(event?.timestamp, 0);
      const agent = String(event?.agent || "coordinator");
      const data = event?.data && typeof event.data === "object" ? event.data : {};
      if (event?.agent) agents.add(agent);

      if (event?.event === "run_started" && timestamp) {
        inputs.push({
          kind: "input",
          subtype: "prompt",
          agent: "coordinator",
          start: timestamp,
          end: timestamp,
          label: "User prompt",
          detail: { message: event.message || "", event },
        });
        continue;
      }

      if (event?.event !== "lifecycle") continue;

      if (event.type === "agent:usage" && timestamp && finite(data.duration_ms, 0) > 0) {
        const durationMs = finite(data.duration_ms, 0);
        const usage = data.usage && typeof data.usage === "object" ? data.usage : {};
        const output = finite(usage.output, 0);
        const tps = durationMs > 0 ? output / (durationMs / 1000) : 0;
        spans.push({
          kind: "model",
          subtype: String(data.kind || "primary"),
          agent,
          start: timestamp - durationMs / 1000,
          end: timestamp,
          durationMs,
          label: `Round ${data.round ?? "?"}`,
          detail: { round: data.round, usage, duration_ms: durationMs, tps, event },
        });
        continue;
      }

      if (event.type === "agent:tools_completed" && timestamp) {
        const batchDurationMs = finite(data.duration_ms, 0);
        const batchStart = batchDurationMs > 0 ? timestamp - batchDurationMs / 1000 : timestamp;
        const calls = Array.isArray(data.tool_calls) ? data.tool_calls : [];
        for (const call of calls) {
          const durationMs = finite(call?.duration_ms, batchDurationMs);
          // execute_batch_timed starts calls as one batch.  The individual
          // duration is exact; the start anchor is the durable batch start.
          spans.push({
            kind: "tool",
            subtype: call?.ok === false ? "failed" : "completed",
            agent,
            start: batchStart,
            end: batchStart + durationMs / 1000,
            durationMs,
            label: String(call?.name || "tool"),
            detail: { round: data.round, call, batch_duration_ms: batchDurationMs, event },
          });
        }
        continue;
      }

      if (event.type === "agent:steer_applied" && timestamp) {
        const messages = Array.isArray(data.messages) ? data.messages : [];
        inputs.push({
          kind: "input",
          subtype: "steer",
          agent,
          start: timestamp,
          end: timestamp,
          label: "Steer applied",
          detail: { round: data.round, messages, event },
        });
      }
    }

    return { spans, inputs, agents: [...agents].sort((a, b) => (a === "coordinator" ? -1 : b === "coordinator" ? 1 : a.localeCompare(b))) };
  }

  function timelineBounds(spans, inputs) {
    const points = [...spans.flatMap((span) => [span.start, span.end]), ...inputs.map((item) => item.start)].filter((value) => value > 0);
    if (!points.length) {
      const now = Date.now() / 1000;
      return { start: now - 60, end: now };
    }
    const start = Math.min(...points);
    const observedEnd = Math.max(...points);
    const runActive = !document.querySelector("#stop")?.disabled;
    const end = runActive ? Math.max(observedEnd, Date.now() / 1000) : observedEnd;
    return { start, end: Math.max(end, start + 5) };
  }

  function spanCard(span, bounds, pxPerSecond) {
    const y = Math.max(0, (span.start - bounds.start) * pxPerSecond);
    const rawHeight = Math.max(0, (span.end - span.start) * pxPerSecond);
    const height = Math.max(span.kind === "input" ? 10 : 7, rawHeight);
    const tps = span.kind === "model" ? finite(span.detail?.tps, 0) : 0;
    const secondary = span.kind === "model"
      ? `${formatDuration(span.durationMs)}${tps > 0 ? ` · ${tps.toFixed(1)} tok/s` : ""}`
      : span.kind === "tool"
        ? formatDuration(span.durationMs)
        : formatClock(span.start);
    const classes = `cpui-timeline-block ${span.kind} ${span.subtype || ""}`;
    return `<button type="button" class="${classes}" style="top:${y.toFixed(2)}px;height:${height.toFixed(2)}px" data-cpui-span="${esc(span._id)}" title="${esc(span.label)} · ${esc(secondary)}"><strong>${esc(span.label)}</strong><small>${esc(secondary)}</small></button>`;
  }

  function timeTicks(bounds, pxPerSecond) {
    const duration = bounds.end - bounds.start;
    const intervals = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600];
    const desiredSeconds = Math.max(1, 72 / pxPerSecond);
    const interval = intervals.find((value) => value >= desiredSeconds) || 3600;
    const first = Math.ceil(bounds.start / interval) * interval;
    const ticks = [];
    for (let value = first; value <= bounds.end + interval; value += interval) {
      const y = (value - bounds.start) * pxPerSecond;
      if (y < -10 || y > duration * pxPerSecond + 10) continue;
      ticks.push(`<div class="cpui-time-tick" style="top:${y.toFixed(2)}px"><span>${esc(formatClock(value))}</span></div>`);
    }
    return ticks.join("");
  }

  function renderTimeline() {
    const events = lastRunWindow(state.timelineEvents);
    const parsed = timelineSpans(events);
    let id = 0;
    const lookup = new Map();
    [...parsed.spans, ...parsed.inputs].forEach((span) => {
      span._id = `s${id++}`;
      lookup.set(span._id, span);
    });
    state.timelineLookup = lookup;

    const bounds = timelineBounds(parsed.spans, parsed.inputs);
    const duration = Math.max(5, bounds.end - bounds.start);
    const pxPerSecond = clamp(900 / duration, 0.35, 4.5);
    const height = Math.max(560, duration * pxPerSecond + 80);

    const agentColumns = parsed.agents.map((agent) => {
      const tool = parsed.spans.filter((span) => span.agent === agent && span.kind === "tool");
      const model = parsed.spans.filter((span) => span.agent === agent && span.kind === "model");
      const input = parsed.inputs.filter((span) => span.agent === agent);
      const column = (lane, spans) => `<div class="cpui-sub-lane ${lane}" data-lane="${lane}">${spans.map((span) => spanCard(span, bounds, pxPerSecond)).join("")}</div>`;
      return `
        <section class="cpui-agent-lane" data-agent="${esc(agent)}">
          <header class="cpui-agent-lane-head"><strong>${esc(agent)}</strong><small>${model.length} model · ${tool.length} tool</small></header>
          <div class="cpui-agent-subheads"><span>TOOL</span><span>MODEL</span><span>INPUT</span></div>
          <div class="cpui-agent-lane-body" style="height:${height}px">
            ${column("tool", tool)}${column("model", model)}${column("input", input)}
          </div>
        </section>`;
    }).join("");

    timelineSurface.innerHTML = `
      <header class="cpui-surface-header">
        <div><p>TRACE / WATERFALL</p><h2>Agent Execution Timeline</h2></div>
        <div class="cpui-surface-actions"><span>${esc(state.sessionId)}</span><button type="button" data-cpui-refresh="timeline">↻</button></div>
      </header>
      <div class="cpui-timeline-viewport">
        <aside class="cpui-time-axis"><div class="cpui-time-axis-head">TIME</div><div class="cpui-time-axis-body" style="height:${height}px">${timeTicks(bounds, pxPerSecond)}</div></aside>
        <div class="cpui-agent-lanes">${agentColumns || '<p class="cpui-empty">No durable Agent timing events yet.</p>'}</div>
      </div>
    `;

    $$(`[data-cpui-span]`, timelineSurface).forEach((button) => {
      button.addEventListener("click", () => openTimelineOverlay(button, lookup.get(button.dataset.cpuiSpan)));
    });
    $(`[data-cpui-refresh="timeline"]`, timelineSurface)?.addEventListener("click", () => refreshTimeline(true));
  }

  function detailRows(detail) {
    const rows = [];
    if (detail?.round !== undefined) rows.push(["Round", detail.round]);
    if (detail?.duration_ms !== undefined) rows.push(["Duration", formatDuration(detail.duration_ms)]);
    if (detail?.tps) rows.push(["Decode", `${detail.tps.toFixed(2)} tok/s`]);
    return rows.map(([key, value]) => `<div><span>${esc(key)}</span><strong>${esc(value)}</strong></div>`).join("");
  }

  function jsonBlock(title, value) {
    if (value === undefined || value === null || value === "") return "";
    let text;
    try { text = typeof value === "string" ? value : JSON.stringify(value, null, 2); }
    catch { text = String(value); }
    return `<section class="cpui-overlay-section"><h4>${esc(title)}</h4><pre>${esc(text)}</pre></section>`;
  }

  function overlayContent(span) {
    const detail = span?.detail || {};
    const heading = span.kind === "tool" ? "TOOL CALL" : span.kind === "model" ? "MODEL CALL" : "USER INPUT";
    const common = `
      <header class="cpui-overlay-head"><div><p>${heading}</p><h3>${esc(span.label)}</h3></div><button type="button" data-cpui-overlay-close aria-label="Close">×</button></header>
      <div class="cpui-overlay-meta"><div><span>Agent</span><strong>${esc(span.agent)}</strong></div><div><span>Start</span><strong>${esc(formatClock(span.start, true))}</strong></div><div><span>End</span><strong>${esc(formatClock(span.end, true))}</strong></div>${detailRows(detail)}</div>`;
    if (span.kind === "model") {
      return `${common}${jsonBlock("Usage", detail.usage)}${jsonBlock("Raw event", detail.event)}`;
    }
    if (span.kind === "tool") {
      return `${common}${jsonBlock("Arguments", detail.call?.args ?? detail.call?.arguments)}${jsonBlock("Result", detail.call?.result)}${jsonBlock("Raw event", detail.event)}`;
    }
    return `${common}${jsonBlock(span.subtype === "steer" ? "Applied steer" : "Prompt", detail.messages ?? detail.message)}${jsonBlock("Raw event", detail.event)}`;
  }

  function chooseOverlayRect(sourceRect) {
    const width = Math.min(560, Math.max(420, window.innerWidth * 0.36));
    const height = Math.min(620, Math.max(360, window.innerHeight * 0.62));
    const margin = 18;
    let left = sourceRect.right + 14;
    if (left + width > window.innerWidth - margin) left = sourceRect.left - width - 14;
    left = clamp(left, margin, window.innerWidth - width - margin);
    let top = sourceRect.top - 40;
    top = clamp(top, margin, window.innerHeight - height - margin);
    return { left, top, width, height };
  }

  function closeTimelineOverlay(animated = true) {
    const record = state.overlay;
    if (!record) return;
    state.overlay = null;
    const { element, sourceRect } = record;
    if (!animated || !element.isConnected) {
      element.remove();
      return;
    }
    const targetVisible = sourceRect.bottom >= 0 && sourceRect.top <= window.innerHeight;
    if (!targetVisible) {
      element.animate([{ opacity: 1, transform: "scale(1)" }, { opacity: 0, transform: "scale(.98)" }], { duration: 130, easing: "ease-in", fill: "forwards" }).finished.finally(() => element.remove());
      return;
    }
    const current = element.getBoundingClientRect();
    element.animate([
      { left: `${current.left}px`, top: `${current.top}px`, width: `${current.width}px`, height: `${current.height}px`, opacity: 1 },
      { left: `${sourceRect.left}px`, top: `${sourceRect.top}px`, width: `${Math.max(sourceRect.width, 8)}px`, height: `${Math.max(sourceRect.height, 8)}px`, opacity: .15 },
    ], { duration: 180, easing: "cubic-bezier(.4,0,.2,1)", fill: "forwards" }).finished.finally(() => element.remove());
  }

  function openTimelineOverlay(source, span) {
    if (!span) return;
    closeTimelineOverlay(false);
    const sourceRect = source.getBoundingClientRect();
    const target = chooseOverlayRect(sourceRect);
    const overlay = pluginElement("aside", "cpui-timeline-overlay");
    overlay.innerHTML = overlayContent(span);
    Object.assign(overlay.style, {
      left: `${sourceRect.left}px`, top: `${sourceRect.top}px`, width: `${Math.max(sourceRect.width, 8)}px`, height: `${Math.max(sourceRect.height, 8)}px`, opacity: "0.25",
    });
    document.body.appendChild(overlay);
    state.overlay = { element: overlay, sourceRect, source };
    overlay.animate([
      { left: `${sourceRect.left}px`, top: `${sourceRect.top}px`, width: `${Math.max(sourceRect.width, 8)}px`, height: `${Math.max(sourceRect.height, 8)}px`, opacity: .2 },
      { left: `${target.left}px`, top: `${target.top}px`, width: `${target.width}px`, height: `${target.height}px`, opacity: 1 },
    ], { duration: 210, easing: "cubic-bezier(.2,.8,.2,1)", fill: "forwards" });
    Object.assign(overlay.style, { left: `${target.left}px`, top: `${target.top}px`, width: `${target.width}px`, height: `${target.height}px`, opacity: "1" });
    overlay.querySelector("[data-cpui-overlay-close]")?.addEventListener("click", () => closeTimelineOverlay(true));
  }

  async function refreshTimeline(force = false) {
    if (!force && Date.now() - state.timelineLoadedAt < 1800 && state.timelineEvents.length) return renderTimeline();
    state.sessionId = currentSessionId();
    timelineSurface.classList.add("loading");
    try {
      const { events, total } = await loadLatestRunEvents(state.sessionId);
      state.timelineEvents = events;
      state.timelineTotal = total;
      state.timelineLoadedAt = Date.now();
      renderTimeline();
    } catch (error) {
      timelineSurface.innerHTML = `<div class="cpui-error"><strong>Timeline load failed</strong><span>${esc(error.message)}</span></div>`;
    } finally {
      timelineSurface.classList.remove("loading");
    }
  }

  // -------------------------------------------------------------------------
  // Statistics / provider telemetry
  // -------------------------------------------------------------------------

  const RANGES = {
    "1h": { label: "1h", seconds: 3600, bucket: 60 },
    "4h": { label: "4h", seconds: 4 * 3600, bucket: 5 * 60 },
    "12h": { label: "12h", seconds: 12 * 3600, bucket: 10 * 60 },
    "24h": { label: "24h", seconds: 24 * 3600, bucket: 30 * 60 },
    "1d": { label: "1d", today: true, bucket: 30 * 60 },
    "3d": { label: "3d", seconds: 3 * 86400, bucket: 2 * 3600 },
    "7d": { label: "7d", seconds: 7 * 86400, bucket: 4 * 3600 },
  };

  function rangeCutoff(key) {
    const range = RANGES[key] || RANGES["1h"];
    const now = new Date();
    if (range.today) {
      const start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      return start.getTime() / 1000;
    }
    return now.getTime() / 1000 - range.seconds;
  }

  function quantile(values, p) {
    if (!values.length) return 0;
    const sorted = [...values].sort((a, b) => a - b);
    const index = (sorted.length - 1) * p;
    const lower = Math.floor(index);
    const upper = Math.ceil(index);
    if (lower === upper) return sorted[lower];
    return sorted[lower] + (sorted[upper] - sorted[lower]) * (index - lower);
  }

  function average(values) {
    return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;
  }

  function stddev(values) {
    if (values.length < 2) return 0;
    const mean = average(values);
    return Math.sqrt(values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / values.length);
  }

  function eventAgent(event) {
    const data = event?.data && typeof event.data === "object" ? event.data : {};
    return String(event?.agent || data.agent || data.agent_id || "coordinator");
  }

  function telemetry(events) {
    const modelCalls = [];
    const tools = [];
    const internal = [];
    const errors = [];
    const agents = new Set();

    for (const event of events) {
      const timestamp = finite(event?.timestamp, 0);
      const data = event?.data && typeof event.data === "object" ? event.data : {};
      const agent = eventAgent(event);

      if (event?.event === "error" || (event?.event === "lifecycle" && event.type === "agent:invalid_response")) {
        agents.add(agent);
        errors.push({ timestamp, agent, event });
      }
      if (event?.event !== "lifecycle") continue;

      if (event.type === "agent:usage") {
        agents.add(agent);
        const usage = data.usage && typeof data.usage === "object" ? data.usage : {};
        const durationMs = finite(data.duration_ms, 0);
        const output = finite(usage.output, 0);
        modelCalls.push({
          timestamp,
          agent,
          round: data.round,
          durationMs,
          usage: {
            input: finite(usage.input, 0), output, total: finite(usage.total, 0), cached: finite(usage.cached, 0), reasoning: finite(usage.reasoning, 0),
          },
          tps: durationMs > 0 && output > 0 ? output / (durationMs / 1000) : 0,
        });
      }

      if (event.type === "agent:internal_usage") {
        agents.add(agent);
        const usage = data.usage && typeof data.usage === "object" ? data.usage : {};
        internal.push({ timestamp, agent, kind: String(data.kind || "internal"), usage: {
          input: finite(usage.input, 0), output: finite(usage.output, 0), total: finite(usage.total, 0), cached: finite(usage.cached, 0), reasoning: finite(usage.reasoning, 0),
        } });
      }

      if (event.type === "agent:tools_completed") {
        agents.add(agent);
        const calls = Array.isArray(data.tool_calls) ? data.tool_calls : [];
        for (const call of calls) {
          tools.push({ timestamp, agent, round: data.round, name: String(call?.name || "tool"), ok: call?.ok !== false, durationMs: finite(call?.duration_ms, 0) });
        }
      }
    }

    return {
      modelCalls, tools, internal, errors,
      agents: [...agents].sort((a, b) => (a === "coordinator" ? -1 : b === "coordinator" ? 1 : a.localeCompare(b))),
    };
  }

  function bucketSeries(items, start, end, bucketSeconds, valueFn, reducer = average) {
    const count = Math.max(1, Math.ceil((end - start) / bucketSeconds));
    const buckets = Array.from({ length: count }, (_, index) => ({
      start: start + index * bucketSeconds,
      end: Math.min(end, start + (index + 1) * bucketSeconds),
      values: [],
    }));
    for (const item of items) {
      const timestamp = finite(item.timestamp, 0);
      if (timestamp < start || timestamp > end) continue;
      const index = clamp(Math.floor((timestamp - start) / bucketSeconds), 0, buckets.length - 1);
      const value = valueFn(item);
      if (Number.isFinite(value)) buckets[index].values.push(value);
    }
    return buckets.map((bucket) => ({ ...bucket, value: bucket.values.length ? reducer(bucket.values) : null }));
  }

  function chartSvg(series, options = {}) {
    const width = 900;
    const height = 190;
    const pad = { l: 44, r: 18, t: 14, b: 28 };
    const values = series.map((point) => point.value).filter((value) => value !== null && Number.isFinite(value));
    if (!values.length) return `<div class="cpui-chart-empty">No samples in this window.</div>`;
    const min = options.zeroFloor === false ? Math.min(...values) : 0;
    const rawMax = Math.max(...values);
    const max = rawMax <= min ? min + 1 : rawMax * 1.08;
    const x = (index) => pad.l + (index / Math.max(1, series.length - 1)) * (width - pad.l - pad.r);
    const y = (value) => pad.t + (1 - (value - min) / (max - min)) * (height - pad.t - pad.b);
    let path = "";
    let drawing = false;
    series.forEach((point, index) => {
      if (point.value === null || !Number.isFinite(point.value)) {
        drawing = false;
        return;
      }
      path += `${drawing ? " L" : " M"}${x(index).toFixed(2)} ${y(point.value).toFixed(2)}`;
      drawing = true;
    });
    const yTicks = [0, .25, .5, .75, 1].map((ratio) => {
      const value = min + (max - min) * (1 - ratio);
      const yy = pad.t + ratio * (height - pad.t - pad.b);
      return `<line x1="${pad.l}" x2="${width - pad.r}" y1="${yy}" y2="${yy}" class="grid"/><text x="${pad.l - 8}" y="${yy + 4}" text-anchor="end">${esc(options.formatY ? options.formatY(value) : value.toFixed(0))}</text>`;
    }).join("");
    const firstLabel = formatClock(series[0]?.start || 0, true);
    const lastLabel = formatClock(series.at(-1)?.end || 0, true);
    return `<svg class="cpui-line-chart" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img">
      <g class="axis">${yTicks}<text x="${pad.l}" y="${height - 6}" text-anchor="start">${esc(firstLabel)}</text><text x="${width - pad.r}" y="${height - 6}" text-anchor="end">${esc(lastLabel)}</text></g>
      <path d="${path.trim()}" class="series" vector-effect="non-scaling-stroke"/>
    </svg>`;
  }

  function tokenTotals(modelCalls, internal) {
    const total = { input: 0, output: 0, total: 0, cached: 0, reasoning: 0 };
    for (const record of [...modelCalls, ...internal]) {
      for (const key of Object.keys(total)) total[key] += finite(record.usage?.[key], 0);
    }
    return total;
  }

  function activitySeries(modelCalls, tools, start, end, bucket) {
    const combined = [
      ...modelCalls.map((item) => ({ timestamp: item.timestamp, value: 1 })),
      ...tools.map((item) => ({ timestamp: item.timestamp, value: 1 })),
    ];
    return bucketSeries(combined, start, end, bucket, (item) => item.value, (values) => values.length);
  }

  function internalBreakdown(records) {
    const byKind = new Map();
    for (const record of records) {
      const current = byKind.get(record.kind) || 0;
      byKind.set(record.kind, current + finite(record.usage?.total, 0));
    }
    const sum = [...byKind.values()].reduce((a, b) => a + b, 0);
    return [...byKind.entries()].sort((a, b) => b[1] - a[1]).map(([kind, tokens]) => ({ kind, tokens, pct: sum ? tokens / sum * 100 : 0 }));
  }

  function renderStatistics() {
    const range = RANGES[state.statsRange] || RANGES["1h"];
    const end = Date.now() / 1000;
    const start = rangeCutoff(state.statsRange);
    const windowEvents = state.statsEvents.filter((event) => {
      const timestamp = finite(event.timestamp, 0);
      return timestamp >= start && timestamp <= end + 2;
    });
    const windowData = telemetry(windowEvents);
    const availableAgents = windowData.agents;
    if (state.statsAgent !== "all" && !availableAgents.includes(state.statsAgent)) {
      state.statsAgent = "all";
      localStorage.cpuiStatsAgent = "all";
    }
    const events = state.statsAgent === "all"
      ? windowEvents
      : windowEvents.filter((event) => eventAgent(event) === state.statsAgent);
    const data = telemetry(events);
    const tpsValues = data.modelCalls.map((call) => call.tps).filter((value) => value > 0);
    const latencyValues = data.modelCalls.map((call) => call.durationMs / 1000).filter((value) => value > 0);
    const jitter = average(tpsValues) > 0 ? stddev(tpsValues) / average(tpsValues) * 100 : 0;
    const totals = tokenTotals(data.modelCalls, data.internal);
    const cacheHit = totals.input > 0 ? totals.cached / totals.input * 100 : 0;
    const toolFailures = data.tools.filter((tool) => !tool.ok).length;
    const errorRate = data.modelCalls.length ? data.errors.length / data.modelCalls.length * 100 : 0;

    const tpsSeries = bucketSeries(data.modelCalls.filter((call) => call.tps > 0), start, end, range.bucket, (call) => call.tps);
    const latencySeries = bucketSeries(data.modelCalls, start, end, range.bucket, (call) => call.durationMs / 1000);
    const cacheSeries = bucketSeries(data.modelCalls, start, end, range.bucket, (call) => call.usage.input > 0 ? call.usage.cached / call.usage.input * 100 : NaN);
    const toolLatencySeries = bucketSeries(data.tools.filter((tool) => tool.durationMs > 0), start, end, range.bucket, (tool) => tool.durationMs / 1000);
    const activity = activitySeries(data.modelCalls, data.tools, start, end, range.bucket);

    const internal = internalBreakdown(data.internal);
    const rangeButtons = Object.entries(RANGES).map(([key, item]) => `<button type="button" class="${state.statsRange === key ? "active" : ""}" data-cpui-range="${key}" title="${key === "1d" ? "Today (local midnight → now)" : item.label}">${item.label}</button>`).join("");
    const agentOptions = [
      `<option value="all"${state.statsAgent === "all" ? " selected" : ""}>ALL AGENTS</option>`,
      ...availableAgents.map((agent) => `<option value="${esc(agent)}"${state.statsAgent === agent ? " selected" : ""}>${esc(agent)}</option>`),
    ].join("");
    const scopeLabel = state.statsAgent === "all" ? "All agents" : state.statsAgent;

    statisticsSurface.innerHTML = `
      <header class="cpui-surface-header cpui-stat-head">
        <div><p>SESSION TELEMETRY · ${esc(scopeLabel)}</p><h2>Statistics</h2></div>
        <div class="cpui-stat-controls">
          <label class="cpui-agent-filter" title="Filter all telemetry panels to one Agent"><span>AGENT</span><select data-cpui-stats-agent>${agentOptions}</select></label>
          <div class="cpui-range-tabs">${rangeButtons}</div>
          <button type="button" data-cpui-refresh="statistics">↻</button>
        </div>
      </header>
      <div class="cpui-stat-scroll">
        <div class="cpui-kpi-strip">
          <div><span>TPS P50</span><strong>${tpsValues.length ? quantile(tpsValues, .5).toFixed(1) : "—"}</strong><small>tok/s</small></div>
          <div><span>TPS P95</span><strong>${tpsValues.length ? quantile(tpsValues, .95).toFixed(1) : "—"}</strong><small>tok/s</small></div>
          <div><span>JITTER</span><strong>${tpsValues.length > 1 ? jitter.toFixed(1) : "—"}</strong><small>% CV</small></div>
          <div><span>CACHE HIT</span><strong>${totals.input ? cacheHit.toFixed(1) : "—"}</strong><small>%</small></div>
          <div><span>ERRORS</span><strong>${data.errors.length}</strong><small>${errorRate.toFixed(1)}%</small></div>
          <div><span>CALLS</span><strong>${data.modelCalls.length}</strong><small>${data.tools.length} tools</small></div>
        </div>

        <section class="cpui-chart-panel wide"><header><div><p>MODEL</p><h3>Throughput</h3></div><span>P50 ${tpsValues.length ? quantile(tpsValues, .5).toFixed(1) : "—"} · max ${tpsValues.length ? Math.max(...tpsValues).toFixed(1) : "—"} tok/s</span></header>${chartSvg(tpsSeries, { formatY: (value) => `${value.toFixed(0)}` })}</section>

        <div class="cpui-chart-grid">
          <section class="cpui-chart-panel"><header><div><p>MODEL</p><h3>Latency</h3></div><span>P95 ${latencyValues.length ? quantile(latencyValues, .95).toFixed(1) : "—"}s</span></header>${chartSvg(latencySeries, { formatY: (value) => `${value.toFixed(0)}s` })}</section>
          <section class="cpui-chart-panel"><header><div><p>PROMPT</p><h3>Cache Hit</h3></div><span>${totals.cached.toLocaleString()} cached</span></header>${chartSvg(cacheSeries, { formatY: (value) => `${value.toFixed(0)}%` })}</section>
          <section class="cpui-chart-panel"><header><div><p>TOOLS</p><h3>Execution Latency</h3></div><span>${toolFailures} failed / ${data.tools.length}</span></header>${chartSvg(toolLatencySeries, { formatY: (value) => `${value.toFixed(1)}s` })}</section>
          <section class="cpui-chart-panel"><header><div><p>ACTIVITY</p><h3>Calls per Bucket</h3></div><span>${state.statsAgent === "all" ? `${availableAgents.length || 1} agents seen` : esc(scopeLabel)}</span></header>${chartSvg(activity, { formatY: (value) => `${value.toFixed(0)}` })}</section>
        </div>

        <section class="cpui-token-panel">
          <header><div><p>USAGE LEDGER</p><h3>Token Usage</h3></div><span>${totals.total.toLocaleString()} total</span></header>
          <div class="cpui-token-bars">
            ${[["Cached input", totals.cached, totals.input], ["Uncached input", Math.max(0, totals.input - totals.cached), totals.input], ["Output", totals.output, totals.total], ["Reasoning", totals.reasoning, totals.total]].map(([label, value, denominator]) => `<div><span>${label}</span><div><i style="width:${denominator ? clamp(value / denominator * 100, 0, 100) : 0}%"></i></div><strong>${formatNumber(value)}</strong></div>`).join("")}
          </div>
        </section>

        <section class="cpui-internal-panel">
          <header><div><p>HIDDEN MODEL WORK</p><h3>Internal LLM Usage</h3></div><span>${data.internal.length} calls</span></header>
          <div class="cpui-internal-list">${internal.length ? internal.map((item) => `<div><strong>${esc(item.kind)}</strong><span>${item.tokens.toLocaleString()} tokens</span><em>${item.pct.toFixed(1)}%</em></div>`).join("") : '<p class="cpui-empty">No internal usage ledger entries in this window.</p>'}</div>
        </section>
      </div>`;

    $$(`[data-cpui-range]`, statisticsSurface).forEach((button) => button.addEventListener("click", () => {
      state.statsRange = button.dataset.cpuiRange;
      refreshStatistics(true);
    }));
    $(`[data-cpui-stats-agent]`, statisticsSurface)?.addEventListener("change", (event) => {
      state.statsAgent = String(event.target.value || "all");
      localStorage.cpuiStatsAgent = state.statsAgent;
      renderStatistics();
    });
    $(`[data-cpui-refresh="statistics"]`, statisticsSurface)?.addEventListener("click", () => refreshStatistics(true));
  }

  async function refreshStatistics(force = false) {
    if (!force && Date.now() - state.statsLoadedAt < 1800 && state.statsEvents.length) return renderStatistics();
    state.sessionId = currentSessionId();
    statisticsSurface.classList.add("loading");
    try {
      const cutoff = rangeCutoff(state.statsRange);
      const { events } = await loadEventsSince(state.sessionId, cutoff, 160);
      state.statsEvents = events;
      state.statsLoadedAt = Date.now();
      renderStatistics();
    } catch (error) {
      statisticsSurface.innerHTML = `<div class="cpui-error"><strong>Statistics load failed</strong><span>${esc(error.message)}</span></div>`;
    } finally {
      statisticsSurface.classList.remove("loading");
    }
  }

  // -------------------------------------------------------------------------
  // Slash Console
  // -------------------------------------------------------------------------

  const BUILTIN_COMMANDS = [
    { command: "/help", title: "Show slash command help", keywords: "help commands", immediate: true },
    { command: "/new", title: "Create and switch session", keywords: "session create", args: "<session name>" },
    { command: "/switch", title: "Switch session", keywords: "session workspace", args: "<session>" },
    { command: "/clear", title: "Clear transcript view", keywords: "chat transcript", immediate: true },
    { command: "/connectors", title: "Open connector settings", keywords: "provider model connector", immediate: true },
    { command: "/settings", title: "Open settings", keywords: "configuration", args: "[--panel=…]" },
    { command: "/plan", title: "Open host plan inspector", keywords: "tasks", immediate: true },
    { command: "/agents", title: "Open host Agent inspector", keywords: "swarm", immediate: true },
    { command: "/usage", title: "Open host token usage", keywords: "tokens", immediate: true },
    { command: "/trace", title: "Open host raw trace", keywords: "events", immediate: true },
    { command: "/stop", title: "Request safe stop", keywords: "run", immediate: true },
    { command: "/force-stop", title: "Force-stop current run", keywords: "run kill", immediate: true },
    { command: "/agent", title: "Select Agent transcript", keywords: "swarm", args: "<agent>" },
    { command: "/delete", title: "Delete session", keywords: "session", args: "<session>" },
    { command: "/compact", title: "Compact context", keywords: "context summary", args: "[--agent=<id>]" },
  ];

  const VIEW_COMMANDS = [
    { command: "/timeline", title: "Open Control Plane Timeline", view: "timeline", keywords: "waterfall trace" },
    { command: "/statistics", title: "Open Control Plane Statistics", view: "statistics", keywords: "metrics telemetry charts" },
    { command: "/transcript", title: "Open Transcript", view: "transcript", keywords: "chat" },
    { command: "/agents-view", title: "Open Agent topology", view: "agents", keywords: "swarm" },
    { command: "/plan-view", title: "Open Plan", view: "plan", keywords: "task" },
  ];

  async function agentSuggestions(prefix = "") {
    try {
      const payload = await apiJson(`/api/sessions/${encodeURIComponent(currentSessionId())}/agents`);
      return (Array.isArray(payload.agents) ? payload.agents : [])
        .filter((agent) => agent?.id && agent.id !== "all" && String(agent.id).toLowerCase().includes(prefix.toLowerCase()))
        .map((agent) => ({ value: String(agent.id), title: agent.parent ? `Agent · parent ${agent.parent}` : "Agent" }));
    } catch { return []; }
  }

  function sessionSuggestions(prefix = "") {
    return [...workspaceSelect.options]
      .map((option) => ({ value: option.value, label: option.textContent || option.value }))
      .filter((item) => `${item.value} ${item.label}`.toLowerCase().includes(prefix.toLowerCase()))
      .map((item) => ({ value: item.value, title: item.label }));
  }

  function commandCatalog() {
    const pluginCommands = window.Angelus?.getRegisteredCommands?.() || [];
    const pluginItems = pluginCommands
      .filter((command) => command?.key && command.plugin !== PLUGIN)
      .map((command) => ({ command: `/${command.key}`, title: command.description || "Plugin command", pluginKey: command.key, keywords: `plugin ${command.plugin}` }));
    return [...VIEW_COMMANDS, ...BUILTIN_COMMANDS, ...pluginItems];
  }

  async function slashItems(value) {
    const text = String(value || "");
    if (!text.startsWith("/") || text.startsWith("//")) return { mode: "closed", items: [] };
    const firstSpace = text.indexOf(" ");
    if (firstSpace < 0) {
      const needle = text.slice(1).toLowerCase();
      const items = commandCatalog().filter((item) => {
        const hay = `${item.command.slice(1)} ${item.title} ${item.keywords || ""}`.toLowerCase();
        return !needle || hay.includes(needle);
      }).slice(0, 14);
      return { mode: "commands", items };
    }

    const command = text.slice(0, firstSpace);
    const argument = text.slice(firstSpace + 1);
    if (command === "/agent") return { mode: "agent", items: (await agentSuggestions(argument)).map((item) => ({ ...item, command })) };
    if (command === "/switch" || command === "/delete") return { mode: "session", items: sessionSuggestions(argument).map((item) => ({ ...item, command })) };
    if (command === "/compact") {
      const prefix = argument.replace(/^--agent=/, "");
      return { mode: "agent", items: (await agentSuggestions(prefix)).map((item) => ({ ...item, command, flag: "--agent=" })) };
    }
    if (command === "/settings") {
      const prefix = argument.replace(/^--panel=/, "");
      const panels = ["connection", "agent", "plugins", "future"].filter((value) => value.includes(prefix));
      return { mode: "settings", items: panels.map((value) => ({ value, title: "Settings panel", command, flag: "--panel=" })) };
    }
    return { mode: "commands", items: [] };
  }

  function renderSlashConsole() {
    const { items, mode } = state.slash;
    if (!state.slash.open || !items.length) {
      slashConsole.hidden = true;
      document.body.classList.remove("cpui-command-mode");
      commandLabel.querySelector("span").textContent = "COMMAND";
      return;
    }
    slashConsole.hidden = false;
    document.body.classList.add("cpui-command-mode");
    commandLabel.querySelector("span").textContent = "COMMAND MODE";
    const modeTitle = { commands: "COMMANDS", agent: "AGENTS", session: "SESSIONS", settings: "SETTINGS" }[mode] || "COMMANDS";
    slashConsole.innerHTML = `
      <header><strong>${modeTitle}</strong><span>${items.length}</span></header>
      <div class="cpui-slash-items">${items.map((item, index) => {
        const primary = item.command || item.value || "";
        const suffix = item.args ? ` ${item.args}` : "";
        return `<button type="button" class="${index === state.slash.selected ? "active" : ""}" data-cpui-slash-index="${index}"><code>${esc(primary)}${esc(suffix)}</code><span>${esc(item.title || "")}</span>${item.pluginKey ? '<em>PLUGIN</em>' : ""}</button>`;
      }).join("")}</div>
      <footer><span>↑↓ select</span><span>Tab complete</span><span>Enter run</span><span>Esc close</span></footer>`;
    $$(`[data-cpui-slash-index]`, slashConsole).forEach((button) => button.addEventListener("mouseenter", () => {
      state.slash.selected = Number(button.dataset.cpuiSlashIndex || 0);
      renderSlashConsole();
    }));
    $$(`[data-cpui-slash-index]`, slashConsole).forEach((button) => button.addEventListener("mousedown", (event) => {
      event.preventDefault();
      state.slash.selected = Number(button.dataset.cpuiSlashIndex || 0);
      acceptSlashSelection(false);
    }));
  }

  async function updateSlashConsole() {
    const text = messageInput.value;
    const seq = ++state.slash.querySeq;
    const result = await slashItems(text);
    if (seq !== state.slash.querySeq || text !== messageInput.value) return;
    state.slash.mode = result.mode;
    state.slash.items = result.items;
    state.slash.selected = clamp(state.slash.selected, 0, Math.max(0, result.items.length - 1));
    state.slash.open = result.mode !== "closed" && result.items.length > 0;
    renderSlashConsole();
  }

  function closeSlashConsole() {
    state.slash.open = false;
    state.slash.items = [];
    state.slash.selected = 0;
    renderSlashConsole();
  }

  function replaceInput(value) {
    messageInput.value = value;
    messageInput.dispatchEvent(new Event("input", { bubbles: true }));
    messageInput.focus();
    messageInput.setSelectionRange(value.length, value.length);
  }

  function clearAndResizeInput() {
    messageInput.value = "";
    messageInput.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function acceptSlashSelection(execute) {
    const item = state.slash.items[state.slash.selected];
    if (!item) return;

    if (state.slash.mode === "commands") {
      if (item.view) {
        if (execute) {
          setView(item.view);
          clearAndResizeInput();
          closeSlashConsole();
        } else {
          replaceInput(item.command);
        }
        return;
      }
      if (item.pluginKey) {
        if (execute) {
          window.Angelus?.dispatchCommand?.(item.pluginKey, [], {});
          clearAndResizeInput();
          closeSlashConsole();
        } else replaceInput(item.command);
        return;
      }
      if (execute && item.immediate) {
        replaceInput(item.command);
        closeSlashConsole();
        composer.requestSubmit();
        return;
      }
      replaceInput(`${item.command}${item.args ? " " : ""}`);
      return;
    }

    const command = item.command || messageInput.value.split(/\s+/, 1)[0];
    const value = `${command} ${item.flag || ""}${item.value}`;
    replaceInput(value);
    if (execute) {
      closeSlashConsole();
      composer.requestSubmit();
    }
  }

  messageInput.addEventListener("input", () => { updateSlashConsole(); });
  messageInput.addEventListener("keydown", (event) => {
    if (!state.slash.open) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      event.stopImmediatePropagation();
      const delta = event.key === "ArrowDown" ? 1 : -1;
      state.slash.selected = (state.slash.selected + delta + state.slash.items.length) % state.slash.items.length;
      renderSlashConsole();
      return;
    }
    if (event.key === "Tab") {
      event.preventDefault();
      event.stopImmediatePropagation();
      acceptSlashSelection(false);
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopImmediatePropagation();
      closeSlashConsole();
      return;
    }
    if (event.key === "Enter" && !event.shiftKey && !event.altKey && !event.isComposing) {
      event.preventDefault();
      event.stopImmediatePropagation();
      acceptSlashSelection(true);
    }
  }, true);

  // -------------------------------------------------------------------------
  // Host/session lifecycle
  // -------------------------------------------------------------------------

  workspaceSelect.addEventListener("change", () => {
    state.sessionId = currentSessionId();
    state.timelineEvents = [];
    state.statsEvents = [];
    state.timelineLoadedAt = 0;
    state.statsLoadedAt = 0;
    closeTimelineOverlay(false);
    if (state.view === "timeline") setTimeout(() => refreshTimeline(true), 80);
    if (state.view === "statistics") setTimeout(() => refreshStatistics(true), 80);
  });

  document.addEventListener("click", (event) => {
    if (state.overlay && !event.target.closest?.(".cpui-timeline-overlay") && !event.target.closest?.("[data-cpui-span]")) closeTimelineOverlay(true);
    if (state.slash.open && !event.target.closest?.("#cpui-slash-console") && event.target !== messageInput) closeSlashConsole();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && state.overlay) closeTimelineOverlay(true);
  });

  // Light live refresh without opening another durable SSE consumer.
  state.refreshTimer = window.setInterval(() => {
    if (document.hidden) return;
    if (state.view === "timeline") refreshTimeline(true);
    else if (state.view === "statistics" && Date.now() - state.statsLoadedAt >= 30_000) refreshStatistics(true);
  }, 7000);

  // -------------------------------------------------------------------------
  // Plugin bridge commands
  // -------------------------------------------------------------------------

  const viewCommands = {
    timeline: "timeline",
    transcript: "transcript",
    agents: "agents",
    plan: "plan",
    statistics: "statistics",
  };
  Object.entries(viewCommands).forEach(([id, view]) => {
    window.Angelus?.registerCommand?.(PLUGIN, {
      id,
      description: `Switch Control Plane UI to ${view}`,
      handler() { setView(view); return { view }; },
    });
  });

  // Initial render; do not block the host boot sequence.
  setTimeout(() => refreshTimeline(true), 50);
  console.info(`[${PLUGIN}] v${VERSION} mounted`);
})();
