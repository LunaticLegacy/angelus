import { escapeHtml } from "./dom.js";

/**
 * Render a nested task-plan record as Workbench inspector markup.
 *
 * Args:
 *   task: API task object with id, title, status, priority, description, and subtasks.
 *   depth: Current tree nesting level used only for the CSS depth class.
 *
 * Returns:
 *   Escaped HTML for the task and all of its descendants. The caller owns DOM insertion.
 */
export function renderTaskPlanItem(task, depth = 0) {
  const children = (task.subtasks || []).map((item) =>
    renderTaskPlanItem(item, depth + 1)).join("");
  const estimate = task.estimated_minutes ? ` · ${task.estimated_minutes} 分钟` : "";
  return `<article class="task-block depth-${depth}"><div class="task-block-head"><span class="task-status ${escapeHtml(task.status)}"></span><div><strong>${escapeHtml(task.title)}</strong><p>${escapeHtml(task.priority)}${estimate}</p></div><select data-task-id="${escapeHtml(task.id)}" class="task-state"><option value="not_started" ${task.status === "not_started" ? "selected" : ""}>未开始</option><option value="in_progress" ${task.status === "in_progress" ? "selected" : ""}>进行中</option><option value="completed" ${task.status === "completed" ? "selected" : ""}>已完成</option><option value="blocked" ${task.status === "blocked" ? "selected" : ""}>受阻</option></select></div>${task.description ? `<p class="task-description">${escapeHtml(task.description)}</p>` : ""}${children ? `<div class="task-children">${children}</div>` : ""}</article>`;
}
