"""Test _agent_turns_from_events for duplicate turns."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from angelus.webapp import _agent_turns_from_events, _append_session_event


class AgentTurnsFromEventsTests(unittest.TestCase):
    """Verify _agent_turns_from_events deduplication and ordering."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name) / "ws1"
        self.workspace.mkdir()
        self.session = "test-session"
        (self.workspace / self.session).mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_events(self, events: list[dict]) -> None:
        """Write events to a temp events.ndjson."""
        event_path = self.workspace / self.session / "events.ndjson"
        with open(event_path, "w", encoding="utf-8") as f:
            for evt in events:
                f.write(json.dumps(evt, ensure_ascii=False) + "\n")

    def _read_turns(self, agent_name: str) -> list[dict]:
        """Read turns using the same session path logic."""
        with patch("angelus.webapp._session_path", return_value=self.workspace / self.session):
            return _agent_turns_from_events(
                str(self.workspace), self.session, agent_name
            )

    def test_single_round_no_duplicates(self):
        """One user message + one coordinator agent:round should produce 2 turns."""
        events = [
            {"event": "lifecycle", "type": "agent:start", "agent": "coordinator",
             "message": "Hello", "timestamp": 1},
            {"event": "lifecycle", "type": "agent:round", "agent": "coordinator",
             "data": {"round": 1, "assistant_content": "Hi there!", "reasoning_content": ""},
             "timestamp": 2},
            {"event": "result", "content": "Hi there!", "reasoning": "",
             "timestamp": 3},
        ]
        self._write_events(events)
        turns = self._read_turns("coordinator")
        roles = [t["role"] for t in turns]
        self.assertEqual(roles, ["user", "assistant"],
                         f"Expected [user, assistant] but got duplicate/missing turns: {roles}")
        self.assertEqual(turns[0]["content"], "Hello")
        self.assertEqual(turns[1]["content"], "Hi there!")

    def test_two_rounds_no_duplicates(self):
        """Two user questions + two coordinator responses → 4 turns."""
        events = [
            {"event": "lifecycle", "type": "agent:start", "agent": "coordinator",
             "message": "Q1", "timestamp": 1},
            {"event": "lifecycle", "type": "agent:round", "agent": "coordinator",
             "data": {"round": 1, "assistant_content": "A1", "reasoning_content": ""},
             "timestamp": 2},
            {"event": "result", "content": "A1", "reasoning": "",
             "timestamp": 3},
            {"event": "lifecycle", "type": "agent:start", "agent": "coordinator",
             "message": "Q2", "timestamp": 4},
            {"event": "lifecycle", "type": "agent:round", "agent": "coordinator",
             "data": {"round": 1, "assistant_content": "A2", "reasoning_content": ""},
             "timestamp": 5},
            {"event": "result", "content": "A2", "reasoning": "",
             "timestamp": 6},
        ]
        self._write_events(events)
        turns = self._read_turns("coordinator")
        roles = [t["role"] for t in turns]
        self.assertEqual(roles, ["user", "assistant", "user", "assistant"],
                         f"Expected 4 turns but got: {roles}")
        contents = [t["content"] for t in turns]
        self.assertEqual(contents, ["Q1", "A1", "Q2", "A2"])

    def test_duplicate_agent_round_events_produce_duplicate_turns(self):
        """If agent:round fires twice, turns are duplicated (the real issue)."""
        events = [
            {"event": "lifecycle", "type": "agent:start", "agent": "coordinator",
             "message": "Q1", "timestamp": 1},
            {"event": "lifecycle", "type": "agent:round", "agent": "coordinator",
             "data": {"round": 1, "assistant_content": "A1", "reasoning_content": ""},
             "timestamp": 2},
            # DUPLICATE agent:round — same content, emitted by a second hook
            {"event": "lifecycle", "type": "agent:round", "agent": "coordinator",
             "data": {"round": 1, "assistant_content": "A1", "reasoning_content": ""},
             "timestamp": 3},
            {"event": "result", "content": "A1", "reasoning": "",
             "timestamp": 4},
        ]
        self._write_events(events)
        turns = self._read_turns("coordinator")
        roles = [t["role"] for t in turns]
        self.assertEqual(roles, ["user", "assistant", "assistant"],
                         f"Duplicate agent:round events cause duplicate assistant turns: {roles}")

    def test_non_coordinator_agent_only_gets_its_own_rounds(self):
        """A sub-agent 'worker-1' sees coordinator user messages + its own rounds."""
        events = [
            {"event": "lifecycle", "type": "agent:start", "agent": "coordinator",
             "message": "Do task X", "timestamp": 1},
            {"event": "lifecycle", "type": "agent:round", "agent": "coordinator",
             "data": {"round": 1, "assistant_content": "I'll dispatch", "reasoning_content": ""},
             "timestamp": 2},
            {"event": "lifecycle", "type": "agent:submitted", "agent": "worker-1",
             "message": "Do task X", "timestamp": 3},
            {"event": "lifecycle", "type": "agent:round", "agent": "worker-1",
             "data": {"round": 1, "assistant_content": "Task X done", "reasoning_content": ""},
             "timestamp": 4},
            {"event": "result", "content": "I'll dispatch", "reasoning": "",
             "timestamp": 5},
        ]
        self._write_events(events)
        turns = self._read_turns("worker-1")
        roles = [t["role"] for t in turns]
        self.assertEqual(roles, ["user", "assistant"],
                         f"Worker-1 should see [user, assistant] but got: {roles}")
        self.assertEqual(turns[0]["content"], "Do task X")
        self.assertEqual(turns[1]["content"], "Task X done")


if __name__ == "__main__":
    unittest.main()
