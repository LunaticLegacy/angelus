"""Regression coverage for the lifecycle SSE frame order.

The browser renders a round's streamed deltas into a live card and removes that
card when the durable ``agent:round`` fact arrives.  If the durable page is
flushed before the ephemeral backlog, a round's trailing deltas are delivered
*after* the record that closed the round, so the browser re-creates a streaming
card for an already-finished round and nothing ever removes it.
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from angelus.api import session_console


class _StubService:
    """Serve one pending live frame and one durable round-closing fact."""

    def __init__(self) -> None:
        self.rounds: list[dict[str, object]] = [
            {"type": "agent:round", "agent": "coordinator", "data": {"round": 1}},
        ]
        self.live: list[dict[str, object]] = [
            {
                "type": "agent:stream_delta",
                "agent": "coordinator",
                "ephemeral": True,
                "ephemeral_sequence": 1,
                "data": {"round": 1, "channel": "content", "delta": "tail"},
            },
        ]

    def ephemeral_cursor(self, _session_id: str) -> int:
        """Expose a pending backlog instead of the new-subscriber skip."""
        # A fresh subscriber normally starts at the current sequence; this test
        # is about ordering, so the backlog must be visible.
        return 0

    def ephemeral_events(self, _session_id: str, cursor: int = 0) -> dict[str, object]:
        """Return every live frame newer than *cursor*."""
        pending = [event for event in self.live if int(event["ephemeral_sequence"]) > cursor]
        return {"events": pending, "next_cursor": cursor}

    def events(self, _session_id: str, cursor: int = 0, limit: int = 200) -> dict[str, object]:
        """Return the durable page for *cursor*."""
        return {
            "events": self.rounds[cursor:],
            "next_cursor": None,
            "has_more": False,
            "durable_offset": 0,
        }


def _frames(body: str) -> list[str]:
    """Split one SSE body into its non-empty frames."""
    return [frame for frame in body.split("\n\n") if frame.strip()]


class LifecycleEventStreamOrderTests(unittest.TestCase):
    """Pin the frame order the browser's live rendering depends on."""

    def _body(self, service: _StubService) -> str:
        """Open the lifecycle stream once and return its whole SSE body."""
        app = FastAPI()
        app.include_router(session_console.router)
        # An idle status makes the generator finish after one poll iteration.
        app.state.angelus_core = SimpleNamespace(
            execution_service=SimpleNamespace(
                status=lambda _session_id: SimpleNamespace(state="idle"),
            ),
        )
        with patch.object(session_console, "_service", return_value=service):
            with TestClient(app) as client:
                return client.get("/api/sessions/s1/events/stream").text

    def test_live_frames_precede_the_durable_record_that_closes_their_round(self) -> None:
        """A round's deltas must arrive before its own ``agent:round`` fact."""
        frames = _frames(self._body(_StubService()))

        self.assertEqual(2, len(frames), frames)
        self.assertIn("agent:stream_delta", frames[0])
        self.assertTrue(frames[0].startswith("data: "), frames[0])
        self.assertIn("agent:round", frames[1])
        self.assertTrue(frames[1].startswith("id: 1"), frames[1])

    def test_ephemeral_frames_never_carry_a_replay_id(self) -> None:
        """Live frames must not advance the durable Last-Event-ID cursor."""
        frames = _frames(self._body(_StubService()))

        live_frame = next(frame for frame in frames if "agent:stream_delta" in frame)
        self.assertTrue(live_frame.startswith("data: "), live_frame)
        self.assertNotIn("id:", live_frame)


if __name__ == "__main__": unittest.main()
