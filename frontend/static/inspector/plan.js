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
        <span class="task-state-buttons" role="group" aria-label="任务状态">
          ${["not_started","in_progress","completed","blocked","failed"].map((value)=>`<button type="button" data-task-id="${escapeHtml(task.id)}" data-status="${value}" class="task-state-btn ${task.status === value ? "active" : ""}" title="标记为${({not_started:"未开始",in_progress:"进行中",completed:"已完成",blocked:"受阻",failed:"失败"})[value]}">${({not_started:"未开始",in_progress:"进行中",completed:"已完成",blocked:"受阻",failed:"失败"})[value]}</button>`).join("")}
        </span>
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
  $("task-plan").addEventListener("click", (event) => {
    const button = event.target.closest(".task-state-btn");
    if (button)
      updateStatus(
        button.dataset.taskId,
        button.dataset.status
      ).catch((error) => console.error("任务更新失败", error));
  });
}
