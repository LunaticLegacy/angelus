/**
 * Inspector tab switching.
 */

export function initTabs() {
  document.querySelectorAll(".inspector-tabs button").forEach((button) => {
    button.addEventListener("click", () => {
      document
        .querySelectorAll(".inspector-tabs button")
        .forEach((btn) => btn.classList.toggle("active", btn === button));
      document
        .querySelectorAll(".inspector-panel")
        .forEach(
          (panel) =>
            panel.classList.toggle("active", panel.id === button.dataset.panel)
        );
    });
  });
}
