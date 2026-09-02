/** External Agent Hub configuration and capability-gated context inspection workbench. */

const ADAPTERS = [
  ["codex_app_server", "Codex App Server"],
  ["claude_sdk", "Claude Agent SDK"],
  ["coze", "Coze"],
  ["opencode", "OpenCode"],
  ["workbuddy", "WorkBuddy"],
  ["custom", "Custom adapter"],
];

/** Create the host-owned view for global External Agent Hub configuration. */
export function createExternalAgentHubView(dialog, root) {
  let agents = [];
  let selectedId = "";
  let candidates = [];
  let createDraft = null;

  /** Open the dialog and refresh durable Agent definitions. */
  async function open() {
    if (!dialog.open) dialog.showModal();
    await refresh();
  }

  /** Close the host dialog without changing durable configuration. */
  function close() {
    dialog.close();
  }

  /** Reload the global Hub list and retain a valid selected item. */
  async function refresh() {
    setBusy("正在读取 External Agent Hub…");
    try {
      const payload = await request("/api/external-agents");
      agents = Array.isArray(payload.agents) ? payload.agents : [];
      if (!agents.some((agent) => agent.id === selectedId)) selectedId = agents[0]?.id || "";
      render();
    } catch (error) {
      root.replaceChildren(message(`无法加载 Hub：${error.message}`, "error"));
    }
  }

  /** Render the list rail and either an Agent detail pane or creation form. */
  function render() {
    const layout = element("div", "external-hub-layout");
    const rail = element("aside", "external-hub-list");
    const actions = element("div", "external-hub-list-actions");
    actions.append(
      button("＋ 添加", () => { selectedId = ""; createDraft = null; render(); }, "primary"),
      button("扫描本机", () => discoverLocalProcesses(), "secondary"),
      button("↻", () => refresh(), "icon", "刷新"),
    );
    rail.append(actions);
    if (!agents.length) rail.append(message("尚未配置外部 Agent。", "empty"));
    for (const agent of agents) rail.append(agentCard(agent));
    const detail = element("section", "external-hub-detail");
    detail.append(selectedId ? detailView(agents.find((agent) => agent.id === selectedId)) : createView());
    layout.append(rail, detail);
    root.replaceChildren(layout);
  }

  /** Render a selectable concise definition card. */
  function agentCard(agent) {
    const active = agent.id === selectedId;
    const card = button("", () => { selectedId = agent.id; render(); }, `external-hub-agent-card${active ? " selected" : ""}`);
    const dot = element("i", `external-hub-dot ${agent.enabled ? "enabled" : "disabled"}`);
    const text = element("span");
    text.append(element("strong", "", agent.title || agent.id), element("small", "", `${adapterLabel(agent.adapter_kind)} · ${agent.enabled ? "已启用" : "已停用"}`));
    card.append(dot, text);
    return card;
  }

  /** Render the full creation form with a generated stable ID. */
  function createView() {
    const view = element("div", "external-hub-create");
    view.append(heading("添加 External Agent", "保存的是协议和连接引用；不会保存 API key，也不会启动远端任务。"));
    if (candidates.length) view.append(candidateSection());
    const form = definitionForm(createDraft || defaultDefinition(), "创建");
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const body = readDefinition(form);
      await mutate("创建失败", async () => {
        await request("/api/external-agents", { method: "POST", body });
        selectedId = body.id;
        createDraft = null;
      });
    });
    view.append(form);
    return view;
  }

  /** Render process candidates that require a separate definition create action. */
  function candidateSection() {
    const sectionNode = section("已发现的本机实例", "扫描只读取进程信息。它不会附着、停止或复用这些实例。", "", "external-hub-candidates");
    const body = sectionNode.querySelector(".external-hub-section-body");
    const rows = candidates.map((candidate) => {
      const row = element("article", "external-hub-candidate");
      const copy = element("div");
      copy.append(
        element("strong", "", candidate.title || "未知外部 Agent"),
        element("small", "", `PID ${candidate.process_id} · ${adapterLabel(candidate.adapter_kind)} · 不可附着`),
        element("p", "", candidate.working_directory ? `工作目录：${candidate.working_directory}` : candidate.command || candidate.detail || "未提供额外进程信息。"),
      );
      row.append(copy, button("用于新定义", () => { createDraft = definitionFromCandidate(candidate); render(); }, "secondary"));
      return row;
    });
    body.replaceChildren(...rows);
    return sectionNode;
  }

  /** Perform an explicit read-only local process scan. */
  async function discoverLocalProcesses() {
    try {
      const payload = await request("/api/external-agents/discover", { method: "POST" });
      candidates = Array.isArray(payload.candidates) ? payload.candidates : [];
      selectedId = "";
      createDraft = null;
      render();
    } catch (error) {
      window.alert(`扫描本机失败：${error.message}`);
    }
  }

  /** Render one definition editor plus inspection controls and data. */
  function detailView(agent) {
    if (!agent) return message("所选 External Agent 已不存在。", "error");
    const view = element("div", "external-hub-agent-detail");
    view.append(heading(agent.title || agent.id, `${adapterLabel(agent.adapter_kind)} · ${agent.enabled ? "允许用于未来运行" : "已停用"}`));
    const form = definitionForm(agent, "保存修改");
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const body = readDefinition(form);
      await mutate("保存失败", async () => request(`/api/external-agents/${encodeURIComponent(agent.id)}`, { method: "PUT", body }));
    });
    const tools = element("div", "external-hub-actions");
    tools.append(button("健康检查", () => loadHealth(agent.id, view), "secondary"), button("删除", async () => {
      if (!window.confirm(`删除“${agent.title || agent.id}”的 Hub 定义？连接器凭据不会被删除。`)) return;
      await mutate("删除失败", async () => { await request(`/api/external-agents/${encodeURIComponent(agent.id)}`, { method: "DELETE" }); selectedId = ""; });
    }, "danger"));
    const health = element("div", "external-hub-health", "尚未检查连接。");
    health.dataset.hubHealth = agent.id;
    const capabilities = section("Capabilities", "只读查看 adapter 已声明的能力。", "正在读取…", "external-hub-capabilities");
    const sessions = section("External Sessions", "仅列出远端会话摘要；不会导入、恢复或运行它们。", "正在读取…", "external-hub-sessions");
    const contexts = section("External Contexts", "仅显示 adapter 真实支持读取的上下文。读取失败会保留服务端的领域错误；不会伪造空数据。", "正在读取…", "external-hub-contexts");
    view.append(form, tools, health, capabilities, sessions, contexts);
    loadCapabilities(agent.id, capabilities).catch((error) => renderError(capabilities, error));
    loadSessions(agent.id, sessions).catch((error) => renderError(sessions, error));
    loadContexts(agent.id, contexts).catch((error) => renderError(contexts, error));
    return view;
  }

  /** Build a strict definition form shared by create and edit paths. */
  function definitionForm(agent, submitLabel) {
    const form = element("form", "external-hub-form");
    const identifier = field("ID", "id", "text", agent.id, "例如 codex-local");
    identifier.input.pattern = "[a-z][a-z0-9_-]{1,63}";
    identifier.input.required = true;
    identifier.input.disabled = Boolean(agent.id);
    const title = field("名称", "title", "text", agent.title, "例如 Local Codex");
    title.input.required = true;
    const adapter = element("label", "external-hub-field");
    adapter.append(element("span", "", "协议 adapter"));
    const select = element("select");
    select.name = "adapter_kind";
    for (const [value, label] of ADAPTERS) {
      const option = element("option", "", label);
      option.value = value;
      option.selected = value === agent.adapter_kind;
      select.append(option);
    }
    adapter.append(select);
    const endpoint = field("Endpoint", "endpoint", "text", agent.endpoint, "Codex 当前仅支持 stdio://");
    const connector = field("Connector 引用", "connector_id", "text", agent.connector_id, "可选；仅保存连接器 ID，不显示密钥");
    const description = element("label", "external-hub-field full");
    description.append(element("span", "", "说明"));
    const textarea = element("textarea");
    textarea.name = "description";
    textarea.rows = 3;
    textarea.value = agent.description || "";
    description.append(textarea);
    const enabled = element("label", "external-hub-enabled");
    const checkbox = element("input");
    checkbox.type = "checkbox";
    checkbox.name = "enabled";
    checkbox.checked = agent.enabled !== false;
    enabled.append(checkbox, element("span", "", "启用此定义用于未来外部运行"));
    const grid = element("div", "external-hub-fields");
    grid.append(identifier.label, title.label, adapter, endpoint.label, connector.label, description, enabled);
    const submit = button(submitLabel, () => {}, "primary");
    submit.type = "submit";
    form.append(grid, submit);
    return form;
  }

  /** Read a complete form body that matches the strict Hub API payload. */
  function readDefinition(form) {
    const get = (name) => form.elements.namedItem(name);
    return {
      id: get("id").value.trim(), title: get("title").value.trim(), adapter_kind: get("adapter_kind").value,
      endpoint: get("endpoint").value.trim(), connector_id: get("connector_id").value.trim(),
      enabled: get("enabled").checked, description: get("description").value.trim(),
    };
  }

  /** Execute a mutation, preserve domain errors, then refresh durable state. */
  async function mutate(prefix, operation) {
    try {
      await operation();
      await refresh();
    } catch (error) {
      window.alert(`${prefix}：${error.message}`);
    }
  }

  /** Render a health result after a deliberate non-executing probe. */
  async function loadHealth(agentId, view) {
    const target = view.querySelector(`[data-hub-health="${CSS.escape(agentId)}"]`);
    target.textContent = "正在检查协议连接…";
    try {
      const payload = await request(`/api/external-agents/${encodeURIComponent(agentId)}/health`, { method: "POST" });
      const health = payload.health || {};
      target.className = `external-hub-health ${health.status || "unknown"}`;
      target.textContent = `${health.status || "unknown"} · ${health.message || "无诊断信息"}`;
    } catch (error) {
      target.className = "external-hub-health unavailable";
      target.textContent = `健康检查失败：${error.message}`;
    }
  }

  /** Populate capability declarations without issuing an external run. */
  async function loadCapabilities(agentId, container) {
    const payload = await request(`/api/external-agents/${encodeURIComponent(agentId)}/capabilities`);
    const body = container.querySelector(".external-hub-section-body");
    const values = Array.isArray(payload.capabilities) ? payload.capabilities : [];
    const rows = values.length
      ? values.map((item) => element("p", "external-hub-row", `${item.title || item.id} · ${item.invocation_mode} — ${item.description || ""}`))
      : [message("该 adapter 尚未声明可用能力。", "empty")];
    body.replaceChildren(...rows);
  }

  /** Populate external session summaries without importing them into Angelus. */
  async function loadSessions(agentId, container) {
    const payload = await request(`/api/external-agents/${encodeURIComponent(agentId)}/sessions?limit=50`);
    const body = container.querySelector(".external-hub-section-body");
    const values = Array.isArray(payload.sessions) ? payload.sessions : [];
    const rows = values.length
      ? values.map((item) => element("p", "external-hub-row", `${item.title || item.external_id} · ${item.status || "—"} · ${item.external_id}`))
      : [message("尚未发现可读取的外部会话。", "empty")];
    body.replaceChildren(...rows);
  }

  /** Populate readable external contexts and render an explicit package preview action. */
  async function loadContexts(agentId, container) {
    const payload = await request(`/api/external-agents/${encodeURIComponent(agentId)}/contexts?limit=50`);
    const body = container.querySelector(".external-hub-section-body");
    const values = Array.isArray(payload.contexts) ? payload.contexts : [];
    const rows = values.length ? values.map((item) => {
      const row = element("div", "external-hub-row external-hub-context-row");
      row.append(
        element("span", "", `${item.title || item.external_id} · ${item.message_count ?? "?"} 条消息`),
        button("预览包", () => previewContext(agentId, item.external_id, container), "secondary"),
      );
      return row;
    }) : [message("该 adapter 没有可读取的上下文，或尚未配置其读取协议。", "empty")];
    body.replaceChildren(...rows);
  }

  /** Read one explicitly selected context and show its redacted portable envelope. */
  async function previewContext(agentId, contextId, container) {
    try {
      const payload = await request(`/api/external-agents/${encodeURIComponent(agentId)}/contexts/${encodeURIComponent(contextId)}`);
      const packageValue = payload.package || {};
      const preview = element("pre", "external-hub-context-preview", JSON.stringify(packageValue, null, 2));
      const body = container.querySelector(".external-hub-section-body");
      body.append(preview);
    } catch (error) {
      window.alert(`读取上下文失败：${error.message}`);
    }
  }

  return { open, close, refresh };
}

