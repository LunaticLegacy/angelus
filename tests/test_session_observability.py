"""Regression coverage for persisted session trace and token usage views."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from angelus import storage, webapp


class SessionObservabilityTests(unittest.TestCase):
    """Exercise event pagination and per-Agent token aggregation."""

    def test_session_list_exposes_four_state_indicator(self) -> None:
        """Sidebar status is a compact projection of each durable run state."""
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            original_index = storage.WORKSPACE_INDEX
            running_key = ("running", "running")
            with storage._sessions_lock:
                prior_running = storage._sessions.get(running_key)
                storage._sessions[running_key] = webapp.BrowserSession(
                    active=webapp.ActiveRun(control=webapp.BrowserRunControl()),
                )
            storage.WORKSPACE_ROOT = Path(directory)
            storage.WORKSPACE_INDEX = Path(directory) / "sessions.json"
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
                storage.WORKSPACE_ROOT = original_root
                storage.WORKSPACE_INDEX = original_index
                with storage._sessions_lock:
                    storage._sessions.pop(running_key, None)
                    if prior_running is not None:
                        storage._sessions[running_key] = prior_running

    def test_event_page_is_newest_first_and_usage_uses_round_deltas(self) -> None:
        """Keep historical trace order and avoid cumulative-usage double counts."""
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(directory)
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
                self.assertTrue(page["has_more"])
                self.assertIsNotNone(page["next_cursor"])
                self.assertEqual(page["durable_offset"], event_path.stat().st_size)

                summary = webapp._session_usage_summary(webapp._read_session_event_log("demo", "demo"))
                self.assertEqual(summary["usage"], {"input": 10, "output": 3, "total": 13, "cached": 1, "reasoning": 1})
                self.assertEqual([agent["id"] for agent in summary["agents"]], ["worker", "coordinator"])
                self.assertEqual(summary["round"], {"input": 7, "output": 1, "total": 8, "cached": 0, "reasoning": 0})
                # Legacy log has no run_started marker, so the "本次" window
                # falls back to the whole log.
                self.assertEqual(summary["run"], summary["usage"])
                for agent in summary["agents"]:
                    self.assertEqual(agent["run"], agent["usage"])
            finally:
                storage.WORKSPACE_ROOT = original_root

    def test_event_cursor_pages_backwards_and_skips_incomplete_tail(self) -> None:
        """Trace cursors cover old records while SSE resumes at a complete line."""
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(directory)
            try:
                event_path = webapp._session_path("demo", "demo") / "events.ndjson"
                complete = b"".join(
                    json.dumps({"event": "item", "index": index}).encode() + b"\n"
                    for index in range(5)
                )
                event_path.write_bytes(complete + b'{"event":"partial"')

                newest = webapp._session_event_page("demo", "demo", before=None, limit=2)
                older = webapp._session_event_page(
                    "demo", "demo", cursor=newest["next_cursor"], before=None, limit=2,
                )
                oldest = webapp._session_event_page(
                    "demo", "demo", cursor=older["next_cursor"], before=None, limit=2,
                )

                self.assertEqual([event["index"] for event in newest["events"]], [4, 3])
                self.assertEqual([event["index"] for event in older["events"]], [2, 1])
                self.assertEqual([event["index"] for event in oldest["events"]], [0])
                self.assertEqual(newest["durable_offset"], len(complete))
                self.assertFalse(oldest["has_more"])
                self.assertIsNone(oldest["next_cursor"])
            finally:
                storage.WORKSPACE_ROOT = original_root

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
        self.assertEqual(summary["agents"], [
            {"id": "coordinator", "usage": summary["usage"], "run": summary["usage"]},
        ])
        self.assertEqual(summary["round"], {"input": 99, "output": 99, "total": 198, "cached": 0, "reasoning": 0})

    def test_usage_run_tracks_current_lifecycle_and_excludes_steers(self) -> None:
        """The "本次" (run) tile counts the latest run and drops steer work."""
        events = [
            # 旧 run：不应进入“本次”
            {"event": "run_started", "run_id": "old", "timestamp": 1.0},
            {"event": "lifecycle", "type": "agent:usage", "agent": "coordinator",
             "data": {"usage": {"input": 100, "output": 10, "total": 110, "cached": 0, "reasoning": 0}}},
            {"event": "done", "timestamp": 2.0},
            # 当前 run（用户本次输入）
            {"event": "run_started", "run_id": "new", "timestamp": 3.0},
            {"event": "lifecycle", "type": "agent:usage", "agent": "coordinator",
             "data": {"usage": {"input": 5, "output": 2, "total": 7, "cached": 1, "reasoning": 1}}},
            {"event": "lifecycle", "type": "agent:usage", "agent": "worker",
             "data": {"usage": {"input": 3, "output": 1, "total": 4, "cached": 0, "reasoning": 0}}},
            # 用户 steer：之后的所有轮次都算 steer 工作，不计入“本次”
            {"event": "lifecycle", "type": "agent:steer_applied", "agent": "coordinator",
             "data": {"round": 2, "messages": ["调整方向"]}},
            {"event": "lifecycle", "type": "agent:usage", "agent": "coordinator",
             "data": {"usage": {"input": 50, "output": 20, "total": 70, "cached": 0, "reasoning": 5}}},
            {"event": "done", "timestamp": 4.0},
        ]

        summary = webapp._session_usage_summary(events)

        # 整会话：旧 run 与 steer 后续都计入
        self.assertEqual(summary["usage"]["input"], 158)
        self.assertEqual(summary["usage"]["output"], 33)
        self.assertEqual(summary["usage"]["total"], 191)
        # “本次”：仅当前 run 中 steer 之前的用量
        self.assertEqual(
            summary["run"],
            {"input": 8, "output": 3, "total": 11, "cached": 1, "reasoning": 1},
        )
        by_id = {agent["id"]: agent for agent in summary["agents"]}
        self.assertEqual(
            by_id["coordinator"]["run"],
            {"input": 5, "output": 2, "total": 7, "cached": 1, "reasoning": 1},
        )
        self.assertEqual(
            by_id["worker"]["run"],
            {"input": 3, "output": 1, "total": 4, "cached": 0, "reasoning": 0},
        )

    def test_orphaned_running_state_becomes_persisted_interruption(self) -> None:
        """Expose a restart-lost worker as a durable, explainable terminal state."""
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            key = ("demo", "demo")
            with storage._sessions_lock:
                prior_session = storage._sessions.pop(key, None)
            storage.WORKSPACE_ROOT = Path(directory)
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
                storage.WORKSPACE_ROOT = original_root
                with storage._sessions_lock:
                    storage._sessions.pop(key, None)
                    if prior_session is not None:
                        storage._sessions[key] = prior_session

    def test_graph_read_reconciles_legacy_states_and_dispatch_edges(self) -> None:
        """Project an old failed graph into precise task and node terminals."""
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            key = ("demo", "demo")
            with storage._sessions_lock:
                prior_session = storage._sessions.pop(key, None)
            storage.WORKSPACE_ROOT = Path(directory)
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
                storage.WORKSPACE_ROOT = original_root
                with storage._sessions_lock:
                    storage._sessions.pop(key, None)
                    if prior_session is not None:
                        storage._sessions[key] = prior_session


if __name__ == "__main__":
    unittest.main()
