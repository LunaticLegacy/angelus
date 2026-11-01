/** Own Run graph and lifecycle SSE connections, cursors, and stale-session guards. */
export function createRunStreamController({
  getSessionId,
  isRunActive,
  graphUrl,
  lifecycleUrl,
  getRunStatus,
  createEventStream,
  closedState,
  onGraphEvent,
  onLifecycleEvent,
  onStatus,
  onFinish,
  onTrace,
}) {
  let graphSource = null;
  let lifecycleSource = null;
  let graphSessionId = "";
  let lifecycleSessionId = "";
  let graphCursor = 0;
  let lifecycleCursor = 0;
  let statusCheckPending = false;
  let lifecycleStatusCheckPending = false;

  function closeGraph() {
    graphSource?.close();
    graphSource = null;
    graphSessionId = "";
  }

  function closeLifecycle() {
    lifecycleSource?.close();
    lifecycleSource = null;
    lifecycleSessionId = "";
  }

  function closeAll() {
    closeGraph();
    closeLifecycle();
  }

  function reset() {
    closeAll();
    graphCursor = 0;
    lifecycleCursor = 0;
    statusCheckPending = false;
    lifecycleStatusCheckPending = false;
  }

  function connectGraph() {
    closeGraph();
    const sessionId = getSessionId();
    const source = createEventStream(graphUrl(graphCursor));
    graphSource = source;
    graphSessionId = sessionId;
    source.onmessage = (message) => {
      if (getSessionId() !== graphSessionId) return;
      const event = JSON.parse(message.data);
      const cursor = Number(event.sequence || message.lastEventId);
      if (Number.isSafeInteger(cursor) && cursor >= 0) graphCursor = cursor;
      onGraphEvent(event);
    };
    source.onerror = () => {
      if (graphSource !== source) return;
      if (source.readyState === closedState) {
        if (!isRunActive()) onFinish();
        return;
      }
      if (statusCheckPending) return;
      statusCheckPending = true;
      getRunStatus(sessionId)
        .then((state) => {
          if (graphSource !== source) return;
          if (state.active || ["running", "stopping", "force_stopping"].includes(state.status)) {
            onStatus("执行图连接中断，正在重连…", "running");
          } else {
            onFinish();
          }
        })
        .catch(() => {
          if (graphSource === source) onStatus("执行图连接中断，正在重连…", "running");
        })
        .finally(() => { statusCheckPending = false; });
    };
  }

  function connectLifecycle() {
    closeLifecycle();
    const sessionId = getSessionId();
    const source = createEventStream(lifecycleUrl(lifecycleCursor));
    lifecycleSource = source;
    lifecycleSessionId = sessionId;
    source.onmessage = (message) => {
      if (getSessionId() !== lifecycleSessionId) return;
      const cursor = Number(message.lastEventId);
      if (Number.isSafeInteger(cursor) && cursor >= 0) lifecycleCursor = cursor;
      try {
        const event = JSON.parse(message.data);
        onLifecycleEvent(event);
        // The server closes the stream after terminal lifecycle facts.  An
        // EventSource otherwise reconnects automatically forever, replaying
        // the same tail and keeping the browser event loop busy.
        if (["done", "error", "stopped"].includes(String(event?.event || event?.type))) {
          source.close();
          if (lifecycleSource === source) lifecycleSource = null;
        }
      } catch (error) {
        onTrace("生命周期事件格式无效", error.message);
      }
    };
    source.onerror = () => {
      if (lifecycleSource !== source) return;
      if (source.readyState === closedState) {
        lifecycleSource = null;
        return;
      }
      if (lifecycleStatusCheckPending) return;
      lifecycleStatusCheckPending = true;
      getRunStatus(sessionId)
        .then((state) => {
          if (lifecycleSource !== source) return;
          const active = state.active || ["running", "stopping", "force_stopping"].includes(state.status);
          if (!active) {
            source.close();
            lifecycleSource = null;
            onFinish();
          } else {
            onStatus("生命周期连接中断，正在重连…", "running");
          }
        })
        .catch(() => {
          if (lifecycleSource === source) onStatus("生命周期连接中断，正在重连…", "running");
        })
        .finally(() => { lifecycleStatusCheckPending = false; });
    };
  }

  return {
    connectGraph,
    connectLifecycle,
    closeGraph,
    closeLifecycle,
    closeAll,
    reset,
  };
}
