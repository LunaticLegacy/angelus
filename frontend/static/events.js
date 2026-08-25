/**
 * SSE / EventSource lifecycle management.
 *
 * Only one connection is allowed at a time.  Calling connectRun() silently
 * closes any previous connection before opening a new one.  The workspaceId
 * guard prevents stale events from updating the wrong session after a fast
 * switchSession() → connectRun() sequence.
 */

let _source = null;
let _workspaceId = "";

export function connectRun(workspaceId, runId, handlers) {
  disconnect();

  const source = new EventSource(
    `/api/workspaces/${workspaceId}/runs/${runId}/events`
  );
  _source = source;
  _workspaceId = workspaceId;

  source.onmessage = (event) => {
    if (workspaceId !== _workspaceId) return; // stale — user switched away
    handlers.onEvent?.(JSON.parse(event.data));
  };

  source.onerror = () => {
    if (source.readyState === EventSource.CLOSED && _source === source) {
      disconnect();
      handlers.onDone?.();
    }
  };
}

export function disconnect() {
  _source?.close();
  _source = null;
  _workspaceId = "";
}

export function isConnected() {
  return _source !== null;
}

export function currentWorkspaceId() {
  return _workspaceId;
}
