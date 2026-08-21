/** Workbench composition root: coordinates feature state, REST calls, and views. */
import { $, escapeHtml } from "./components/dom.js";
import { createChatView } from "./components/chat-view.js?v=tool-payload-2";
import { createTraceView } from "./components/trace-view.js";
import { renderTaskPlanItem } from "./components/task-plan-view.js";
import { initPlugins, loadPlugins, unloadPlugin } from "./plugins.js?v=plugin-controls-1";

/* ================================================================
 *  Theme (light / dark) — wired to the ☾ sidebar-footer button.
 *  Persisted in localStorage["llmfetcherTheme"]; the inline <head>
 *  script applies the saved theme before first paint.
 * ================================================================ */
const THEME_KEY = "llmfetcherTheme";
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const btn = $("theme-toggle");
  if (btn) {
    btn.textContent = theme === "light" ? "☀" : "☾";
    btn.title = theme === "light" ? "切换到深色主题" : "切换到浅色主题";
  }
  try { localStorage.setItem(THEME_KEY, theme); } catch (e) { /* private mode etc. */ }
}
function initTheme() {
  let theme = "dark";
  try { theme = localStorage.getItem(THEME_KEY) || "dark"; } catch (e) {}
  applyTheme(theme);
  const btn = $("theme-toggle");
  if (btn) btn.addEventListener("click", () =>
    applyTheme(document.documentElement.dataset.theme === "light" ? "dark" : "light"));
}
initTheme();

let sessionId = localStorage.llmfetcherSession || localStorage.llmfetcherWorkspace || "default";
let workspaceId = sessionId;
let connectorId = localStorage.llmfetcherConnector || "";
let source = null;
let sourceWorkspaceId = "";
let selectedAgent = "all";
let activeInspectorPanel = localStorage.llmfetcherInspectorPanel || "inspector-plan";
let traceBefore = null;
let traceEvents = [];
let durableEventCount = 0;
let renderedSteerEvents = new Set();
let renderedRoundEvents = new Set();
let currentAgents = [];
let currentGraph = {nodes:[],edges:[],assignments:{},task_states:{},node_states:{}};
let selectedPlanAgent = localStorage.llmfetcherPlanAgent || "coordinator";
let availableSessions = [];
let runActive = false;
let pendingRoundTools = new Map();
let pluginStatuses = [];
let selectedPluginKey = "";
let contextDialogAgent = "";

const KIMI_CODE_PROVIDER = "kimi-code";
const KIMI_CODE_BASE_URL = "https://api.kimi.com/coding/v1";
const KIMI_CODE_DEFAULT_MODEL = "kimi-for-coding";
const KIMI_CODE_TEMPERATURE = 1;

