function streamKey(agent, round) {
  return `${agent || "coordinator"}:${round || ""}`;
}

/** Own transient streamed chat state; the view owns all transcript DOM. */
export function createStreamController({ chatView }) {
  const streams = new Map();

  function stateFor(agent, round) {
    const key = streamKey(agent, round);
    let state = streams.get(key);
    if (!state) {
      state = {
        content: "",
        reasoning: "",
        tools: new Map(),
        view: chatView.beginStream(agent),
      };
      streams.set(key, state);
    }
    return { key, state };
  }

  function updateDelta(agent, data) {
    const { state } = stateFor(agent, data?.round);
    if (data?.channel === "reasoning") {
      state.reasoning += String(data.delta || "");
    } else if (data?.channel === "tool_arguments") {
      const id = String(data.call_id || "tool");
      const previous = state.tools.get(id) || {};
      const next = {
        ...previous,
        call_id: id,
        raw_arguments: `${previous.raw_arguments || ""}${String(data.delta || "")}`,
        status: "参数生成中",
      };
      state.tools.set(id, next);
      state.view.updateTool(next);
    } else {
      state.content += String(data?.delta || "");
    }
    state.view.update(state.content, state.reasoning);
  }

  function updateTool(agent, data, status) {
    const { state } = stateFor(agent, data?.round);
    const id = String(data?.stream_call_id || data?.call_id || `${data?.round || ""}:${data?.name || "tool"}`);
    const next = { ...(state.tools.get(id) || {}), ...data, call_id: id, status: status || data?.status };
    state.tools.set(id, next);
    state.view.updateTool(next);
  }

  function discard(agent, round) {
    const key = streamKey(agent, round);
    const state = streams.get(key);
    if (!state) return;
    state.view.remove();
    streams.delete(key);
  }

  function discardAgent(agent) {
    const prefix = `${agent || "coordinator"}:`;
    for (const [key, state] of streams) {
      if (!key.startsWith(prefix)) continue;
      state.view.remove();
      streams.delete(key);
    }
  }

  function clear() {
    for (const state of streams.values()) state.view.remove();
    streams.clear();
  }

  return { updateDelta, updateTool, discard, discardAgent, clear };
}
