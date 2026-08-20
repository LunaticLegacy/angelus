/**
 * Application entry point.
 *
 * Imports every module and wires them together: event listeners, state
 * subscriptions, and the initialisation sequence.
 */

import { $ } from "./utils.js";
import { getState, setState, subscribe } from "./state.js";
import { apiJson, apiPost } from "./api.js";
import { initPlugins } from "./plugins.js";
import { disconnect, connectRun } from "./events.js";
import {
  persistSettings,
  restoreSettings,
  bindSettingsPersistence,
  updateModelSummary,
  applyConnector,
} from "./settings.js";
import { loadAll as loadSessions, create as createSession, remove as removeSession } from "./sessions.js";
import { loadAll as loadConnectors, create as createConnector, update as updateConnector, remove as removeConnector } from "./connectors.js";
import {
  appendMessage,
  loadHistory,
  setEventHandlers,
  initComposer,
  handleEvent,
  finishRun,
} from "./chat.js";
import { load as loadPlan, bindStatusUpdates } from "./inspector/plan.js";
import { load as loadGraph } from "./inspector/graph.js";
import { append as appendTrace } from "./inspector/trace.js";
import { update as updateMetrics } from "./inspector/metrics.js";
import { initTabs } from "./inspector/index.js";

/* ================================================================
 *  State subscriptions
 * ================================================================ */

subscribe("running", (running) => {
  $("send").disabled = running;
  $("stop").disabled = !running;
  $("force-stop").disabled = !running;
  $("message").disabled = running;
});

subscribe("statusText", (text) => {
  $("status").textContent = text;
});

subscribe("statusClass", (cls) => {
  $("status").className = `status ${cls}`;
});

/* ================================================================
 *  Event handlers passed to chat.js
 * ================================================================ */

setEventHandlers({
  onTrace(title, message, data, kind) {
    appendTrace(title, message, data, kind ? "tool" : "");
  },
  onMetrics(data) {
    updateMetrics(data);
  },
  onGraphChange() {
    loadGraph().catch((error) =>
      appendTrace("执行图加载失败", error.message)
    );
  },
  onPlanChange() {
    loadPlan().catch((error) =>
      appendTrace("任务规划加载失败", error.message)
    );
  },
  onFinish() {
    disconnect();
  },
});

/* ================================================================
 *  Session switching
 * ================================================================ */

async function switchSession(selected) {
  persistSettings();
  disconnect();

  await loadSessions(selected);
  await _reloadConnectorsKeepId();
  restoreSettings();
  updateModelSummary();

  await Promise.all([loadHistory(), loadPlan(), loadGraph()]);
  await _restoreRunState();
}

async function _reloadConnectorsKeepId() {
  const currentId = getState("connectorId");
  const { connector } = await loadConnectors(currentId);
  if (connector) applyConnector(connector);
}

async function _restoreRunState() {
  try {
    const ws = getState("workspaceId");
    const sid = getState("sessionId");
    const state = await apiJson(
      `/api/workspaces/${ws}/runs/${sid}/status`
    );
    if (state.active && state.run_id) {
      setState({ running: true, statusText: "正在执行", statusClass: "running" });
      connectRun(ws, state.run_id, {
        onEvent: handleEvent,
        onDone: finishRun,
      });
    } else if (state.status === "error") {
      setState({ statusText: "上次运行失败", statusClass: "error" });
    }
  } catch (error) {
    appendTrace("运行状态加载失败", error.message);
  }
}

/* ================================================================
 *  Model / provider summary live updates
 * ================================================================ */

$("model").addEventListener("input", updateModelSummary);
$("provider").addEventListener("change", updateModelSummary);
$("max-tokens").addEventListener("input", updateModelSummary);
$("temperature").addEventListener("input", updateModelSummary);

/* ================================================================
 *  Composer
 * ================================================================ */

initComposer($("composer"));

/* ================================================================
 *  Stop / Force-stop buttons
 * ================================================================ */

$("stop").addEventListener("click", async () => {
  const ws = getState("workspaceId");
  const sid = getState("sessionId");
  await apiPost(`/api/workspaces/${ws}/runs/${sid}/stop`);
  $("stop").disabled = true;
  setState({ statusText: "等待安全停止", statusClass: "running" });
});

$("force-stop").addEventListener("click", async () => {
  if (
    !confirm(
      "强行停止当前会话？正在执行的 Shell 工具进程也会被立即终止。"
    )
  )
    return;
  $("force-stop").disabled = true;
  $("stop").disabled = true;
  setState({ statusText: "正在强行停止", statusClass: "running" });

  const ws = getState("workspaceId");
  const sid = getState("sessionId");
  const response = await fetch(
    `/api/workspaces/${ws}/runs/${sid}/force-stop`,
    { method: "POST" }
  );

  if (!response.ok) {
    appendTrace("强行停止失败", `${response.status}`);
    setState({ statusText: "停止失败", statusClass: "error" });
    setState({ running: true });
    return;
  }
  appendTrace("强行停止", "已请求终止当前 Agent 及工具进程。");
});

