/** Read-only external-history importer for independent Angelus workspaces. */
const state = { providers: [], selectedProvider: null, sessions: [], candidate: null };
const $ = (id) => document.getElementById(id);

/** Request JSON and expose only the server's browser-safe error detail. */
async function request(path, options = {}) { const response = await fetch(path, options); const payload = await response.json().catch(() => ({})); if (!response.ok) throw new Error(payload.detail || `${response.status} ${response.statusText}`); return payload; }
/** Update the live status without interpreting external source material as HTML. */
function feedback(message = "", kind = "") { const node = $("hub-feedback"); node.textContent = message; node.dataset.kind = kind; }
/** Make a text-only button with one fixed local action. */
function button(label, handler, disabled = false) { const node = document.createElement("button"); node.type = "button"; node.textContent = label; node.disabled = disabled; node.addEventListener("click", handler); return node; }
/** Render source cards according to their actual direct-import capability. */
function renderProviders() {
  const root = $("provider-list"); root.replaceChildren();
  for (const provider of state.providers) {
    const card = document.createElement("button"); card.type = "button"; card.className = "external-provider-card"; card.classList.toggle("selected", provider.id === state.selectedProvider?.id);
    const direct = (provider.capabilities || []).includes("import_history");
    card.append(Object.assign(document.createElement("strong"), { textContent: provider.label }), Object.assign(document.createElement("small"), { textContent: provider.runtime_available ? "本机可读取" : "运行时不可用" }), Object.assign(document.createElement("span"), { textContent: direct ? "可直接导入历史" : "可通过 transcript 文件导入" }));
    card.addEventListener("click", () => selectProvider(provider.id)); root.append(card);
  }
  if (!state.providers.length) root.textContent = "未发现可用来源。";
}
/** Load metadata only; discovery and transcript reading remain explicit actions. */
async function loadProviders() { state.providers = (await request("/api/external-agents/providers")).providers || []; renderProviders(); }
/** Probe local providers and focus the first usable source. */
async function autoDetectProviders() { const result = await request("/api/external-agents/providers/auto-detect", { method: "POST" }); await loadProviders(); const found = (result.providers || []).find((item) => item.available); if (found) selectProvider(found.id); feedback(found ? "已检测到本机来源。选择一个会话开始导入。" : "未检测到可直接读取的来源；仍可导入 transcript 文件。", found ? "success" : "warning"); }
/** Select one provider and reset any old discovery result. */
function selectProvider(providerId) {
  state.selectedProvider = state.providers.find((item) => item.id === providerId) || null; state.sessions = []; renderProviders(); const provider = state.selectedProvider; $("source-detail").hidden = !provider; if (!provider) return;
  const direct = (provider.capabilities || []).includes("import_history"); $("source-title").textContent = `${provider.label} 会话`; $("source-help").textContent = direct ? "读取的是只读历史。导入后会创建新的 Angelus 工作空间，不会接管或修改原会话。" : "该来源暂不支持安全的直接历史读取；请使用下方 transcript 文件导入。"; $("discover-sessions").disabled = !direct; $("external-session-list").textContent = direct ? "点击“读取会话”查看可导入工作。" : "直接导入尚不可用。";
}
/** Discover only sessions exposed by the provider's read-only interface. */
async function discoverSessions() { const provider = state.selectedProvider; if (!provider) return; state.sessions = (await request(`/api/external-agents/providers/${encodeURIComponent(provider.id)}/sessions`)).sessions || []; renderSessions(); feedback(`找到 ${state.sessions.length} 个可读取会话。`, "success"); }
/** Offer one explicit import action per source session—no control lease UI. */
function renderSessions() { const root = $("external-session-list"); root.replaceChildren(); for (const session of state.sessions) { const row = document.createElement("article"); row.className = "external-session-row"; const copy = document.createElement("div"); copy.append(Object.assign(document.createElement("strong"), { textContent: session.title || session.id }), Object.assign(document.createElement("small"), { textContent: `${session.status || "unknown"} · ${session.project_path || "需要选择项目目录"}` })); row.append(copy, button("导入到 Angelus", () => reviewDiscoveredSession(session))); root.append(row); } if (!state.sessions.length) root.textContent = "没有可导入的会话。"; }
/** Prepare a direct session import; the source is converted server-side at commit. */
function reviewDiscoveredSession(session) { state.candidate = { kind: "discovered", provider: state.selectedProvider.id, session }; $("review-summary").textContent = `将从 ${state.selectedProvider.label} 只读导入“${session.title || session.id}”。`; $("import-name").value = `${session.title || state.selectedProvider.label} · import`; $("import-project-path").value = session.project_path || ""; renderReport({ preserved: ["对话历史", "来源标记"], degraded: ["工具调用不会重放"] }); $("import-review").hidden = false; $("import-review").scrollIntoView({ behavior: "smooth", block: "start" }); }
/** Read a JSON array/object or JSONL transcript without uploading it before preview. */
async function readTranscriptFile() { const file = $("transcript-file").files?.[0]; if (!file) throw new Error("请选择 transcript 文件"); const text = await file.text(); try { return JSON.parse(text); } catch (_) { return { events: text.split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line)) }; } }
/** Preview canonicalization before a file import can create any persistent workspace. */
async function previewFileImport() { const provider = state.selectedProvider; if (!provider) throw new Error("请先选择来源类型"); const transcript = await readTranscriptFile(); const preview = await request("/api/external-agents/import/preview", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ provider: provider.id, transcript }) }); state.candidate = { kind: "file", provider: provider.id, transcript }; $("review-summary").textContent = `已解析 ${preview.event_count || 0} 条记录；请确认要绑定的项目目录。`; $("import-name").value = `${provider.label} transcript · import`; $("import-project-path").value = ""; renderReport(preview.conversion_report || {}); $("import-review").hidden = false; }
/** Render only generated conversion metadata as text. */
function renderReport(report) { const root = $("conversion-report"); root.replaceChildren(); for (const [label, values] of [["将保留", report.preserved], ["可能降级", report.degraded], ["省略", report.omitted]]) { if (Array.isArray(values) && values.length) { const item = document.createElement("p"); item.textContent = `${label}：${values.join("、")}`; root.append(item); } } }
/** Commit an import and ask the parent workbench to open the new session. */
async function commitImport() { const candidate = state.candidate; if (!candidate) throw new Error("请先选择一个会话或 transcript 文件"); const name = $("import-name").value.trim(); const project_path = $("import-project-path").value.trim(); if (!project_path) throw new Error("请输入要绑定的项目目录"); const options = { method: "POST", headers: { "Content-Type": "application/json" } }; let imported; if (candidate.kind === "discovered") { options.body = JSON.stringify({ name, project_path }); imported = await request(`/api/external-agents/providers/${encodeURIComponent(candidate.provider)}/sessions/${encodeURIComponent(candidate.session.id)}/import`, options); } else { options.body = JSON.stringify({ provider: candidate.provider, transcript: candidate.transcript, name, project_path }); imported = await request("/api/external-agents/import", options); } feedback("工作空间已创建。正在打开，可继续给 Angelus 下达下一步任务。", "success"); window.parent.postMessage({ type: "angelus:imported-session", sessionId: imported.id }, window.location.origin); }
/** Open the host directory picker and keep the chosen project in the import review. */
async function chooseImportDirectory() { const control = $("choose-import-directory"); control.disabled = true; feedback("正在打开目录选择器…"); try { const result = await request("/api/workspace-directory/pick", { method: "POST" }); const path = result.cancelled ? "" : String(result.path || ""); if (path) { $("import-project-path").value = path; feedback("已选择项目目录。", "success"); } } finally { control.disabled = false; } }
$("refresh-providers").addEventListener("click", () => loadProviders().catch((error) => feedback(error.message, "error")));
$("auto-detect-providers").addEventListener("click", () => autoDetectProviders().catch((error) => feedback(error.message, "error")));
$("discover-sessions").addEventListener("click", () => discoverSessions().catch((error) => feedback(error.message, "error")));
$("preview-file-import").addEventListener("click", () => previewFileImport().catch((error) => feedback(error.message, "error")));
$("choose-import-directory").addEventListener("click", () => chooseImportDirectory().catch((error) => feedback(`无法选择目录：${error.message}`, "error")));
$("commit-import").addEventListener("click", () => commitImport().catch((error) => feedback(error.message, "error")));
$("cancel-import").addEventListener("click", () => { state.candidate = null; $("import-review").hidden = true; });
loadProviders().catch((error) => feedback(`无法读取来源：${error.message}`, "error"));
