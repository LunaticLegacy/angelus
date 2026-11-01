/** Generic file attachments that are registered when the message is sent. */
export function createFileComposer({ picker, button, previews, feedback, isRunning }) {
  let files = [];
  function render() {
    const existing = previews.querySelectorAll(".composer-file"); existing.forEach((node) => node.remove());
    files.forEach((file) => { const chip = document.createElement("span"); chip.className = "composer-file"; chip.textContent = `${file.name} (${Math.ceil(file.size / 1024)} KB)`; const remove = document.createElement("button"); remove.type = "button"; remove.textContent = "×"; remove.addEventListener("click", () => { files = files.filter((item) => item !== file); render(); }); chip.append(remove); previews.append(chip); });
    previews.hidden = !previews.querySelector(".composer-image") && !files.length;
    if (feedback && !feedback.textContent) feedback.hidden = !files.length;
  }
  function addFiles(items) {
    if (isRunning()) { feedback.textContent = "运行中请等待任务结束后发送附件。"; feedback.hidden = false; return; }
    files = [...files, ...Array.from(items).filter((file) => file.size > 0 && file.size <= 20 * 1024 * 1024)];
    render();
  }
  button.addEventListener("click", () => picker.click());
  picker.addEventListener("change", () => { addFiles(picker.files); picker.value = ""; });
  return { addFiles, beginSend() { return files.slice(); }, finishSend(sent) { if (sent) files = []; render(); }, get files() { return files; } };
}
