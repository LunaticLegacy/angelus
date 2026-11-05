import { controlRun, openCompactionStream, startRun } from "../runtime/run-api.js";

/** Keep run commands behind one session-aware controller. */
export function createRunController({ getSessionId }) {
  function session() {
    const id = getSessionId();
    if (!id) throw new Error("尚未选择会话");
    return id;
  }

  return {
    start(payload) {
      return startRun(payload);
    },
    control(payload) {
      return controlRun(session(), payload);
    },
    compact(agent) {
      return openCompactionStream(session(), agent);
    },
  };
}
