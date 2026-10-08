/** JSON-backed locale service for the desktop frontend. */
const DEFAULT_LOCALE = "en";
const LOCALE_STORAGE_KEY = "angelusLocale";
const LOCALE_FILES = { en: "en", "zh-CN": "zh-CN" };
let locale = DEFAULT_LOCALE;
let fallback = DEFAULT_LOCALE;
let messages = {};
let fallbackMessages = {};
const listeners = new Set();

function normalizeLocale(value) {
  if (!value) return DEFAULT_LOCALE;
  if (value.toLowerCase().startsWith("zh")) return "zh-CN";
  return "en";
}

async function loadMessages(name) {
  const file = LOCALE_FILES[name] || LOCALE_FILES[DEFAULT_LOCALE];
  const response = await fetch(`/static/locales/${encodeURIComponent(file)}.json`);
  if (!response.ok) throw new Error(`Unable to load locale ${name}`);
  return response.json();
}

export function t(key, variables = {}) {
  const value = messages[key] ?? fallbackMessages[key] ?? key;
  return String(value).replace(/\{(\w+)\}/g, (_, name) => String(variables[name] ?? `{${name}}`));
}

export function currentLocale() { return locale; }

const runtimeAliases = {
  "准备就绪": "status.ready",
  "正在执行": "runtime.running",
  "运行失败": "runtime.failed",
  "已完成": "runtime.completed",
  "已停止": "runtime.stopped",
  "正在重试": "runtime.retrying",
  "运行中 — 指令会在安全的轮次边界生效": "runtime.steering",
  "图片上传失败": "runtime.imageUploadFailed",
  "未知错误": "runtime.unknownError"
};

export function translateRuntime(text) {
  const value = String(text ?? "");
  const exact = runtimeAliases[value];
  if (exact) return t(exact);
  if (value.startsWith("正在重试")) return t("runtime.retrying");
  return value;
}

export async function initI18n() {
  let stored = null;
  try { stored = localStorage.getItem(LOCALE_STORAGE_KEY); } catch { /* private mode */ }
  locale = normalizeLocale(stored || navigator.language);
  try { fallbackMessages = await loadMessages(fallback); } catch { fallbackMessages = {}; }
  try { messages = locale === fallback ? fallbackMessages : await loadMessages(locale); }
  catch { locale = fallback; messages = fallbackMessages; }
  applyTranslations();
  bindLocaleToggle();
  return locale;
}

export async function setLocale(next) {
  const normalized = normalizeLocale(next);
  if (normalized === locale && Object.keys(messages).length) return locale;
  messages = normalized === fallback ? fallbackMessages : await loadMessages(normalized);
  locale = normalized;
  try { localStorage.setItem(LOCALE_STORAGE_KEY, locale); } catch { /* private mode */ }
  applyTranslations();
  listeners.forEach((listener) => listener(locale));
  return locale;
}

