/** Capability-gated browser controller for the standalone External Agent Hub. */
const state = { providers: [], selectedProvider: null, sessions: [], activeLink: null, lease: null };
const clientInstanceId = crypto.randomUUID?.() || `hub-${Date.now()}-${Math.random()}`;
let leaseTimer = null;
const $ = (id) => document.getElementById(id);

/** Request JSON from a Hub endpoint and return its safe error detail on failure. */
async function request(path, options = {}) {
  const response = await fetch(path, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || `${response.status} ${response.statusText}`);
  return payload;
}
/** Update the live feedback region without inserting Provider-controlled HTML. */
function feedback(message = "", kind = "") { const node = $("hub-feedback"); node.textContent = message; node.dataset.kind = kind; }
/** Build a text-only button bound to one fixed local action. */
function button(label, handler, disabled = false) { const node = document.createElement("button"); node.type = "button"; node.textContent = label; node.disabled = disabled; node.addEventListener("click", handler); return node; }
/** Render Provider cards while preserving the current selection. */
function renderProviders() {
  const root = $("provider-list"); root.replaceChildren();
  for (const provider of state.providers) {
    const card = document.createElement("button"); card.type = "button"; card.className = "external-provider-card"; card.classList.toggle("selected", state.selectedProvider?.id === provider.id);
    const title = document.createElement("strong"); title.textContent = provider.label;
    const status = document.createElement("small"); status.textContent = `${provider.runtime_available ? "运行时可用" : "运行时不可用"} · ${provider.configured ? "已配置" : "未配置"}`;
    const caps = document.createElement("span"); caps.textContent = (provider.capabilities || []).join(" · ") || "预留接口";
    card.append(title, status, caps); card.addEventListener("click", () => selectProvider(provider.id)); root.append(card);
  }
  if (!state.providers.length) root.textContent = "未发现 Provider。";
}
/** Load public Provider metadata without starting a vendor runtime. */
async function loadProviders() { state.providers = (await request("/api/external-agents/providers")).providers || []; renderProviders(); }
/** Show one Provider configuration form and its capability-specific safety guidance. */
function selectProvider(providerId) {
  state.selectedProvider = state.providers.find((item) => item.id === providerId) || null; renderProviders(); const provider = state.selectedProvider; $("provider-detail").hidden = !provider; if (!provider) return;
  $("provider-label").value = provider.label; $("provider-endpoint-row").hidden = provider.id !== "opencode"; $("provider-endpoint").value = provider.endpoint || ""; $("provider-runtime-state").textContent = provider.runtime_available ? "运行时可用" : "运行时不可用";
  $("provider-help").textContent = provider.id === "claude-code" ? "已发现的 Claude transcript 仅可读取；只有 Angelus 启动的 Claude 会话可控制。" : provider.id === "opencode" ? "仅接受 loopback URL；远程服务及凭据不通过此页面配置。" : "Codex 使用本机 App Server；不会从浏览器接收命令或凭据。";
  state.sessions = []; $("session-count").textContent = ""; $("external-session-list").textContent = "点击“发现会话”读取该 Provider。";
}
/** Persist non-secret local settings for the selected Provider. */
async function saveProvider(event) {
  event.preventDefault(); const provider = state.selectedProvider; if (!provider) return;
  await request(`/api/external-agents/providers/${encodeURIComponent(provider.id)}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ configured: true, endpoint: $("provider-endpoint").value.trim() }) });
  await loadProviders(); selectProvider(provider.id); feedback("Provider 设置已保存。", "success");
}
/** Probe installed runtime state without opening a vendor session. */
async function probeProvider() { const provider = state.selectedProvider; if (!provider) return; const result = await request(`/api/external-agents/providers/${encodeURIComponent(provider.id)}/probe`, { method: "POST" }); feedback(result.available ? "运行时可用。" : "运行时不可用；请检查本机 CLI、SDK 或 OpenCode 服务。", result.available ? "success" : "warning"); await loadProviders(); }
/** Discover read-only session descriptors through the selected Provider adapter. */
async function discoverSessions() { const provider = state.selectedProvider; if (!provider) return; feedback("正在发现外部会话…"); state.sessions = (await request(`/api/external-agents/providers/${encodeURIComponent(provider.id)}/sessions`)).sessions || []; renderSessions(); feedback(`发现 ${state.sessions.length} 个会话。`, "success"); }
/** Render safely text-projected external sessions with explicit Angelus-link actions. */
function renderSessions() {
  const root = $("external-session-list"); root.replaceChildren(); $("session-count").textContent = `${state.sessions.length} 个`;
  for (const session of state.sessions) { const row = document.createElement("article"); row.className = "external-session-row"; const copy = document.createElement("div"); const title = document.createElement("strong"); title.textContent = session.title || session.id; const details = document.createElement("small"); details.textContent = `${session.status || "unknown"} · ${session.project_path || "未公开项目路径"}`; copy.append(title, details); row.append(copy, button("连接", () => linkSession(session))); root.append(row); }
  if (!state.sessions.length) root.textContent = "没有可读取的会话。";
}
/** Create a safe Angelus link and request its non-preemptive control lease. */
async function linkSession(session) { const link = await request("/api/external-agents/links", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ provider: session.provider, session_id: session.id, project_path: session.project_path || "" }) }); await activateLink(link); feedback("已连接外部会话。", "success"); }
/** Acquire or renew this tab's exclusive control lease. */
async function renewLease() { if (!state.activeLink) return; state.lease = await request(`/api/external-agents/links/${encodeURIComponent(state.activeLink.id)}/lease`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ client_instance_id: clientInstanceId, lease_token: state.lease?.lease_token }) }); renderLink(); }
/** Start 20-second lease heartbeats after selecting a link. */
async function activateLink(link) { state.activeLink = link; state.lease = null; clearInterval(leaseTimer); await renewLease(); leaseTimer = setInterval(() => renewLease().catch((error) => feedback(`控制 lease 续期失败：${error.message}`, "warning")), 20_000); }
/** Render only operations advertised by the Provider and granted by the lease. */
function renderLink() {
  const link = state.activeLink; $("link-detail").hidden = !link; if (!link) return; const provider = state.providers.find((item) => item.id === link.provider); const caps = provider?.capabilities || []; const controls = state.lease?.mode === "control";
  $("link-title").textContent = provider?.label || link.provider; $("link-subtitle").textContent = link.external_session_id; $("lease-state").textContent = controls ? "控制 lease 已取得" : "只读观察";
  const capRoot = $("link-capabilities"); capRoot.replaceChildren(...caps.map((capability) => Object.assign(document.createElement("span"), { textContent: capability })));
  const actions = $("link-actions"); actions.replaceChildren(); const labels = { send: "发送", steer: "Steer", interrupt: "中断", fork: "Fork", resume: "恢复", diff: "查看 Diff" }; for (const action of ["send", "steer", "resume", "fork", "interrupt", "diff"]) if (caps.includes(action)) actions.append(button(labels[action], () => runAction(action), !controls));
}
/** Submit one idempotent fixed action; arbitrary vendor payloads are never exposed. */
async function runAction(action) { const link = state.activeLink; if (!link || state.lease?.mode !== "control") return; const result = await request(`/api/external-agents/links/${encodeURIComponent(link.id)}/actions`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action, lease_token: state.lease.lease_token, idempotency_key: crypto.randomUUID?.() || `${Date.now()}-${Math.random()}`, message: $("link-message").value }) }); const output = $("link-result"); output.hidden = false; output.textContent = JSON.stringify(result, null, 2); feedback(`${action} 已提交。`, "success"); }
/** Drop this page's local lease state without interrupting the vendor session. */
function releaseLink() { clearInterval(leaseTimer); state.lease = null; state.activeLink = null; $("link-detail").hidden = true; feedback("已断开本页控制。", "success"); }
$("refresh-providers").addEventListener("click", () => loadProviders().catch((error) => feedback(error.message, "error")));
$("provider-form").addEventListener("submit", (event) => saveProvider(event).catch((error) => feedback(error.message, "error")));
$("probe-provider").addEventListener("click", () => probeProvider().catch((error) => feedback(error.message, "error")));
$("discover-sessions").addEventListener("click", () => discoverSessions().catch((error) => feedback(error.message, "error")));
$("release-link").addEventListener("click", releaseLink); window.addEventListener("pagehide", () => clearInterval(leaseTimer)); loadProviders().catch((error) => feedback(`无法读取 Provider：${error.message}`, "error"));
