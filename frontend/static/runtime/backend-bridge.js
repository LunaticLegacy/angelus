/**
 * Backend frontier for the desktop client.
 *
 * UI modules should depend on this boundary instead of calling fetch or
 * constructing EventSource instances directly.  Keeping transport here makes
 * retries, auth, telemetry, and a future Tauri transport swappable without
 * rewriting the interface.
 */
export { apiJson, apiPost, apiPut, apiPatch, apiDelete } from "../api.js";

/**
 * Low-level request escape hatch for operations that need status codes or
 * non-JSON bodies. Keeping it here makes the browser transport replaceable
 * without spreading fetch calls through controllers.
 */
export function request(url, options = {}) {
  return fetch(url, options);
}

export const EVENT_STREAM_CLOSED = 2;

/** Create an event stream without exposing EventSource construction to UI code. */
export function createEventStream(url) {
  return new EventSource(url);
}

export function openEventStream(url, { onMessage, onError, onOpen } = {}) {
  const source = new EventSource(url);
  source.onopen = () => onOpen?.();
  source.onmessage = (event) => {
    try { onMessage?.(JSON.parse(event.data), event); }
    catch (error) { onError?.(error, event); }
  };
  source.onerror = (error) => onError?.(error);
  return {
    close() { source.close(); },
    get readyState() { return source.readyState; },
  };
}

export const clientStorage = {
  get(key, fallback = null) {
    try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem(key, String(value)); } catch { /* private mode */ }
  },
};