async function request(path, options = {}) {
  const init = { ...options };
  if (options.body !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(options.body);
  }
  const response = await fetch(path, init);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || `${response.status} ${response.statusText}`);
  return payload;
}
function element(tag, className = "", text = "") { const node = document.createElement(tag); node.className = className; if (text) node.textContent = text; return node; }
function button(text, handler, className = "", title = "") { const node = element("button", `external-hub-button ${className}`, text); node.type = "button"; if (title) node.title = title; node.addEventListener("click", handler); return node; }
function message(text, className) { return element("p", `external-hub-message ${className}`, text); }
function heading(title, note) { const node = element("header", "external-hub-detail-heading"); node.append(element("h3", "", title), element("p", "", note)); return node; }
function section(title, note, loading, className) { const node = element("section", `external-hub-section ${className}`); node.append(heading(title, note), element("div", "external-hub-section-body", loading)); return node; }
function field(label, name, type, current, placeholder) { const input = element("input"); input.name = name; input.type = type; input.value = current || ""; input.placeholder = placeholder; const labelNode = element("label", "external-hub-field"); labelNode.append(element("span", "", label), input); return { label: labelNode, input }; }
function adapterLabel(kind) { return ADAPTERS.find(([id]) => id === kind)?.[1] || kind || "未知 adapter"; }
function defaultDefinition() { return { id: "", title: "", adapter_kind: "codex_app_server", endpoint: "stdio://", connector_id: "", enabled: true, description: "" }; }
function definitionFromCandidate(candidate) { return { id: `${String(candidate.adapter_kind || "agent").replace(/[^a-z0-9_-]/g, "-")}-${candidate.process_id}`, title: candidate.title || "Detected external Agent", adapter_kind: candidate.adapter_kind || "custom", endpoint: candidate.endpoint || "", connector_id: "", enabled: true, description: `${candidate.detail || "Detected local process."}${candidate.working_directory ? ` Working directory: ${candidate.working_directory}` : ""}`.slice(0, 2000) }; }
function setBusy(text) { const root = document.getElementById("external-agent-hub-root"); root.replaceChildren(message(text, "loading")); }
function renderError(container, error) { const body = container.querySelector(".external-hub-section-body"); body.replaceChildren(message(`读取失败：${error.message}`, "error")); }