const value = (id) => $(id).value.trim();
function mcpServers() { const raw=$("mcp-servers").value.trim(); if(!raw)return []; let servers; try { servers=JSON.parse(raw); } catch { throw new Error("MCP 服务器配置必须是合法 JSON"); } if(!Array.isArray(servers))throw new Error("MCP 服务器配置必须是 JSON 数组"); return servers; }
const config = () => ({
  provider: value("provider"), model: value("model"), api_key: $("api-key").value, connector_id: connectorId,
  api_url: value("api-url"), system_prompt: $("system-prompt").value,
  temperature: Number($("temperature").value), max_tokens: Number($("max-tokens").value),
  max_rounds: Number($("max-rounds").value), max_retries: Number($("max-retries").value), max_context_threshold: Number($("max-context-threshold").value),
  enable_shell: $("enable-shell").checked, enable_mcp: $("enable-mcp").checked,
  mcp_servers: $("enable-mcp").checked ? mcpServers() : [], enable_swarm: $("enable-swarm").checked,
  max_swarm_agents: Number($("max-swarm-agents").value),
  session_memory_search_sessions: selectedMemorySessions(), session_memory_read_sessions: selectedMemorySessions(),
  session_artifact_search_sessions: selectedMemorySessions(), session_artifact_open_sessions: selectedMemorySessions(),
});
const agentSettingsIds = ["system-prompt", "temperature", "max-tokens", "max-rounds", "max-retries", "max-context-threshold", "max-swarm-agents", "session-memory-sessions", "mcp-servers"];
const connectionDraftIds = ["provider", "model", "api-url"];
function settingsKey(id=workspaceId) { return `llmfetcherAgentSettings:${id}`; }
function connectionDraftKey(id=workspaceId) { return `llmfetcherConnectionDraft:${id}`; }
function persistedFields(ids) { return Object.fromEntries(ids.map(id=>[id.replaceAll("-","_"), $(id).value])); }
function persistSettings() { if(!workspaceId) return; localStorage.setItem(settingsKey(), JSON.stringify({...persistedFields(agentSettingsIds), enable_shell:$("enable-shell").checked, enable_mcp:$("enable-mcp").checked, enable_swarm:$("enable-swarm").checked})); if(!connectorId) localStorage.setItem(connectionDraftKey(), JSON.stringify(persistedFields(connectionDraftIds))); }
function restoreSettings() { try { let settings=JSON.parse(localStorage.getItem(settingsKey()) || "null"); let draft=JSON.parse(localStorage.getItem(connectionDraftKey()) || "null"); const legacy=JSON.parse(localStorage.getItem(`llmfetcherSettings:${workspaceId}`) || "null"); if(legacy) { settings ??={}; agentSettingsIds.forEach(id=>{const key=id.replaceAll("-","_"); if(legacy[key] !== undefined) settings[key]=legacy[key];}); settings.enable_shell ??=legacy.enable_shell; settings.enable_mcp ??=legacy.enable_mcp; settings.enable_swarm ??=legacy.enable_swarm; if(!connectorId) { draft ??={}; connectionDraftIds.forEach(id=>{const key=id.replaceAll("-","_"); if(legacy[key] !== undefined) draft[key]=legacy[key];}); } localStorage.setItem(settingsKey(),JSON.stringify(settings)); if(draft) localStorage.setItem(connectionDraftKey(),JSON.stringify(draft)); localStorage.removeItem(`llmfetcherSettings:${workspaceId}`); } if(settings) { agentSettingsIds.forEach(id=>{const key=id.replaceAll("-","_"); if(settings[key] !== undefined) $(id).value=settings[key];}); $("enable-shell").checked=Boolean(settings.enable_shell); $("enable-mcp").checked=Boolean(settings.enable_mcp); $("enable-swarm").checked=Boolean(settings.enable_swarm); } if(!connectorId && draft) connectionDraftIds.forEach(id=>{const key=id.replaceAll("-","_"); if(draft[key] !== undefined) $(id).value=draft[key];}); } catch { /* Ignore malformed browser-local settings. */ } renderMemorySessionPicker(); }
function bindSettingsPersistence() { [...agentSettingsIds,...connectionDraftIds,"enable-shell","enable-mcp","enable-swarm"].forEach(id=>["input","change"].forEach(event=>$(id).addEventListener(event,persistSettings))); }
function setStatus(text, state="idle") { const el=$("status"); el.textContent=text; el.className=`status ${state}`; }
function providerLabel(provider) { return provider===KIMI_CODE_PROVIDER ? "Kimi Code" : provider; }
function updateProviderHint() { const hint=$("provider-hint"); const isKimi=$("provider").value===KIMI_CODE_PROVIDER; hint.hidden=!isKimi; hint.textContent=isKimi ? "已使用 Kimi Code 的 OpenAI 兼容接口。请填写 Kimi Code Console 创建的 API Key；它不能与 Kimi 开放平台 Key 混用。该模型只接受温度 1，已自动锁定。" : ""; }
function applyProviderPreset() { const temperature=$("temperature"), isKimi=$("provider").value===KIMI_CODE_PROVIDER; temperature.disabled=isKimi; if(!isKimi) { updateProviderHint(); return; } const apiUrl=$("api-url"), model=$("model"); if(!apiUrl.value.trim() || apiUrl.value.trim()==="https://api.openai.com/v1") apiUrl.value=KIMI_CODE_BASE_URL; if(!model.value.trim() || model.value.trim()==="gpt-4.1-mini") model.value=KIMI_CODE_DEFAULT_MODEL; temperature.value=KIMI_CODE_TEMPERATURE; updateProviderHint(); }
function updateModelSummary() { $("model-label").textContent=$("model").value.trim() || "模型配置"; $("provider-label").textContent=$("provider").options[$("provider").selectedIndex]?.text || "OpenAI compatible"; updateProviderHint(); }
/** Return explicitly selected, non-current session IDs for run-scoped memory grants. */
function selectedMemorySessions() { return [...new Set($("session-memory-sessions").value.split(",").map(value=>value.trim()).filter(value=>value && value !== sessionId))]; }
/** Render searchable session choices and removable selections without exposing session content. */
function renderMemorySessionPicker() { const options=$("session-memory-options"), selected=$("session-memory-selected"), search=$("session-memory-search"); if(!options || !selected || !search) return; const chosen=selectedMemorySessions(), query=search.value.trim().toLowerCase(); const candidates=availableSessions.filter(item=>item.id !== sessionId && (`${item.name} ${item.id}`).toLowerCase().includes(query)); selected.innerHTML=chosen.length ? chosen.map(id=>{const item=availableSessions.find(candidate=>candidate.id===id); return `<button type="button" class="memory-session-chip" data-memory-session="${escapeHtml(id)}">${escapeHtml(item?.name || id)} ×</button>`;}).join("") : '<span class="memory-session-empty">未授权其他会话</span>'; options.innerHTML=candidates.length ? candidates.map(item=>`<button type="button" class="memory-session-option ${chosen.includes(item.id)?"selected":""}" data-memory-session="${escapeHtml(item.id)}"><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.id)}</small></button>`).join("") : '<p class="memory-session-empty">没有匹配的会话</p>'; document.querySelectorAll("[data-memory-session]").forEach(button=>button.addEventListener("click",()=>{const id=button.dataset.memorySession; const next=chosen.includes(id) ? chosen.filter(value=>value!==id) : [...chosen,id]; $("session-memory-sessions").value=next.join(","); persistSettings(); renderMemorySessionPicker();})); }
const chatView = createChatView({ getAgentLabel: () => selectedAgent });
const traceView = createTraceView();
/** Normalize live tool lifecycle data while preserving structured results for chat rendering. */
function liveTools(data) { const calls=data?.tool_calls||[]; if(!Array.isArray(calls)) return []; return calls.filter(item=>item && typeof item==="object").map(item=>({name:String(item.name||"unknown"), arguments:item.args??item.arguments??{}, result:item.result??item.output??""})); }
/** Append a single transcript turn live (real-time path). */
function appendMessage(role, content, reasoning="", contentHtml="", reasoningHtml="", tools=[], agentName="") { if(role === "steer") return appendSteerMessage(content); chatView.append({role,content,reasoning,content_html:contentHtml,reasoning_html:reasoningHtml,tools},agentName); }
/** Display a durable run failure in the chat pane without hiding prior work. */
function appendRunErrorBlock(title, message, rawContent="") { chatView.appendError(title, message, rawContent); }
/** Render one durably applied steering message beside the original user input. */
function appendSteerMessage(text, eventKey="") { if(eventKey && renderedSteerEvents.has(eventKey)) return; if(eventKey) renderedSteerEvents.add(eventKey); chatView.append({role:"steer",content:text}); }
/** Load the canonical session transcript using the same detailed message UI. */
/** Bulk-render a transcript into #chat in a single layout pass. */
function renderMessagesInto(messages, assistantLabel="coordinator") { chatView.render(messages, assistantLabel); }
async function loadAllAgentBehavior() { const [{total=0},{messages=[]}]=await Promise.all([apiJson(`/api/sessions/${sessionId}/events?limit=1`),apiJson(`/api/sessions/${sessionId}/messages`)]); durableEventCount=total; renderedSteerEvents.clear(); renderedRoundEvents.clear(); pendingRoundTools.clear(); renderMessagesInto(messages, "coordinator"); }
function trace(title, message="", data=null, kind="") { traceView.append(title, message, data, kind); }
function tracePayload(event, position="prepend") { traceView.appendEvent(event, position); }
function updateHeaderMetrics(data) { if (!data) return; $("header-tokens").textContent=data.usage?.total ?? data.total ?? "—"; if(data.duration_ms) $("header-duration").textContent=`${(data.duration_ms/1000).toFixed(1)}s`; }
function setRunning(running) { runActive=running; $("stop").disabled=!running; $("force-stop").disabled=!running; const composer=$("composer"), input=$("message"), hint=$("steer-hint"); composer.classList.toggle("steer-mode", running); if(hint) hint.hidden=!running; input.placeholder=running ? "调整正在执行的 Agent…" : "给 Agent 一个任务… （/ 开头为指令，/help 查看）"; if(running){ resizeComposer(); setSteerStatus("运行中 — 指令会在安全的轮次边界生效"); input.focus(); } const guidance=$("run-guidance"); if(running && !guidance){const panel=document.createElement("aside");panel.id="run-guidance";panel.className="run-guidance";panel.innerHTML="<strong>Agent 正在执行</strong><span>可在右侧查看工具调用与用量。</span><span>停止会在当前模型与工具步骤完成后生效。</span><span>强行停止会中断当前模型请求，并立即终止已注册的 Shell 工具进程。</span><span>切换工作空间不会中断后台任务，结果会保存在原会话。</span><span>运行中可直接在输入框发送调整指令，Agent 会在安全的轮次边界应用。</span>"; $("chat").append(panel);} if(!running) guidance?.remove(); }
let steerStatusTimer = null;
const steerHintText = "运行中 — 指令会在安全的轮次边界生效";
function setSteerStatus(text, state="") { const el=$("steer-status"); if(!el) return; const hint=el.closest(".steer-hint"); el.textContent=text; el.className=state ? `steer-status ${state}` : "steer-status"; if(hint) hint.className=`steer-hint ${state || ""}`.trim(); clearTimeout(steerStatusTimer); if(state) steerStatusTimer=setTimeout(()=>{ el.textContent=steerHintText; el.className="steer-status"; if(hint) hint.className="steer-hint"; }, 6000); }
async function sendSteer(message) { const send=$("send"), input=$("message"); send.disabled=true; setSteerStatus("正在加入队列…","sending"); try { const response=await fetch(`/api/workspaces/${workspaceId}/runs/${sessionId}/steer`, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({message})}); const payload=await response.json().catch(()=>({})); if(!response.ok) throw new Error(payload.detail || `${response.status} ${response.statusText}`); input.value=""; resizeComposer(); setSteerStatus("指令已加入队列，将在安全的轮次边界应用 ✓","queued"); } catch(error) { setSteerStatus(`发送失败：${error.message}`,"error"); trace("调整指令发送失败", error.message); } finally { send.disabled=false; input.focus(); } }
async function apiJson(path) { const response=await fetch(path); if(!response.ok) throw new Error(`${response.status} ${response.statusText} (${path})`); return response.json(); }
/** Load every session into the select and independently scrollable quick list. */
function setWorkspaceIndicator(id,status) { const item=document.querySelector(`[data-workspace-id="${CSS.escape(id)}"]`); if(!item)return; item.dataset.status=status; item.title=`会话状态：${({idle:"待机",running:"运行中",error:"错误",done:"已完成"})[status]||"待机"}`; }
async function loadWorkspaces(selected=sessionId) { const {sessions}=await apiJson("/api/sessions"); if(!sessions.length) throw new Error("会话列表为空"); availableSessions=sessions; const select=$("workspace"); select.innerHTML=sessions.map(item=>`<option value="${escapeHtml(item.id)}">${escapeHtml(item.name)}</option>`).join(""); workspaceId=sessions.some(item=>item.id===selected)?selected:sessions[0].id; sessionId=workspaceId; select.value=workspaceId; localStorage.llmfetcherWorkspace=workspaceId; localStorage.llmfetcherSession=sessionId; const opened=sessions.find(item=>item.id===workspaceId); $("workspace-open-hint").textContent=opened?`当前工作空间：${opened.name}`:""; const recent=$("recent-sessions"); recent.innerHTML=sessions.map(item=>`<button class="recent-session ${item.id===workspaceId?"active":""}" type="button" data-workspace-id="${escapeHtml(item.id)}" data-status="${escapeHtml(item.status||"idle")}" title="会话状态：${escapeHtml(({idle:"待机",running:"运行中",error:"错误",done:"已完成"})[item.status]||"待机")}">${escapeHtml(item.name)}</button>`).join(""); recent.querySelectorAll("[data-workspace-id]").forEach(button=>button.addEventListener("click",()=>switchSession(button.dataset.workspaceId).catch(error=>trace("会话切换失败",error.message)))); recent.querySelector(".active")?.scrollIntoView({block:"nearest"}); renderMemorySessionPicker(); }
function applyConnector(connector) { ["provider","model","api-url"].forEach(id=>{const key=id.replaceAll("-","_"); if(connector[key] !== undefined) $(id).value=connector[key];}); applyProviderPreset(); $("api-key").value=""; $("api-key").placeholder=connector.has_api_key ? "已安全保存；留空以继续使用" : "仅保留在当前浏览器"; }
async function loadConnectors(selected=connectorId) { const {connectors}=await apiJson("/api/connectors"); const select=$("connector"); select.innerHTML=`<option value="">未保存的临时连接</option>${connectors.map(item=>`<option value="${escapeHtml(item.id)}">${escapeHtml(item.name)}</option>`).join("")}`; connectorId=connectors.some(item=>item.id===selected)?selected:""; select.value=connectorId; localStorage.llmfetcherConnector=connectorId; const connector=connectors.find(item=>item.id===connectorId); if(connector) applyConnector(connector); }
function connectorPayload(name) { return {name, provider:value("provider"), model:value("model"), api_url:value("api-url"), api_key:$("api-key").value}; }
/** Give connector saves a visible local result instead of relying on hidden Trace. */
function connectorFeedback(text, state="") { const button=$("save-connector"); button.textContent=text; button.dataset.state=state; clearTimeout(connectorFeedback.timer); connectorFeedback.timer=setTimeout(()=>{button.textContent="保存";button.dataset.state="";},1800); }
/** Persist the current fields as a new globally available connector. */
async function createConnector(name) { const response=await fetch("/api/connectors",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(connectorPayload(name))}); const connector=await response.json(); if(!response.ok) throw new Error(connector.detail||"无法保存连接"); await loadConnectors(connector.id); trace("已保存连接",connector.name); connectorFeedback("已保存","success"); }
/** Replace the selected connector while keeping its global identity. */
async function saveSelectedConnector() { if(!connectorId){openConnectorDialog();return;} const name=$("connector").selectedOptions[0]?.text||"当前连接"; const response=await fetch(`/api/connectors/${connectorId}`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(connectorPayload(name))}); if(!response.ok){const payload=await response.json().catch(()=>({}));throw new Error(payload.detail||"无法更新连接");} trace("已更新连接",name); connectorFeedback("已保存","success"); }
/** Open the document-native name dialog used by both new and unsaved connectors. */
function openConnectorDialog() { const dialog=$("new-connector-dialog"); const input=$("new-connector-name"); input.value=""; dialog.showModal(); input.focus(); }
function openSettings(section="connection") { const dialog=$("settings-dialog"); showSettingsSection(section); if(!dialog.open) dialog.showModal(); }
function showSettingsSection(section) { document.querySelectorAll("[data-settings-panel]").forEach(panel=>panel.classList.toggle("active",panel.dataset.settingsPanel===section)); document.querySelectorAll("[data-settings-section]").forEach(button=>{const active=button.dataset.settingsSection===section; button.classList.toggle("active",active); button.setAttribute("aria-selected",String(active));}); if(section==="plugins") loadPluginStatuses().catch(error=>setPluginFeedback(`加载插件状态失败：${error.message}`,"error")); }
function setPluginFeedback(text="", state="") { const el=$("plugin-settings-feedback"); if(!el)return; el.textContent=text; el.className=state ? `plugin-settings-feedback ${state}` : "plugin-settings-feedback"; }
function pluginStateLabel(state) { return ({active:"已加载", discovered:"已发现", blocked:"已阻塞", error:"错误", inactive:"未加载"})[state] || state || "未知"; }
function pluginSettingsRegistration(name) { return window.Angelus?.getRegisteredSettings?.().find(item=>item?.plugin===name) || null; }
function pluginKey(plugin) { return plugin.id || plugin.name || ""; }
function renderPluginStatusList() { const list=$("plugin-status-list"); if(!list)return; if(!pluginStatuses.length) { list.innerHTML='<p class="empty">未发现插件。</p>'; $("plugin-settings-detail").innerHTML='<p class="empty">将插件放入受控目录后会在这里显示状态与可用操作。</p>'; return; } if(!pluginStatuses.some(item=>pluginKey(item)===selectedPluginKey)) selectedPluginKey=pluginKey(pluginStatuses[0]); list.innerHTML=pluginStatuses.map(plugin=>{ const key=pluginKey(plugin); const selected=key===selectedPluginKey; const detail=[pluginStateLabel(plugin.state), plugin.registered ? (plugin.enabled ? "已启用" : "未启用") : "未加入工作台"].join(" · "); return `<button type="button" class="plugin-status-card ${selected?"selected":""}" data-plugin-key="${escapeHtml(key)}"><i class="plugin-status-dot ${escapeHtml(plugin.state||"")}"></i><span><strong>${escapeHtml(plugin.name||"未命名插件")}</strong><small>${escapeHtml(detail)} · v${escapeHtml(plugin.version||"—")}</small></span></button>`; }).join(""); list.querySelectorAll("[data-plugin-key]").forEach(button=>button.addEventListener("click",()=>selectPluginSettings(button.dataset.pluginKey))); if(selectedPluginKey) selectPluginSettings(selectedPluginKey); }
async function loadPluginStatuses() { const payload=await apiJson("/api/plugins/status"); pluginStatuses=Array.isArray(payload?.plugins) ? payload.plugins : []; renderPluginStatusList(); const active=pluginStatuses.filter(item=>item.state==="active" && item.enabled).length; setPluginFeedback(pluginStatuses.length ? `${pluginStatuses.length} 个已发现 · ${active} 个已加载` : "未发现插件"); }
function pluginPermissionsNote(plugin) { const requested=Array.isArray(plugin.permissions_requested)?plugin.permissions_requested:[]; const granted=Array.isArray(plugin.permissions_granted)?plugin.permissions_granted:[]; if(!requested.length)return "该插件未声明额外能力。"; const missing=requested.filter(item=>!granted.includes(item)); return missing.length ? `加载时需要确认 ${missing.join("、")} 权限。` : `已授予权限：${requested.join("、")}。`; }
function pluginLifecycleControls(plugin) { if(!plugin.id)return `<div class="plugin-lifecycle"><p>此插件已在受控目录中发现，但尚未加入本机工作台。加入不会执行代码；之后可查看设置并按权限确认加载。</p><button type="button" class="plugin-lifecycle-button register" data-plugin-action="register">加入工作台</button></div>`; const active=plugin.state==="active" && plugin.enabled; const action=active ? "unload" : "load"; const label=active ? "卸载插件" : "加载插件"; const hint=active ? "卸载会停止插件并移除其前端面板；源码和设置会保留。" : pluginPermissionsNote(plugin); return `<div class="plugin-lifecycle"><p>${escapeHtml(hint)}</p><button type="button" class="plugin-lifecycle-button ${action}" data-plugin-action="${action}">${label}</button></div>`; }
function bindPluginLifecycleControls(plugin) { const button=document.querySelector("[data-plugin-action]"); if(button) button.addEventListener("click",()=>changePluginLifecycle(plugin,button.dataset.pluginAction)); }
function renderPluginDetail(plugin, payload={}) { const detail=$("plugin-settings-detail"); if(!detail)return; const registration=pluginSettingsRegistration(plugin.name); const title=registration?.title || `${plugin.name} 设置`; const description=registration?.description || "这些设置将安全保存在本机插件注册表。保存后在下次插件加载时传入 Python 运行时。"; const heading=`<div class="plugin-detail-heading"><div><h4>${escapeHtml(title)}</h4><p>${escapeHtml(plugin.name||"插件")} · v${escapeHtml(plugin.version||"—")}</p></div><span class="plugin-state-badge ${escapeHtml(plugin.state||"")}">${escapeHtml(pluginStateLabel(plugin.state))}</span></div>`; if(!plugin.settings_available || !plugin.id) { const reason=plugin.error || (plugin.settings_available ? "插件尚未写入注册表，无法保存设置。" : "该插件没有在 manifest 中声明 frontend.settings。") ; detail.innerHTML=`${heading}<p class="plugin-settings-note">${escapeHtml(reason)}</p>${pluginLifecycleControls(plugin)}`; bindPluginLifecycleControls(plugin); return; } detail.innerHTML=`${heading}<p class="plugin-settings-note">${escapeHtml(description)}</p>${pluginLifecycleControls(plugin)}<form id="plugin-settings-form" class="plugin-settings-editor"><label>JSON 配置<textarea id="plugin-settings-json" spellcheck="false" aria-label="${escapeHtml(plugin.name)} JSON 配置"></textarea></label><div class="plugin-settings-actions"><button type="submit">保存插件设置</button></div></form>`; $("plugin-settings-json").value=JSON.stringify(payload.settings || {}, null, 2); $("plugin-settings-form").addEventListener("submit",event=>savePluginSettings(event,plugin)); bindPluginLifecycleControls(plugin); }
async function selectPluginSettings(key) { selectedPluginKey=key; const plugin=pluginStatuses.find(item=>pluginKey(item)===key); if(!plugin)return; document.querySelectorAll(".plugin-status-card").forEach(card=>card.classList.toggle("selected",card.dataset.pluginKey===key)); if(!plugin.settings_available || !plugin.id) { renderPluginDetail(plugin,{}); return; } try { const payload=await apiJson(`/api/plugins/${encodeURIComponent(plugin.id)}/settings`); renderPluginDetail(plugin,payload); } catch(error) { $("plugin-settings-detail").innerHTML=`<p class="empty">无法读取设置：${escapeHtml(error.message)}</p>`; } }
async function savePluginSettings(event, plugin) { event.preventDefault(); let settings; try { settings=JSON.parse($("plugin-settings-json").value); if(!settings || Array.isArray(settings) || typeof settings!=="object") throw new Error("设置必须是 JSON 对象"); } catch(error) { setPluginFeedback(`无法保存：${error.message}`,"error"); return; } const response=await fetch(`/api/plugins/${encodeURIComponent(plugin.id)}/settings`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(settings)}); const payload=await response.json().catch(()=>({})); if(!response.ok) { setPluginFeedback(`无法保存：${payload.detail||response.statusText}`,"error"); return; } plugin.has_saved_settings=Object.keys(settings).length>0; setPluginFeedback(`${plugin.name} 的设置已保存；下次插件加载时生效。`,"success"); }
async function changePluginLifecycle(plugin, action) { if(!plugin)return; const registering=action==="register"; const loading=action==="load"; if(!registering && !plugin.id)return; const requested=Array.isArray(plugin.permissions_requested)?plugin.permissions_requested:[]; const granted=Array.isArray(plugin.permissions_granted)?plugin.permissions_granted:[]; const missing=requested.filter(item=>!granted.includes(item)); const message=registering ? `将“${plugin.name}”加入本机工作台注册表不会执行插件代码。之后仍需确认权限才能加载。\n\n继续吗？` : loading ? `加载“${plugin.name}”会执行其插件代码。${missing.length?`\n\n同时授予其声明的权限：\n${missing.map(item=>`• ${item}`).join("\n")}`:""}\n\n继续吗？` : `卸载“${plugin.name}”会停止插件并移除其前端面板。插件文件和设置会保留。\n\n继续吗？`; if(!window.confirm(message))return; const button=document.querySelector("[data-plugin-action]"); if(button)button.disabled=true; try { const url=registering ? `/api/plugins/discovered/${encodeURIComponent(plugin.name)}/register` : `/api/plugins/${encodeURIComponent(plugin.id)}/${loading?"load":"unload"}`; const response=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({confirm:true,grant_permissions:loading&&missing.length>0})}); const payload=await response.json().catch(()=>({})); if(!response.ok)throw new Error(payload.detail||response.statusText); if(registering)selectedPluginKey=payload.plugin?.id||plugin.name; if(loading)await loadPlugins(); else if(!registering)unloadPlugin(plugin.name); await loadPluginStatuses(); setPluginFeedback(registering ? `${plugin.name} 已加入工作台，可继续加载。` : loading ? `${plugin.name} 已加载。` : `${plugin.name} 已卸载；插件文件和设置已保留。`,"success"); } catch(error) { const verb=registering?"加入":loading?"加载":"卸载"; setPluginFeedback(`${verb}失败：${error.message}`,"error"); if(button)button.disabled=false; } }
function planUrl() { return `/api/sessions/${sessionId}/plan?agent=${encodeURIComponent(selectedPlanAgent)}`; }
function messagesUrl() { return `/api/sessions/${sessionId}/messages?agent=${encodeURIComponent(selectedAgent)}`; }
function graphUrl() { return `/api/sessions/${sessionId}/graph`; }
function agentIcon(agent) { if(agent.id === "all") return ["purple", "✦"]; if(agent.id === "coordinator") return ["purple", "♛"]; if(agent.dynamic) return ["amber", "↳"]; return ["blue", "&lt;/&gt;"]; }
function acknowledgementKey() { return `llmfetcherAcknowledgedAgents:${sessionId}`; }
function acknowledgedAgents() { try { return new Set(JSON.parse(localStorage.getItem(acknowledgementKey()) || "[]")); } catch { return new Set(); } }
/** Resolve one canonical graph state for every Agent status surface. */
function agentStateView(agentId, agents=currentAgents) {
  const agentIds=(agents||[]).filter(agent=>agent.id!=="all").map(agent=>agent.id);
  if(agentId==="all"){
    // A completed run is successful even when the coordinator recovered from
    // a failed worker; retain the worker's red light without failing the run.
    if(!runActive && currentGraph.run_status?.status==="completed") return stateView("completed","当前会话：运行完毕",agentId);
    const views=agentIds.map(id=>agentStateView(id,agents));
    const priority=["failed","interrupted","queued","running","completed"];
    const canonical=priority.find(state=>views.some(view=>view.canonical===state))||"idle";
    return stateView(canonical,canonical==="idle"?"当前会话待机":`当前会话：${stateLabel(canonical)}`,agentId);
  }

  // The live/persisted trace is newer than a graph response already in the
  // browser, so it wins until the refreshed graph snapshot arrives.
  const event=traceEvents.find(item=>(item.event==="lifecycle"&&item.agent===agentId)||(item.event==="error"&&agentId==="coordinator"));
  const persisted=currentGraph.node_states?.[agentId];
  if(event&&(!persisted?.state||Number(event.timestamp||0)>=Number(persisted.updated_at||0))){
    const type=String(event.type||"");
    let canonical="running";
    if(event.event==="error"||["agent:error","agent:failed"].includes(type)) canonical="failed";
    else if(type==="agent:stopped") canonical="interrupted";
    else if(type==="task:dispatched") canonical="queued";
    else if(type==="task:report_missing") canonical="failed";
    else if(["agent:complete","agent:completed"].includes(type)) canonical="completed";
    else if(type==="task:reported"){
      const status=String(event.data?.status||"").toLowerCase();
      canonical=["completed","complete","success","succeeded","done"].includes(status)?"completed":"failed";
    } else if(type==="task:finalized") canonical=String(event.data?.state||"interrupted");
    return stateView(canonical,event.message||stateLabel(canonical),agentId);
  }
  if(persisted?.state) return stateView(persisted.state,persisted.message||stateLabel(persisted.state),agentId);
  return stateView("idle","尚无执行事件",agentId);
}
/** Translate one canonical backend state into its Chinese UI label. */
function stateLabel(state) { return ({idle:"待机",queued:"等待执行",running:"正在运行",completed:"运行完毕",failed:"运行错误",interrupted:"已中断",cancelled:"已取消"})[state] || state; }
/** Apply acknowledgement and color-class rules to a canonical Agent state. */
function stateView(canonical, message, agentId) { const acknowledged=canonical==="completed" && acknowledgedAgents().has(agentId); const ui=acknowledged?"idle":canonical==="queued"?"pending":["failed","interrupted"].includes(canonical)?"error":canonical==="cancelled"?"idle":canonical; return {canonical,ui,message:acknowledged?"已确认完成":message}; }
function agentRunState(agentId, agents=currentAgents) { return agentStateView(agentId,agents).ui; }
function acknowledgeAgent(agentId) { const acknowledged=acknowledgedAgents(); if(agentId === "all") currentAgents.filter(agent=>agent.id !== "all" && agentRunState(agent.id) === "completed").forEach(agent=>acknowledged.add(agent.id)); else acknowledged.add(agentId); localStorage.setItem(acknowledgementKey(),JSON.stringify([...acknowledged])); renderAgentSelector(currentAgents); }
/** Render a secondary context-graph action without changing Agent-card selection. */
function agentCard(agent, selected, tone, icon, subtitle, view, title) {
  if (agent.id === "all") return `<button class="agent-filter ${selected?"selected active":""}" type="button" data-agent="all" aria-pressed="${selected}"><span class="agent-icon ${tone}">${icon}</span><span><strong>${escapeHtml(agent.name)}</strong><small>${escapeHtml(subtitle)}</small></span><i class="agent-state ${view.ui}" data-ack-agent="all" title="${escapeHtml(title)}"></i></button>`;
  return `<article class="agent-card ${selected?"selected active":""}"><button class="agent-card-main" type="button" data-agent="${escapeHtml(agent.id)}" aria-pressed="${selected}"><span class="agent-icon ${tone}">${icon}</span><span><strong>${escapeHtml(agent.name)}</strong><small>${escapeHtml(subtitle)}</small></span></button><button class="agent-context-button" type="button" data-context-agent="${escapeHtml(agent.id)}" title="查看 ${escapeHtml(agent.name)} 的上下文图" aria-label="查看 ${escapeHtml(agent.name)} 的上下文图">◎</button><i class="agent-state ${view.ui}" data-ack-agent="${escapeHtml(agent.id)}" title="${escapeHtml(title)}"></i></article>`;
}
function renderAgentSelector(agents=[]) { const row=$("agent-row"); const visible=agents.length ? agents : [{id:"all",name:"全部",kind:"filter"}]; currentAgents=visible; if(!visible.some(agent=>agent.id===selectedAgent)) selectedAgent="all"; row.innerHTML=visible.map(agent=>{const [tone,icon]=agentIcon(agent);const selected=agent.id===selectedAgent;const subtitle=agent.id==="all"?"当前会话":agent.dynamic?"动态子 Agent":agent.parent?`上级：${agent.parent}`:"Agent 会话";const view=agentStateView(agent.id,visible);const title=view.ui==="completed"?"点击确认完成":view.message;return agentCard(agent,selected,tone,icon,subtitle,view,title);}).join(""); row.querySelectorAll("[data-agent]").forEach(control=>control.addEventListener("click",()=>selectAgent(control.dataset.agent))); row.querySelectorAll("[data-context-agent]").forEach(control=>control.addEventListener("click",()=>openContextGraph(control.dataset.contextAgent))); row.querySelectorAll("[data-ack-agent]").forEach(dot=>dot.addEventListener("click",event=>{event.stopPropagation();const agentId=dot.dataset.ackAgent;if(agentRunState(agentId) === "completed") acknowledgeAgent(agentId);})); renderPlanAgentPicker(); }

