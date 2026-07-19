const $ = (id) => document.getElementById(id);
const sessionId = localStorage.llmfetcherSession || crypto.randomUUID().replaceAll("-", "");
localStorage.llmfetcherSession = sessionId;
let workspaceId = localStorage.llmfetcherWorkspace || "default";
let source = null;

const value = (id) => $(id).value.trim();
const config = () => ({
  provider: value("provider"), model: value("model"), api_key: $("api-key").value,
  api_url: value("api-url"), system_prompt: $("system-prompt").value,
  temperature: Number($("temperature").value), max_tokens: Number($("max-tokens").value),
  max_rounds: Number($("max-rounds").value), enable_shell: $("enable-shell").checked,
});
function setStatus(text, state="idle") { const el=$("status"); el.textContent=text; el.className=`status ${state}`; }
function escapeHtml(text) { const node=document.createElement("div"); node.textContent=text ?? ""; return node.innerHTML; }
function removeWelcome() { $("chat").querySelector(".welcome")?.remove(); }
function appendMessage(role, content, reasoning="") { removeWelcome(); const el=document.createElement("article"); el.className=`message ${role}`; el.innerHTML=`<div class="role">${role === "user" ? "你" : "Agent"}</div><div class="bubble">${escapeHtml(content)}</div>${reasoning ? `<div class="reasoning">${escapeHtml(reasoning)}</div>` : ""}`; $("chat").append(el); $("chat").scrollTop=$("chat").scrollHeight; }
function trace(title, message="", data=null, kind="") { $("trace").querySelector(".empty")?.remove(); const el=document.createElement("article"); el.className=`trace-event ${kind}`; const detail=data ? `<pre>${escapeHtml(JSON.stringify(data, null, 2))}</pre>` : ""; el.innerHTML=`<h3>${escapeHtml(title)}</h3><p>${escapeHtml(message)}</p>${detail}`; $("trace").prepend(el); }
function metrics(data) { if (!data) return; const b=$("metrics").querySelectorAll("b"); b[0].textContent=data.rounds ?? "—"; b[1].textContent=data.usage?.total ?? data.total ?? "—"; if(data.duration_ms) b[2].textContent=`${(data.duration_ms/1000).toFixed(1)}s`; }
function setRunning(running) { $("send").disabled=running; $("stop").disabled=!running; $("message").disabled=running; }
async function loadWorkspaces(selected=workspaceId) { const response=await fetch("/api/workspaces"); const {workspaces}=await response.json(); const select=$("workspace"); select.innerHTML=workspaces.map(item=>`<option value="${escapeHtml(item.id)}">${escapeHtml(item.name)}</option>`).join(""); workspaceId=workspaces.some(item=>item.id===selected)?selected:workspaces[0].id; select.value=workspaceId; localStorage.llmfetcherWorkspace=workspaceId; }

async function start(message) {
  setRunning(true); setStatus("正在执行", "running"); appendMessage("user", message);
  try {
    const response=await fetch("/api/runs", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({session_id:sessionId, workspace_id:workspaceId, message, config:config()})});
    const payload=await response.json(); if(!response.ok) throw new Error(payload.detail || "无法开始运行");
    source=new EventSource(`/api/workspaces/${workspaceId}/runs/${payload.run_id}/events`);
    source.onmessage=(event)=>handleEvent(JSON.parse(event.data)); source.onerror=()=>{ if(source?.readyState===EventSource.CLOSED) finish(); };
  } catch(error) { trace("请求失败", error.message, null); setStatus("请求失败", "error"); setRunning(false); }
}
function handleEvent(event) {
  if(event.event === "lifecycle") { const title=event.type.replace("agent:", "").replaceAll("_", " "); const tool=event.type.includes("tool"); trace(title, event.message, event.data, tool ? "tool" : ""); if(event.type === "agent:complete") metrics(event.data); return; }
  if(event.event === "result") { appendMessage("assistant", event.content, event.reasoning); metrics(event); trace("完成", `${event.provider} · ${event.model}`, event.usage); return; }
  if(event.event === "error") { trace("运行失败", event.message); setStatus("运行失败", "error"); return; }
  if(event.event === "stopped") trace("已停止", event.message);
  if(event.event === "done") finish();
}
function finish() { source?.close(); source=null; setRunning(false); if(!$("status").classList.contains("error")) setStatus("准备就绪"); }
$("composer").addEventListener("submit", (event)=>{event.preventDefault(); const message=value("message"); if(!message) return; $("message").value=""; start(message);});
$("message").addEventListener("input", ()=>{const el=$("message");el.style.height="auto";el.style.height=`${Math.min(el.scrollHeight,170)}px`;});
$("stop").addEventListener("click", async()=>{await fetch(`/api/workspaces/${workspaceId}/runs/${sessionId}/stop`,{method:"POST"}); $("stop").disabled=true;setStatus("等待安全停止", "running");});
$("workspace").addEventListener("change", event=>{workspaceId=event.target.value;localStorage.llmfetcherWorkspace=workspaceId;trace("已切换工作空间", event.target.options[event.target.selectedIndex].text);});
$("new-workspace").addEventListener("click", async()=>{const name=window.prompt("工作空间名称");if(!name?.trim())return;const response=await fetch("/api/workspaces",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name})});const workspace=await response.json();if(!response.ok){alert(workspace.detail||"无法创建工作空间");return;}await loadWorkspaces(workspace.id);trace("已创建工作空间",workspace.name);});
fetch("/api/providers").then(r=>r.json()).then(({providers})=>{const select=$("provider"), chosen=select.value;select.innerHTML=providers.map(x=>`<option value="${x}">${x}</option>`).join("");select.value=providers.includes(chosen)?chosen:providers[0];}).catch(()=>{});
loadWorkspaces().catch(()=>trace("工作空间加载失败", "请刷新页面后重试"));
