/**
 * Token Burner 🔥 — plugin.js
 *
 * Renders Angelus' token burn rate as a living flame.
 *
 * Data source (browser-visible, credential-free, contract-consistent):
 *   - GET /api/sessions/{id}/usage   → session-wide cumulative token totals
 *   - GET /api/sessions/{id}/events  → durable lifecycle log (agent:round /
 *                                       agent:complete activity hints)
 * The burn rate is computed from the *slope* of the cumulative total over a
 * sliding window (default 20 s), then exponentially smoothed — never from
 * a single instantaneous sample, so the flame never flickers spastically.
 *
 * Window modes:
 *   1. Host workbench — a draggable floating window (position:fixed overlay,
 *      z-index above the workbench), toggled by the "token-burner:toggle"
 *      plugin command.
 *   2. Popout — "⤢" or "token-burner:popout" opens window.html in a real,
 *      OS-managed, detached browser window (same origin → same APIs).
 *
 * The backend entry (main.py) is deliberately inert; this file does all work.
 */
(function () {
  "use strict";

  const PLUGIN = "token-burner";
  const VERSION = "0.1.1";

  // Guard: plugin.js may run in the host page AND in the popout window.html.
  if (window.__tokenBurnerStarted) return;
  window.__tokenBurnerStarted = true;

  const isPopout = document.body && document.body.classList.contains("tb-popout");
  const hasBridge = typeof window.Angelus !== "undefined" && window.Angelus;

  /* ================================================================
   * Preferences (localStorage — host page and popout share the origin)
   * ================================================================ */
  const PREFS_KEY = "token-burner.prefs";
  function readPrefs() {
    try { return JSON.parse(localStorage.getItem(PREFS_KEY) || "{}"); } catch (_) { return {}; }
  }
  const prefs = Object.assign({
    windowSeconds: 20,      // sliding window for the average burn rate
    scaleTokensPerSec: 60,  // tokens/sec that maps to a full blaze
    pollMs: 2000,           // usage poll interval
    maxParticles: 140,      // particle pool cap (perf guard)
    showReadout: true,      // show tok/s + total readout
  }, readPrefs());

  /* ================================================================
   * Session identity — same source of truth as the workbench
   * (app.js: sessionId = localStorage.llmfetcherSession ||
   * llmfetcherWorkspace || "default")
   * ================================================================ */
  function currentSessionId() {
    const fromQuery = new URLSearchParams(location.search).get("session");
    return (
      fromQuery ||
      localStorage.llmfetcherSession ||
      localStorage.llmfetcherWorkspace ||
      "default"
    );
  }

  function fmt(n) {
    const v = Number(n) || 0;
    if (v >= 1e6) return (v / 1e6).toFixed(2) + "M";
    if (v >= 1e3) return (v / 1e3).toFixed(1) + "k";
    return String(Math.round(v));
  }

  /* ================================================================
   * Data layer — smoothed burn rate
   * ================================================================ */
  const samples = [];       // [{t: ms, total: tokens}] ring buffer
  let lastTotal = 0;
  let lastPollAt = 0;
  let staleSince = 0;       // 0 = healthy
  let smoothRate = 0;       // tokens/sec, EWMA
  let burst = 0;            // combustion pulse 0..1 (on usage deltas)
  let recentActivity = 0;   // 0..1 from recent round/complete events

  function onUsageDelta(total, now) {
    if (total > 0 && lastTotal > 0 && total > lastTotal) {
      burst = Math.min(1, burst + 0.55);       // combustion event → sparks
      lastPollAt = now;
    }
    lastTotal = total;
  }

  function pushSample(total, now) {
    samples.push({ t: now, total });
    const cutoff = now - 150000;                 // keep ~150 s of history
    while (samples.length && samples[0].t < cutoff) samples.shift();
  }

  function windowRate(now) {
    if (samples.length < 2) return 0;
    const winStart = now - prefs.windowSeconds * 1000;
    let first = samples[0];
    for (const s of samples) {
      if (s.t >= winStart) { first = s; break; }
      first = s;
    }
    const last = samples[samples.length - 1];
    const dtMs = last.t - first.t;
    if (dtMs < 1500) return 0;                   // need real time span
    return Math.max(0, (last.total - first.total) / (dtMs / 1000));
  }

  async function pollUsage() {
    const sid = currentSessionId();
    const now = Date.now();
    try {
      const res = await fetch(
        "/api/sessions/" + encodeURIComponent(sid) + "/usage",
        { cache: "no-store" }
      );
      if (!res.ok) throw new Error("HTTP " + res.status);
      const payload = await res.json();
      const total = Number((payload.usage && payload.usage.total) || 0);
      if (total !== lastTotal) onUsageDelta(total, now);
      pushSample(total, now);
      staleSince = 0;
      const rate = windowRate(now);
      smoothRate += (rate - smoothRate) * 0.35;  // EWMA per poll (2 s)
      refreshActivity(sid).catch(function () {}); // activity hint, non-fatal
    } catch (_) {
      if (!staleSince) staleSince = now;
      else if (now - staleSince > 8000) smoothRate *= 0.6; // decay to ember
    }
  }

  /** Recent agent:round/complete/start within the window → warm signal. */
  async function refreshActivity(sid) {
    const res = await fetch(
      "/api/sessions/" + encodeURIComponent(sid) + "/events?limit=30",
      { cache: "no-store" }
    );
    if (!res.ok) return;
    const payload = await res.json();
    const events = Array.isArray(payload.events) ? payload.events : [];
    const now = Date.now() / 1000;
    let act = 0;
    for (const ev of events) {
      const type = String(ev.type || "");
      if (type !== "agent:round" && type !== "agent:complete" && type !== "agent:start") continue;
      const ts = Number(ev.timestamp || 0);
      if (!ts) continue;
      const age = Math.max(0, now - ts);
      if (age > prefs.windowSeconds) continue;
      act = Math.max(act, Math.exp(-age / prefs.windowSeconds));
    }
    recentActivity = Math.max(recentActivity * 0.6, act); // ~10 s decay
  }

  /** Normalized flame intensity target (0..1, never fully 0 → embers). */
  function targetIntensity() {
    let inten = smoothRate / prefs.scaleTokensPerSec;
    inten = Math.max(inten, recentActivity * 0.35); // stay warm between rounds
    return Math.max(0.045, Math.min(1, inten));
  }

  /* ================================================================
   * Flame engine — canvas particles + layered gradients
   * ================================================================ */
  let canvas = null;
  let ctx = null;
  let W = 0;
  let H = 0;
  let DPR = 1;
  let displayIntensity = 0.05;
  let lastFrame = 0;

  const PALETTE = [
    [255, 250, 210], // 0 white-hot
    [255, 214, 110], // 1 yellow
    [255, 156, 64],  // 2 orange
    [255, 96, 40],   // 3 red-orange
    [205, 56, 22],   // 4 ember red
  ];
  const sprites = [];

  function buildSprites() {
    for (let i = 0; i < PALETTE.length; i++) {
      const s = document.createElement("canvas");
      s.width = s.height = 64;
      const c = s.getContext("2d");
      const rgb = PALETTE[i].join(",");
      const grad = c.createRadialGradient(32, 32, 0, 32, 32, 32);
      grad.addColorStop(0, "rgba(" + rgb + ",1)");
      grad.addColorStop(0.35, "rgba(" + rgb + ",0.55)");
      grad.addColorStop(1, "rgba(" + rgb + ",0)");
      c.fillStyle = grad;
      c.fillRect(0, 0, 64, 64);
      sprites.push(s);
    }
  }

  function resize() {
    const rect = canvas.parentElement.getBoundingClientRect();
    DPR = Math.min(2, window.devicePixelRatio || 1);
    W = Math.max(64, Math.round(rect.width));
    H = Math.max(64, Math.round(rect.height));
    canvas.width = Math.round(W * DPR);
    canvas.height = Math.round(H * DPR);
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
  }

  const particles = [];
  const sparks = [];

  function spawnParticle(intensity) {
    if (particles.length >= prefs.maxParticles) return;
    const cx = W * 0.5;
    const hot = Math.random() < 0.18 + intensity * 0.58;
    const hueIdx = hot
      ? (Math.random() < 0.64 ? 0 : 1)
      : (Math.random() < 0.72 ? 2 : (Math.random() < 0.78 ? 3 : 4));
    particles.push({
      x: cx + (Math.random() - 0.5) * W * (0.20 + intensity * 0.18),
      y: H * (0.77 + Math.random() * 0.13),
      vx: (Math.random() - 0.5) * (0.28 + intensity * 0.72),
      vy: -(0.55 + Math.random() * 2.5) * (0.55 + intensity * 1.55),
      size: (1.8 + Math.random() * 5.2) * (0.58 + intensity * 0.92),
      life: 1,
      decay: 0.005 + Math.random() * 0.014,
      hueIdx: hueIdx,
      seed: Math.random() * Math.PI * 2,
      spin: (Math.random() - 0.5) * 0.03,
    });
  }

  function spawnSpark(intensity) {
    if (sparks.length > 24) return;
    sparks.push({
      x: W * 0.5 + (Math.random() - 0.5) * W * 0.3,
      y: H * (0.68 + Math.random() * 0.24),
      vx: (Math.random() - 0.5) * 3.4,
      vy: -(2.6 + Math.random() * 4.6) * (0.5 + intensity),
      life: 1,
      decay: 0.015 + Math.random() * 0.03,
      len: 6 + Math.random() * 11,
    });
  }

  function flamePath(cx, baseY, w, h, tSec, phase, lean, pinch) {
    const wobble = Math.sin(tSec * (2.0 + phase * 0.11) + phase) * w * 0.035;
    const flutter = Math.sin(tSec * (4.4 + phase * 0.17) + phase * 1.7) * w * 0.018;
    const tipX = cx + lean + wobble * 2.6 + flutter * 2.4;
    const neckX = cx + lean * 0.62 + wobble;
    const shoulder = 0.40 + pinch * 0.08;

    ctx.beginPath();
    ctx.moveTo(cx - w * 0.5, baseY);
    ctx.bezierCurveTo(
      cx - w * (0.67 + 0.05 * Math.sin(tSec * 2.2 + phase)), baseY - h * 0.20,
      neckX - w * shoulder, baseY - h * 0.57,
      tipX, baseY - h
    );
    ctx.bezierCurveTo(
      neckX + w * (0.32 - pinch * 0.04), baseY - h * 0.72,
      cx + w * (0.69 + 0.04 * Math.sin(tSec * 2.8 + phase * 0.7)), baseY - h * 0.23,
      cx + w * 0.5, baseY
    );
    ctx.bezierCurveTo(
      cx + w * 0.30, baseY + h * 0.025,
      cx - w * 0.29, baseY + h * 0.025,
      cx - w * 0.5, baseY
    );
    ctx.closePath();
  }

  function drawTongue(cx, baseY, w, h, tSec, phase, alpha, rgb) {
    const lean = Math.sin(tSec * 2.6 + phase) * w * 0.55;
    const grad = ctx.createLinearGradient(cx, baseY, cx + lean, baseY - h);
    grad.addColorStop(0, "rgba(" + rgb + "," + alpha.toFixed(3) + ")");
    grad.addColorStop(0.58, "rgba(" + rgb + "," + (alpha * 0.48).toFixed(3) + ")");
    grad.addColorStop(1, "rgba(" + rgb + ",0)");
    ctx.fillStyle = grad;
    flamePath(cx, baseY, w, h, tSec, phase, lean, 0.6);
    ctx.fill();
  }

  function drawFlame(intensity, tSec) {
    const cx = W * 0.5;
    const baseY = H * 0.875;
    const breathe = 0.965 + 0.035 * Math.sin(tSec * 3.9);
    const h = (26 + intensity * 132) * breathe;
    const w = (30 + intensity * 50) * (0.985 + 0.028 * Math.sin(tSec * 2.25 + 0.8));
    const lean = Math.sin(tSec * 1.45) * (2.0 + intensity * 5.4)
      + Math.sin(tSec * 3.55 + 1.4) * (0.8 + intensity * 2.3);

    // Ground bloom: a soft elliptical pool of light that makes the flame feel anchored.
    ctx.save();
    ctx.globalCompositeOperation = "lighter";
    const floor = ctx.createRadialGradient(cx, baseY + 3, 0, cx, baseY + 3, w * 2.05);
    floor.addColorStop(0, "rgba(255,196,92," + (0.10 + intensity * 0.26).toFixed(3) + ")");
    floor.addColorStop(0.36, "rgba(255,101,28," + (0.08 + intensity * 0.18).toFixed(3) + ")");
    floor.addColorStop(1, "rgba(255,60,10,0)");
    ctx.save();
    ctx.scale(1, 0.34);
    ctx.fillStyle = floor;
    ctx.fillRect(cx - w * 2.2, (baseY - w * 0.65) / 0.34, w * 4.4, w * 1.3 / 0.34);
    ctx.restore();

    // Broad atmospheric glow. Two halos give depth without per-particle blur.
    const glowR = w * 2.45 + h * 0.72;
    const glow = ctx.createRadialGradient(cx + lean * 0.3, baseY - h * 0.34, 0, cx, baseY - h * 0.30, glowR);
    glow.addColorStop(0, "rgba(255,154,60," + (0.07 + intensity * 0.17).toFixed(3) + ")");
    glow.addColorStop(0.30, "rgba(255,83,24," + (0.05 + intensity * 0.10).toFixed(3) + ")");
    glow.addColorStop(1, "rgba(255,60,15,0)");
    ctx.fillStyle = glow;
    ctx.fillRect(cx - glowR, baseY - h * 1.55, glowR * 2, h * 1.85);
    ctx.restore();

    // Small side tongues appear as the flame grows. They keep the silhouette alive.
    ctx.save();
    ctx.globalCompositeOperation = "screen";
    if (intensity > 0.16) {
      drawTongue(cx - w * 0.24, baseY - h * 0.01, w * (0.26 + intensity * 0.12), h * (0.38 + intensity * 0.23), tSec, 2.3, 0.16 + intensity * 0.18, "255,106,38");
    }
    if (intensity > 0.34) {
      drawTongue(cx + w * 0.27, baseY - h * 0.015, w * (0.22 + intensity * 0.10), h * (0.30 + intensity * 0.20), tSec, 5.1, 0.12 + intensity * 0.16, "255,150,52");
    }
    ctx.restore();

    // Main body. Each layer has its own lean/phase so the edges do not stack into a flat icon.
    const layers = [
      { scaleW: 1.00, scaleH: 1.00, rgb: "183,48,18", a0: 0.28, a1: 0.46, phase: 0.0, pinch: 0.1 },
      { scaleW: 0.79, scaleH: 0.88, rgb: "244,79,20", a0: 0.34, a1: 0.54, phase: 1.4, pinch: 0.25 },
      { scaleW: 0.59, scaleH: 0.70, rgb: "255,148,42", a0: 0.42, a1: 0.64, phase: 2.9, pinch: 0.42 },
      { scaleW: 0.39, scaleH: 0.49, rgb: "255,213,93", a0: 0.52, a1: 0.76, phase: 4.3, pinch: 0.58 },
      { scaleW: 0.21, scaleH: 0.29, rgb: "255,250,218", a0: 0.66, a1: 0.92, phase: 5.8, pinch: 0.72 },
    ];

    for (let i = 0; i < layers.length; i++) {
      const L = layers[i];
      const lh = h * L.scaleH;
      const lw = w * L.scaleW;
      const alpha = Math.min(1, L.a0 + intensity * (L.a1 - L.a0));
      const localLean = lean * (1 - i * 0.10) + Math.sin(tSec * (2.1 + i * 0.34) + L.phase) * lw * 0.028;
      const grad = ctx.createLinearGradient(cx, baseY + 2, cx + localLean, baseY - lh * 1.03);
      grad.addColorStop(0, "rgba(" + L.rgb + "," + alpha.toFixed(3) + ")");
      grad.addColorStop(0.48, "rgba(" + L.rgb + "," + (alpha * 0.88).toFixed(3) + ")");
      grad.addColorStop(0.82, "rgba(" + L.rgb + "," + (alpha * 0.40).toFixed(3) + ")");
      grad.addColorStop(1, "rgba(" + L.rgb + ",0)");

      ctx.save();
      if (i >= 2) ctx.globalCompositeOperation = "screen";
      ctx.fillStyle = grad;
      flamePath(cx, baseY, lw, lh, tSec, L.phase, localLean, L.pinch);
      ctx.fill();
      ctx.restore();
    }

    // White-hot base lick: tiny, bright and deliberately asymmetric.
    if (intensity > 0.08) {
      ctx.save();
      ctx.globalCompositeOperation = "lighter";
      const coreH = h * (0.17 + intensity * 0.05);
      const coreW = w * 0.12;
      const core = ctx.createLinearGradient(cx, baseY, cx, baseY - coreH);
      core.addColorStop(0, "rgba(255,255,242," + (0.55 + intensity * 0.38).toFixed(3) + ")");
      core.addColorStop(0.58, "rgba(255,245,194," + (0.34 + intensity * 0.28).toFixed(3) + ")");
      core.addColorStop(1, "rgba(255,236,168,0)");
      ctx.fillStyle = core;
      flamePath(cx - w * 0.025, baseY, coreW, coreH, tSec, 7.7, Math.sin(tSec * 3.8) * 1.3, 0.8);
      ctx.fill();
      ctx.restore();
    }

    // Gentle warm haze over the lower half of the stage.
    const haze = ctx.createLinearGradient(0, H * 0.50, 0, H);
    const hazeA = 0.022 + intensity * 0.058;
    haze.addColorStop(0, "rgba(255,140,60,0)");
    haze.addColorStop(0.58, "rgba(255,112,42," + hazeA.toFixed(3) + ")");
    haze.addColorStop(1, "rgba(255,72,22," + (hazeA * 0.38).toFixed(3) + ")");
    ctx.fillStyle = haze;
    ctx.fillRect(0, H * 0.50, W, H * 0.50);
  }

  function drawParticles(intensity, tSec) {
    ctx.globalCompositeOperation = "lighter";
    for (let i = particles.length - 1; i >= 0; i--) {
      const p = particles[i];
      p.life -= p.decay;
      if (p.life <= 0) { particles.splice(i, 1); continue; }
      p.vy *= 0.994;
      p.vx += Math.sin(tSec * 1.7 + p.seed) * 0.003 * intensity;
      p.x += p.vx + Math.sin(tSec * 2.2 + p.seed) * intensity * 1.45;
      p.y += p.vy;
      if (p.y > H + 8) { particles.splice(i, 1); continue; }
      const alpha = Math.max(0, Math.min(1, p.life));
      const size = p.size * (0.5 + 0.5 * p.life);
      ctx.globalAlpha = alpha;
      const stretch = 1.0 + (1 - p.life) * 0.55;
      ctx.drawImage(sprites[p.hueIdx], p.x - size / 2, p.y - (size * stretch) / 2, size, size * stretch);
    }
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = "source-over";
  }

  function drawSparks() {
    if (!sparks.length) return;
    ctx.globalCompositeOperation = "lighter";
    for (let i = sparks.length - 1; i >= 0; i--) {
      const s = sparks[i];
      s.life -= s.decay;
      if (s.life <= 0) { sparks.splice(i, 1); continue; }
      s.x += s.vx;
      s.y += s.vy;
      ctx.strokeStyle = "rgba(255," + (176 + Math.floor(76 * s.life)) + ",82," + (s.life * 0.92).toFixed(3) + ")";
      ctx.lineWidth = 0.55 + 1.25 * s.life;
      ctx.lineCap = "round";
      ctx.beginPath();
      ctx.moveTo(s.x, s.y);
      ctx.lineTo(s.x - s.vx * 1.6, s.y - s.vy * 1.6);
      ctx.stroke();
    }
    ctx.globalCompositeOperation = "source-over";
  }

  let readoutEl = null;

  function updateReadout() {
    if (!readoutEl || !prefs.showReadout) return;
    readoutEl.innerHTML =
      '<span>🔥 <b>' + Math.round(smoothRate) + "</b> tok/s</span>" +
      "<span>总 <b>" + fmt(lastTotal) + "</b></span>";
  }

  function frame(now) {
    requestAnimationFrame(frame);
    if (document.hidden) { lastFrame = now; return; } // freeze off-screen
    const dt = Math.min(0.05, lastFrame ? (now - lastFrame) / 1000 : 0.016);
    lastFrame = now;
    const tSec = now / 1000;

    const target = targetIntensity();
    displayIntensity += (target - displayIntensity) * Math.min(1, dt * 2.4);
    const I = Math.max(0.03, displayIntensity);

    ctx.clearRect(0, 0, W, H);

    // Emission rate scales with intensity; embers keep a trickle alive
    const spawnN = I * dt * 78;
    let n = Math.floor(spawnN);
    if (Math.random() < spawnN - n) n++;
    for (let i = 0; i < n; i++) spawnParticle(I);

    // Sparks: random when roaring + bursts on usage deltas
    if (I > 0.30 && Math.random() < I * 0.065) spawnSpark(I);
    if (burst > 0.02) {
      const k = Math.ceil(burst * 2.5);
      for (let i = 0; i < k; i++) spawnSpark(I);
      burst *= 0.94;
    }

    drawFlame(I, tSec);
    drawParticles(I, tSec);
    drawSparks();
    updateReadout();
  }

  function initFlame(canvasEl, readoutElArg) {
    canvas = canvasEl;
    ctx = canvas.getContext("2d");
    readoutEl = readoutElArg || null;
    buildSprites();
    resize();
    window.addEventListener("resize", resize);
    requestAnimationFrame(function (now) { lastFrame = now; requestAnimationFrame(frame); });
  }

  /* ================================================================
   * Host workbench: floating window
   * ================================================================ */
  let rootEl = null;
  let pollTimer = null;

  function createFloatingWindow() {
    const root = document.createElement("div");
    root.className = "tb-root";
    root.dataset.angelusPlugin = PLUGIN;
    root.innerHTML =
      '<div class="tb-titlebar">' +
      '<span class="tb-title">🔥 Token Burner</span>' +
      '<button type="button" class="tb-popout-btn" title="弹出独立窗口">⤢</button>' +
      '<button type="button" class="tb-close-btn" title="隐藏">✕</button>' +
      "</div>" +
      '<div class="tb-stage">' +
      '<canvas id="tb-canvas"></canvas>' +
      '<div class="tb-readout" id="tb-readout"></div>' +
      "</div>";
    document.body.appendChild(root);

    // Restore last position
    try {
      const pos = JSON.parse(localStorage.getItem("token-burner.pos") || "{}");
      if (typeof pos.x === "number" && typeof pos.y === "number") {
        root.style.left = pos.x + "px";
        root.style.top = pos.y + "px";
      }
    } catch (_) { /* ignore */ }

    // Drag by the title bar
    const bar = root.querySelector(".tb-titlebar");
    bar.addEventListener("pointerdown", function (e) {
      if (e.target.closest("button")) return;
      e.preventDefault();
      const startX = e.clientX;
      const startY = e.clientY;
      const rect = root.getBoundingClientRect();
      const ox = rect.left;
      const oy = rect.top;
      function move(ev) {
        root.style.left = Math.max(0, Math.min(window.innerWidth - 70, ox + ev.clientX - startX)) + "px";
        root.style.top = Math.max(0, Math.min(window.innerHeight - 40, oy + ev.clientY - startY)) + "px";
      }
      function up() {
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", up);
        try {
          localStorage.setItem(
            "token-burner.pos",
            JSON.stringify({
              x: parseFloat(root.style.left) || 0,
              y: parseFloat(root.style.top) || 0,
            })
          );
        } catch (_) { /* ignore */ }
      }
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", up);
    });

    root.querySelector(".tb-close-btn").addEventListener("click", function () {
      toggleWindow(false);
    });
    root.querySelector(".tb-popout-btn").addEventListener("click", function () {
      openPopout();
    });
    return root;
  }

  function ensureWindow() {
    if (!rootEl || !rootEl.isConnected) rootEl = createFloatingWindow();
    return rootEl;
  }

  function toggleWindow(force) {
    const el = ensureWindow();
    const willShow = typeof force === "boolean" ? force : el.classList.contains("tb-hidden");
    el.classList.toggle("tb-hidden", !willShow);
    return willShow;
  }

  function openPopout() {
    const url =
      "/plugins/" + PLUGIN + "/static/window.html?session=" +
      encodeURIComponent(currentSessionId());
    window.open(url, "token-burner-popout", "width=340,height=440,resizable=yes,scrollbars=no");
  }

  function startPolling() {
    if (pollTimer) return;
    pollTimer = setInterval(pollUsage, prefs.pollMs);
    pollUsage().catch(function () { /* first poll may race page load */ });
  }

  /* ================================================================
   * Boot
   * ================================================================ */
  if (isPopout) {
    // Standalone window: fill the page with flame.
    const stage = document.getElementById("tb-popout-stage");
    const popCanvas = document.getElementById("tb-canvas");
    const popReadout = document.getElementById("tb-readout");
    if (stage && popCanvas) initFlame(popCanvas, popReadout);
    startPolling();
    return;
  }

  if (hasBridge) {
    // Register plugin commands (dispatch keys: token-burner:toggle / :popout).
    window.Angelus.registerCommand(PLUGIN, {
      id: "toggle",
      description: "显示 / 隐藏 Token Burner 浮动窗口",
      handler: function () {
        const visible = toggleWindow();
        return { ok: true, visible: visible };
      },
    });
    window.Angelus.registerCommand(PLUGIN, {
      id: "popout",
      description: "弹出独立的 Token Burner 浏览器窗口",
      handler: function () {
        openPopout();
        return { ok: true };
      },
    });

    const win = ensureWindow();
    initFlame(win.querySelector("canvas"), win.querySelector(".tb-readout"));
    startPolling();

    // Tidy up if the plugin is unloaded while the page stays open:
    // the loader removes our <script> tag — observe and release DOM/timers.
    const scriptTag = document.querySelector('script[data-angelus-plugin="' + PLUGIN + '"]');
    if (scriptTag) {
      const observer = new MutationObserver(function () {
        if (scriptTag.isConnected) return;
        observer.disconnect();
        if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
        if (rootEl) { rootEl.remove(); rootEl = null; }
      });
      observer.observe(document.documentElement, { childList: true, subtree: true });
    }
  } else {
    // No bridge (loaded in an unexpected context): still render a window.
    const win = ensureWindow();
    initFlame(win.querySelector("canvas"), win.querySelector(".tb-readout"));
    startPolling();
  }
})();
