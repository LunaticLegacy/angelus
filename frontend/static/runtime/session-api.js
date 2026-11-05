import { apiJson, apiPost, request } from "./backend-bridge.js";

function sessionPath(sessionId, suffix = "") {
  if (!sessionId) throw new Error("尚未选择会话");
  return `/api/sessions/${encodeURIComponent(sessionId)}${suffix}`;
}

export function listSessions() {
  return apiJson("/api/sessions");
}

export function createSession({ name, projectPath = null }) {
  return apiPost("/api/sessions", { name, project_path: projectPath });
}

export function deleteSession(sessionId) {
  return request(sessionPath(sessionId), {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirmation: sessionId }),
  }).then(async (response) => {
    const payload = await response.json().catch(() => ({}));
    if (response.status === 404) return { missing: true };
    if (!response.ok) throw new Error(payload.detail || `${response.status} ${response.statusText}`);
    return { missing: false };
  });
}

export function uploadSessionImage(sessionId, file) {
  const url = `${sessionPath(sessionId, "/attachments/images")}?filename=${encodeURIComponent(file.name)}`;
  return request(url, { method: "POST", headers: { "Content-Type": file.type }, body: file }).then(async (response) => {
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || `${response.status} ${response.statusText}`);
    return payload;
  });
}

export function uploadSessionArtifact(sessionId, file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const value = typeof reader.result === "string" ? reader.result : "";
      const comma = value.indexOf(",");
      const data = comma >= 0 ? value.slice(comma + 1) : value;
      request(sessionPath(sessionId, "/artifacts"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ data_base64: data, logical_name: file.name, mime_type: file.type || "application/octet-stream" }),
      }).then(async (response) => {
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(payload.detail || `${response.status} ${response.statusText}`);
        resolve(payload);
      }).catch(reject);
    };
    reader.onerror = () => reject(reader.error || new Error("读取附件失败"));
    reader.readAsDataURL(file);
  });
}

export function listMessages(sessionId, { agent = "all", before = null, limit = 80 } = {}) {
  const params = new URLSearchParams({ agent, limit: String(limit) });
  if (before !== null && before !== undefined) params.set("before", String(before));
  return apiJson(`${sessionPath(sessionId, "/messages")}?${params}`);
}

export function sessionResource(sessionId, suffix = "") {
  return sessionPath(sessionId, suffix);
}