/** Map untrusted entity types to the finite visual palette used by the graph. */
function contextNodeTone(type) { return ({file:"blue",tool:"amber",person:"pink",decision:"green",module:"purple",framework:"purple"})[String(type).toLowerCase()] || "slate"; }
/** Render the selected entity and its in-graph relationships into the dialog detail pane. */
function renderContextGraphDetail(graph, nodeId) {
  const node=(graph.nodes||[]).find(item=>item.id===nodeId); const target=$("context-graph-detail");
  if(!node){target.innerHTML='<p class="empty">选择一个实体查看详情。</p>';return;}
  const relations=(graph.edges||[]).filter(edge=>edge.source_id===nodeId||edge.target_id===nodeId);
  const names=Object.fromEntries((graph.nodes||[]).map(item=>[item.id,item.name]));
  const aliases=(node.aliases||[]).length ? `<p><b>别名</b>${escapeHtml(node.aliases.join("、"))}</p>` : "";
  const summary=node.summary ? `<p><b>摘要</b>${escapeHtml(node.summary)}</p>` : '<p class="muted">尚无实体摘要。</p>';
  const rows=relations.length ? relations.map(edge=>{const other=edge.source_id===nodeId?edge.target_id:edge.source_id;return `<li>${escapeHtml(edge.relation)} <span>· ${escapeHtml(names[other]||other)} · 时间线 ${edge.last_seen}</span></li>`;}).join("") : '<li class="muted">尚无可展示的内部关系。</li>';
  target.innerHTML=`<header><span class="context-entity-dot ${contextNodeTone(node.entity_type)}"></span><div><strong>${escapeHtml(node.name)}</strong><small>${escapeHtml(node.entity_type)} · 出现 ${Number(node.freq||0)} 次</small></div></header>${summary}${aliases}<p><b>时间线</b>${Number(node.first_seen||0)} — ${Number(node.last_seen||0)}</p><h4>关联</h4><ul>${rows}</ul>`;
}
/** Build the bounded relationship view, then bind entity selections for the current graph. */
function renderContextGraph(payload) {
  const graph=payload.graph||{}; const nodes=graph.nodes||[]; const edges=graph.edges||[];
  $("context-graph-title").textContent=`${payload.agent} · 上下文图`;
  $("context-graph-subtitle").textContent=graph.available?"这是 Agent 最近一次持久化 checkpoint 的长期记忆索引。":"该 Agent 尚未生成可查看的上下文图。";
  const ctx=payload.context||{};
  $("context-graph-summary").innerHTML=`<span>实体 <b>${Number(graph.node_count||0)}</b></span><span>关系 <b>${Number(graph.edge_count||0)}</b></span><span>社区 <b>${Number(graph.community_count||0)}</b></span><span>上下文 <b>${Number(ctx.messages||0)}</b> 条</span>${graph.truncated?'<small>仅显示最近的 60 个实体</small>':""}`;
  const canvas=$("context-graph-canvas"), list=$("context-graph-nodes");
  if(!graph.available || !nodes.length){canvas.innerHTML='<p class="empty">尚无实体。图会在 Agent 处理消息并完成 checkpoint 后出现。</p>';list.innerHTML="";$("context-graph-detail").innerHTML='<p class="empty">没有可检查的实体。</p>';return;}
  // Spread dense graphs across the full landscape canvas while leaving space
  // above and below every label instead of shrinking them into the center.
  const width=640,height=270,centerX=width/2,centerY=height/2;
  const radiusX=Math.min(245,Math.max(140,nodes.length*14));
  const radiusY=Math.min(95,Math.max(68,nodes.length*5));
  const positions=Object.fromEntries(nodes.map((node,index)=>{const angle=(Math.PI*2*index/nodes.length)-Math.PI/2;return [node.id,{x:centerX+Math.cos(angle)*radiusX,y:centerY+Math.sin(angle)*radiusY}];}));
  // Each point is the visual center of its absolutely positioned entity
  // button, so a relation starts and ends at the center of its two entities.
  const lines=edges.map(edge=>{const source=positions[edge.source_id],target=positions[edge.target_id];if(!source||!target)return "";return `<line x1="${source.x}" y1="${source.y}" x2="${target.x}" y2="${target.y}" class="${edge.valid===false?"invalid":""}"><title>${escapeHtml(edge.relation)}</title></line>`;}).join("");
  const points=nodes.map(node=>{const point=positions[node.id];return `<button type="button" class="context-graph-point ${contextNodeTone(node.entity_type)}" data-context-node="${escapeHtml(node.id)}" style="left:${(point.x/width)*100}%;top:${(point.y/height)*100}%" title="${escapeHtml(node.name)} · ${escapeHtml(node.entity_type)}">${escapeHtml(node.name.slice(0,18))}</button>`;}).join("");
  // Stretch the SVG to the canvas instead of preserving its intrinsic ratio.
  // This gives SVG endpoints the same percentage coordinate system as buttons.
  canvas.innerHTML=`<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-hidden="true">${lines}</svg>${points}`;
  list.innerHTML=nodes.map(node=>`<button type="button" class="context-graph-list-item" data-context-node="${escapeHtml(node.id)}"><span class="context-entity-dot ${contextNodeTone(node.entity_type)}"></span><span><strong>${escapeHtml(node.name)}</strong><small>${escapeHtml(node.entity_type)} · ${Number(node.freq||0)} 次</small></span></button>`).join("");
  document.querySelectorAll("[data-context-node]").forEach(control=>control.addEventListener("click",()=>renderContextGraphDetail(graph,control.dataset.contextNode)));
  renderContextGraphDetail(graph,nodes[0].id);
}
/** Switch the context dialog between its graph and raw-context top-level tabs. */
function selectContextDialogTab(tab) { const selected=tab==="prompt"?"prompt":"graph"; document.querySelectorAll("[data-context-dialog-tab]").forEach(button=>{const active=button.dataset.contextDialogTab===selected;button.setAttribute("aria-selected",String(active));button.classList.toggle("active",active);}); $("context-panel-graph").hidden=selected!=="graph"; $("context-panel-prompt").hidden=selected!=="prompt"; }
/**
 * Decode complete JSON-string layers for the context preview without touching raw text.
 *
 * Actual line feeds remain line feeds. A literal ``\\n`` is converted only after a
 * complete JSON string has been verified and parsed, so copied stdout and code keep
 * their byte-level meaning.
 *
 * @param {*} value Provider-neutral scalar prompt value.
 * @returns {string} Human-readable text with verified JSON escapes decoded.
 */
