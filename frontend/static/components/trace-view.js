import { $, escapeHtml } from "./dom.js";

/**
 * Create the expandable event Trace view.
 *
 * Returns:
 *   Functions that classify event records and mutate only `#trace`.
 */
export function createTraceView() {
  function kindFor(event) {
    const type = String(event?.type || event?.event || "event");
    if (event?.event === "error") return "error";
    if (event?.event === "result") return "result";
    if (event?.event === "stopped") return "stopped";
    return type.includes("tool") ? "tool" : "status";
  }

  function formatTime(timestamp) {
    if (!timestamp) return "";
    const date = new Date(timestamp);
    return Number.isNaN(date.getTime()) ? "" : date.toLocaleTimeString("zh-CN", {
      hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
  }

  function build(title, message = "", data = null, kind = "status", meta = {}) {
    const element = document.createElement("article");
    element.className = `trace-event kind-${kind || "status"}`;
    const labels = { status: "状态", tool: "工具", result: "结果", error: "错误", stopped: "已停止" };
    const detail = data ? `<pre>${escapeHtml(JSON.stringify(data, null, 2))}</pre>` : "";
    const agent = meta.agent ? `<span class="trace-agent">${escapeHtml(meta.agent)}</span>` : "";
    const time = meta.time ? `<time class="trace-time">${escapeHtml(meta.time)}</time>` : "";
    element.innerHTML = `<button class="trace-toggle" type="button" aria-expanded="false"><span class="trace-summary"><span class="trace-title"><strong>${escapeHtml(title)}</strong>${agent}</span><small class="trace-label">${labels[kind] || "状态"}</small></span>${time}<span class="trace-chevron">⌄</span></button><div class="trace-details"><p>${escapeHtml(message)}</p>${detail}</div>`;
    element.querySelector(".trace-toggle").addEventListener("click", () => {
      const expanded = element.classList.toggle("expanded");
      element.querySelector(".trace-toggle").setAttribute("aria-expanded", String(expanded));
    });
    return element;
  }

  function append(title, message = "", data = null, kind = "") {
    const target = $("trace");
    target.querySelector(".empty")?.remove();
    target.prepend(build(title, message, data, kind));
  }

  function appendEvent(event, position = "prepend") {
    const lifecycle = event.event === "lifecycle";
    const type = String(event.type || event.event || "event");
    const title = lifecycle ? type.replace("agent:", "").replaceAll("_", " ") : type;
    const node = build(title, event.message || "", event.data || event.usage || null,
      kindFor(event), { time: formatTime(event.timestamp), agent: lifecycle ? event.agent : "" });
    const target = $("trace");
    target.querySelector(".empty")?.remove();
    target[position](node);
  }

  return { append, appendEvent, build, formatTime, kindFor };
}
