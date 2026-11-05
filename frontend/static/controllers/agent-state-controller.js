function stateView(canonical, message, agentId, acknowledged) {
  const ui = acknowledged ? "idle"
    : canonical === "succeeded" ? "completed"
      : ["pending", "queued"].includes(canonical) ? "pending"
        : ["stopped", "interrupted"].includes(canonical) ? "stopped"
          : canonical === "failed" ? "error"
            : ["cancelled", "skipped"].includes(canonical) ? "idle" : canonical;
  return { canonical, ui, message: acknowledged ? "已确认完成" : message };
}

export function createAgentStateController({ getSessionId, getGraph, getRunActive }) {
  function acknowledgedAgents() {
    try { return new Set(JSON.parse(localStorage.getItem(`llmfetcherAcknowledgedAgents:${getSessionId()}`) || "[]")); }
    catch { return new Set(); }
  }

  function stateLabel(state) {
    return ({ idle: "待机", pending: "待执行", queued: "等待执行", running: "正在运行", succeeded: "运行完毕", completed: "运行完毕", failed: "运行错误", stopped: "已停止", interrupted: "已中断", cancelled: "已取消", skipped: "已跳过" })[state] || state;
  }

  function stateFor(agentId, agents = []) {
    if (agentId === "all") {
      const views = agents.filter((agent) => agent.id !== "all").map((agent) => stateFor(agent.id, agents));
      if (views.some((view) => view.canonical === "running")) return stateView("running", "当前会话：正在运行", agentId, false);
      if (views.some((view) => view.canonical === "queued")) return stateView("queued", "当前会话：等待执行", agentId, false);
      const terminal = String(getGraph()?.state || "");
      if (!getRunActive() && terminal === "completed") return stateView("succeeded", "当前会话：运行完毕", agentId, acknowledgedAgents().has(agentId));
      if (!getRunActive() && terminal === "failed") return stateView("failed", "当前会话：运行错误", agentId, false);
      if (!getRunActive() && ["stopped", "interrupted"].includes(terminal)) return stateView("stopped", "当前会话：已停止", agentId, false);
      const canonical = ["failed", "stopped", "succeeded"].find((state) => views.some((view) => view.canonical === state)) || "idle";
      return stateView(canonical, canonical === "idle" ? "当前会话待机" : `当前会话：${stateLabel(canonical)}`, agentId, acknowledgedAgents().has(agentId));
    }
    const node = (getGraph()?.nodes || []).find((item) => item.id === agentId);
    if (node?.state) {
      if (node.state === "pending" && !node.updated_at) return stateView("idle", "本轮未开始", agentId, false);
      return stateView(node.state, node.error || node.reason || node.message || stateLabel(node.state), agentId, acknowledgedAgents().has(agentId));
    }
    return stateView("idle", "本轮未开始", agentId, false);
  }

  function runState(agentId, agents) { return stateFor(agentId, agents).ui; }

  function nodeFor(agentId) { return (getGraph()?.nodes || []).find((node) => node.id === agentId) || null; }

  function acknowledge(agentId, agents) {
    const acknowledged = acknowledgedAgents();
    if (agentId === "all") agents.filter((agent) => agent.id !== "all" && runState(agent.id, agents) === "completed").forEach((agent) => acknowledged.add(agent.id));
    else acknowledged.add(agentId);
    localStorage.setItem(`llmfetcherAcknowledgedAgents:${getSessionId()}`, JSON.stringify([...acknowledged]));
  }

  return { stateFor, runState, nodeFor, acknowledge };
}