function decodePromptText(value) { let text=String(value??""); for(let depth=0;depth<3;depth+=1){const trimmed=text.trim();if(!(trimmed.startsWith('"')&&trimmed.endsWith('"')))break;try{const parsed=JSON.parse(trimmed);if(typeof parsed!=="string")break;text=parsed;}catch(_error){break;}} return text; }
/** Render one provider-neutral value without JSON escaping its human-readable strings. */
function readablePromptValue(value,indent="") { if(value===null)return "null"; if(Array.isArray(value))return value.map((item,index)=>`${indent}- [${index}] ${readablePromptValue(item,`${indent}  `)}`).join("\n"); if(typeof value==="object")return Object.entries(value).map(([key,item])=>`${indent}${key}: ${typeof item==="object"&&item!==null?`\n${readablePromptValue(item,`${indent}  `)}`:decodePromptText(item)}`).join("\n"); return decodePromptText(value); }
/** Render one selected Agent's metadata table and complete raw prompt in one context panel. */
function renderContextPrompt(payload) { const metadata=Array.isArray(payload.metadata)?payload.metadata:[], request=payload.request&&typeof payload.request==="object"?payload.request:null, stats=payload.stats&&typeof payload.stats==="object"?payload.stats:null, preview=$("context-prompt-preview"), rows=$("context-metadata-list"); preview.textContent=request?readablePromptValue(request):"此 Agent 尚未捕获完整远程请求。持久化 checkpoint 及其历史 tool_calls 不能替代真实请求，因此不会在这里伪装成远程 payload。请重启到当前版本后发起一次新的模型请求。"; $("context-request-note").textContent=request?"最近一次实际远程请求的完整内容；不保存 API key 或 endpoint。":"未捕获远程请求快照；下方仅保留当前 checkpoint 的元数据，不能代表远程请求。"; $("context-prompt-status").textContent=request?`${Number((request.messages||[]).length)} 条请求消息`:"快照缺失"; $("context-request-stats").innerHTML=stats?`<span>消息 <b>${Number(stats.messages)}</b></span><span>请求 <b>${Number(stats.characters).toLocaleString()}</b> 字符</span><span>工具 <b>${Number(stats.tool_schemas)}</b></span><span>Schema <b>${Number(stats.tool_schema_characters).toLocaleString()}</b> 字符</span><span>估算 <b>≈${Number(stats.estimated_tokens).toLocaleString()}</b> tokens</span>`:""; rows.innerHTML=metadata.length?metadata.map(item=>`<tr><td>${Number(item.index||0)}</td><td>${escapeHtml(item.source)}</td><td>${escapeHtml(item.type)}</td><td>${Number(item.length||0).toLocaleString()}</td><td>${escapeHtml(item.timeline)}</td></tr>`).join(""):'<tr><td colspan="5">没有可显示的上下文元数据。</td></tr>'; }
/** Fetch the complete persisted checkpoint once for the dialog's context tab. */
async function loadContextPrompt(agentId) { const payload=await apiJson(`/api/sessions/${encodeURIComponent(sessionId)}/agents/${encodeURIComponent(agentId)}/context`);renderContextPrompt(payload); }
/** Fetch a single Agent's persisted graph and open it in the theme-aware dialog. */
async function openContextGraph(agentId) {
  const dialog=$("context-graph-dialog"); if(!dialog) return;
  contextDialogAgent=agentId;
  $("context-graph-title").textContent=`${agentId} · 上下文图`; $("context-graph-subtitle").textContent="正在读取最近一次持久化 checkpoint…";
  $("context-graph-summary").innerHTML=""; $("context-graph-canvas").innerHTML='<p class="empty">正在加载…</p>'; $("context-graph-nodes").innerHTML=""; $("context-graph-detail").innerHTML="";
  selectContextDialogTab("graph");$("context-prompt-preview").textContent="正在读取当前上下文…";$("context-metadata-list").innerHTML='<tr><td colspan="5">正在读取…</td></tr>';$("context-prompt-status").textContent="读取中…";
  if(!dialog.open) dialog.showModal();
  try { const [graphPayload]=await Promise.all([apiJson(`/api/sessions/${encodeURIComponent(sessionId)}/agents/${encodeURIComponent(agentId)}/context-graph`),loadContextPrompt(agentId)]);renderContextGraph(graphPayload); }
  catch(error) { $("context-graph-subtitle").textContent="无法读取上下文图。"; $("context-graph-canvas").innerHTML=`<p class="empty">${escapeHtml(error.message)}</p>`;$("context-prompt-preview").textContent=error.message; }
}
async function loadAgents() { try { const payload=await apiJson(`/api/sessions/${sessionId}/agents`); renderAgentSelector(payload.agents); } catch(error) { trace("Agent 列表加载失败",error.message); renderAgentSelector(); } }
async function selectAgent(agentId) { if(!agentId || agentId===selectedAgent) return; selectedAgent=agentId; try { await rehydrateSelectedView({reloadAgents:true}); } catch(error) { trace("Agent 会话加载失败",error.message); } }
function renderGraph(graph) { const target=$("execution-graph"); const nodes=graph.nodes||[]; if(!nodes.length){target.innerHTML=`<p class="empty">当前 session 尚未启动 Swarm。</p>`;return;} const nodeIds=new Set(nodes.map(node=>node.id));const incoming={},outgoing={},parent={};for(const edge of graph.edges||[]){if(!nodeIds.has(edge.source)||!nodeIds.has(edge.target))continue;if((edge.kind||"dependency")==="dispatch"){if(edge.source!==edge.target)parent[edge.target]=edge.source;continue;}(incoming[edge.target]??=[]).push(edge.source);(outgoing[edge.source]??=[]).push(edge.target);}for(const node of nodes){if(node.parent&&nodeIds.has(node.parent)&&node.parent!==node.id)parent[node.id]=node.parent;}const children={};for(const [child,ancestor] of Object.entries(parent))(children[ancestor]??=[]).push(child);const byId=Object.fromEntries(nodes.map(node=>[node.id,node]));const rendered=new Set();const renderNode=(nodeId,depth=0,path=new Set())=>{const node=byId[nodeId];if(!node||path.has(nodeId))return "";rendered.add(nodeId);const nextPath=new Set(path).add(nodeId);const view=agentStateView(nodeId);const deps=incoming[nodeId]||[];const downstream=outgoing[nodeId]||[];const descendants=(children[nodeId]||[]).sort().map(child=>renderNode(child,depth+1,nextPath)).join("");return `<div class="graph-branch"><article class="graph-node ${view.ui}" style="--graph-depth:${depth}"><div class="graph-node-head"><strong>${escapeHtml(node.id)}</strong><i class="graph-node-state ${view.ui}"></i></div><span>${node.dynamic?"子智能体":node.kind==="routing"?"路由节点":"Agent"} · ${escapeHtml(stateLabel(view.canonical))}</span>${node.parent?`<small>调度者：${escapeHtml(node.parent)}</small>`:""}${deps.length?`<small>依赖：${escapeHtml(deps.join("、"))}</small>`:""}${downstream.length?`<small>下游：${escapeHtml(downstream.join("、"))}</small>`:""}${view.message?`<small>${escapeHtml(view.message)}</small>`:""}</article>${descendants?`<div class="graph-children">${descendants}</div>`:""}</div>`;};const roots=nodes.filter(node=>!parent[node.id]).map(node=>node.id).sort();const html=roots.map(id=>renderNode(id)).join("");const leftovers=nodes.filter(node=>!rendered.has(node.id)).map(node=>renderNode(node.id)).join("");target.innerHTML=html+leftovers; }
/** Refresh the graph data used by the selector, topology, and usage views. */
async function loadGraph() { const response=await fetch(graphUrl()); if(response.status===404){currentGraph={nodes:[],edges:[],assignments:{},task_states:{},node_states:{}};renderAgentSelector(currentAgents);return;} if(!response.ok) throw new Error(`${response.status} ${response.statusText} (${graphUrl()})`); currentGraph=await response.json();renderAgentSelector(currentAgents); }
/** Build the cursor-paginated durable Trace request for the selected session. */
function traceUrl(before=null) { const params=new URLSearchParams({limit:"200"}); if(before !== null) params.set("before",String(before)); return `/api/sessions/${sessionId}/events?${params}`; }
async function loadTrace(reset=true) { const page=await apiJson(traceUrl(reset ? null : traceBefore)); const events=page.events || []; const target=$("trace"); if(reset){ traceEvents=events; traceBefore=page.next_before; target.innerHTML=""; } else { traceEvents.push(...events); traceBefore=page.next_before; } if(!traceEvents.length){target.innerHTML=`<p class="empty">当前 session 尚无事件。</p>`;} else { const fragment=document.createDocumentFragment(); for(const event of events) { const lifecycle=event.event === "lifecycle"; const type=String(event.type || event.event || "event"); const title=lifecycle ? type.replace("agent:","").replaceAll("_"," ") : type; fragment.append(traceView.build(title,event.message || "",event.data || event.usage || null,traceView.kindFor(event),{time:traceView.formatTime(event.timestamp),agent:lifecycle && event.agent ? event.agent : ""})); } target.append(fragment); } $("load-more-trace").hidden=traceBefore === null; }
function agentContextStats(agent) {
  const ctx = agent.context || {};
  const messages = Number(ctx.messages || 0);
  const chars = Number(ctx.characters || 0);
  const abstractChars = Number(ctx.abstract_characters || 0);
  const threshold = Number(ctx.threshold || 0);
  const compacted = Boolean(ctx.compacted);
  const ratio = Number(ctx.ratio || 0);

  if (!messages && !chars && !abstractChars) {
    return `<small class="agent-context">上下文：—</small>`;
  }

  const charsLabel = `${chars.toLocaleString()}`;
  const ratioLabel = threshold > 0 ? ` · ${Math.round(ratio * 100)}%` : "";
  const compactLabel = compacted ? ` · 已压缩` : "";
  const thresholdLabel = threshold > 0 ? ` / 阈值 ${threshold.toLocaleString()}` : "";
  return `<small class="agent-context" title="消息 ${messages} 条 · 字符 ${chars + abstractChars} · 压缩阈值 ${threshold}">上下文：${messages} 条 · ${charsLabel} 字符${thresholdLabel}${ratioLabel}${compactLabel}</small>`;
}

