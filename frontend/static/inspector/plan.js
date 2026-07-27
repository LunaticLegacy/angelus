/**
 * Task plan panel — tree rendering and status updates.
 */

import { $, escapeHtml } from "../utils.js";
import { apiJson, apiPatch } from "../api.js";
import { getState } from "../state.js";

/* ---- data ---- */

export async function load() {
  const sid = getState("sessionId");
  const plan = await apiJson(`/api/sessions/${sid}/plan`);

  $("plan-summary").textContent = plan.goal
    ? `${plan.goal}${plan.summary ? ` · ${plan.summary}` : ""}`
    : "Agent 生成的任务计划会显示在这里。";

  $("task-plan").innerHTML =
    (plan.tasks || []).map((t) => renderTask(t)).join("") ||
    '<p class="empty">尚未建立任务计划。</p>';
}

/* ---- rendering ---- */

function renderTask(task, depth = 0) {
  const children = (task.subtasks || [])
    .map((t) => renderTask(t, depth + 1))
    .join("");
  const estimate = task.estimated_minutes
    ? ` · ${task.estimated_minutes} 分钟`
    : "";
  return `
    <article class="task-block depth-${depth}">
      <div class="task-block-head">
        <span class="task-status ${escapeHtml(task.status)}"></span>
        <div>
          <strong>${escapeHtml(task.title)}</strong>
          <p>${escapeHtml(task.priority)}${estimate}</p>
        </div>
        <select data-task-id="${escapeHtml(task.id)}" class="task-state">
          <option value="not_started" ${task.status === "not_started" ? "selected" : ""}>未开始</option>
          <option value="in_progress" ${task.status === "in_progress" ? "selected" : ""}>进行中</option>
          <option value="completed" ${task.status === "completed" ? "selected" : ""}>已完成</option>
          <option value="blocked" ${task.status === "blocked" ? "selected" : ""}>受阻</option>
        </select>
      </div>
      ${task.description ? `<p class="task-description">${escapeHtml(task.description)}</p>` : ""}
      ${children ? `<div class="task-children">${children}</div>` : ""}
    </article>`;
}

/* ---- status updates ---- */

async function updateStatus(taskId, status) {
  const sid = getState("sessionId");
  await apiPatch(`/api/sessions/${sid}/tasks/${taskId}`, { status });
  await load();
}

export function bindStatusUpdates() {
  $("task-plan").addEventListener("change", (event) => {
    if (event.target.matches(".task-state"))
      updateStatus(
        event.target.dataset.taskId,
        event.target.value
      ).catch((error) => console.error("任务更新失败", error));
  });
}
