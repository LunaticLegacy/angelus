import {
  deleteMcpServer,
  listMcpBindings,
  listMcpServers,
  probeMcpServer,
  saveMcpBindings,
  saveMcpServer,
} from "../runtime/mcp-api.js";

/** Coordinate MCP server data with the selected session's binding policy. */
export function createMcpController({ getSessionId, hasSession }) {
  async function load() {
    if (!hasSession()) return { servers: [], bindings: [] };
    const sessionId = getSessionId();
    const [serverPayload, bindingPayload] = await Promise.all([
      listMcpServers(),
      listMcpBindings(sessionId),
    ]);
    return {
      servers: Array.isArray(serverPayload?.servers) ? serverPayload.servers : [],
      bindings: Array.isArray(bindingPayload?.bindings) ? bindingPayload.bindings : [],
    };
  }

  async function save(serverId, payload) {
    const server = await saveMcpServer(serverId, payload);
    return server;
  }

  async function saveBindings(bindings) {
    return saveMcpBindings(getSessionId(), bindings);
  }

  async function remove(serverId) {
    await deleteMcpServer(serverId);
  }

  async function probe(serverId) {
    return probeMcpServer(serverId);
  }

  return { load, save, saveBindings, remove, probe };
}
