import { listSessions } from "../runtime/session-api.js";
import { renderSessionList } from "../components/session-list.js";

/** Coordinate Session identity and list actions without owning page markup. */
export function createSessionController({
  getSessionId,
  setSessionId,
  setAvailableSessions,
  getProfileWorkspaceId,
  setProfileWorkspaceId,
  setStoredSessionId,
  setImageSession,
  renderMemorySessionPicker,
  getElements,
  hydrateIcons,
  onSelect,
  onOpen,
  onDelete,
}) {
  async function load(selected = getSessionId()) {
    const { sessions } = await listSessions();
    setAvailableSessions(sessions);
    const { select, recent } = getElements();

    if (!sessions.length) {
      setSessionId(null);
      setStoredSessionId(null);
      select.innerHTML = '<option value="">尚无会话</option>';
      select.disabled = true;
      recent.innerHTML = '<p class="empty">创建一个会话以开始。</p>';
      setImageSession(null);
      renderMemorySessionPicker();
      return { sessions, selectedId: null };
    }

    const selectedId = sessions.some((item) => item.id === selected)
      ? selected
      : sessions[0].id;
    setSessionId(selectedId);
    if (!getProfileWorkspaceId()) setProfileWorkspaceId(selectedId);
    setStoredSessionId(selectedId);
    setImageSession(selectedId);
    renderSessionList({
      select,
      recent,
      sessions,
      selectedId,
      hydrateIcons,
      onSelect,
      onOpen,
      onDelete,
    });
    renderMemorySessionPicker();
    return { sessions, selectedId };
  }

  return { load };
}
