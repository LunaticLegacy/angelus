/** Thin fetch wrapper — no state, no DOM. Every method returns parsed JSON. */

async function _fetch(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(
      payload?.detail || `${response.status} ${response.statusText} (${url})`
    );
  }
  return payload;
}

export function apiJson(url) {
  return _fetch(url);
}

export function apiPost(url, body) {
  return _fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function apiPut(url, body) {
  return _fetch(url, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function apiPatch(url, body) {
  return _fetch(url, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function apiDelete(url, body) {
  return _fetch(url, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
}
