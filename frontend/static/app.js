const $ = (id) => document.getElementById(id);

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
let currentAgents = [];
let currentGraph = {nodes:[],edges:[],assignments:{},task_states:{},node_states:{}};

const value = (id) => $(id).value.trim();
const config = () => ({
  provider: value("provider"), model: value("model"), api_key: $("api-key").value,
  api_url: value("api-url"), system_prompt: $("system-prompt").value,
  temperature: Number($("temperature").value), max_tokens: Number($("max-tokens").value),
  max_rounds: Number($("max-rounds").value), max_context_threshold: Number($("max-context-threshold").value), enable_shell: $("enable-shell").checked,
  enable_swarm: $("enable-swarm").checked, max_swarm_agents: Number($("max-swarm-agents").value),
});
const settingsIds = ["provider", "model", "api-url", "api-key", "system-prompt", "temperature", "max-tokens", "max-rounds", "max-context-threshold", "max-swarm-agents"];
function settingsKey(id=workspaceId) { return `llmfetcherSettings:${id}`; }
function persistSettings() { if(!workspaceId) return; const settings={...config(), enable_shell:$('enable-shell').checked, enable_swarm:$('enable-swarm').checked}; localStorage.setItem(settingsKey(), JSON.stringify(settings)); }
function restoreSettings() { try { const settings=JSON.parse(localStorage.getItem(settingsKey()) || "null"); if(!settings) return; settingsIds.forEach(id=>{const key=id.replaceAll("-","_"); if(settings[key] !== undefined) $(id).value=settings[key];}); $("enable-shell").checked=Boolean(settings.enable_shell); $("enable-swarm").checked=Boolean(settings.enable_swarm); } catch { /* Ignore malformed browser-local settings. */ } }
function bindSettingsPersistence() { [...settingsIds,"enable-shell","enable-swarm"].forEach(id=>["input","change"].forEach(event=>$(id).addEventListener(event,persistSettings))); }
function setStatus(text, state="idle") { const el=$("status"); el.textContent=text; el.className=`status ${state}`; }
function updateModelSummary() { $("model-label").textContent=$("model").value.trim() || "模型配置"; $("provider-label").textContent=$("provider").options[$("provider").selectedIndex]?.text || "OpenAI compatible"; }
function escapeHtml(text) { const node=document.createElement("div"); node.textContent=text ?? ""; return node.innerHTML; }
function removeWelcome() { $("chat").querySelector(".welcome")?.remove(); }
async function copyResult(text, button) { try { await navigator.clipboard.writeText(text); button.textContent="已复制"; setTimeout(()=>button.textContent="复制结果",1200); } catch { button.textContent="复制失败"; } }
function renderTools(tools=[]) { if(!tools.length)return ""; const calls=tools.map(tool=>`<article class="tool-call"><strong>${escapeHtml(tool.name)}</strong><p>参数</p><pre>${escapeHtml(JSON.stringify(tool.arguments,null,2))}</pre><p>结果</p><pre>${escapeHtml(tool.result || "(无返回内容)")}</pre></article>`).join(""); return `<details class="tool-calls"><summary>工具调用 · ${tools.length}</summary>${calls}</details>`; }
/** Render a user or selected-Agent transcript turn with an explicit speaker. */
function appendMessage(role, content, reasoning="", contentHtml="", reasoningHtml="", tools=[], agentName="") { removeWelcome(); const el=document.createElement("article"); el.className=`message ${role}`; const body=contentHtml || escapeHtml(content); const bodyClass=contentHtml ? "markdown" : "plain-text"; const thought=reasoningHtml || escapeHtml(reasoning); const copy=role === "assistant" && content ? `<button class="copy-result" type="button">复制结果</button>` : ""; const bubble=content ? `<div class="bubble ${bodyClass}">${body}</div>` : ""; const isUser=role === "user"; const speaker=isUser ? "你" : (agentName || selectedAgent || "Coordinator"); const kind=isUser ? "用户输入" : "Agent 回复"; el.innerHTML=`<div class="message-meta"><div class="role role-${isUser ? "user" : "agent"}"><i></i><span>${escapeHtml(speaker)}</span></div><small>${kind}</small>${copy}</div>${bubble}${reasoning ? `<details class="reasoning"><summary>思考过程</summary><div class="markdown">${thought}</div></details>` : ""}${renderTools(tools)}`; el.querySelector(".copy-result")?.addEventListener("click",()=>copyResult(content,el.querySelector(".copy-result"))); $("chat").append(el); $("chat").scrollTop=$("chat").scrollHeight; }
/** Display a durable run failure in the chat pane without hiding prior work. */
function appendRunErrorBlock(title, message) { removeWelcome(); const el=document.createElement("article"); el.className="run-error"; el.innerHTML=`<strong>⚠ ${escapeHtml(title)}</strong><p>${escapeHtml(message || "未提供错误详情。")}</p>`; $("chat").append(el); $("chat").scrollTop=$("chat").scrollHeight; }
/** Load the canonical session transcript using the same detailed message UI. */
async function loadAllAgentBehavior() { const [{total=0},{messages=[]}]=await Promise.all([apiJson(`/api/sessions/${sessionId}/events?limit=1`),apiJson(`/api/sessions/${sessionId}/messages`)]); durableEventCount=total; $("chat").innerHTML=""; for(const message of messages) appendMessage(message.role,message.content,message.reasoning,message.content_html,message.reasoning_html,message.tools,message.role === "assistant" ? "coordinator" : ""); if(!messages.length) $("chat").innerHTML=`<div class="welcome"><div class="welcome-symbol">✦</div><h2>等待 Agent 回复</h2><p>用户输入和 Agent 回复会按时间顺序显示在这里。</p></div>`; }
/** Build one escaped, expandable Trace card from persisted or live event data. */
function traceElement(title, message="", data=null, kind="") { const el=document.createElement("article"); el.className=`trace-event ${kind}`; const detail=data ? `<pre>${escapeHtml(JSON.stringify(data, null, 2))}</pre>` : ""; const label=kind==="tool"?"TOOL CALL":"STATUS"; el.innerHTML=`<button class="trace-toggle" type="button" aria-expanded="false"><span class="trace-summary"><i></i><strong>${escapeHtml(title)}</strong><small>${label}</small></span><span class="trace-chevron">⌄</span></button><div class="trace-details"><p>${escapeHtml(message)}</p>${detail}</div>`; el.querySelector(".trace-toggle").addEventListener("click",()=>{const expanded=el.classList.toggle("expanded");el.querySelector(".trace-toggle").setAttribute("aria-expanded",String(expanded));}); return el; }
function trace(title, message="", data=null, kind="") { const target=$("trace"); target.querySelector(".empty")?.remove(); target.prepend(traceElement(title,message,data,kind)); }
function tracePayload(event, position="prepend") { const lifecycle=event.event === "lifecycle"; const type=String(event.type || event.event || "event"); const title=lifecycle ? `${event.agent ? `[${event.agent}] ` : ""}${type.replace("agent:","").replaceAll("_"," ")}` : type; const kind=type.includes("tool") ? "tool" : ""; const node=traceElement(title,event.message || "",event.data || event.usage || null,kind); const target=$("trace"); target.querySelector(".empty")?.remove(); target[position](node); }
function updateHeaderMetrics(data) { if (!data) return; $("header-tokens").textContent=data.usage?.total ?? data.total ?? "—"; if(data.duration_ms) $("header-duration").textContent=`${(data.duration_ms/1000).toFixed(1)}s`; }
function setRunning(running) { $("send").disabled=running; $("stop").disabled=!running; $("force-stop").disabled=!running; $("message").disabled=running; $("composer").hidden=running; const steerComposer=$("steer-composer"); steerComposer.hidden=!running; if(running){ resizeSteerComposer(); setSteerStatus("运行中 — 输入指令，Agent 会在安全的轮次边界调整方向"); $("steer-message").focus(); } const guidance=$("run-guidance"); if(running && !guidance){const panel=document.createElement("aside");panel.id="run-guidance";panel.className="run-guidance";panel.innerHTML="<strong>Agent 正在执行</strong><span>可在右侧查看工具调用与用量。</span><span>停止会在当前模型与工具步骤完成后生效。</span><span>强行停止会立即终止已注册的 Shell 工具进程。</span><span>切换工作空间不会中断后台任务，结果会保存在原会话。</span><span>运行中可在下方输入框发送调整指令，Agent 会在安全的轮次边界应用。</span>"; $("chat").append(panel);} if(!running) guidance?.remove(); }
let steerStatusTimer = null;
const steerHintText = "运行中 — 输入指令，Agent 会在安全的轮次边界调整方向";
function setSteerStatus(text, state="") { const el=$("steer-status"); if(!el) return; const hint=el.closest(".steer-hint"); el.textContent=text; el.className=state ? `steer-status ${state}` : "steer-status"; if(hint) hint.className=`steer-hint ${state || ""}`.trim(); clearTimeout(steerStatusTimer); if(state) steerStatusTimer=setTimeout(()=>{ el.textContent=steerHintText; el.className="steer-status"; if(hint) hint.className="steer-hint"; }, 6000); }
function resizeSteerComposer() { const el=$("steer-message"); el.style.height="auto"; if(el.value) el.style.height=`${Math.min(el.scrollHeight,170)}px`; }
async function sendSteer(message) { const send=$("steer-send"), input=$("steer-message"); send.disabled=true; setSteerStatus("正在加入队列…","sending"); try { const response=await fetch(`/api/workspaces/${workspaceId}/runs/${sessionId}/steer`, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({message})}); const payload=await response.json().catch(()=>({})); if(!response.ok) throw new Error(payload.detail || `${response.status} ${response.statusText}`); input.value=""; resizeSteerComposer(); setSteerStatus("指令已加入队列，将在安全的轮次边界应用 ✓","queued"); } catch(error) { setSteerStatus(`发送失败：${error.message}`,"error"); trace("调整指令发送失败", error.message); } finally { send.disabled=false; input.focus(); } }
async function apiJson(path) { const response=await fetch(path); if(!response.ok) throw new Error(`${response.status} ${response.statusText} (${path})`); return response.json(); }
/** Load every session into the select and independently scrollable quick list. */
async function loadWorkspaces(selected=sessionId) { const {sessions}=await apiJson("/api/sessions"); if(!sessions.length) throw new Error("会话列表为空"); const select=$("workspace"); select.innerHTML=sessions.map(item=>`<option value="${escapeHtml(item.id)}">${escapeHtml(item.name)}</option>`).join(""); workspaceId=sessions.some(item=>item.id===selected)?selected:sessions[0].id; sessionId=workspaceId; select.value=workspaceId; localStorage.llmfetcherWorkspace=workspaceId; localStorage.llmfetcherSession=sessionId; const recent=$("recent-sessions"); recent.innerHTML=sessions.map(item=>`<button class="recent-session ${item.id===workspaceId?"active":""}" type="button" data-workspace-id="${escapeHtml(item.id)}">${escapeHtml(item.name)}</button>`).join(""); recent.querySelectorAll("[data-workspace-id]").forEach(button=>button.addEventListener("click",()=>switchSession(button.dataset.workspaceId).catch(error=>trace("会话切换失败",error.message)))); recent.querySelector(".active")?.scrollIntoView({block:"nearest"}); }
function applyConnector(connector) { ["provider","model","api-url","api-key","system-prompt","temperature","max-tokens","max-rounds","max-context-threshold","max-swarm-agents"].forEach(id=>{const key=id.replaceAll("-","_"); if(connector[key] !== undefined) $(id).value=connector[key];}); $("enable-shell").checked=Boolean(connector.enable_shell); $("enable-swarm").checked=Boolean(connector.enable_swarm); }
async function loadConnectors(selected=connectorId) { const {connectors}=await apiJson("/api/connectors"); const select=$("connector"); select.innerHTML=`<option value="">未保存的临时连接</option>${connectors.map(item=>`<option value="${escapeHtml(item.id)}">${escapeHtml(item.name)}</option>`).join("")}`; connectorId=connectors.some(item=>item.id===selected)?selected:""; select.value=connectorId; localStorage.llmfetcherConnector=connectorId; const connector=connectors.find(item=>item.id===connectorId); if(connector) applyConnector(connector); }
function connectorPayload(name) { return {name, ...config()}; }
/** Give connector saves a visible local result instead of relying on hidden Trace. */
function connectorFeedback(text, state="") { const button=$("save-connector"); button.textContent=text; button.dataset.state=state; clearTimeout(connectorFeedback.timer); connectorFeedback.timer=setTimeout(()=>{button.textContent="保存";button.dataset.state="";},1800); }
/** Persist the current fields as a new globally available connector. */
async function createConnector(name) { const response=await fetch("/api/connectors",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(connectorPayload(name))}); const connector=await response.json(); if(!response.ok) throw new Error(connector.detail||"无法保存连接"); await loadConnectors(connector.id); trace("已保存连接",connector.name); connectorFeedback("已保存","success"); }
/** Replace the selected connector while keeping its global identity. */
async function saveSelectedConnector() { if(!connectorId){openConnectorDialog();return;} const name=$("connector").selectedOptions[0]?.text||"当前连接"; const response=await fetch(`/api/connectors/${connectorId}`,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(connectorPayload(name))}); if(!response.ok){const payload=await response.json().catch(()=>({}));throw new Error(payload.detail||"无法更新连接");} trace("已更新连接",name); connectorFeedback("已保存","success"); }
/** Open the document-native name dialog used by both new and unsaved connectors. */
function openConnectorDialog() { const dialog=$("new-connector-dialog"); const input=$("new-connector-name"); input.value=""; dialog.showModal(); input.focus(); }
function planUrl() { return `/api/sessions/${sessionId}/plan`; }
function messagesUrl() { return `/api/sessions/${sessionId}/messages?agent=${encodeURIComponent(selectedAgent)}`; }
function graphUrl() { return `/api/sessions/${sessionId}/graph`; }
function agentIcon(agent) { if(agent.id === "all") return ["purple", "✦"]; if(agent.id === "coordinator") return ["purple", "♛"]; if(agent.dynamic) return ["amber", "↳"]; return ["blue", "&lt;/&gt;"]; }
function acknowledgementKey() { return `llmfetcherAcknowledgedAgents:${sessionId}`; }
function acknowledgedAgents() { try { return new Set(JSON.parse(localStorage.getItem(acknowledgementKey()) || "[]")); } catch { return new Set(); } }
/** Resolve one canonical graph state for every Agent status surface. */
function agentStateView(agentId, agents=currentAgents) {
  const agentIds=(agents||[]).filter(agent=>agent.id!=="all").map(agent=>agent.id);
  if(agentId==="all"){
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
function renderAgentSelector(agents=[]) { const row=$("agent-row"); const visible=agents.length ? agents : [{id:"all",name:"全部",kind:"filter"}]; currentAgents=visible; if(!visible.some(agent=>agent.id===selectedAgent)) selectedAgent="all"; row.innerHTML=visible.map(agent=>{const [tone,icon]=agentIcon(agent);const selected=agent.id===selectedAgent;const subtitle=agent.id==="all"?"当前会话":agent.dynamic?"动态子 Agent":agent.parent?`上级：${agent.parent}`:"Agent 会话";const view=agentStateView(agent.id,visible);const title=view.ui==="completed"?"点击确认完成":view.message;return `<button class="${agent.id==="all"?"agent-filter":"agent-card"} ${selected?"selected active":""}" type="button" data-agent="${escapeHtml(agent.id)}" aria-pressed="${selected}"><span class="agent-icon ${tone}">${icon}</span><span><strong>${escapeHtml(agent.name)}</strong><small>${escapeHtml(subtitle)}</small></span><i class="agent-state ${view.ui}" data-ack-agent="${escapeHtml(agent.id)}" title="${escapeHtml(title)}"></i></button>`;}).join(""); row.querySelectorAll("[data-agent]").forEach(control=>control.addEventListener("click",()=>selectAgent(control.dataset.agent))); row.querySelectorAll("[data-ack-agent]").forEach(dot=>dot.addEventListener("click",event=>{event.stopPropagation();const agentId=dot.dataset.ackAgent;if(agentRunState(agentId) === "completed") acknowledgeAgent(agentId);})); }
async function loadAgents() { try { const payload=await apiJson(`/api/sessions/${sessionId}/agents`); renderAgentSelector(payload.agents); } catch(error) { trace("Agent 列表加载失败",error.message); renderAgentSelector(); } }
async function selectAgent(agentId) { if(!agentId || agentId===selectedAgent) return; selectedAgent=agentId; try { await rehydrateSelectedView({reloadAgents:true}); } catch(error) { trace("Agent 会话加载失败",error.message); } }
function renderGraph(graph) { const target=$("execution-graph"); const nodes=graph.nodes||[]; if(!nodes.length){target.innerHTML=`<p class="empty">当前 session 尚未启动 Swarm。</p>`;return;} const nodeIds=new Set(nodes.map(node=>node.id));const incoming={},outgoing={},parent={};for(const edge of graph.edges||[]){if(!nodeIds.has(edge.source)||!nodeIds.has(edge.target))continue;if((edge.kind||"dependency")==="dispatch"){if(edge.source!==edge.target)parent[edge.target]=edge.source;continue;}(incoming[edge.target]??=[]).push(edge.source);(outgoing[edge.source]??=[]).push(edge.target);}for(const node of nodes){if(node.parent&&nodeIds.has(node.parent)&&node.parent!==node.id)parent[node.id]=node.parent;}const children={};for(const [child,ancestor] of Object.entries(parent))(children[ancestor]??=[]).push(child);const byId=Object.fromEntries(nodes.map(node=>[node.id,node]));const rendered=new Set();const renderNode=(nodeId,depth=0,path=new Set())=>{const node=byId[nodeId];if(!node||path.has(nodeId))return "";rendered.add(nodeId);const nextPath=new Set(path).add(nodeId);const view=agentStateView(nodeId);const deps=incoming[nodeId]||[];const downstream=outgoing[nodeId]||[];const descendants=(children[nodeId]||[]).sort().map(child=>renderNode(child,depth+1,nextPath)).join("");return `<div class="graph-branch"><article class="graph-node ${view.ui}" style="--graph-depth:${depth}"><div class="graph-node-head"><strong>${escapeHtml(node.id)}</strong><i class="graph-node-state ${view.ui}"></i></div><span>${node.dynamic?"子智能体":node.kind==="routing"?"路由节点":"Agent"} · ${escapeHtml(stateLabel(view.canonical))}</span>${node.parent?`<small>调度者：${escapeHtml(node.parent)}</small>`:""}${deps.length?`<small>依赖：${escapeHtml(deps.join("、"))}</small>`:""}${downstream.length?`<small>下游：${escapeHtml(downstream.join("、"))}</small>`:""}${view.message?`<small>${escapeHtml(view.message)}</small>`:""}</article>${descendants?`<div class="graph-children">${descendants}</div>`:""}</div>`;};const roots=nodes.filter(node=>!parent[node.id]).map(node=>node.id).sort();const html=roots.map(id=>renderNode(id)).join("");const leftovers=nodes.filter(node=>!rendered.has(node.id)).map(node=>renderNode(node.id)).join("");target.innerHTML=html+leftovers; }
async function loadGraph() { const response=await fetch(graphUrl()); if(response.status===404){currentGraph={nodes:[],edges:[],assignments:{},task_states:{},node_states:{}};renderGraph(currentGraph);return;} if(!response.ok) throw new Error(`${response.status} ${response.statusText} (${graphUrl()})`); currentGraph=await response.json();renderGraph(currentGraph);renderAgentSelector(currentAgents); }
/** Build the cursor-paginated durable Trace request for the selected session. */
function traceUrl(before=null) { const params=new URLSearchParams({limit:"200"}); if(before !== null) params.set("before",String(before)); return `/api/sessions/${sessionId}/events?${params}`; }
async function loadTrace(reset=true) { const page=await apiJson(traceUrl(reset ? null : traceBefore)); const events=page.events || []; const target=$("trace"); if(reset){ traceEvents=events; traceBefore=page.next_before; target.innerHTML=""; } else { traceEvents.push(...events); traceBefore=page.next_before; } if(!traceEvents.length){target.innerHTML=`<p class="empty">当前 session 尚无事件。</p>`;} else { const fragment=document.createDocumentFragment(); for(const event of events) { const lifecycle=event.event === "lifecycle"; const type=String(event.type || event.event || "event"); const title=lifecycle ? `${event.agent ? `[${event.agent}] ` : ""}${type.replace("agent:","").replaceAll("_"," ")}` : type; fragment.append(traceElement(title,event.message || "",event.data || event.usage || null,type.includes("tool") ? "tool" : "")); } target.append(fragment); } $("load-more-trace").hidden=traceBefore === null; }
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

async function loadInspectorAgents() { const [agentPayload,graphPayload]=await Promise.all([apiJson(`/api/sessions/${sessionId}/agents`),apiJson(graphUrl())]);currentGraph=graphPayload;const agents=(agentPayload.agents||[]).filter(agent=>agent.id!=="all");const target=$("inspector-agents-list");target.innerHTML=agents.length?agents.map(agent=>{const view=agentStateView(agent.id,agentPayload.agents);return `<article class="inspector-agent"><i class="${escapeHtml(view.ui)}"></i><div><strong>${escapeHtml(agent.name)}</strong><small>${escapeHtml(view.message)}</small>${agentContextStats(agent)}</div></article>`;}).join(""):`<p class="empty">当前 session 尚未创建 Agent。</p>`;renderAgentSelector(agentPayload.agents);renderGraph(graphPayload); }
function usageCells(usage) { return [["Input",usage.input],["Output",usage.output],["Total",usage.total],["Cached",usage.cached],["Reasoning",usage.reasoning]].map(([label,value])=>`<span>${label}<b>${Number(value || 0).toLocaleString()}</b></span>`).join(""); }
async function loadUsage() { const payload=await apiJson(`/api/sessions/${sessionId}/usage`); const usage=payload.usage || {}; $("usage-total").innerHTML=Number(usage.total || 0) ? usageCells(usage).replaceAll("<span>","<div>").replaceAll("</span>","</div>") : `<p class="empty">尚无已完成的模型调用。</p>`; $("usage-agents").innerHTML=(payload.agents || []).map(agent=>`<article class="usage-agent"><header><strong>${escapeHtml(agent.id)}</strong><span>${Number(agent.usage.total || 0).toLocaleString()} tokens</span></header><div class="usage-agent-grid">${usageCells(agent.usage)}</div></article>`).join(""); }
function selectInspectorPanel(panel, refresh=true) { const target=document.getElementById(panel); if(!target) return; activeInspectorPanel=panel; localStorage.llmfetcherInspectorPanel=panel; document.querySelectorAll("[data-inspector-panel]").forEach(button=>button.classList.toggle("active",button.dataset.inspectorPanel===panel)); document.querySelectorAll(".inspector-panel").forEach(item=>item.classList.toggle("active",item===target)); if(!refresh) return; const loaders={"inspector-plan":loadPlan,"inspector-agents":loadInspectorAgents,"inspector-trace":()=>loadTrace(true),"inspector-usage":loadUsage}; loaders[panel]?.().catch(error=>trace("检查器加载失败",error.message)); }
function initInspectorTabs() { document.querySelectorAll("[data-inspector-panel]").forEach(button=>button.addEventListener("click",()=>selectInspectorPanel(button.dataset.inspectorPanel))); selectInspectorPanel(activeInspectorPanel,false); }
function renderTask(task, depth=0) { const children=(task.subtasks||[]).map(item=>renderTask(item,depth+1)).join(""); const estimate=task.estimated_minutes ? ` · ${task.estimated_minutes} 分钟` : ""; return `<article class="task-block depth-${depth}"><div class="task-block-head"><span class="task-status ${escapeHtml(task.status)}"></span><div><strong>${escapeHtml(task.title)}</strong><p>${escapeHtml(task.priority)}${estimate}</p></div><select data-task-id="${escapeHtml(task.id)}" class="task-state"><option value="not_started" ${task.status==="not_started"?"selected":""}>未开始</option><option value="in_progress" ${task.status==="in_progress"?"selected":""}>进行中</option><option value="completed" ${task.status==="completed"?"selected":""}>已完成</option><option value="blocked" ${task.status==="blocked"?"selected":""}>受阻</option></select></div>${task.description ? `<p class="task-description">${escapeHtml(task.description)}</p>` : ""}${children ? `<div class="task-children">${children}</div>` : ""}</article>`; }
async function loadPlan() { const plan=await apiJson(planUrl()); $("plan-summary").textContent=plan.goal ? `${plan.goal}${plan.summary ? ` · ${plan.summary}` : ""}` : "Agent 生成的任务计划会显示在这里。"; $("task-plan").innerHTML=(plan.tasks||[]).map(task=>renderTask(task)).join("") || `<p class="empty">尚未建立任务计划。</p>`; }
async function updatePlanStatus(taskId,status) { const response=await fetch(`${planUrl()}/tasks/${taskId}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({status})}); if(!response.ok) throw new Error("任务状态更新失败"); await loadPlan(); }
/** Rehydrate the aggregate view or one Agent's durable trajectory and transcript. */
async function loadHistory() {
  if (selectedAgent === "all") return loadAllAgentBehavior();
  const [{messages = []}, {total = 0}] = await Promise.all([
    apiJson(messagesUrl()),
    apiJson(`/api/sessions/${sessionId}/events?limit=1`),
  ]);
  durableEventCount = total;
  $("chat").innerHTML = "";
  for (const message of messages) {
    appendMessage(message.role, message.content, message.reasoning,
      message.content_html, message.reasoning_html, message.tools, selectedAgent);
  }
  if (!messages.length) {
    $("chat").innerHTML = `<div class="welcome"><div class="welcome-symbol">✦</div><h2>暂无 ${escapeHtml(selectedAgent)} 的轨迹</h2><p>此视图会展示该 Agent 的回复、思考和工具调用详情。</p></div>`;
  }
}
/** Rebuild the selected filter from durable state, then safely reconnect its run. */
async function rehydrateSelectedView({reloadAgents=false}={}) { if(reloadAgents) await loadAgents(); await loadHistory(); await restoreRunState(); }
async function switchSession(selected) { persistSettings(); if(source && sourceWorkspaceId !== selected){source.close();source=null;sourceWorkspaceId="";setRunning(false);setStatus("准备就绪");} selectedAgent="all"; traceBefore=null; traceEvents=[]; durableEventCount=0; await loadWorkspaces(selected); await loadConnectors(); restoreSettings(); await Promise.all([loadPlan(),loadGraph(),loadTrace(true)]); await rehydrateSelectedView({reloadAgents:true}); await loadInspectorAgents(); }

async function start(message) {
  // Show the submitted prompt immediately in every filter; the durable reload
  // after a result will replace this optimistic turn with canonical history.
  setRunning(true); setStatus("正在执行", "running"); appendMessage("user", message);
  try {
    const response=await fetch("/api/runs", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({session_id:sessionId, workspace_id:workspaceId, message, config:config()})});
    const payload=await response.json(); if(!response.ok) throw new Error(payload.detail || "无法开始运行");
    connectRunEvents(payload.run_id);
  } catch(error) { trace("请求失败", error.message, null); appendRunErrorBlock("无法启动运行", error.message); setStatus("请求失败", "error"); setRunning(false); }
}
function handleEvent(event) {
  durableEventCount+=1;
  if(event.event === "lifecycle") { traceEvents.unshift(event); tracePayload(event); renderAgentSelector(currentAgents); if(event.type === "agent:steer_applied") setSteerStatus(`已应用 ${(event.data?.messages||[]).length || 1} 条调整指令 ✓`,"applied"); if(event.type === "agent:complete") updateHeaderMetrics(event.data); if(activeInspectorPanel === "inspector-usage" && event.type === "agent:round") loadUsage().catch(error=>trace("用量加载失败",error.message)); if(activeInspectorPanel === "inspector-agents") loadInspectorAgents().catch(error=>trace("Agent 检查器加载失败",error.message)); if(event.source === "graph" || event.source === "plan" || event.type.includes("task:")){ loadGraph().then(loadAgents).catch(error=>trace("执行图加载失败",error.message)); loadPlan().catch(error=>trace("任务规划加载失败",error.message)); } return; }
  if(event.event === "result") { const resultAgent=event.agent || "coordinator"; if(selectedAgent === "all") loadHistory().catch(error=>trace("聚合会话加载失败",error.message)); else if(selectedAgent === resultAgent) appendMessage("assistant", event.content, event.reasoning, event.content_html, event.reasoning_html, [], resultAgent); updateHeaderMetrics(event); loadPlan().catch(error=>trace("任务规划加载失败",error.message)); loadGraph().then(loadAgents).catch(error=>trace("执行图加载失败",error.message)); traceEvents.unshift(event); tracePayload({...event,message:`${event.provider} · ${event.model}`,data:event.usage}); return; }
  if(event.event === "error") { traceEvents.unshift({...event,type:"agent:error",agent:event.agent || "coordinator"}); tracePayload(event); renderAgentSelector(currentAgents); appendRunErrorBlock("运行失败",event.message); setStatus("运行失败", "error"); return; }
  if(event.event === "stopped") { traceEvents.unshift(event); tracePayload(event); }
  if(event.event === "done") finish();
}
function finish() { source?.close(); source=null; sourceWorkspaceId=""; setRunning(false); if(!$("status").classList.contains("error")) setStatus("准备就绪"); }
/** Resize the composer to its content, restoring the compact size when empty. */
function resizeComposer() { const el=$("message"); el.style.height="auto"; if(el.value) el.style.height=`${Math.min(el.scrollHeight,170)}px`; }
function connectRunEvents(runId) { source?.close(); const eventSource=new EventSource(`/api/workspaces/${workspaceId}/runs/${runId}/events?after=${durableEventCount}`); source=eventSource; sourceWorkspaceId=workspaceId; eventSource.onmessage=(event)=>{ if(workspaceId === sourceWorkspaceId) handleEvent(JSON.parse(event.data)); }; eventSource.onerror=()=>{ if(eventSource.readyState===EventSource.CLOSED && source===eventSource) finish(); }; }
async function restoreRunState() { try { const state=await apiJson(`/api/workspaces/${workspaceId}/runs/${sessionId}/status`); if(state.active && state.run_id){ setRunning(true); setStatus("正在执行", "running"); connectRunEvents(state.run_id); return; } if(state.status === "error" || state.status === "interrupted"){ const title=state.status === "interrupted" ? "执行已中断" : "上次运行失败"; setStatus(title,"error"); appendRunErrorBlock(title,state.error); trace(title,state.error); return; } if(state.status === "completed") setStatus("已完成"); else if(state.status === "stopped") setStatus("已停止"); } catch(error) { appendRunErrorBlock("运行状态加载失败",error.message); trace("运行状态加载失败", error.message); } }
$("composer").addEventListener("submit", (event)=>{event.preventDefault(); const message=$("message").value; if(!message.trim()) return; $("message").value=""; resizeComposer(); start(message);});
$("message").addEventListener("keydown", (event)=>{
  // Plain Enter submits; Shift/Alt+Enter insert a newline in the textarea.
  if(event.key !== "Enter" || event.shiftKey || event.altKey || event.isComposing) return;
  event.preventDefault();
  $("composer").requestSubmit();
});
$("message").addEventListener("input", resizeComposer);
$("steer-composer").addEventListener("submit", event=>{event.preventDefault(); const message=$("steer-message").value.trim(); if(!message) return; sendSteer(message);});
$("steer-message").addEventListener("keydown", event=>{ if(event.key !== "Enter" || event.shiftKey || event.altKey || event.isComposing) return; event.preventDefault(); $("steer-composer").requestSubmit(); });
$("steer-message").addEventListener("input", resizeSteerComposer);
$("model").addEventListener("input",updateModelSummary); $("provider").addEventListener("change",updateModelSummary);
$("stop").addEventListener("click", async()=>{await fetch(`/api/workspaces/${workspaceId}/runs/${sessionId}/stop`,{method:"POST"}); $("stop").disabled=true;setStatus("等待安全停止", "running");});
$("force-stop").addEventListener("click", async()=>{if(!confirm("强行停止当前会话？正在执行的 Shell 工具进程也会被立即终止。"))return; $("force-stop").disabled=true; $("stop").disabled=true; setStatus("正在强行停止", "running"); const response=await fetch(`/api/workspaces/${workspaceId}/runs/${sessionId}/force-stop`,{method:"POST"}); if(!response.ok){const message=`${response.status} ${response.statusText}`;trace("强行停止失败",message);appendRunErrorBlock("强行停止失败",message);setStatus("停止失败","error"); setRunning(true); return;} trace("强行停止","已请求终止当前 Agent 及工具进程。");});
$("workspace").addEventListener("change", event=>{const nextWorkspaceId=event.target.value;switchSession(nextWorkspaceId).then(()=>trace("已切换会话", event.target.options[event.target.selectedIndex].text)).catch(error=>trace("会话切换失败",error.message));});
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
$("delete-workspace").addEventListener("click",async()=>{const selected=$("workspace").selectedOptions[0];if(!selected)return;const name=selected.text;if(!confirm(`删除会话“${name}”及其所有数据？此操作不可恢复。`))return;const confirmation=prompt(`请输入会话名称“${name}”以确认删除：`);if(confirmation !== name)return;const response=await fetch(`/api/sessions/${sessionId}`,{method:"DELETE",headers:{"Content-Type":"application/json"},body:JSON.stringify({confirmation})});const payload=await response.json();if(response.status===404){await loadWorkspaces();await loadHistory();await loadPlan();await loadGraph();trace("会话已不存在",`${name} 已被移除，已切换到有效会话。`);return;}if(!response.ok){alert(payload.detail||"无法删除会话");return;}if(payload.status==="stopping"){trace("正在停止并删除会话",payload.message);return;}await loadWorkspaces();await loadHistory();await loadPlan();await loadGraph();trace("会话已删除",name);});
$("connector").addEventListener("change", event=>{connectorId=event.target.value;localStorage.llmfetcherConnector=connectorId;loadConnectors(connectorId).then(persistSettings);});
$("new-connector").addEventListener("click", openConnectorDialog);
$("cancel-new-connector").addEventListener("click", ()=>$("new-connector-dialog").close());
$("new-connector-form").addEventListener("submit", async event=>{event.preventDefault(); const input=$("new-connector-name"); const name=input.value.trim(); if(!name){input.focus();return;} $("new-connector-dialog").close(); try{await createConnector(name);}catch(error){trace("保存连接器失败",error.message);connectorFeedback("保存失败","error");alert(`无法保存连接器：${error.message}`);}});
$("save-connector").addEventListener("click", async()=>{try{await saveSelectedConnector();}catch(error){trace("更新连接器失败",error.message);connectorFeedback("保存失败","error");alert(`无法保存连接器：${error.message}`);}});
$("delete-connector").addEventListener("click", async()=>{if(!connectorId||!confirm("删除这个连接及其保存的密钥？"))return;const response=await fetch(`/api/connectors/${connectorId}`,{method:"DELETE"});if(!response.ok){alert("无法删除连接");return;}connectorId="";localStorage.llmfetcherConnector="";await loadConnectors();trace("已删除连接");});
$("refresh-plan").addEventListener("click",()=>loadPlan().catch(error=>trace("任务规划加载失败",error.message)));
$("refresh-graph").addEventListener("click",()=>loadInspectorAgents().catch(error=>trace("执行图加载失败",error.message)));
$("refresh-trace").addEventListener("click",()=>loadTrace(true).catch(error=>trace("Trace 加载失败",error.message)));
$("load-more-trace").addEventListener("click",()=>loadTrace(false).catch(error=>trace("Trace 加载失败",error.message)));
$("refresh-usage").addEventListener("click",()=>loadUsage().catch(error=>trace("用量加载失败",error.message)));
$("task-plan").addEventListener("change",event=>{if(event.target.matches(".task-state"))updatePlanStatus(event.target.dataset.taskId,event.target.value).catch(error=>trace("任务更新失败",error.message));});
if(location.protocol === "file:") trace("服务未启动", "请通过 llmfetcher web 启动控制台，而不是直接打开 HTML 文件。");
async function loadProviders() { try { const {providers}=await apiJson("/api/providers"); const select=$("provider"), chosen=select.value; select.innerHTML=providers.map(x=>`<option value="${escapeHtml(x)}">${escapeHtml(x)}</option>`).join(""); select.value=providers.includes(chosen)?chosen:providers[0]; } catch {} }
async function initializeConsole() { initInspectorTabs(); bindSettingsPersistence(); await loadProviders(); await loadWorkspaces(); await loadConnectors(); restoreSettings(); updateModelSummary(); await Promise.all([loadPlan(),loadGraph(),loadTrace(true)]); await rehydrateSelectedView({reloadAgents:true}); await loadInspectorAgents(); }
initializeConsole().catch(error=>trace("工作空间/会话加载失败", error.message));
