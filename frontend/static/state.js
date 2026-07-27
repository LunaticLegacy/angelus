/**
 * Lightweight pub/sub state container.
 *
 * setState merges a partial object and notifies subscribers whose key changed.
 * subscribe(key, fn) returns an unsubscribe function.
 */

const _state = {
  sessionId:
    localStorage.llmfetcherSession ||
    localStorage.llmfetcherWorkspace ||
    "default",
  workspaceId: null,
  connectorId: localStorage.llmfetcherConnector || "",
  running: false,
  statusText: "准备就绪",
  statusClass: "idle",
};

const _subscribers = {};

export function getState(key) {
  return key ? _state[key] : _state;
}

export function setState(partial) {
  const changed = Object.keys(partial);
  Object.assign(_state, partial);
  changed.forEach((key) => {
    const fns = _subscribers[key];
    if (fns) fns.forEach((fn) => fn(_state[key]));
  });
}

export function subscribe(key, fn) {
  (_subscribers[key] ??= []).push(fn);
  return () => {
    const idx = _subscribers[key]?.indexOf(fn);
    if (idx !== undefined && idx !== -1) _subscribers[key].splice(idx, 1);
  };
}
