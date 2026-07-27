/**
 * Chat message rendering and Composer form management.
 */

import { $, escapeHtml, copyResult } from "./utils.js";
import { getState, setState } from "./state.js";
import { apiJson, apiPost } from "./api.js";
import { getConfig } from "./settings.js";
import { connectRun } from "./events.js";

/* ---- rendering ---- */

export function removeWelcome() {
  $("chat").querySelector(".welcome")?.remove();
}

export function appendMessage(
  role,
  content,
  reasoning = "",
  contentHtml = "",
  reasoningHtml = "",
  tools = []
) {
  removeWelcome();
  const el = document.createElement("article");
  el.className = `message ${role}`;

  const body = contentHtml || escapeHtml(content);
  const bodyClass = contentHtml ? "markdown" : "plain-text";
  const thought = reasoningHtml || escapeHtml(reasoning);
  const copy =
    role === "assistant" && content
      ? `<button class="copy-result" type="button">复制结果</button>`
      : "";
  const bubble = content
    ? `<div class="bubble ${bodyClass}">${body}</div>`
    : "";

  el.innerHTML = `
    <div class="message-meta">
      <div class="role">${role === "user" ? "你" : "Agent"}</div>
      ${copy}
    </div>
    ${bubble}
    ${reasoning ? `<details class="reasoning"><summary>思考过程</summary><div class="markdown">${thought}</div></details>` : ""}
    ${renderTools(tools)}
  `;

  el.querySelector(".copy-result")?.addEventListener("click", () =>
    copyResult(content, el.querySelector(".copy-result"))
  );

  $("chat").append(el);
  $("chat").scrollTop = $("chat").scrollHeight;
}

function renderTools(tools = []) {
  if (!tools.length) return "";
  const calls = tools
    .map(
      (t) => `
      <article class="tool-call">
        <strong>${escapeHtml(t.name)}</strong>
        <p>参数</p>
        <pre>${escapeHtml(JSON.stringify(t.arguments, null, 2))}</pre>
        <p>结果</p>
        <pre>${escapeHtml(t.result || "(无返回内容)")}</pre>
      </article>`
    )
    .join("");
  return `<details class="tool-calls"><summary>工具调用 · ${tools.length}</summary>${calls}</details>`;
}

/* ---- history ---- */

export async function loadHistory() {
  const sessionId = await _resolveSessionId();
  const { messages } = await apiJson(`/api/sessions/${sessionId}/messages`);

  $("chat").innerHTML = "";
  for (const msg of messages) {
    appendMessage(
      msg.role,
      msg.content,
      msg.reasoning,
      msg.content_html,
      msg.reasoning_html,
      msg.tools
    );
  }
  if (!messages.length) {
    $("chat").innerHTML = `<div class="welcome"><div class="welcome-orbit">✦</div><h2>开始一个新对话</h2><p>配置模型后，把任务交给你的 Agent。<br />执行过程、计划和协作关系会实时显示。</p></div>`;
  }
}

/* ---- run ---- */

export async function startRun(message) {
  setState({ running: true, statusText: "正在执行", statusClass: "running" });
  appendMessage("user", message);

  const sessionId = await _resolveSessionId();
  const ws = await _resolveWorkspaceId();
  const config = getConfig();

  const payload = await apiPost("/api/runs", {
    session_id: sessionId,
    workspace_id: ws,
    message,
    config,
  });

  connectRun(ws, payload.run_id, {
    onEvent: handleEvent,
    onDone: finishRun,
  });
}

/* ---- event handling ---- */

let _eventHandlers = null;

export function setEventHandlers(handlers) {
  _eventHandlers = handlers;
}

export function handleEvent(event) {
  if (event.event === "lifecycle") {
    const title = `${event.agent ? `[${event.agent}] ` : ""}${event.type.replace("agent:", "").replaceAll("_", " ")}`;
    const isTool = event.type.includes("tool");
    _eventHandlers?.onTrace?.(title, event.message, event.data, isTool);
    if (event.type === "agent:complete") _eventHandlers?.onMetrics?.(event.data);
    if (event.source === "graph" || event.type.includes("task:"))
      _eventHandlers?.onGraphChange?.();
    return;
  }

  if (event.event === "result") {
    appendMessage(
      "assistant",
      event.content,
      event.reasoning,
      event.content_html,
      event.reasoning_html
    );
    _eventHandlers?.onMetrics?.(event);
    _eventHandlers?.onPlanChange?.();
    _eventHandlers?.onGraphChange?.();
    _eventHandlers?.onTrace?.(
      "完成",
      `${event.provider} · ${event.model}`,
      event.usage
    );
    return;
  }

  if (event.event === "error") {
    _eventHandlers?.onTrace?.("运行失败", event.message);
    setState({ statusText: "运行失败", statusClass: "error" });
    return;
  }

  if (event.event === "stopped")
    _eventHandlers?.onTrace?.("已停止", event.message);

  if (event.event === "done") finishRun();
}

export function finishRun() {
  _eventHandlers?.onFinish?.();
  setState({ running: false });
  const currentClass = getState("statusClass");
  if (currentClass !== "error") setState({ statusText: "准备就绪", statusClass: "idle" });
}

function _resolveSessionId() {
  return getState("sessionId") || "default";
}

function _resolveWorkspaceId() {
  return getState("workspaceId") || "default";
}

/* ---- composer ---- */

export function initComposer(formEl) {
  const textarea = formEl.querySelector("textarea");

  formEl.addEventListener("submit", (event) => {
    event.preventDefault();
    const message = textarea.value.trim();
    if (!message) return;
    textarea.value = "";
    startRun(message);
  });

  textarea.addEventListener("keydown", (event) => {
    if (
      event.key !== "Enter" ||
      event.shiftKey ||
      event.altKey ||
      event.isComposing
    )
      return;
    event.preventDefault();
    formEl.requestSubmit();
  });

  textarea.addEventListener("input", () => {
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 170)}px`;
  });
}
