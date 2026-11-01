/** Own Inspector tab navigation and panel activation state. */
export function createInspectorController({
  activity,
  tabsRoot = document,
  panelsRoot = document,
  initialPanel,
  storageKey = "llmfetcherInspectorPanel",
  loaders = {},
  onError = () => {},
  onChange = () => {},
}) {
  let activePanel = initialPanel;

  function select(panel, refresh = true, open = true) {
    const target = panelsRoot.getElementById?.(panel) || document.getElementById(panel);
    if (!target) return;
    const isCurrent = activePanel === panel;
    const isOpen = activity?.dataset.inspectorOpen === "true";
    if (refresh && isCurrent && isOpen) open = false;
    activePanel = panel;
    try { localStorage.setItem(storageKey, panel); } catch {}
    tabsRoot.querySelectorAll("[data-inspector-panel]").forEach((button) => {
      const selected = button.dataset.inspectorPanel === panel;
      button.classList.toggle("active", selected);
      button.setAttribute("aria-pressed", String(selected && open));
    });
    panelsRoot.querySelectorAll(".inspector-panel").forEach((item) => item.classList.toggle("active", item === target));
    if (activity) {
      activity.dataset.inspectorOpen = String(open);
      document.body.classList.toggle("inspector-open", open);
    }
    onChange(panel);
    if (!refresh) return;
    // A panel loader may be async, synchronous, or intentionally absent
    // (Notes can render directly from localStorage). Normalise all three
    // shapes so one optional panel cannot break Inspector navigation.
    Promise.resolve()
      .then(() => loaders[panel]?.())
      .catch((error) => onError(error));
  }

  function init() {
    tabsRoot.querySelectorAll("[data-inspector-panel]").forEach((button) => {
      button.addEventListener("click", () => select(button.dataset.inspectorPanel));
    });
    if (!document.getElementById(activePanel)) activePanel = "inspector-plan";
    // Hydrate the initially selected panel after the shell is mounted. This
    // keeps a hard refresh from showing an empty Inspector until the user
    // clicks a tab.
    select(activePanel, true, false);
  }

  return { init, select, getActive: () => activePanel };
}
