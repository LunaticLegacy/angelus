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
let _durableOffset = 0;
let _runKey = "";

export function connectRun(workspaceId, runId, handlers) {
  const runKey = `${workspaceId}:${runId}`;
  if (runKey !== _runKey) _durableOffset = 0;
  disconnect();
  _runKey = runKey;

  const query = _durableOffset > 0 ? `?cursor=${_durableOffset}` : "";
  const source = new EventSource(
    `/api/workspaces/${workspaceId}/runs/${runId}/events${query}`
  );
  _source = source;
  _workspaceId = workspaceId;

  source.onmessage = (event) => {
    if (workspaceId !== _workspaceId) return; // stale — user switched away
    const offset = Number(event.lastEventId);
    if (Number.isSafeInteger(offset) && offset >= 0) _durableOffset = offset;
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
