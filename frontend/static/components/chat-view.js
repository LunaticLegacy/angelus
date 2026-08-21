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

  /**
   * Convert a quoted Python literal into a JSON string without evaluating it.
   *
   * @param {string} source Legacy Python-repr container text.
   * @returns {string|null} Equivalent JSON text, or ``null`` when malformed.
   */
  function legacyPythonContainerToJson(source) {
    let json = "";
    for (let index = 0; index < source.length; index += 1) {
      const current = source[index];
      if (current === "'" || current === '"') {
        const quote = current;
        let value = "";
        let closed = false;
        for (index += 1; index < source.length; index += 1) {
          const next = source[index];
          if (next === quote) { closed = true; break; }
          if (next !== "\\") { value += next; continue; }
          index += 1;
          const escape = source[index];
          if (escape === undefined) return null;
          const simple = { n: "\n", r: "\r", t: "\t", b: "\b", f: "\f", v: "\v" };
          if (Object.hasOwn(simple, escape)) { value += simple[escape]; continue; }
          if (escape === "x" || escape === "u") {
            const width = escape === "x" ? 2 : 4;
            const hex = source.slice(index + 1, index + 1 + width);
            if (!new RegExp(`^[0-9a-fA-F]{${width}}$`).test(hex)) return null;
            value += String.fromCodePoint(Number.parseInt(hex, 16));
            index += width;
            continue;
          }
          value += escape;
        }
        if (!closed) return null;
        json += JSON.stringify(value);
        continue;
      }
      if (source.startsWith("True", index) && !/[A-Za-z0-9_]/.test(source[index - 1] || "") && !/[A-Za-z0-9_]/.test(source[index + 4] || "")) {
        json += "true"; index += 3; continue;
      }
      if (source.startsWith("False", index) && !/[A-Za-z0-9_]/.test(source[index - 1] || "") && !/[A-Za-z0-9_]/.test(source[index + 5] || "")) {
        json += "false"; index += 4; continue;
      }
      if (source.startsWith("None", index) && !/[A-Za-z0-9_]/.test(source[index - 1] || "") && !/[A-Za-z0-9_]/.test(source[index + 4] || "")) {
        json += "null"; index += 3; continue;
      }
      json += current;
    }
    return json;
  }

  /**
   * Decode JSON supplied as an object or as one/more JSON-encoded strings.
   *
   * A tool adapter may serialize its payload before it reaches the event log.
   * Repeatedly unwrapping JSON-looking strings restores quotes, newlines, and
   * Unicode escapes. A constrained non-evaluating fallback also recognizes
   * old Python ``str(dict)`` event values so historical and live cards share
   * the same structured renderer.
   *
   * @param {*} value Tool argument or result payload.
   * @returns {{decoded: *, parsed: boolean}} Decoded JSON and parse status.
   */
  function decodeJson(value) {
    let decoded = value;
    let parsed = false;
    for (let depth = 0; depth < 3 && typeof decoded === "string"; depth += 1) {
      const text = decoded.trim();
      if (!text || !/^(?:\{|\[|\")/.test(text)) break;
      try {
        decoded = JSON.parse(text);
        parsed = true;
      } catch {
        const legacyJson = legacyPythonContainerToJson(text);
        if (!legacyJson) break;
        try {
          decoded = JSON.parse(legacyJson);
          parsed = true;
        } catch {
          break;
        }
      }
    }
    return { decoded, parsed: parsed || (value !== null && typeof value === "object") };
  }

  /**
   * Unwrap only complete JSON-string layers for display.
   *
   * JSON payloads occasionally preserve a nested string such as
   * ``\"line one\\nline two\"``. Parsing that complete string restores its
   * actual newline. This deliberately does not replace arbitrary ``\\n`` text:
   * raw stdout and code snippets may need those two literal characters.
   *
   * @param {*} value JSON scalar value to display.
   * @returns {string} Human-readable scalar text with verified JSON escapes decoded.
   */
  function decodeDisplayString(value) {
    let text = String(value ?? "");
    for (let depth = 0; depth < 3; depth += 1) {
      const candidate = text.trim();
      if (!(candidate.startsWith('"') && candidate.endsWith('"'))) break;
      try {
        const decoded = JSON.parse(candidate);
        if (typeof decoded !== "string") break;
        text = decoded;
      } catch {
        break;
      }
    }
    return text;
  }

  /**
   * Render JSON as a bounded hierarchy instead of a single escaped blob.
   *
   * @param {*} value Parsed JSON value to render.
   * @returns {string} Escaped HTML for a recursive JSON tree.
   */
  function renderJson(value) {
    if (Array.isArray(value)) {
      const children = value.map((item, index) => `<li><span class="json-key">[${index}]</span>${renderJson(item)}</li>`).join("");
      return `<details class="json-node" open><summary>数组 · ${value.length} 项</summary><ul>${children}</ul></details>`;
    }
    if (value && typeof value === "object") {
      const entries = Object.entries(value);
      const children = entries.map(([key, item]) => `<li><span class="json-key">${escapeHtml(key)}</span>${renderJson(item)}</li>`).join("");
      return `<details class="json-node" open><summary>对象 · ${entries.length} 项</summary><ul>${children}</ul></details>`;
    }
    if (value === null) return '<span class="json-value json-null">null</span>';
    if (typeof value === "boolean" || typeof value === "number") return `<span class="json-value">${escapeHtml(String(value))}</span>`;
    return `<span class="json-value json-string">${escapeHtml(decodeDisplayString(value))}</span>`;
  }

  /**
   * Choose the structured JSON view when possible; preserve stdout verbatim otherwise.
   *
   * @param {*} value Tool argument or result payload.
   * @param {string} emptyText Placeholder for an absent payload.
   * @returns {string} Escaped HTML for either JSON or a raw text block.
   */
  function renderToolPayload(value, emptyText) {
    if (value === undefined || value === null || value === "") return `<p class="tool-empty">${escapeHtml(emptyText)}</p>`;
    const { decoded, parsed } = decodeJson(value);
    if (parsed) return `<div class="tool-json">${renderJson(decoded)}</div>`;
    return `<pre class="tool-stdout">${escapeHtml(String(value))}</pre>`;
  }

  function renderTools(tools = []) {
    if (!tools.length) return "";
    const calls = tools.map((tool) => `
      <article class="tool-call"><strong>${escapeHtml(tool.name)}</strong><p>参数</p>
      ${renderToolPayload(tool.arguments, "无参数")}<p>结果</p>
      ${renderToolPayload(tool.result, "无返回内容")}</article>`).join("");
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

    // Reasoning is visible before the formal answer in both live and restored
    // transcript cards, so readers see the model's working context first.
    element.innerHTML = `<div class="message-meta"><div class="role role-${isUser ? "user" : "agent"}"><i></i><span>${escapeHtml(speaker)}</span></div><small>${isUser ? "用户输入" : "Agent 回复"}</small>${copy}</div>${reasoning ? `<section class="reasoning" aria-label="思考过程"><h4>思考过程</h4><div class="markdown">${thought}</div></section>` : ""}${content ? `<div class="bubble ${contentHtml ? "markdown" : "plain-text"}">${body}</div>` : ""}${renderTools(tools)}`;
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

  function beginStream(agentName = "") {
    /** Create one mutable assistant card for provider text/thinking deltas. */
    removeWelcome();
    const element = document.createElement("article");
    const speaker = agentName || getAgentLabel() || "Coordinator";
    element.className = "message assistant streaming";
    element.innerHTML = `<div class="message-meta"><div class="role role-agent"><i></i><span>${escapeHtml(speaker)}</span></div><small>正在生成</small></div><section class="reasoning" aria-label="思考过程" hidden><h4>思考过程</h4><div class="markdown plain-text"></div></section><div class="bubble plain-text"></div>`;
    $("chat").append(element);
    return {
      update(content, reasoning) {
        const reasoningSection = element.querySelector(".reasoning");
        reasoningSection.hidden = !reasoning;
        reasoningSection.querySelector(".markdown").textContent = reasoning;
        element.querySelector(".bubble").textContent = content;
        $("chat").scrollTop = $("chat").scrollHeight;
      },
      remove() { element.remove(); },
    };
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

  return { append, appendError, beginStream, buildMessage, removeWelcome, render };
}