/** Render the delegation tree; activating one Agent opens its context graph. */
function renderAgentTopology(agents, graph) {
  const target=$("inspector-agents-list");
  if(!agents.length){target.innerHTML=`<p class="empty">当前 session 尚未创建 Agent。</p>`;return;}
  const byId=Object.fromEntries(agents.map(agent=>[agent.id,agent])); const parent={}; const children={};
  // Prefer explicit parents, then recover the same hierarchy from dispatch edges.
  for(const agent of agents) if(agent.parent && byId[agent.parent] && agent.parent!==agent.id) parent[agent.id]=agent.parent;
  for(const edge of graph.edges||[]) if(edge.kind==="dispatch" && byId[edge.source] && byId[edge.target] && edge.source!==edge.target) parent[edge.target]=edge.source;
  for(const [child,leader] of Object.entries(parent)) (children[leader]??=[]).push(child);
  const taskByAgent={}; for(const [taskId,agentId] of Object.entries(graph.assignments||{})) (taskByAgent[agentId]??=[]).push(taskId);
  const rendered=new Set(); const render=(id,depth=0,path=new Set())=>{const agent=byId[id];if(!agent||path.has(id))return "";rendered.add(id);const view=agentStateView(id,[...agents,{id:"all"}]);const tasks=(taskByAgent[id]||[]).map(task=>`<span class="agent-task">${escapeHtml(task)}</span>`).join("");const descendants=(children[id]||[]).sort().map(child=>render(child,depth+1,new Set(path).add(id))).join("");return `<div class="agent-topology-branch"><article class="inspector-agent ${escapeHtml(view.ui)}" data-context-agent="${escapeHtml(id)}" role="button" tabindex="0" aria-label="查看 ${escapeHtml(agent.name||id)} 的上下文图" style="--agent-depth:${depth}"><i class="${escapeHtml(view.ui)}"></i><div><header><strong>${escapeHtml(agent.name||id)}</strong><small>${agent.dynamic?"动态子 Agent":id==="coordinator"?"协调者":"Agent"}</small></header><p>${escapeHtml(view.message)}</p>${tasks?`<div class="agent-tasks">${tasks}</div>`:""}${agentContextStats(agent)}</div></article>${descendants?`<div class="agent-topology-children">${descendants}</div>`:""}</div>`;};
  const roots=agents.filter(agent=>!parent[agent.id]).map(agent=>agent.id).sort((a,b)=>a==="coordinator"?-1:b==="coordinator"?1:a.localeCompare(b)); const html=roots.map(id=>render(id)).join("")+agents.filter(agent=>!rendered.has(agent.id)).map(agent=>render(agent.id)).join(""); target.innerHTML=html;
  target.querySelectorAll("[data-context-agent]").forEach(control=>{
    control.addEventListener("click",()=>openContextGraph(control.dataset.contextAgent));
    control.addEventListener("keydown",event=>{if(event.key==="Enter"||event.key===" "){event.preventDefault();openContextGraph(control.dataset.contextAgent);}});
  });
}
async function loadInspectorAgents() { const [agentPayload,graphPayload]=await Promise.all([apiJson(`/api/sessions/${sessionId}/agents`),apiJson(graphUrl())]);currentGraph=graphPayload;const agents=(agentPayload.agents||[]).filter(agent=>agent.id!=="all");renderAgentTopology(agents,graphPayload);renderAgentSelector(agentPayload.agents); }
function usageCells(usage) { return [["Input",usage.input],["Output",usage.output],["Total",usage.total],["Cached",usage.cached],["Reasoning",usage.reasoning]].map(([label,value])=>`<span>${label}<b>${Number(value || 0).toLocaleString()}</b></span>`).join(""); }
/** Render per-Agent token totals with the same reconciled state lights as other Agent surfaces. */
async function loadUsage() { const [payload,graphPayload]=await Promise.all([apiJson(`/api/sessions/${sessionId}/usage`),apiJson(graphUrl()).catch(()=>null)]); if(graphPayload) currentGraph=graphPayload; const usage=payload.usage || {}; $("usage-total").innerHTML=Number(usage.total || 0) ? usageCells(usage).replaceAll("<span>","<div>").replaceAll("</span>","</div>") : `<p class="empty">尚无已完成的模型调用。</p>`; $("usage-agents").innerHTML=(payload.agents || []).map(agent=>{const view=agentStateView(agent.id); return `<article class="usage-agent"><header><span class="usage-agent-title"><i class="agent-state ${escapeHtml(view.ui)}" title="${escapeHtml(view.message)}"></i><strong>${escapeHtml(agent.id)}</strong></span><span>${Number(agent.usage.total || 0).toLocaleString()} tokens</span></header><div class="usage-agent-grid">${usageCells(agent.usage)}</div></article>`;}).join(""); }
function selectInspectorPanel(panel, refresh=true) { const target=document.getElementById(panel); if(!target) return; activeInspectorPanel=panel; localStorage.llmfetcherInspectorPanel=panel; document.querySelectorAll("[data-inspector-panel]").forEach(button=>button.classList.toggle("active",button.dataset.inspectorPanel===panel)); document.querySelectorAll(".inspector-panel").forEach(item=>item.classList.toggle("active",item===target)); if(!refresh) return; const loaders={"inspector-plan":loadPlan,"inspector-agents":loadInspectorAgents,"inspector-trace":()=>loadTrace(true),"inspector-usage":loadUsage}; loaders[panel]?.().catch(error=>trace("检查器加载失败",error.message)); }
function initInspectorTabs() { document.querySelectorAll("[data-inspector-panel]").forEach(button=>button.addEventListener("click",()=>selectInspectorPanel(button.dataset.inspectorPanel))); if(!document.getElementById(activeInspectorPanel)) activeInspectorPanel="inspector-plan"; selectInspectorPanel(activeInspectorPanel,false); }
function knownPlanAgents() { const known=new Map([["coordinator",{id:"coordinator",name:"协调者（总计划）"}]]); for(const agent of currentAgents||[]) if(agent?.id && agent.id!=="all") known.set(agent.id,agent); for(const node of currentGraph.nodes||[]) if(node?.id) known.set(node.id,{id:node.id,name:node.id,dynamic:node.dynamic}); return [...known.values()]; }
function renderPlanAgentPicker() { const select=$("plan-agent"); if(!select)return; const agents=knownPlanAgents(); if(!agents.some(agent=>agent.id===selectedPlanAgent)) selectedPlanAgent="coordinator"; select.innerHTML=agents.map(agent=>`<option value="${escapeHtml(agent.id)}">${escapeHtml(agent.id==="coordinator"?"协调者（总计划）":agent.name||agent.id)}</option>`).join(""); select.value=selectedPlanAgent; }
async function loadPlan() { renderPlanAgentPicker(); const plan=await apiJson(planUrl()); const agentLabel=selectedPlanAgent==="coordinator"?"协调者":selectedPlanAgent; $("plan-summary").textContent=plan.goal ? `${agentLabel} · ${plan.goal}${plan.summary ? ` · ${plan.summary}` : ""}` : `${agentLabel} 尚未建立任务计划。`; $("task-plan").innerHTML=(plan.tasks||[]).map(task=>renderTaskPlanItem(task)).join("") || `<p class="empty">尚未建立任务计划。</p>`; }
async function updatePlanStatus(taskId,status) { const response=await fetch(`${planUrl()}/tasks/${taskId}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({status})}); if(!response.ok) throw new Error("任务状态更新失败"); await loadPlan(); }
/** Rehydrate the aggregate view or one Agent's durable trajectory and transcript. */
async function loadHistory() {
  if (selectedAgent === "all") return loadAllAgentBehavior();
  const [{messages = []}, {total = 0}] = await Promise.all([
    apiJson(messagesUrl()),
    apiJson(`/api/sessions/${sessionId}/events?limit=1`),
  ]);
  durableEventCount = total;
  renderedSteerEvents.clear();
  renderedRoundEvents.clear();
  pendingRoundTools.clear();
  const chat = $("chat");
  chat.innerHTML = "";
  if (!messages.length) {
    chat.innerHTML = `<div class="welcome"><div class="welcome-symbol">✦</div><h2>暂无 ${escapeHtml(selectedAgent)} 的轨迹</h2><p>此视图会展示该 Agent 的回复、思考和工具调用详情。</p></div>`;
    return;
  }
  const fragment = document.createDocumentFragment();
  for (const message of messages) {
    fragment.append(chatView.buildMessage(message, selectedAgent));
  }
  chat.append(fragment);
  chat.scrollTop = chat.scrollHeight;
}
/** Rebuild the selected filter from durable state, then safely reconnect its run. */
async function rehydrateSelectedView({reloadAgents=false}={}) { if(reloadAgents) await loadAgents(); await loadHistory(); await restoreRunState(); }
async function switchSession(selected) { persistSettings(); if(source && sourceWorkspaceId !== selected){source.close();source=null;sourceWorkspaceId="";setRunning(false);setStatus("准备就绪");} selectedAgent="all"; selectedPlanAgent="coordinator"; traceBefore=null; traceEvents=[]; durableEventCount=0; await loadWorkspaces(selected); await loadConnectors(); restoreSettings(); await Promise.all([loadPlan(),loadGraph(),loadTrace(true)]); await rehydrateSelectedView({reloadAgents:true}); await loadInspectorAgents(); }

async function start(message) {
  let runConfig;
  try { runConfig=config(); } catch(error) { setStatus("MCP 配置无效", "error"); trace("MCP 配置无效", error.message); alert(error.message); return; }
  // Show the submitted prompt immediately in every filter; the durable reload
  // after a result will replace this optimistic turn with canonical history.
  setRunning(true); setStatus("正在执行", "running"); appendMessage("user", message);
  try {
    const response=await fetch("/api/runs", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({session_id:sessionId, workspace_id:workspaceId, message, config:runConfig})});
    const payload=await response.json(); if(!response.ok) throw new Error(payload.detail || "无法开始运行");
    setWorkspaceIndicator(workspaceId,"running"); connectRunEvents(payload.run_id);
  } catch(error) { trace("请求失败", error.message, null); appendRunErrorBlock("无法启动运行", error.message); setStatus("请求失败", "error"); setRunning(false); }
}
function handleEvent(event) {
  durableEventCount+=1;
  // A captured preflight snapshot is durable before its SSE event arrives,
  // so an open inspector can safely refresh to the exact newest request.
  if(event.event === "lifecycle" && event.type === "agent:remote_request" && $("context-graph-dialog").open && contextDialogAgent === (event.agent || "coordinator")) loadContextPrompt(contextDialogAgent).catch(error=>trace("上下文请求预览刷新失败",error.message));
  if(event.event === "lifecycle") { traceEvents.unshift(event); tracePayload(event); renderAgentSelector(currentAgents); if(event.type === "agent:tools_requested") { pendingRoundTools.set(`${event.agent||"coordinator"}:${event.data?.round||""}`, liveTools(event.data)); } if(event.type === "agent:tools_completed") { pendingRoundTools.set(`${event.agent||"coordinator"}:${event.data?.round||""}`, liveTools(event.data)); } if(event.type === "agent:steer_applied") { setSteerStatus(`已应用 ${(event.data?.messages||[]).length || 1} 条调整指令 ✓`,"applied"); const eventKey=`${event.timestamp || ""}:${event.agent || "coordinator"}:${JSON.stringify(event.data?.messages || [])}`; if(selectedAgent === "all" || selectedAgent === (event.agent || "coordinator")) (event.data?.messages||[]).forEach((text,index)=>appendSteerMessage(text,`${eventKey}:${index}`)); } if(event.type === "agent:round") { const roundAgent=event.agent || "coordinator"; if(selectedAgent === "all" || selectedAgent === roundAgent){ const roundData=event.data||{}; const roundContent=String(roundData.assistant_content||""); const roundReasoning=String(roundData.reasoning_content||""); const roundContentHtml=String(roundData.assistant_content_html||""); const roundReasoningHtml=String(roundData.reasoning_content_html||""); const roundKey=roundData.round||""; const roundTools=pendingRoundTools.get(`${roundAgent}:${roundKey}`) || liveTools(roundData); if(roundKey) pendingRoundTools.delete(`${roundAgent}:${roundKey}`); if(roundContent || roundReasoning || roundTools.length){ const dedupeKey=`${event.timestamp||""}:${roundAgent}:${roundKey}:${roundContent}`; if(!renderedRoundEvents.has(dedupeKey)){ renderedRoundEvents.add(dedupeKey); appendMessage("assistant", roundContent, roundReasoning, roundContentHtml, roundReasoningHtml, roundTools, roundAgent); } } } } if(event.type === "agent:complete") updateHeaderMetrics(event.data); if(activeInspectorPanel === "inspector-usage" && event.type === "agent:round") loadUsage().catch(error=>trace("用量加载失败",error.message)); if(activeInspectorPanel === "inspector-agents") loadInspectorAgents().catch(error=>trace("Agent 检查器加载失败",error.message)); if(event.source === "graph" || event.source === "plan" || event.type.includes("task:")){ loadGraph().then(loadAgents).catch(error=>trace("执行图加载失败",error.message)); loadPlan().catch(error=>trace("任务规划加载失败",error.message)); } return; }
  if(event.event === "result") { const resultAgent=event.agent || "coordinator"; if(selectedAgent === "all" || selectedAgent === resultAgent) loadHistory().catch(error=>trace("聚合会话加载失败",error.message)); updateHeaderMetrics(event); loadPlan().catch(error=>trace("任务规划加载失败",error.message)); loadGraph().then(loadAgents).catch(error=>trace("执行图加载失败",error.message)); traceEvents.unshift(event); tracePayload({...event,message:`${event.provider} · ${event.model}`,data:event.usage}); return; }
  if(event.event === "error") { setWorkspaceIndicator(workspaceId,"error"); traceEvents.unshift({...event,type:"agent:error",agent:event.agent || "coordinator"}); tracePayload(event); renderAgentSelector(currentAgents); appendRunErrorBlock("运行失败",event.message); setStatus("运行失败", "error"); return; }
  if(event.event === "stopped") { setWorkspaceIndicator(workspaceId,"done"); traceEvents.unshift(event); tracePayload(event); }
  if(event.event === "done") { setWorkspaceIndicator(workspaceId,"done"); finish(); loadGraph().then(loadAgents).catch(error=>trace("执行图加载失败",error.message)); }
}
function finish() { source?.close(); source=null; sourceWorkspaceId=""; setRunning(false); if(!$("status").classList.contains("error")) setStatus("准备就绪"); }
/* ---- Slash commands -------------------------------------------------- */
function showSlashHelp() {
  chatView.removeWelcome();
  const rows=[
    ["/help","显示本帮助"],
    ["/new <会话名>","创建并切换到新会话"],
    ["/switch <会话名>","切换到已有会话"],
    ["/clear","清空聊天区视图（会话记录仍保留）"],
    ["/connectors","打开连接设置"],
    ["/settings [--panel=…]","打开设置对话框"],
    ["/plan /agents /usage /trace","切换右侧检查器面板"],
    ["/stop /force-stop","停止 / 强行停止当前运行"],
    ["/agent <agentId>","查看指定 Agent 会话"],
    ["/delete <会话名>","删除会话（需确认）"],
    ["/compact [--agent=<id>]","手动压缩上下文为摘要"],
    ["","参数支持引号、转义与 --key=value"],
  ];
  const el=document.createElement("article"); el.className="message assistant";
  const body=rows.map(([cmd,desc])=>`<tr><td>${escapeHtml(cmd)}</td><td>${escapeHtml(desc)}</td></tr>`).join("");
  el.innerHTML=`<div class="message-meta"><div class="role role-agent"><i></i><span>斜杠指令</span></div><small>帮助</small></div><div class="bubble markdown"><table><thead><tr><th>指令</th><th>说明</th></tr></thead><tbody>${body}</tbody></table><p>参数支持引号分组、反斜杠转义与 <code>--key=value</code> 命名参数。</p></div>`;
  $("chat").append(el); $("chat").scrollTop=$("chat").scrollHeight;
}
function sessionByName(name) { return availableSessions.find(item=>item.name===name || item.id===name); }
async function switchSessionByName(name) { const target=sessionByName(name); if(!target){ setStatus(`未找到会话「${name}」`,"error"); return; } await switchSession(target.id); trace("已切换会话", target.name); }
async function deleteSessionByName(name) { const target=sessionByName(name); if(!target){ setStatus(`未找到会话「${name}」`,"error"); return; } if(!confirm(`删除会话「${target.name}」？此操作不可撤销。`)) return; const response=await fetch(`/api/sessions/${encodeURIComponent(target.id)}`,{method:"DELETE",headers:{"Content-Type":"application/json"},body:JSON.stringify({confirmation:target.id})}); if(!response.ok){ const payload=await response.json().catch(()=>({})); throw new Error(payload.detail||"删除失败"); } await loadWorkspaces(); setStatus(`已删除会话「${target.name}」`); trace("已删除会话", target.name); }
async function runStop() { await fetch(`/api/workspaces/${workspaceId}/runs/${sessionId}/stop`,{method:"POST"}); $("stop").disabled=true; setStatus("等待安全停止", "running"); }
async function runForceStop() { if(!confirm("强行停止当前会话？这会中断当前模型请求，并立即终止正在执行的 Shell 工具进程。")) return; $("force-stop").disabled=true; $("stop").disabled=true; setStatus("正在强行停止", "running"); const response=await fetch(`/api/workspaces/${workspaceId}/runs/${sessionId}/force-stop`,{method:"POST"}); if(!response.ok){const message=`${response.status} ${response.statusText}`;trace("强行停止失败",message);appendRunErrorBlock("强行停止失败",message);setStatus("停止失败","error"); setRunning(true); return;} trace("强行停止","已请求中断当前模型调用并终止工具进程。"); }
let compacting=false;
async function runCompact(agent="coordinator") {
  if(compacting){ setStatus("压缩已在进行中…", "running"); return; }
  if($("composer").hidden){ setStatus("运行结束后才能压缩上下文", "error"); return; }
  compacting=true; $("message").disabled=true;
  const startedSession=sessionId;
  try {
    setStatus("正在压缩上下文…", "running"); trace("上下文压缩", `开始压缩 ${agent} 的上下文…`);
    const response=await fetch(`/api/sessions/${sessionId}/compact`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({agent, config: config()})});
    if(!response.ok || !response.body){ const payload=await response.json().catch(()=>({})); const detail=payload.detail||`${response.status} ${response.statusText}`; setStatus(`压缩失败：${detail}`, "error"); trace("压缩失败", detail); return; }
    const reader=response.body.getReader(); const decoder=new TextDecoder(); let buffer="";
    while(true){ const {done, value}=await reader.read(); if(done) break; buffer+=decoder.decode(value,{stream:true}); const lines=buffer.split("\n"); buffer=lines.pop()||""; for(const line of lines){ if(!line.trim()) continue; let record; try{ record=JSON.parse(line); }catch{ continue; } handleCompactStage(record, startedSession); } }
  } catch(error){ setStatus(`压缩失败：${error.message}`,"error"); trace("压缩失败", error.message); }
  finally { compacting=false; if(sessionId===startedSession) $("message").disabled=false; }
}
function handleCompactStage(record, startedSession) {
  if(sessionId!==startedSession) return; /* 切换会话后忽略旧压缩流 */
  const {stage, detail, kind, error="", raw_content:rawContent=""}=record;
  if(kind==="error"){ const diagnostic=error ? `${detail}\n原因：${error}` : detail; setStatus(detail,"error"); trace("压缩失败", diagnostic); appendRunErrorBlock("上下文压缩失败", diagnostic, rawContent); }
  else if(stage==="done"){ setStatus(detail,"idle"); trace("上下文压缩", detail); loadInspectorAgents().catch(()=>{}); }
  else setStatus(detail,"running");
}
const slashHandlers = {
  help: ()=> showSlashHelp(),
  "new": (args)=> args.length ? createAndSwitchSession(args.join(" ")) : setStatus("用法：/new <会话名>", "error"),
  "switch": (args)=> args.length ? switchSessionByName(args.join(" ")).catch(error=>setStatus(`切换失败：${error.message}`,"error")) : setStatus("用法：/switch <会话名>", "error"),
  clear: ()=> { renderMessagesInto([]); trace("聊天区已清空","仅清空当前视图，会话记录仍会保留。"); },
  connectors: ()=> openConnectorDialog(),
  settings: (args,flags)=> openSettings(flags.panel || "connection"),
  plan: ()=> selectInspectorPanel("inspector-plan"),
  agents: ()=> selectInspectorPanel("inspector-agents"),
  usage: ()=> selectInspectorPanel("inspector-usage"),
  trace: ()=> selectInspectorPanel("inspector-trace"),
  stop: ()=> runStop().catch(error=>trace("停止失败",error.message)),
  "force-stop": ()=> runForceStop().catch(error=>trace("强行停止失败",error.message)),
  agent: (args)=> args.length ? selectAgent(args[0]) : setStatus("用法：/agent <agentId>，可用 /agents 查看", "error"),
  delete: (args)=> args.length ? deleteSessionByName(args.join(" ")).catch(error=>{ setStatus(`删除失败：${error.message}`,"error"); trace("删除失败",error.message); }) : setStatus("用法：/delete <会话名>", "error"),
  compact: (args,flags)=> runCompact(String(flags.agent || "coordinator")),
};
function dispatchSlashCommand(parsed) {
  const { command, args, flags } = parsed;
  const handler = slashHandlers[command];
  if(!handler){ setStatus(`未知指令 /${command}，输入 /help 查看可用指令`, "error"); return; }
  handler(args, flags);
}

/** Resize the composer to its content, restoring the compact size when empty. */
function resizeComposer() { const el=$("message"); el.style.height="auto"; if(el.value) el.style.height=`${Math.min(el.scrollHeight,170)}px`; }
function connectRunEvents(runId, after=durableEventCount) { source?.close(); const eventSource=new EventSource(`/api/workspaces/${workspaceId}/runs/${runId}/events?after=${after}`); source=eventSource; sourceWorkspaceId=workspaceId; eventSource.onmessage=(event)=>{ if(workspaceId === sourceWorkspaceId) handleEvent(JSON.parse(event.data)); }; eventSource.onerror=()=>{ if(eventSource.readyState===EventSource.CLOSED && source===eventSource) finish(); else if(eventSource.readyState===EventSource.CONNECTING && source===eventSource) setStatus("连接中断，正在重连…", "running"); }; }
async function restoreRunState() { try { const state=await apiJson(`/api/workspaces/${workspaceId}/runs/${sessionId}/status`); if(state.active && state.run_id){ setRunning(true); setStatus("正在执行", "running"); connectRunEvents(state.run_id, durableEventCount); return; } if(state.status === "error" || state.status === "interrupted"){ const title=state.status === "interrupted" ? "执行已中断" : "上次运行失败"; setStatus(title,"error"); appendRunErrorBlock(title,state.error); trace(title,state.error); return; } if(state.status === "completed") setStatus("已完成"); else if(state.status === "stopped") setStatus("已停止"); } catch(error) { appendRunErrorBlock("运行状态加载失败",error.message); trace("运行状态加载失败", error.message); } }
$("composer").addEventListener("submit", (event)=>{event.preventDefault(); const message=$("message").value; if(!message.trim()) return; if(runActive){ sendSteer(message); return; } $("message").value=""; resizeComposer(); const parsed=parseSlashCommand(message); if(parsed){ dispatchSlashCommand(parsed); return; } start(message);});
$("message").addEventListener("keydown", (event)=>{
  // Plain Enter submits; Shift/Alt+Enter insert a newline in the textarea.
  if(event.key !== "Enter" || event.shiftKey || event.altKey || event.isComposing) return;
  event.preventDefault();
  $("composer").requestSubmit();
});
$("message").addEventListener("input", resizeComposer);
$("model").addEventListener("input",updateModelSummary); $("provider").addEventListener("change",()=>{applyProviderPreset(); updateModelSummary();});
$("stop").addEventListener("click", ()=>runStop().catch(error=>trace("停止失败",error.message)));
$("force-stop").addEventListener("click", ()=>runForceStop().catch(error=>trace("强行停止失败",error.message)));
$("close-context-graph").addEventListener("click", ()=>{contextDialogAgent="";$("context-graph-dialog").close();});
document.querySelectorAll("[data-context-dialog-tab]").forEach(button=>button.addEventListener("click",()=>selectContextDialogTab(button.dataset.contextDialogTab)));
$("workspace").addEventListener("change", event=>{const nextWorkspaceId=event.target.value;switchSession(nextWorkspaceId).then(()=>trace("已切换会话", event.target.options[event.target.selectedIndex].text)).catch(error=>trace("会话切换失败",error.message));});
$("open-workspace").addEventListener("click",async()=>{try{const response=await fetch(`/api/sessions/${encodeURIComponent(workspaceId)}/open-folder`,{method:"POST"});const payload=await response.json();if(!response.ok)throw new Error(payload.detail||"无法打开工作空间目录");trace("已打开工作空间目录",payload.path||workspaceId);}catch(error){trace("打开工作空间目录失败",error.message);alert(`无法打开工作空间目录：${error.message}`);}});
async function createAndSwitchSession(name) {
  if(!name?.trim()) return;
  try {
    const response=await fetch("/api/sessions",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name})});
    const session=await response.json();
    if(!response.ok) throw new Error(session.detail || "无法创建会话");
    await switchSession(session.id);
    trace("已创建并切换会话",session.name);
  } catch(error) {
    // The record may have been created before a later view-rehydration request failed.
    await loadWorkspaces().catch(()=>{});
    trace("创建或切换会话失败",error.message);
    alert(`无法创建或切换会话：${error.message}`);
  }
}
/** Open an in-page dialog so session creation does not depend on browser prompts. */
$("new-workspace").addEventListener("click", ()=>{
  const dialog=$("new-session-dialog");
  const input=$("new-session-name");
  input.value="";
  dialog.showModal();
  input.focus();
});
$("cancel-new-session").addEventListener("click", ()=>$("new-session-dialog").close());
$("new-session-form").addEventListener("submit", async event=>{
  event.preventDefault();
  const input=$("new-session-name");
  const name=input.value.trim();
  if(!name) { input.focus(); return; }
  $("new-session-dialog").close();
  await createAndSwitchSession(name);
});
$("delete-workspace").addEventListener("click",async()=>{const selected=$("workspace").selectedOptions[0];if(!selected)return;const targetId=selected.value;const name=selected.text;if(!confirm(`删除会话“${name}”及其所有数据？此操作不可恢复。`))return;const confirmation=prompt(`请输入会话名称“${name}”以确认删除：`);if(confirmation !== name)return;const response=await fetch(`/api/sessions/${encodeURIComponent(targetId)}`,{method:"DELETE",headers:{"Content-Type":"application/json"},body:JSON.stringify({confirmation})});const payload=await response.json();if(response.status===404){await loadWorkspaces();await loadHistory();await loadPlan();await loadGraph();trace("会话已不存在",`${name} 已被移除，已切换到有效会话。`);return;}if(!response.ok){alert(payload.detail||"无法删除会话");return;}if(payload.status==="stopping"){trace("正在停止并删除会话",payload.message);return;}await loadWorkspaces();await loadHistory();await loadPlan();await loadGraph();trace("会话已删除",name);});
$("connector").addEventListener("change", event=>{connectorId=event.target.value;localStorage.llmfetcherConnector=connectorId;loadConnectors(connectorId).then(()=>{ persistSettings(); updateModelSummary(); });});
$("new-connector").addEventListener("click", openConnectorDialog);
$("open-settings").addEventListener("click", ()=>openSettings());
$("close-settings").addEventListener("click", ()=>$("settings-dialog").close());
document.querySelectorAll("[data-settings-section]").forEach(button=>button.addEventListener("click",()=>showSettingsSection(button.dataset.settingsSection)));
$("refresh-plugins").addEventListener("click",()=>loadPluginStatuses().catch(error=>setPluginFeedback(`加载插件状态失败：${error.message}`,"error")));
$("session-memory-search").addEventListener("input", renderMemorySessionPicker);
$("cancel-new-connector").addEventListener("click", ()=>$("new-connector-dialog").close());
$("new-connector-form").addEventListener("submit", async event=>{event.preventDefault(); const input=$("new-connector-name"); const name=input.value.trim(); if(!name){input.focus();return;} $("new-connector-dialog").close(); try{await createConnector(name);}catch(error){trace("保存连接器失败",error.message);connectorFeedback("保存失败","error");alert(`无法保存连接器：${error.message}`);}});
$("save-connector").addEventListener("click", async()=>{try{await saveSelectedConnector();}catch(error){trace("更新连接器失败",error.message);connectorFeedback("保存失败","error");alert(`无法保存连接器：${error.message}`);}});
$("delete-connector").addEventListener("click", async()=>{if(!connectorId||!confirm("删除这个连接及其保存的密钥？"))return;const response=await fetch(`/api/connectors/${connectorId}`,{method:"DELETE"});if(!response.ok){alert("无法删除连接");return;}connectorId="";localStorage.llmfetcherConnector="";await loadConnectors();trace("已删除连接");});
$("refresh-plan").addEventListener("click",()=>loadPlan().catch(error=>trace("任务规划加载失败",error.message)));
$("plan-agent").addEventListener("change",event=>{selectedPlanAgent=event.target.value||"coordinator";localStorage.llmfetcherPlanAgent=selectedPlanAgent;loadPlan().catch(error=>trace("任务规划加载失败",error.message));});
$("refresh-graph").addEventListener("click",()=>loadInspectorAgents().catch(error=>trace("执行图加载失败",error.message)));
$("refresh-trace").addEventListener("click",()=>loadTrace(true).catch(error=>trace("Trace 加载失败",error.message)));
$("load-more-trace").addEventListener("click",()=>loadTrace(false).catch(error=>trace("Trace 加载失败",error.message)));
$("refresh-usage").addEventListener("click",()=>loadUsage().catch(error=>trace("用量加载失败",error.message)));
$("task-plan").addEventListener("change",event=>{if(event.target.matches(".task-state"))updatePlanStatus(event.target.dataset.taskId,event.target.value).catch(error=>trace("任务更新失败",error.message));});
if(location.protocol === "file:") trace("服务未启动", "请通过 llmfetcher web 启动控制台，而不是直接打开 HTML 文件。");
async function loadProviders() { try { const {providers}=await apiJson("/api/providers"); const select=$("provider"), chosen=select.value; select.innerHTML=providers.map(x=>`<option value="${escapeHtml(x)}">${escapeHtml(providerLabel(x))}</option>`).join(""); select.value=providers.includes(chosen)?chosen:providers[0]; } catch {} }
async function initializeConsole() { initInspectorTabs(); bindSettingsPersistence(); await initPlugins(); await loadProviders(); await loadWorkspaces(); await loadConnectors(); restoreSettings(); applyProviderPreset(); updateModelSummary(); await Promise.all([loadPlan(),loadGraph(),loadTrace(true)]); await rehydrateSelectedView({reloadAgents:true}); await loadInspectorAgents(); }
initializeConsole().catch(error=>trace("工作空间/会话加载失败", error.message));
