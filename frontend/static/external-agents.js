/** Render the standalone External Agent Hub provider capability catalog. */
async function loadProviders() {
  /** Read the public catalog and render text with DOM APIs to avoid HTML injection. */
  const response = await fetch("/api/external-agents/providers");
  const payload = await response.json();
  if (!response.ok) throw new Error(payload?.detail || response.statusText);
  const root = document.getElementById("providers");
  root.replaceChildren(...(payload.providers || []).map((provider) => {
    const card = document.createElement("article");
    card.className = "plugin-status-card";
    const title = document.createElement("strong");
    title.textContent = provider.label;
    const details = document.createElement("small");
    details.textContent = `${provider.available ? "已配置" : "未配置"} · ${(provider.capabilities || []).join("、") || "仅预留接口"}`;
    card.append(title, details);
    return card;
  }));
}

loadProviders().catch((error) => {
  document.getElementById("providers").textContent = `无法读取 Provider：${error.message}`;
});
