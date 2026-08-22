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

const TASK_STATES = [
  ["not_started", "未开始"],
  ["in_progress", "进行中"],
  ["completed", "已完成"],
  ["blocked", "受阻"],
  ["failed", "失败"],
];

function stateButtons(task) {
  return TASK_STATES.map(([value, label]) =>
    `<button type="button" data-task-id="${escapeHtml(task.id)}" data-status="${value}" class="task-state-btn ${task.status === value ? "active" : ""}" title="标记为${label}">${label}</button>`
  ).join("");
}

export function renderTaskPlanItem(task, depth = 0) {
  const hasChildren = Array.isArray(task.subtasks) && task.subtasks.length > 0;
  const children = (task.subtasks || []).map((item) =>
    renderTaskPlanItem(item, depth + 1)).join("");
  const estimate = task.estimated_minutes ? ` · ${task.estimated_minutes} 分钟` : "";
  const stateControl = hasChildren
    ? `<span class="task-state-derived" title="父任务状态由子任务派生">子项派生</span>`
    : `<span class="task-state-buttons" role="group" aria-label="任务状态">${stateButtons(task)}</span>`;
  return `<article class="task-block depth-${depth}"><div class="task-block-head"><span class="task-status ${escapeHtml(task.status)}"></span><div><strong>${escapeHtml(task.title)}</strong><p>${escapeHtml(task.priority)}${estimate}</p></div>${stateControl}</div>${task.description ? `<p class="task-description">${escapeHtml(task.description)}</p>` : ""}${children ? `<div class="task-children">${children}</div>` : ""}</article>`;
}
