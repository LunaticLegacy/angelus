from __future__ import annotations

import json
import hashlib
import tempfile
import unittest
from pathlib import Path

from angelus.modules.run_graph_module import RunGraphProjector
from angelus.modules.run_graph_module.models import RunGraph
from angelus.modules.run_graph_module.reducer import apply_journal_event


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


class RunGraphCheckpointReplayTests(unittest.TestCase):
    """Bounded replay must resume from the checkpoint cursor exactly.

    A checkpoint snapshot carries the ``event_cursor`` of the last fact folded
    into it.  Replay may skip that many valid journal lines and reduce the tail,
    but must never seek by the checkpoint's byte ``event_offset``: facts appended
    between the snapshot and the commit line would then be silently dropped,
    under-counting the cursor and losing node activity.
    """

    def _write_attempt(self, root: Path, events: list[dict[str, object]], *, checkpoint: dict[str, object] | None, execution_id: str = "run-1") -> Path:
        attempt = root / "executions" / execution_id
        (attempt / "run-graph").mkdir(parents=True, exist_ok=True)
        (attempt / "execution.events.ndjson").write_text(
            "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
        manifest: dict[str, object] = {"execution_id": execution_id, "attempt": 1, "state": "failed"}
        if checkpoint is not None:
            encoded = json.dumps(checkpoint, ensure_ascii=False, indent=2, sort_keys=True).encode()
            (attempt / "run-graph" / "checkpoint.json").write_bytes(encoded)
            manifest["checkpoint"] = {
                "run_graph": {"path": "run-graph/checkpoint.json", "sha256": hashlib.sha256(encoded).hexdigest()},
            }
        (attempt / "execution-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return attempt

    def _reference(self, events: list[dict[str, object]], execution_id: str = "run-1") -> dict[str, object]:
        graph = RunGraph(session_id="session-1", execution_id=execution_id, attempt=1)
        for cursor, event in enumerate(events, start=1):
            apply_journal_event(graph, event, cursor=cursor)
        return graph.to_json()

    @staticmethod
    def _facts() -> list[dict[str, object]]:
        # Facts 3 and 4 are appended after the snapshot (cursor 2) but before the
        # checkpoint commit line (5); byte-offset seeking would skip them.
        return [
            {"type": "execution_started", "timestamp": 10, "data": {}},
            {"type": "task:dispatched", "timestamp": 11, "agent": "worker", "data": {"task_id": "t1"}},
            {"type": "agent:failed", "timestamp": 12, "agent": "worker", "message": "bad schema", "data": {"task_id": "t1", "error": "bad schema"}},
            {"type": "agent:retry", "timestamp": 13, "agent": "worker", "data": {"task_id": "t1"}},
            {"type": "checkpoint_committed", "timestamp": 14, "data": {"run_graph": {"path": "run-graph/checkpoint.json"}}},
            {"type": "agent:completed", "timestamp": 15, "agent": "worker", "data": {"task_id": "t1"}},
        ]

    def test_project_resumes_tail_from_cursor_without_skipping_interleaved_facts(self) -> None:
        events = self._facts()
        snapshot = self._reference(events[:2])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_attempt(root, events, checkpoint=snapshot)
            result = RunGraphProjector().project("session-1", root)
            reference = self._reference(events)

        self.assertEqual(reference["event_cursor"], result["event_cursor"])
        self.assertEqual(6, result["event_cursor"])
        nodes = {node["id"]: node for node in result["nodes"]}
        self.assertEqual("succeeded", nodes["worker"]["state"])
        self.assertIsNotNone(result["checkpoint"])

    def test_events_replays_from_start_when_cursor_precedes_checkpoint(self) -> None:
        events = self._facts()
        snapshot = self._reference(events[:2])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_attempt(root, events, checkpoint=snapshot)
            projector = RunGraphProjector()
            full = projector.events("session-1", root, cursor=0, limit=100)
            tail = projector.events("session-1", root, cursor=2, limit=100)

        self.assertEqual([1, 2, 3, 4, 5, 6], [event["sequence"] for event in full["events"]])
        self.assertFalse(full["has_more"])
        self.assertEqual(6, full["next_cursor"])
        # Resuming at the checkpoint must still surface every fact after it.
        self.assertEqual([3, 4, 5, 6], [event["sequence"] for event in tail["events"]])

    def test_journal_reader_skips_checkpointed_prefix_without_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "execution.events.ndjson"
            # The skipped prefix is raw byte-discarded, so even a malformed line
            # costs no JSON parsing; the parsed tail still tolerates garbage.
            path.write_bytes(b"not-json-prefix\n" + json.dumps({"type": "skipped"}).encode() + b"\n" + json.dumps({"type": "kept"}).encode() + b"\n")

            kept = list(RunGraphProjector._events(path, skip_lines=2))
            all_valid = list(RunGraphProjector._events(path))

        self.assertEqual([{"type": "kept"}], kept)
        self.assertEqual([{"type": "skipped"}, {"type": "kept"}], all_valid)


if __name__ == "__main__":
    unittest.main()
