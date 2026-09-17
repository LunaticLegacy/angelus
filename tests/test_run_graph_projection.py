from __future__ import annotations

import json
import hashlib
import tempfile
import unittest
from pathlib import Path

from angelus.modules.run_graph_module import RunGraphProjector


class RunGraphProjectionTests(unittest.TestCase):
    def test_projects_checkpoint_and_journal_into_normalized_states(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            attempt = root / "executions" / "run-1"
            (attempt / "run-graph").mkdir(parents=True)
            checkpoint = {
                "schema_version": 1, "kind": "angelus.run-graph", "session_id": "session-1",
                "execution_id": "run-1", "attempt": 2, "state": "running",
                "nodes": [{"id": "coordinator", "kind": "agent", "origin": "blueprint", "parent_id": None, "state": "running", "task_id": None, "plan_task_id": None, "message": "", "error": None, "reason": None, "updated_at": 10}],
                "edges": [], "event_cursor": 1, "started_at": 10, "finished_at": None,
                "error": None, "stop_reason": None, "checkpoint": None,
            }
            encoded = json.dumps(checkpoint, ensure_ascii=False, indent=2, sort_keys=True).encode()
            (attempt / "run-graph" / "checkpoint.json").write_bytes(encoded)
            (attempt / "execution-manifest.json").write_text(json.dumps({
                "execution_id": "run-1", "attempt": 2, "state": "failed",
                "started_at": 10, "finished_at": 20, "error": "root failed",
                "checkpoint": {"run_graph": {"path": "run-graph/checkpoint.json", "sha256": hashlib.sha256(encoded).hexdigest()}},
            }), encoding="utf-8")
            events = [
                {"type": "execution_started", "timestamp": 10, "data": {}},
                {"type": "agent:failed", "timestamp": 15, "agent": "worker", "message": "tool failed", "data": {"task_id": "task-1", "error": "bad schema"}},
                {"type": "execution_failed", "timestamp": 20, "data": {"error": "root failed"}},
            ]
            (attempt / "execution.events.ndjson").write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")

            result = RunGraphProjector().project("session-1", root)

        self.assertEqual(result["kind"], "angelus.run-graph")
        self.assertEqual(result["state"], "failed")
        self.assertEqual(result["event_cursor"], 3)
        nodes = {node["id"]: node for node in result["nodes"]}
        self.assertEqual(nodes["worker"]["state"], "failed")
        self.assertEqual(nodes["worker"]["error"], "bad schema")

    def test_live_snapshot_overlays_latest_attempt_without_changing_history_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = RunGraphProjector().project(
                "session-1", Path(temporary),
                live_snapshot={
                    "nodes": [{"id": "coordinator", "kind": "agent", "dynamic": False}],
                    "edges": [], "assignments": {}, "task_states": {},
                    "node_states": {"coordinator": {"state": "running", "message": "Round 1", "updated_at": 12}},
                },
                live_status={"execution_id": "live-1", "attempt": 1, "state": "running", "started_at": 10},
            )

        self.assertEqual(result["execution_id"], "live-1")
        self.assertEqual(result["state"], "running")
        self.assertEqual(result["nodes"][0]["state"], "running")

    def test_recovery_requires_verified_run_graph_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            attempt = root / "executions" / "run-1"
            (attempt / "run-graph").mkdir(parents=True)
            payload = {
                "schema_version": 1, "kind": "angelus.run-graph", "session_id": "session-1",
                "execution_id": "run-1", "attempt": 1, "state": "interrupted",
                "nodes": [], "edges": [], "event_cursor": 1, "started_at": 10,
                "finished_at": 20, "error": "shutdown", "stop_reason": None, "checkpoint": None,
            }
            encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode()
            (attempt / "run-graph" / "checkpoint.json").write_bytes(encoded)
            (attempt / "execution-manifest.json").write_text(json.dumps({
                "execution_id": "run-1", "attempt": 1, "state": "interrupted",
                "checkpoint": {
                    "generation": "checkpoint", "run_graph": {
                        "path": "run-graph/checkpoint.json",
                        "sha256": hashlib.sha256(encoded).hexdigest(),
                    },
                    "recovery": {"schema_version": 1, "strategy": "new_attempt"},
                },
            }), encoding="utf-8")
            (attempt / "execution.events.ndjson").write_text(
                json.dumps({"type": "execution_started", "data": {"message": "original request"}}) + "\n",
                encoding="utf-8",
            )

            recovered = RunGraphProjector().recovery_checkpoint(root, "run-1")

        self.assertEqual(recovered["source_execution_id"], "run-1")
        self.assertEqual(recovered["initial_message"], "original request")

    def test_events_are_standardized_without_the_raw_journal_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            attempt = root / "executions" / "run-1"
            attempt.mkdir(parents=True)
            (attempt / "execution-manifest.json").write_text(json.dumps({"execution_id": "run-1", "attempt": 1}), encoding="utf-8")
            (attempt / "execution.events.ndjson").write_text("".join(json.dumps(item) + "\n" for item in [
                {"type": "execution_started", "timestamp": 1, "data": {}},
                {"type": "agent:failed", "timestamp": 2, "agent": "worker", "message": "bad schema", "data": {"error": "bad schema"}},
            ]), encoding="utf-8")

            page = RunGraphProjector().events("session-1", root)

        self.assertEqual(page["events"][0]["kind"], "angelus.run-graph-event")
        self.assertEqual(page["events"][0]["type"], "run.state_changed")
        self.assertEqual(page["events"][1]["type"], "node.state_changed")
        self.assertNotIn("timestamp", page["events"][1])
