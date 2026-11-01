/**
 * Resilient browser entry for the template workbench.
 *
 * A transient localhost connection failure while resolving one ES module
 * otherwise aborts the whole static module graph. Retry the composition root
 * so a short Uvicorn restart or socket hiccup does not leave a blank shell.
 */
const APP_URL = "/static/app.js?v=context-architecture-15";
const MAX_ATTEMPTS = 4;
const RETRY_DELAY_MS = 350;

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function showBootFailure(error) {
  const message = error instanceof Error ? error.message : String(error);
  console.error("Angelus frontend failed to load", error);
  const status = document.getElementById("status");
  if (status) {
    status.dataset.runtimeText = `前端加载失败：${message}`;
    status.textContent = `前端加载失败：${message}`;
    status.className = "status error";
  }
}

function isModuleLoadFailure(error) {
  const message = error instanceof Error ? error.message : String(error);
  return /fetch|network|load|import|timed out|connection/i.test(message);
}

for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt += 1) {
  try {
    await import(`${APP_URL}&attempt=${attempt}`);
    break;
  } catch (error) {
    if (!isModuleLoadFailure(error) || attempt === MAX_ATTEMPTS) {
      showBootFailure(error);
      break;
    }
    await delay(RETRY_DELAY_MS * attempt);
  }
}
