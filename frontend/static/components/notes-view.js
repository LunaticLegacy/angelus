import { request } from "../runtime/backend-bridge.js";
import { escapeHtml } from "./dom.js";
import { renderMarkdownInto } from "./markdown-renderer.js";

async function jsonRequest(url, options = {}) {
  const response = await request(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) { const error = new Error(typeof payload?.detail === "string" ? payload.detail : `${response.status} ${response.statusText}`); error.status = response.status; throw error; }
  return payload;
}
const draft = (scope) => ({ note_id: "", scope, title: "", content: "", tags: [], status: "active", revision: 0 });
const formatDate = (value) => { const date = new Date(Number(value || 0) * 1000); return Number.isNaN(date.getTime()) ? "" : date.toLocaleDateString(undefined, { month: "short", day: "numeric" }); };

/** Session/Project note browser. Editing is deliberately handled by a modal. */
export function createNotesView(root) {
  if (!root) return { setSession() {}, refresh() {} };
  let sessionId = ""; let scope = "session"; let query = ""; let notes = []; let selected = null; let loading = false;
  const dialog = document.getElementById("notes-edit-dialog");
  const form = document.getElementById("notes-edit-form"); const title = document.getElementById("notes-edit-title-input"); const editor = document.getElementById("notes-edit-content"); const tags = document.getElementById("notes-edit-tags"); const preview = document.querySelector("[data-notes-pane=preview]"); const feedback = document.getElementById("notes-edit-feedback"); const count = document.getElementById("notes-edit-count");
  root.innerHTML = `<div class="notes-heading"><div><p class="eyebrow">DURABLE NOTES</p><h3>笔记</h3></div><button type="button" class="notes-new" title="新建笔记">＋ 新建</button></div><div class="notes-toolbar"><div class="notes-scope-tabs" role="tablist" aria-label="笔记范围"><button type="button" class="notes-scope-tab active" data-scope="session" role="tab">Session</button><button type="button" class="notes-scope-tab" data-scope="project" role="tab">Project</button></div><label class="notes-search-wrap"><span aria-hidden="true">⌕</span><input class="notes-search" type="search" placeholder="搜索标题、内容或标签" aria-label="搜索笔记" /></label></div><div class="notes-list-wrap"><div class="notes-list" role="list"></div></div><p class="notes-error" role="alert" hidden></p>`;
  const list = root.querySelector(".notes-list"); const error = root.querySelector(".notes-error");
  const setError = (message = "") => { error.textContent = message; error.hidden = !message; };
  const url = (suffix = "") => `/api/sessions/${encodeURIComponent(sessionId)}/notes${suffix}`;
  const updateCount = () => { count.textContent = `${editor.value.length.toLocaleString()} 字`; };
  function renderList() {
    if (!sessionId) { list.innerHTML = `<div class="notes-empty"><strong>尚未选择会话</strong><small>选择会话后即可管理笔记</small></div>`; return; }
    if (!notes.length) { list.innerHTML = `<div class="notes-empty"><span class="notes-empty-glyph">✦</span><strong>${query ? "没有匹配的笔记" : "还没有笔记"}</strong><small>${query ? "换个关键词试试" : "点击右上角新建一条"}</small></div>`; return; }
    list.innerHTML = notes.map((note) => `<button type="button" class="notes-item ${selected?.note_id === note.note_id ? "selected" : ""}" data-note-id="${escapeHtml(note.note_id)}" role="listitem"><span class="notes-item-top"><strong>${escapeHtml(note.title)}</strong><time>${escapeHtml(formatDate(note.updated_at))}</time></span><span class="notes-item-preview">${escapeHtml(note.content.slice(0, 120))}</span>${note.tags?.length ? `<span class="notes-item-tags">${note.tags.slice(0, 3).map((tag) => `<em>${escapeHtml(tag)}</em>`).join("")}</span>` : ""}</button>`).join("");
    list.querySelectorAll("[data-note-id]").forEach((button) => button.addEventListener("click", () => openEditor(notes.find((note) => note.note_id === button.dataset.noteId))));
  }
  function updatePreview() { if (!preview) return; const heading = title.value.trim() ? `# ${title.value.trim()}\n\n` : ""; renderMarkdownInto(preview, `${heading}${editor.value || "_还没有内容。_"}`); }
  function openEditor(note = draft(scope)) { selected = note; title.value = note.title; editor.value = note.content; tags.value = note.tags.join(", "); feedback.textContent = note.note_id ? `版本 ${note.revision}` : "新建笔记"; updateCount(); updatePreview(); root.ownerDocument.querySelectorAll("[data-notes-tab]").forEach((item) => { const active = item.dataset.notesTab === "write"; item.classList.toggle("active", active); item.setAttribute("aria-selected", String(active)); }); root.ownerDocument.querySelectorAll("[data-notes-pane]").forEach((pane) => { pane.hidden = pane.dataset.notesPane !== "write"; pane.classList.toggle("active", pane.dataset.notesPane === "write"); }); dialog?.showModal(); setTimeout(() => title.focus(), 0); renderList(); }
  function closeEditor() { if (dialog?.open) dialog.close(); }
  async function load() {
    if (!sessionId) { notes = []; selected = null; renderList(); return; }
    loading = true; setError("");
    try { const params = new URLSearchParams({ scope }); if (query.trim()) params.set("query", query.trim()); const payload = await jsonRequest(`${url()}?${params}`); notes = Array.isArray(payload.notes) ? payload.notes : []; if (selected && !notes.some((note) => note.note_id === selected.note_id)) selected = null; renderList(); }
    catch (err) { setError(`笔记加载失败：${err.message}`); } finally { loading = false; }
  }
  async function save(event) {
    event?.preventDefault(); if (!sessionId || !selected || loading) return;
    const titleValue = title.value.trim(); const contentValue = editor.value.trim(); if (!titleValue || !contentValue) { feedback.textContent = "标题和内容都不能为空"; return; }
    loading = true; feedback.textContent = "保存中…";
    const payload = { scope: selected.scope, title: titleValue, content: contentValue, tags: tags.value.split(",").map((item) => item.trim()).filter(Boolean), ...(selected.note_id ? { revision: selected.revision } : {}) };
    try { const saved = selected.note_id ? await jsonRequest(url(`/${encodeURIComponent(selected.scope)}/${encodeURIComponent(selected.note_id)}`), { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }) : await jsonRequest(url(), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }); selected = saved; feedback.textContent = `已保存 · 版本 ${saved.revision}`; await load(); setTimeout(closeEditor, 180); }
    catch (err) { feedback.textContent = err.status === 409 ? "版本冲突，请刷新后再保存" : `保存失败：${err.message}`; } finally { loading = false; }
  }
  async function remove() {
    if (!selected?.note_id || loading || !window.confirm(`删除笔记“${selected.title}”？`)) return;
    loading = true; feedback.textContent = "删除中…";
    try { await jsonRequest(url(`/${encodeURIComponent(selected.scope)}/${encodeURIComponent(selected.note_id)}?revision=${selected.revision}`), { method: "DELETE" }); selected = null; closeEditor(); await load(); }
    catch (err) { feedback.textContent = err.status === 409 ? "笔记已被修改，请刷新后再删除" : `删除失败：${err.message}`; } finally { loading = false; }
  }
  root.querySelector(".notes-new").addEventListener("click", () => openEditor());
  root.querySelectorAll(".notes-scope-tab").forEach((button) => button.addEventListener("click", () => { if (scope === button.dataset.scope) return; scope = button.dataset.scope; selected = null; root.querySelectorAll(".notes-scope-tab").forEach((tab) => tab.classList.toggle("active", tab === button)); load(); }));
  root.querySelector(".notes-search").addEventListener("input", (event) => { query = event.target.value; clearTimeout(root._notesSearchTimer); root._notesSearchTimer = setTimeout(load, 220); });
  form?.addEventListener("submit", save); document.getElementById("close-notes-edit")?.addEventListener("click", closeEditor); document.getElementById("notes-edit-delete")?.addEventListener("click", remove); [title, editor].forEach((field) => field?.addEventListener("input", () => { updateCount(); updatePreview(); }));
  root.ownerDocument.querySelectorAll("[data-notes-tab]").forEach((tab) => tab.addEventListener("click", () => { const mode = tab.dataset.notesTab; root.ownerDocument.querySelectorAll("[data-notes-tab]").forEach((item) => { const active = item === tab; item.classList.toggle("active", active); item.setAttribute("aria-selected", String(active)); }); root.ownerDocument.querySelectorAll("[data-notes-pane]").forEach((pane) => { pane.hidden = pane.dataset.notesPane !== mode; pane.classList.toggle("active", pane.dataset.notesPane === mode); }); if (mode === "preview") updatePreview(); }));
  dialog?.addEventListener("click", (event) => { if (event.target === dialog) closeEditor(); });
  return { setSession(nextSessionId) { sessionId = nextSessionId || ""; selected = null; load(); }, refresh() { load(); } };
}
