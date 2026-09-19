/** Session-local drafts and upload lifecycle; image bytes stay out of run JSON. */
export function attachmentImageUrl(sessionId, image) {
  if (!sessionId || !/^[A-Za-z0-9_-]+$/.test(image?.attachment_id || "")) return "";
  // Construct the confined endpoint ourselves; never trust a persisted URL.
  return `/api/sessions/${encodeURIComponent(sessionId)}/attachments/images/${encodeURIComponent(image.attachment_id)}`;
}

export function createImageComposer({ input, picker, button, previews, feedback, dropTarget, upload, isRunning, resize }) {
  const drafts = new Map();
  let activeSession = null;
  const getDraft = id => {
    if (!drafts.has(id)) drafts.set(id, { text: "", images: [], pending: 0, sending: false, error: "" });
    return drafts.get(id);
  };
  function render() {
    const draft = getDraft(activeSession);
    previews.replaceChildren();
    for (const image of draft.images) {
      const card = document.createElement("span"); card.className = "composer-image";
      const thumb = document.createElement("img"); thumb.src = attachmentImageUrl(activeSession, image); thumb.alt = image.filename || "图片";
      const remove = document.createElement("button"); remove.type = "button"; remove.textContent = "×"; remove.setAttribute("aria-label", `移除 ${thumb.alt}`);
      remove.addEventListener("click", () => { draft.images = draft.images.filter(item => item !== image); render(); });
      card.append(thumb, remove); previews.append(card);
    }
    previews.hidden = !draft.images.length;
    feedback.textContent = draft.error || (draft.pending ? `正在上传 ${draft.pending} 张图片…` : draft.sending ? "正在发送…" : "");
    feedback.hidden = !feedback.textContent;
    button.disabled = !activeSession || draft.sending;
  }
  async function addFiles(files) {
    const id = activeSession, draft = getDraft(id);
    if (!id) { draft.error = "请先选择会话。"; render(); return; }
    if (isRunning()) { draft.error = "运行中仅支持文字调整指令，请等待任务结束后发送图片。"; render(); return; }
    if (draft.sending) return;
    draft.error = "";
    await Promise.all(Array.from(files).map(async file => {
      if (!/^image\/(png|jpeg|gif|webp)$/.test(file.type)) { draft.error = "请选择 PNG、JPEG、GIF 或 WebP 图片。"; return; }
      draft.pending += 1; if (activeSession === id) render();
      try {
        const image = await upload(id, file);
        if (!attachmentImageUrl(id, image)) throw new Error("图片附件响应无效");
        draft.images.push(image);
      } catch (error) { draft.error = `上传失败：${error.message}；请重新选择或粘贴图片。`; }
      finally { draft.pending -= 1; if (activeSession === id) render(); }
    }));
    if (activeSession === id) render();
  }
  input.addEventListener("input", () => { getDraft(activeSession).text = input.value; });
  button.addEventListener("click", () => picker.click());
  picker.addEventListener("change", () => { addFiles(picker.files); picker.value = ""; });
  input.addEventListener("paste", event => {
    const files = Array.from(event.clipboardData?.files || []);
    if (files.length) { event.preventDefault(); addFiles(files); }
  });
  dropTarget.addEventListener("dragover", event => { if (Array.from(event.dataTransfer?.types || []).includes("Files")) event.preventDefault(); });
  dropTarget.addEventListener("drop", event => {
    if (event.dataTransfer?.files.length) { event.preventDefault(); addFiles(event.dataTransfer.files); }
  });
  return {
    addFiles,
    setSession(id) {
      if (activeSession === id) return;
      getDraft(activeSession).text = input.value;
      activeSession = id; input.value = getDraft(id).text; resize(); render();
    },
    beginSend() {
      const draft = getDraft(activeSession); draft.text = input.value;
      if (draft.sending) return null;
      if (draft.pending) { draft.error = "请等待图片上传完成后发送。"; render(); return null; }
      if (isRunning() && draft.images.length) { draft.error = "运行中仅支持文字调整指令；图片草稿已保留，请在任务结束后发送。"; render(); return null; }
      if (!draft.text.trim() && !draft.images.length) return null;
      draft.sending = true; draft.error = ""; render();
      return { sessionId: activeSession, message: draft.text, images: [...draft.images] };
    },
    finishSend(snapshot, accepted) {
      const draft = getDraft(snapshot.sessionId); draft.sending = false;
      if (accepted) {
        draft.images = draft.images.filter(image => !snapshot.images.includes(image));
        if (draft.text === snapshot.message) draft.text = "";
        if (activeSession === snapshot.sessionId && input.value === snapshot.message) { input.value = ""; resize(); }
      }
      if (activeSession === snapshot.sessionId) render();
    },
  };
}
