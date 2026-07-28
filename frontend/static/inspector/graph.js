/**
 * Execution graph panel + Agent strip bar.
 */

import { $, escapeHtml } from "../utils.js";
import { apiJson } from "../api.js";
import { getState } from "../state.js";

/* ---- data ---- */

export async function load() {
  const sid = getState("sessionId");
  const response = await fetch(`/api/sessions/${sid}/graph`);
  if (response.status === 404) {
    renderGraph({ nodes: [] });
    return;
  }
  if (!response.ok)
    throw new Error(`${response.status} ${response.statusText}`);
  const graph = await response.json();
  renderAgentStrip(graph);
  renderGraph(graph);
}

/* ---- agent strip ---- */

function renderAgentStrip(graph) {
  const nodes = graph.nodes || [];
  if (!nodes.length) return;

  const count = $("agent-count");
  count.textContent = `${nodes.length} Agent${nodes.length === 1 ? "" : "s"}`;

  const cards = nodes
    .slice(0, 5)
    .map((node, index) => {
      const avatar =
        node.kind === "routing" ? "◇" : index === 0 ? "♛" : "&lt;/&gt;";
      const state = node.dynamic ? "busy" : "running";
      const cls =
        node.kind === "routing"
          ? "docs"
          : index === 0
            ? "coordinator"
            : "code";
      return `
        <article class="agent-card ${index === 0 ? "selected" : ""}">
          <div class="agent-avatar ${cls}">${avatar}</div>
          <div>
            <strong>${escapeHtml(node.id)}</strong>
            <small>${node.dynamic ? "子智能体" : node.kind === "routing" ? "路由节点" : "协调节点"}</small>
          </div>
          <span class="agent-state ${state}"></span>
        </article>`;
    })
    .join("");

  $("agent-strip").innerHTML = `
    <button class="agent-filter active" type="button">
      <strong>全部</strong>
      <small>${nodes.length} Agent${nodes.length === 1 ? "" : "s"}</small>
    </button>
    ${cards}`;
}

/* ---- graph tree ---- */

function renderGraph(graph) {
  const target = $("execution-graph");
  const nodes = graph.nodes || [];

  if (!nodes.length) {
    target.innerHTML =
      '<p class="empty">当前 session 尚未启动 Swarm。</p>';
    return;
  }

  const nodeIds = new Set(nodes.map((n) => n.id));
  const incoming = {};
  const outgoing = {};

  for (const edge of graph.edges || []) {
    if (!nodeIds.has(edge.source) || !nodeIds.has(edge.target)) continue;
    (incoming[edge.target] ??= []).push(edge.source);
    (outgoing[edge.source] ??= []).push(edge.target);
  }

  /* build parent map */
  const parent = {};
  for (const node of nodes) {
    if (node.parent && nodeIds.has(node.parent) && node.parent !== node.id)
      parent[node.id] = node.parent;
  }
  for (const node of nodes) {
    if (!parent[node.id] && (incoming[node.id] || []).length)
      parent[node.id] = incoming[node.id][0];
  }

  const children = {};
  for (const [child, ancestor] of Object.entries(parent)) {
    (children[ancestor] ??= []).push(child);
  }

  const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
  const assignments = graph.assignments || {};
  const states = graph.task_states || {};

  function taskFor(id) {
    return (
      Object.entries(assignments).find(([, agent]) => agent === id)?.[0]
    );
  }

  const rendered = new Set();

  function renderNode(nodeId, depth = 0, path = new Set()) {
    const node = byId[nodeId];
    if (!node || path.has(nodeId)) return "";
    rendered.add(nodeId);
    const nextPath = new Set(path).add(nodeId);
    const taskId = taskFor(nodeId);
    const taskState = taskId ? states[taskId] : "";
    const deps = (incoming[nodeId] || []).filter(
      (s) => s !== parent[nodeId]
    );
    const descendants = (children[nodeId] || [])
      .sort()
      .map((c) => renderNode(c, depth + 1, nextPath))
      .join("");
    return `
      <div class="graph-branch">
        <article class="graph-node" style="--graph-depth:${depth}">
          <strong>${escapeHtml(node.id)}</strong>
          <span>${node.dynamic ? "子智能体" : node.kind === "routing" ? "路由节点" : "Agent"}${taskState ? ` · ${escapeHtml(taskState)}` : ""}</span>
          ${node.parent ? `<small>上级：${escapeHtml(node.parent)}</small>` : ""}
          ${deps.length ? `<small>依赖：${escapeHtml(deps.join("、"))}</small>` : ""}
          ${(outgoing[nodeId] || []).length && !descendants ? `<small>下游：${escapeHtml(outgoing[nodeId].join("、"))}</small>` : ""}
        </article>
        ${descendants ? `<div class="graph-children">${descendants}</div>` : ""}
      </div>`;
  }

  const roots = nodes
    .filter((n) => !parent[n.id])
    .map((n) => n.id)
    .sort();
  const html = roots.map((id) => renderNode(id)).join("");
  const leftovers = nodes
    .filter((n) => !rendered.has(n.id))
    .map((n) => renderNode(n.id))
    .join("");
  target.innerHTML = html + leftovers;
}
