"""Regression coverage for persisted session trace and token usage views."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from angelus import webapp


class SessionObservabilityTests(unittest.TestCase):
    """Exercise event pagination and per-Agent token aggregation."""

    def test_session_list_exposes_four_state_indicator(self) -> None:
        """Sidebar status is a compact projection of each durable run state."""
        with tempfile.TemporaryDirectory() as directory:
            original_root = webapp.WORKSPACE_ROOT
            original_index = webapp.WORKSPACE_INDEX
            running_key = ("running", "running")
            with webapp._sessions_lock:
                prior_running = webapp._sessions.get(running_key)
                webapp._sessions[running_key] = webapp.BrowserSession(
                    active=webapp.ActiveRun(control=webapp.BrowserRunControl()),
                )
            webapp.WORKSPACE_ROOT = Path(directory)
            webapp.WORKSPACE_INDEX = Path(directory) / "sessions.json"
            try:
                webapp._write_workspaces([
                    {"id": "idle", "name": "Idle"}, {"id": "running", "name": "Running"},
                    {"id": "error", "name": "Error"}, {"id": "done", "name": "Done"},
                ])
                for session_id, state in (("running", "running"), ("error", "error"), ("done", "completed")):
                    webapp._persist_json(webapp._run_state_path(session_id, session_id), {"status": state})

                statuses = {item["id"]: item["status"] for item in webapp.list_sessions()["sessions"]}

                self.assertEqual(statuses, {"idle": "idle", "running": "running", "error": "error", "done": "done"})
            finally:
                webapp.WORKSPACE_ROOT = original_root
                webapp.WORKSPACE_INDEX = original_index
                with webapp._sessions_lock:
                    webapp._sessions.pop(running_key, None)
                    if prior_running is not None:
                        webapp._sessions[running_key] = prior_running

    def test_event_page_is_newest_first_and_usage_uses_round_deltas(self) -> None:
        """Keep historical trace order and avoid cumulative-usage double counts."""
        with tempfile.TemporaryDirectory() as directory:
            original_root = webapp.WORKSPACE_ROOT
            webapp.WORKSPACE_ROOT = Path(directory)
            try:
                event_path = webapp._session_path("demo", "demo") / "events.ndjson"
                event_path.write_text("\n".join([
                    json.dumps({"event": "lifecycle", "type": "agent:round", "agent": "coordinator", "data": {"round_usage": {"input": 3, "output": 2, "total": 5, "cached": 1, "reasoning": 1}}}),
                    json.dumps({"event": "lifecycle", "type": "agent:round", "agent": "worker", "data": {"round_usage": {"input": 7, "output": 1, "total": 8, "cached": 0, "reasoning": 0}}}),
                    json.dumps({"event": "result", "content": "finished"}),
                ]) + "\n", encoding="utf-8")

                page = webapp._session_event_page("demo", "demo", before=None, limit=2)
                self.assertEqual([event["event"] for event in page["events"]], ["result", "lifecycle"])
                self.assertEqual(page["next_before"], 1)

                summary = webapp._session_usage_summary(webapp._read_session_event_log("demo", "demo"))
                self.assertEqual(summary["usage"], {"input": 10, "output": 3, "total": 13, "cached": 1, "reasoning": 1})
                self.assertEqual([agent["id"] for agent in summary["agents"]], ["worker", "coordinator"])
            finally:
                webapp.WORKSPACE_ROOT = original_root

    def test_usage_prefers_canonical_per_call_ledger(self) -> None:
        """The display-only round payload must not double-count ledger calls."""
        events = [
            {"event": "lifecycle", "type": "agent:usage", "agent": "coordinator",
             "data": {"kind": "primary", "usage": {"input": 3, "output": 2, "total": 5, "cached": 1, "reasoning": 1}}},
            {"event": "lifecycle", "type": "agent:internal_usage", "agent": "coordinator",
             "data": {"kind": "graph_query", "usage": {"input": 4, "output": 1, "total": 5, "cached": 0, "reasoning": 0}}},
            {"event": "lifecycle", "type": "agent:round", "agent": "coordinator",
             "data": {"round_usage": {"input": 99, "output": 99, "total": 198, "cached": 0, "reasoning": 0}}},
        ]

        summary = webapp._session_usage_summary(events)

        self.assertEqual(summary["usage"], {"input": 7, "output": 3, "total": 10, "cached": 1, "reasoning": 1})
        self.assertEqual(summary["agents"], [{"id": "coordinator", "usage": summary["usage"]}])

    def test_orphaned_running_state_becomes_persisted_interruption(self) -> None:
        """Expose a restart-lost worker as a durable, explainable terminal state."""
        with tempfile.TemporaryDirectory() as directory:
            original_root = webapp.WORKSPACE_ROOT
            key = ("demo", "demo")
            with webapp._sessions_lock:
                prior_session = webapp._sessions.pop(key, None)
            webapp.WORKSPACE_ROOT = Path(directory)
            try:
                webapp._persist_json(webapp._run_state_path(*key), {
                    "status": "running",
                    "run_id": "demo",
                    "started_at": 10.0,
                })

                status = webapp.get_run_status(*key)
                persisted = json.loads(webapp._run_state_path(*key).read_text(encoding="utf-8"))

                self.assertFalse(status["active"])
                self.assertEqual(status["status"], "interrupted")
                self.assertIn("工作线程", status["error"])
                self.assertEqual(persisted["status"], "interrupted")
                self.assertEqual(persisted["error"], status["error"])
            finally:
                webapp.WORKSPACE_ROOT = original_root
                with webapp._sessions_lock:
                    webapp._sessions.pop(key, None)
                    if prior_session is not None:
                        webapp._sessions[key] = prior_session

    def test_graph_read_reconciles_legacy_states_and_dispatch_edges(self) -> None:
        """Project an old failed graph into precise task and node terminals."""
        with tempfile.TemporaryDirectory() as directory:
            original_root = webapp.WORKSPACE_ROOT
            key = ("demo", "demo")
            with webapp._sessions_lock:
                prior_session = webapp._sessions.pop(key, None)
            webapp.WORKSPACE_ROOT = Path(directory)
            try:
                session_path = webapp._session_path(*key)
                webapp._persist_json(session_path / "run-state.json", {
                    "status": "error",
                    "run_id": "demo",
                    "started_at": 10.0,
                    "finished_at": 20.0,
                    "error": "coordinator failed",
                })
                webapp._persist_json(session_path / "graph-view.json", {
                    "nodes": [
                        {"id": "coordinator", "kind": "agent", "dynamic": False, "parent": None},
                        {"id": "reported_worker", "kind": "agent", "dynamic": True, "parent": "coordinator"},
                        {"id": "running_worker", "kind": "agent", "dynamic": True, "parent": "coordinator"},
                    ],
                    "edges": [],
                    "assignments": {
                        "reported": "reported_worker",
                        "running": "running_worker",
                        "queued": "queued_worker",
                    },
                    "task_states": {
                        "reported": "reported",
                        "running": "running",
                        "queued": "queued",
                    },
                })
                (session_path / "events.ndjson").write_text(
                    json.dumps({
                        "event": "lifecycle",
                        "type": "task:reported",
                        "agent": "reported_worker",
                        "message": "failed report",
                        "data": {"task_id": "reported", "status": "failed"},
                    }) + "\n",
                    encoding="utf-8",
                )

                graph = webapp.get_session_graph(*key)

                self.assertEqual(graph["run_status"]["status"], "error")
                self.assertEqual(graph["task_states"], {
                    "reported": "failed",
                    "running": "interrupted",
                    "queued": "cancelled",
                })
                self.assertEqual(graph["node_states"]["coordinator"]["state"], "failed")
                self.assertIn("queued_worker", {node["id"] for node in graph["nodes"]})
                self.assertIn(
                    {"source": "coordinator", "target": "running_worker", "kind": "dispatch"},
                    graph["edges"],
                )
            finally:
                webapp.WORKSPACE_ROOT = original_root
                with webapp._sessions_lock:
                    webapp._sessions.pop(key, None)
                    if prior_session is not None:
                        webapp._sessions[key] = prior_session


if __name__ == "__main__":
    unittest.main()