/* ================================================================
 *  Session selector & CRUD
 * ================================================================ */

$("workspace").addEventListener("change", (event) => {
  switchSession(event.target.value).catch((error) =>
    appendTrace("会话切换失败", error.message)
  );
});

$("new-workspace").addEventListener("click", async () => {
  const name = window.prompt("会话名称");
  if (!name?.trim()) return;

  try {
    const session = await createSession(name.trim());
    await switchSession(session.id);
    appendTrace("已创建并切换会话", session.name);
  } catch (error) {
    alert(error.message || "无法创建会话");
  }
});

$("delete-workspace").addEventListener("click", async () => {
  const select = $("workspace");
  const selected = select.options[select.selectedIndex];
  if (!selected) return;
  const name = selected.text;

  if (!confirm(`删除会话"${name}"及其所有数据？此操作不可恢复。`)) return;
  const confirmation = window.prompt(
    `请输入会话名称"${name}"以确认删除：`
  );
  if (confirmation !== name) return;

  const ws = getState("workspaceId");
  try {
    const payload = await removeSession(ws, confirmation);
    if (payload.status === "stopping") {
      appendTrace("正在停止并删除会话", payload.message);
      return;
    }
    await switchSession();
  } catch (error) {
    if (error.message?.includes("404")) {
      /* session already gone — reload */
      await switchSession();
      appendTrace("会话已不存在", `${name} 已被移除，已切换到有效会话。`);
      return;
    }
    alert(error.message || "无法删除会话");
  }
});

/* ================================================================
 *  Connector selector & CRUD
 * ================================================================ */

$("connector").addEventListener("change", async (event) => {
  const id = event.target.value;
  setState({ connectorId: id });
  localStorage.llmfetcherConnector = id;
  const { connector } = await loadConnectors(id);
  if (connector) applyConnector(connector);
  persistSettings();
  updateModelSummary();
});

$("new-connector").addEventListener("click", async () => {
  const name = window.prompt("连接名称");
  if (!name?.trim()) return;
  try {
    const connector = await createConnector(name.trim());
    await loadConnectors(connector.id);
    appendTrace("已保存连接", connector.name);
  } catch (error) {
    alert(error.message || "无法保存连接");
  }
});

$("save-connector").addEventListener("click", async () => {
  const connectorId = getState("connectorId");
  if (!connectorId) {
    /* forward to "new" flow */
    $("new-connector").click();
    return;
  }
  const select = $("connector");
  const name = select.options[select.selectedIndex].text;
  try {
    await updateConnector(connectorId, name);
    appendTrace("已更新连接", name);
  } catch {
    alert("无法更新连接");
  }
});

$("delete-connector").addEventListener("click", async () => {
  const connectorId = getState("connectorId");
  if (!connectorId || !confirm("删除这个连接及其保存的密钥？")) return;
  try {
    await removeConnector(connectorId);
    setState({ connectorId: "" });
    localStorage.llmfetcherConnector = "";
    await loadConnectors("");
    appendTrace("已删除连接");
  } catch {
    alert("无法删除连接");
  }
});

/* ================================================================
 *  Inspector panels
 * ================================================================ */

$("refresh-plan").addEventListener("click", () =>
  loadPlan().catch((error) => appendTrace("任务规划加载失败", error.message))
);

$("refresh-graph").addEventListener("click", () =>
  loadGraph().catch((error) => appendTrace("执行图加载失败", error.message))
);

bindStatusUpdates();
initTabs();

/* ================================================================
 *  Initialisation
 * ================================================================ */

if (location.protocol === "file:") {
  appendTrace(
    "服务未启动",
    "请通过 llmfetcher web 启动控制台，而不是直接打开 HTML 文件。"
  );
}

async function initialize() {
  bindSettingsPersistence();
  await initPlugins(); // S8 — plugin bridge & asset loading (non-fatal)
  await _loadProviders();

  await loadSessions();
  await _reloadConnectorsKeepId();
  restoreSettings();
  updateModelSummary();

  await Promise.all([loadHistory(), loadPlan(), loadGraph()]);
  await _restoreRunState();
}

async function _loadProviders() {
  try {
    const { providers } = await apiJson("/api/providers");
    const select = $("provider");
    const chosen = select.value;
    select.innerHTML = providers
      .map((x) => `<option value="${x}">${x}</option>`)
      .join("");
    select.value = providers.includes(chosen) ? chosen : providers[0];
  } catch {
    /* non-critical — provider list can be manually entered */
  }
}

initialize().catch((error) =>
  appendTrace("工作空间/会话加载失败", error.message)
);
