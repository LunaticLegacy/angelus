/**
 * Trace panel — live event stream.
 */

import { $, escapeHtml } from "../utils.js";

export function append(title, message = "", data = null, kind = "") {
  $("trace").querySelector(".empty")?.remove();
  const el = document.createElement("article");
  el.className = `trace-event ${kind}`;
  const detail = data
    ? `<pre>${escapeHtml(JSON.stringify(data, null, 2))}</pre>`
    : "";
  el.innerHTML = `<h3>${escapeHtml(title)}</h3><p>${escapeHtml(message)}</p>${detail}`;
  $("trace").prepend(el);
}
