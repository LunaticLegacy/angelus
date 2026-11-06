"""Regression tests: both console SSE routes must follow every active state.

The browser's run-stream controller resumes a stream whenever ``onerror`` fires
and ``/api/runs/{id}/status`` still reports ``active``.  A state that the status
route calls active but an SSE route treats as terminal therefore closes, is
resumed one retry delay later, and closes again -- the "寿命周期/执行图连接中断"
banner flaps forever.  A swarm spends seconds in the preparation states before
``RUNNING``, which is why such a split only became visible with a swarm enabled.

The expectations below are written as a literal table on purpose: they must pin
both the status wire flag and the two stream lifetimes to the same contract
instead of re-reading whichever table the production code happens to use.
"""
from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from angelus.api import runs as runs_api
from angelus.api import session_console
from angelus.modules.execution_module import ExecutionState, is_active_state
from angelus.modules.execution_module.state import ACTIVE_STATE_VALUES

# Literal contract: states in which an attempt still owns live work.
ACTIVE = {
    "queued",
    "preparing",
    "materializing_tools",
    "connecting_mcp",
    "materializing_swarm",
    "loading_context",
    "running",
    "stopping",
    "force_stopping",
}


class _StillFollowing(Exception):
    """Raised from the faked ``time.sleep``: the stream kept polling."""


def _stop_polling(*_args: object, **_kwargs: object) -> None:
    raise _StillFollowing()


def _lifetime(response: object) -> str:
    """Drive one SSE generator until its first poll or its early return.

    Args:
        response: Streaming response produced by the route under test.

    Returns:
        ``"following"`` when the generator reached its keep-alive sleep (so the
        browser would stay connected) or ``"closed"`` when it returned.
    """

    async def drain() -> None:
        async for _chunk in response.body_iterator:  # type: ignore[attr-defined]
            pass

    try:
        asyncio.run(drain())
    except _StillFollowing:
        return "following"
    return "closed"


def _status(state: ExecutionState) -> SimpleNamespace:
    """Build the minimal snapshot the routes and the wire flag both read."""
    return SimpleNamespace(
        session_id="demo", execution_id="run-1", attempt=1, state=state,
        started_at=1_000.0, finished_at=None, error=None,
    )


def _request(service: object, status: object) -> SimpleNamespace:
    """Wrap a fake projection service in the request shape the routes expect."""
    core = SimpleNamespace(
        execution_service=SimpleNamespace(status=lambda _session_id: status),
        console_service=service,
    )
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(angelus_core=core)))


def _graph_lifetime(state: ExecutionState) -> str:
    """Return whether ``/graph/events`` keeps following an attempt in ``state``."""
    service = SimpleNamespace(
        graph_events=lambda *_args, **_kwargs: {
            "events": [], "next_cursor": 0, "has_more": False, "execution_id": "run-1"},
        ephemeral_cursor=lambda _session_id: 0,
    )
    status = _status(state)
    with patch.object(session_console, "_service", lambda _request: service), \
            patch.object(session_console, "time", SimpleNamespace(sleep=_stop_polling)):
        response = session_console.graph_events(
            "demo", _request(service, status), cursor=0, last_event_id=None)
        return _lifetime(response)


def _lifecycle_lifetime(state: ExecutionState) -> str:
    """Return whether ``/events/stream`` keeps following an attempt in ``state``."""
    service = SimpleNamespace(
        events=lambda *_args, **_kwargs: {"events": []},
        ephemeral_cursor=lambda _session_id: 0,
        ephemeral_events=lambda *_args, **_kwargs: {"events": []},
    )
    status = _status(state)
    with patch.object(session_console, "_service", lambda _request: service), \
            patch.object(session_console, "time", SimpleNamespace(sleep=_stop_polling)):
        response = session_console.events_stream(
            "demo", _request(service, status), cursor=0, last_event_id=None)
        return _lifetime(response)


class ActiveStateTableTests(unittest.TestCase):
    """The shared table must match the literal lifecycle contract exactly."""

    def test_active_states_are_the_non_terminal_states(self) -> None:
        """Every non-terminal state is active; idle and terminals are not."""
        for state in ExecutionState:
            with self.subTest(state=state.value):
                self.assertEqual(state.value in ACTIVE, is_active_state(state))

    def test_active_table_matches_every_declared_state(self) -> None:
        """The table is exhaustive: no state is silently missing or extra."""
        self.assertEqual(ACTIVE, set(ACTIVE_STATE_VALUES))
        self.assertEqual({state.value for state in ExecutionState},
                         ACTIVE | {"idle", "completed", "stopped", "interrupted", "failed"})

    def test_accepts_wire_strings_and_enum_members(self) -> None:
        """Both the canonical enum and its lowercase wire string are understood."""
        for state in ExecutionState:
            with self.subTest(state=state.value):
                self.assertEqual(is_active_state(state), is_active_state(state.value))

    def test_run_status_wire_flag_uses_the_same_table(self) -> None:
        """``/api/runs/{id}/status`` reports ``active`` from the same contract."""
        for state in ExecutionState:
            with self.subTest(state=state.value):
                wire = runs_api._status_wire(_status(state))
                self.assertEqual(state.value, wire["status"])
                self.assertEqual(state.value in ACTIVE, wire["active"])


class StreamFollowsActiveStatesTests(unittest.TestCase):
    """Neither route may close while the status wire still says active.

    Closing there is exactly what the browser answers with a resume banner and a
    one-second reconnect, so the two lifetimes are the bug's own observable.
    """

    def test_graph_events_follows_exactly_the_active_states(self) -> None:
        """``/graph/events`` survives every active state and closes on terminals."""
        for state in ExecutionState:
            with self.subTest(state=state.value):
                expected = "following" if state.value in ACTIVE else "closed"
                self.assertEqual(expected, _graph_lifetime(state))

    def test_events_stream_follows_exactly_the_active_states(self) -> None:
        """``/events/stream`` survives every active state and closes on terminals."""
        for state in ExecutionState:
            with self.subTest(state=state.value):
                expected = "following" if state.value in ACTIVE else "closed"
                self.assertEqual(expected, _lifecycle_lifetime(state))

    def test_swarm_startup_states_do_not_close_either_stream(self) -> None:
        """The preparation phases a swarm passes through keep both streams open.

        This is the reported defect: swarm startup is long enough for the browser
        to render the reconnect banner once per second while the run was healthy.
        """
        startup = ("preparing", "materializing_tools", "connecting_mcp",
                   "materializing_swarm", "loading_context")
        for value in startup:
            with self.subTest(state=value):
                state = ExecutionState(value)
                self.assertEqual("following", _graph_lifetime(state))
                self.assertEqual("following", _lifecycle_lifetime(state))
                self.assertTrue(runs_api._status_wire(_status(state))["active"])


if __name__ == "__main__":
    unittest.main()
