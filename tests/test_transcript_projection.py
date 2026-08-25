"""Regression coverage for durable cursor-based transcript projection."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from angelus.history import _agent_turns_page


class TranscriptProjectionTests(unittest.TestCase):
    """Exercise incremental projection, recovery, filtering, and pagination."""

    def setUp(self) -> None:
        """Create one isolated session directory for each projection test."""
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.session = self.root / "session"
        self.session.mkdir()
        self.events = self.session / "events.ndjson"

    def tearDown(self) -> None:
        """Remove the isolated session and its generated projection files."""
        self.temporary.cleanup()

    def _append(self, events: list[dict]) -> None:
        """Append complete UTF-8 NDJSON records to the authoritative log.

        Args:
            events: JSON-serializable event dictionaries in durable order.
        """
        with self.events.open("a", encoding="utf-8") as handle:
            for event in events:
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _page(self, agent: str = "all", **kwargs: object) -> dict:
        """Read a projection page using the temporary absolute partition.

        Args:
            agent: Transcript filter passed to the projection.
            **kwargs: Cursor, before, or limit options for the page.

        Returns:
            The browser transcript response mapping.
        """
        return _agent_turns_page(str(self.root), "session", agent, **kwargs)

    def test_pages_450_turns_without_duplicates_or_omissions(self) -> None:
        """Three cursor pages cover every turn exactly once, newest page first."""
        events: list[dict] = []
        for index in range(225):
            events.extend([
                {"event": "run_started", "message": f"问题{index}"},
                {"event": "lifecycle", "type": "agent:round", "agent": "coordinator",
                 "data": {"round": index, "assistant_content": f"回答{index}"}},
            ])
        self._append(events)

        cursor = None
        pages: list[list[dict]] = []
        while True:
            page = self._page(cursor=cursor, limit=200)
            pages.append(page["messages"])
            cursor = page["next_cursor"]
            if cursor is None:
                break

        self.assertEqual([len(page) for page in pages], [200, 200, 50])
        turns = [turn for page in reversed(pages) for turn in page]
        self.assertEqual(len(turns), 450)
        self.assertEqual(turns[0]["content"], "问题0")
        self.assertEqual(turns[-1]["content"], "回答224")
        self.assertEqual(len({turn["content"] for turn in turns}), 450)

    def test_incremental_sync_preserves_projection_prefix(self) -> None:
        """A second read processes only the event tail and keeps prior bytes."""
        self._append([
            {"event": "run_started", "message": "first"},
            {"event": "result", "content": "done"},
        ])
        self._page()
        projection = self.session / "display-turns.ndjson"
        checkpoint_path = self.session / "display-turns.checkpoint.json"
        prefix = projection.read_bytes()
        first_checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))

        self._append([
            {"event": "run_started", "message": "second"},
            {"event": "result", "content": "again"},
        ])
        page = self._page()
        second_checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))

        self.assertTrue(projection.read_bytes().startswith(prefix))
        self.assertGreater(second_checkpoint["event_offset"], first_checkpoint["event_offset"])
        self.assertEqual([turn["content"] for turn in page["messages"]], ["first", "done", "second", "again"])

    def test_uncommitted_projection_tail_is_truncated_before_append(self) -> None:
        """Crash bytes after the committed length never become duplicate turns."""
        self._append([{"event": "run_started", "message": "safe"}])
        self._page()
        projection = self.session / "display-turns.ndjson"
        with projection.open("ab") as handle:
            handle.write(json.dumps({"agent": "*", "role": "user", "content": "ghost"}).encode() + b"\n")

        page = self._page()

        self.assertEqual([turn["content"] for turn in page["messages"]], ["safe"])
        self.assertNotIn(b"ghost", projection.read_bytes())

    def test_truncated_or_rewritten_event_log_rebuilds_projection(self) -> None:
        """A changed authoritative prefix invalidates and replaces cached turns."""
        self._append([{"event": "run_started", "message": "old"}])
        self._page()
        self.events.write_text(json.dumps({"event": "run_started", "message": "new-longer"}) + "\n", encoding="utf-8")

        page = self._page()

        self.assertEqual([turn["content"] for turn in page["messages"]], ["new-longer"])

    def test_agent_filter_pairs_tools_and_deduplicates_rounds(self) -> None:
        """Shared prompts, selected tools, steering, and round dedup stay stable."""
        round_event = {"event": "lifecycle", "type": "agent:round", "agent": "worker",
                       "data": {"round": 1, "assistant_content": "完成", "reasoning_content": "分析"}}
        self._append([
            {"event": "run_started", "message": "处理"},
            {"event": "lifecycle", "type": "agent:steer_applied", "agent": "coordinator",
             "data": {"messages": ["改方向"]}},
            {"event": "lifecycle", "type": "agent:tools_completed", "agent": "worker",
             "data": {"round": 1, "tool_calls": [{"name": "lookup", "args": {"词": "月"}, "result": {"ok": True}}]}},
            round_event,
            round_event,
        ])

        worker = self._page("worker")
        coordinator = self._page("all")

        self.assertEqual([turn["content"] for turn in worker["messages"]], ["处理", "完成"])
        self.assertEqual(worker["messages"][1]["tools"][0]["name"], "lookup")
        self.assertEqual([turn["content"] for turn in coordinator["messages"]], ["处理", "改方向"])

    def test_malformed_and_incomplete_lines_do_not_block_future_unicode(self) -> None:
        """Malformed records advance while an incomplete tail waits for completion."""
        self.events.write_bytes(b"not-json\n" + json.dumps({"event": "run_started", "message": "你好"}, ensure_ascii=False).encode("utf-8") + b"\n" + b'{"event":"result"')
        first = self._page()
        with self.events.open("ab") as handle:
            handle.write(b',"content":"ok"}\n')
        second = self._page()

        self.assertEqual([turn["content"] for turn in first["messages"]], ["你好"])
        self.assertEqual([turn["content"] for turn in second["messages"]], ["你好", "ok"])


if __name__ == "__main__":
    unittest.main()