export function onLocaleChange(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function setText(selector, key) {
  const element = document.querySelector(selector);
  if (element) element.textContent = t(key);
}

function setTexts(selector, keys) {
  document.querySelectorAll(selector).forEach((element, index) => {
    const key = keys[index];
    if (key) element.textContent = t(key);
  });
}

function setAttribute(selector, attribute, key) {
  const element = document.querySelector(selector);
  if (element) element.setAttribute(attribute, t(key));
}

export function applyTranslations() {
  document.documentElement.lang = locale === "zh-CN" ? "zh-CN" : "en";
  document.title = t("app.title");
  document.querySelectorAll("[data-i18n]").forEach((element) => { element.textContent = t(element.dataset.i18n); });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((element) => { element.placeholder = t(element.dataset.i18nPlaceholder); });
  document.querySelectorAll("[data-i18n-title]").forEach((element) => { element.title = t(element.dataset.i18nTitle); });
  document.querySelectorAll("[data-i18n-aria-label]").forEach((element) => { element.setAttribute("aria-label", t(element.dataset.i18nAriaLabel)); });
  const textBindings = {
    ".brand-copy small": "brand.workbench",
    ".side-heading > span": "session.workspaces",
    ".workspace-current strong": "session.current",
    ".title p": "workspace.active",
    ".title h1": "workspace.heading",
    "#status": "status.ready",
    "#chat .welcome h2": "chat.welcome.title",
    "#inspector-plan .section-title h3": "inspector.plan",
    "#inspector-agents .section-title h3": "inspector.agents",
    "#inspector-usage .section-title h3": "inspector.usage",
    "#settings-title": "settings.title",
    "#new-session-title": "dialog.newSession",
    "#new-connector-title": "dialog.newConnector",
    "#mcp-approval-title": "mcp.approval",
    "#context-dialog-title": "context.title",
    "#context-dialog-subtitle": "context.subtitle",
    "#external-agent-hub-dialog h2": "external.title"
  };
  Object.entries(textBindings).forEach(([selector, key]) => {
    if (selector === "#status" && document.querySelector(selector)?.dataset.runtimeText) return;
    setText(selector, key);
  });
  const runtimeStatus = document.querySelector("#status")?.dataset.runtimeText;
  if (runtimeStatus) document.querySelector("#status").textContent = translateRuntime(runtimeStatus);
  const welcome = document.querySelector("#chat .welcome p");
  if (welcome) welcome.innerHTML = t("chat.welcome.body").replace("\n", "<br />");
  const tabs = [["[data-inspector-panel=inspector-plan]", "inspector.plan"], ["[data-inspector-panel=inspector-agents]", "inspector.agents"], ["[data-inspector-panel=inspector-trace]", "inspector.trace"], ["[data-inspector-panel=inspector-usage]", "inspector.usage"]];
  tabs.forEach(([selector, key]) => setText(selector, key));
  setTexts("[data-settings-section]", ["settings.connection", "settings.agent", "settings.permissions", "settings.mcp", "settings.plugins", "settings.language", "settings.future"]);
  setTexts("#settings-dialog .settings-page-heading h3", ["settings.connection", "settings.agent", "settings.permissions", "settings.mcpServers", "settings.plugins", "settings.language", "settings.future"]);
  setTexts("[data-context-dialog-tab]", ["context.graph", "context.prompt", "context.compaction", "context.calls"]);
  setText("#cancel-new-session", "dialog.cancel");
  setText("#choose-session-directory", "dialog.chooseDirectory");
  setText("#new-session-form button[type=submit]", "dialog.create");
  setText("#new-session-form label[for=new-session-name]", "dialog.sessionName");
  setText("#new-session-form label[for=new-session-path]", "dialog.projectDirectory");
  setText("#cancel-new-connector", "dialog.cancel");
  setText("#new-connector-form button[type=submit]", "dialog.save");
  setText("#new-connector-form label[for=new-connector-name]", "dialog.connectorName");
  setText("#save-connector", "dialog.save");
  setText("#reject-mcp-approval", "mcp.reject");
  setText("#mcp-approval-form button[type=submit]", "mcp.allowOnce");
  setText("#mcp-approval-form .toggle-line span", "mcp.remember");
  setAttribute(".activity", "aria-label", "inspector.label");
  setAttribute("#session-filter", "placeholder", "session.filter");
  setAttribute("#message", "placeholder", "composer.placeholder");
  setAttribute("#new-session-name", "placeholder", "dialog.sessionName");
  setAttribute("#new-session-path", "placeholder", "dialog.projectDirectory");
  setAttribute("#new-connector-name", "placeholder", "dialog.connectorName");
  setAttribute("#new-workspace", "title", "session.new");
  setAttribute("#new-workspace", "aria-label", "session.new");
  setAttribute("#delete-workspace", "title", "session.delete");
  setAttribute("#delete-workspace", "aria-label", "session.delete");
  setAttribute("#open-settings", "title", "footer.settings");
  setAttribute("#open-settings", "aria-label", "footer.settings");
  setAttribute("#open-external-agent-hub", "title", "footer.external");
  setAttribute("#open-external-agent-hub", "aria-label", "footer.external");
  setAttribute("#theme-toggle", "title", document.documentElement.dataset.theme === "light" ? "footer.theme.dark" : "footer.theme.light");
  setAttribute("#attach-image", "title", "composer.addImageTitle");
  setAttribute("#send", "aria-label", "composer.send");
  setAttribute("#scroll-to-bottom", "title", "chat.scrollBottom");
  const imageButton = document.querySelector("#attach-image");
  if (imageButton) imageButton.textContent = t("composer.addImage");
  const sendButton = document.querySelector("#send");
  if (sendButton) sendButton.setAttribute("aria-label", t("composer.send"));
  const stop = document.querySelector("#stop");
  if (stop) stop.innerHTML = `<span>■</span> ${t("run.stop")}`;
  const forceStop = document.querySelector("#force-stop");
  if (forceStop) forceStop.textContent = t("run.forceStop");
  document.querySelectorAll(".run-overview small")[0]?.replaceChildren(document.createTextNode(t("run.tokens")));
  document.querySelectorAll(".run-overview small")[1]?.replaceChildren(document.createTextNode(t("run.duration")));
  const meta = document.querySelectorAll(".composer-meta span");
  if (meta[0]) meta[0].textContent = t("composer.enter");
  if (meta[1]) meta[1].textContent = t("composer.newline");
  const languageSelect = document.querySelector("#settings-language");
  if (languageSelect) languageSelect.value = locale;
}

function bindLocaleToggle() {
  const toggle = document.querySelector("#settings-language");
  if (!toggle || toggle.dataset.bound) return;
  toggle.dataset.bound = "true";
  toggle.addEventListener("change", () => setLocale(toggle.value));
}
