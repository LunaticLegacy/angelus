"""Regression coverage for durable steering-instruction retrieval."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from angelus import storage, webapp


class SessionSteersTests(unittest.TestCase):
    """Ensure applied steering instructions survive browser refreshes."""

    def test_get_session_steers_returns_applied_instructions_in_order(self) -> None:
        """Reconstruct steer history from the durable append-only event log."""
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(directory)
            try:
                event_path = webapp._session_path("demo", "demo") / "events.ndjson"
                event_path.write_text("\n".join([
                    json.dumps({"event": "lifecycle", "type": "agent:round", "agent": "coordinator", "data": {}}),
                    json.dumps({"event": "lifecycle", "type": "agent:steer_applied", "agent": "coordinator",
                                "data": {"round": 1, "messages": ["请更简洁", "用中文"]}, "timestamp": 100}),
                    json.dumps({"event": "lifecycle", "type": "agent:steer_applied", "agent": "coordinator",
                                "data": {"round": 2, "messages": ["换个角度"]}, "timestamp": 200}),
                    json.dumps({"event": "result", "content": "done"}),
                ]) + "\n", encoding="utf-8")

                payload = webapp.get_session_steers("demo")
                self.assertEqual(len(payload["steers"]), 2)
                self.assertEqual(payload["steers"][0]["round"], 1)
                self.assertEqual(payload["steers"][0]["messages"], ["请更简洁", "用中文"])
                self.assertEqual(payload["steers"][1]["round"], 2)
                self.assertEqual(payload["steers"][1]["messages"], ["换个角度"])
                self.assertEqual(payload["steers"][0]["timestamp"], 100)
            finally:
                storage.WORKSPACE_ROOT = original_root

    def test_get_session_steers_ignores_non_steer_and_malformed_events(self) -> None:
        """Skip lifecycle records without an applied-steering payload."""
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(directory)
            try:
                event_path = webapp._session_path("demo", "demo") / "events.ndjson"
                event_path.write_text("\n".join([
                    json.dumps({"event": "lifecycle", "type": "agent:round", "data": {}}),
                    json.dumps({"event": "lifecycle", "type": "agent:steer_applied", "data": {}}),
                    json.dumps({"event": "lifecycle", "type": "agent:steer_applied", "data": {"messages": []}}),
                    json.dumps({"event": "result", "content": "done"}),
                ]) + "\n", encoding="utf-8")

                payload = webapp.get_session_steers("demo")
                self.assertEqual(payload["steers"], [])
            finally:
                storage.WORKSPACE_ROOT = original_root


if __name__ == "__main__":
    unittest.main()
