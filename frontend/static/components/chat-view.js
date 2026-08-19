import { $, escapeHtml } from "./dom.js";

/**
 * Create the transcript view for the Workbench chat panel.
 *
 * Args:
 *   getAgentLabel: Returns the currently selected Agent label for live messages.
 *
 * Returns:
 *   DOM rendering operations. They mutate only `#chat`; persistent state remains
 *   owned by the Workbench controller.
 */
export function createChatView({ getAgentLabel }) {
  function removeWelcome() {
    $("chat").querySelector(".welcome")?.remove();
  }

  async function copyResult(text, button) {
    try {
      await navigator.clipboard.writeText(text);
      button.textContent = "已复制";
      setTimeout(() => { button.textContent = "复制结果"; }, 1200);
    } catch {
      button.textContent = "复制失败";
    }
  }

  function renderTools(tools = []) {
    if (!tools.length) return "";
    const calls = tools.map((tool) => `
      <article class="tool-call"><strong>${escapeHtml(tool.name)}</strong><p>参数</p>
      <pre>${escapeHtml(JSON.stringify(tool.arguments, null, 2))}</pre><p>结果</p>
      <pre>${escapeHtml(tool.result || "(无返回内容)")}</pre></article>`).join("");
    return `<details class="tool-calls"><summary>工具调用 · ${tools.length}</summary>${calls}</details>`;
  }

  /** Build one transcript card without inserting it into the document. */
  function buildMessage(message, agentName = "") {
    const { role, content, reasoning = "", content_html: contentHtml = "",
      reasoning_html: reasoningHtml = "", tools = [] } = message;
    if (role === "steer") return buildSteer(content);

    const element = document.createElement("article");
    element.className = `message ${role}`;
    const body = contentHtml || escapeHtml(content);
    const thought = reasoningHtml || escapeHtml(reasoning);
    const isUser = role === "user";
    const speaker = isUser ? "你" : (agentName || getAgentLabel() || "Coordinator");
    const copy = role === "assistant" && content
      ? '<button class="copy-result" type="button">复制结果</button>' : "";

    element.innerHTML = `<div class="message-meta"><div class="role role-${isUser ? "user" : "agent"}"><i></i><span>${escapeHtml(speaker)}</span></div><small>${isUser ? "用户输入" : "Agent 回复"}</small>${copy}</div>${content ? `<div class="bubble ${contentHtml ? "markdown" : "plain-text"}">${body}</div>` : ""}${reasoning ? `<details class="reasoning"><summary>思考过程</summary><div class="markdown">${thought}</div></details>` : ""}${renderTools(tools)}`;
    element.querySelector(".copy-result")?.addEventListener("click", () =>
      copyResult(content, element.querySelector(".copy-result")));
    return element;
  }

  function buildSteer(text) {
    const element = document.createElement("article");
    element.className = "message steer";
    element.innerHTML = `<div class="message-meta"><div class="role role-steer"><i></i><span>调整指令</span></div><small>已应用</small></div><div class="bubble plain-text">${escapeHtml(text)}</div>`;
    return element;
  }

  function append(message, agentName = "") {
    removeWelcome();
    const chat = $("chat");
    chat.append(buildMessage(message, agentName));
    chat.scrollTop = chat.scrollHeight;
  }

  function appendError(title, message, rawContent = "") {
    /** Display a user-visible failure and, when supplied, its raw model reply. */
    removeWelcome();
    const element = document.createElement("article");
    element.className = "run-error";
    const raw = rawContent
      ? `<details class="run-error-raw"><summary>查看 Agent 原始返回</summary><pre>${escapeHtml(rawContent)}</pre></details>`
      : "";
    element.innerHTML = `<strong>⚠ ${escapeHtml(title)}</strong><p>${escapeHtml(message || "未提供错误详情。")}</p>${raw}`;
    $("chat").append(element);
    $("chat").scrollTop = $("chat").scrollHeight;
  }

  function render(messages, assistantLabel = "coordinator") {
    const chat = $("chat");
    chat.innerHTML = "";
    if (!messages.length) {
      chat.innerHTML = '<div class="welcome"><div class="welcome-symbol">✦</div><h2>等待 Agent 回复</h2><p>用户输入和 Agent 回复会按时间顺序显示在这里。</p></div>';
      return;
    }
    const fragment = document.createDocumentFragment();
    for (const message of messages) {
      fragment.append(buildMessage(message, message.role === "assistant" ? assistantLabel : ""));
    }
    chat.append(fragment);
    chat.scrollTop = chat.scrollHeight;
  }

  return { append, appendError, buildMessage, removeWelcome, render };
}
