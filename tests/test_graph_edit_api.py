"""Regression coverage for browser-side live graph editing endpoints."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from angelus import storage, webapp
from angelus.api import sessions as api


def _install_live_swarm(session_id: str = "demo") -> None:
    """Register a session holder with a live coordinator-led Swarm."""
    key = (session_id, session_id)
    with storage._sessions_lock:
        storage._sessions[key] = webapp.BrowserSession(
            active=webapp.ActiveRun(control=webapp.BrowserRunControl()),
        )
    session = storage._sessions[key]
    swarm = webapp._build_swarm(
        webapp.RunConfig(model="demo", api_key="test-key"),
        session_id, session_id, session.active,
    )
    session.active.swarm = swarm


class GraphEditApiTests(unittest.TestCase):
    """Exercise the graph editing toolbar endpoints against a live Swarm."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._original_root = storage.WORKSPACE_ROOT
        storage.WORKSPACE_ROOT = Path(self._tmp.name)

    def tearDown(self) -> None:
        storage.WORKSPACE_ROOT = self._original_root
        with storage._sessions_lock:
            for key in list(storage._sessions):
                storage._sessions.pop(key, None)
        self._tmp.cleanup()

    def _expect_http(self, status_code: int, call) -> None:
        with self.assertRaises(HTTPException) as raised:
            call()
        self.assertEqual(raised.exception.status_code, status_code)

    def test_mutations_reject_sessions_without_a_live_swarm(self) -> None:
        """Every mutation requires an active Swarm; absent/done holders 409."""
        with storage._sessions_lock:
            storage._sessions[("none", "none")] = webapp.BrowserSession()
            storage._sessions[("noswarm", "noswarm")] = webapp.BrowserSession(
                active=webapp.ActiveRun(control=webapp.BrowserRunControl()),
            )
        request = api.GraphAgentRequest(name="worker-1", system_prompt="You are a worker.")
        self._expect_http(409, lambda: api.add_graph_agent("none", request))
        self._expect_http(409, lambda: api.add_graph_agent("noswarm", request))
        self._expect_http(409, lambda: api.get_graph_edit_info("none"))

        _install_live_swarm("done")
        storage._sessions[("done", "done")].active.done.set()
        self._expect_http(409, lambda: api.add_graph_agent("done", request))

    def test_happy_path_mutates_topology_and_persists_view_and_events(self) -> None:
        """Add/connect/mapper/router/remove round-trips through the live graph."""
        _install_live_swarm()
        session = storage._sessions[("demo", "demo")]

        added = api.add_graph_agent(
            "demo", api.GraphAgentRequest(name="worker-1", system_prompt="You are a worker."),
        )
        self.assertTrue(added["ok"])
        self.assertEqual(added["agent"], "worker-1")
        self.assertIn("created", added["status"])
        self.assertIsNotNone(session.active.swarm.get_agent("worker-1"))

        connected = api.add_graph_connection(
            "demo", api.GraphConnectionRequest(source="coordinator", target="worker-1"),
        )
        self.assertIn("Connected", connected["status"])

        mapped = api.set_graph_mapper(
            "demo", api.GraphMapperRequest(agent="worker-1", mode="concat"),
        )
        self.assertIn("concat", mapped["status"])

        routed = api.set_graph_router(
            "demo", api.GraphRouterRequest(agent="coordinator", targets=["worker-1"]),
        )
        self.assertIn("worker-1", routed["status"])

        info = api.get_graph_edit_info("demo")
        self.assertEqual(info["nodes"], ["coordinator", "worker-1"])
        self.assertEqual(
            info["edges"],
            [{"source": "coordinator", "target": "worker-1", "kind": "dependency"}],
        )
        self.assertEqual(info["max_concurrency_agents"], 4)

        disconnected = api.remove_graph_connection(
            "demo", source="coordinator", target="worker-1",
        )
        self.assertIn("Disconnected", disconnected["status"])

        removed = api.remove_graph_agent("demo", name="worker-1")
        self.assertIn("removed", removed["status"])
        self.assertIsNone(session.active.swarm.get_agent("worker-1"))

        # The persisted graph-view.json reflects the final topology.
        graph_path = storage._session_path("demo", "demo") / "graph-view.json"
        self.assertTrue(graph_path.exists())
        persisted = json.loads(graph_path.read_text(encoding="utf-8"))
        self.assertEqual(
            [node["id"] for node in persisted["nodes"]], ["coordinator"],
        )

        # Every mutation produced a durable graph_edit:* lifecycle event.
        event_log = (storage._session_path("demo", "demo") / "events.ndjson").read_text(encoding="utf-8")
        for action in (
            "add_agent", "add_connection", "set_mapper", "set_router",
            "remove_connection", "remove_agent",
        ):
            self.assertIn(f"graph_edit:{action}", event_log)

    def test_duplicate_agent_and_unknown_targets_are_rejected(self) -> None:
        """Duplicate names, unknown nodes, and bad mapper modes return 409."""
        _install_live_swarm()
        api.add_graph_agent(
            "demo", api.GraphAgentRequest(name="dup", system_prompt="p"),
        )
        self._expect_http(
            409,
            lambda: api.add_graph_agent(
                "demo", api.GraphAgentRequest(name="dup", system_prompt="p"),
            ),
        )
        self._expect_http(409, lambda: api.remove_graph_agent("demo", name="nope"))
        self._expect_http(
            409,
            lambda: api.add_graph_connection(
                "demo", api.GraphConnectionRequest(source="coordinator", target="ghost"),
            ),
        )
        self._expect_http(
            409,
            lambda: api.set_graph_mapper(
                "demo", api.GraphMapperRequest(agent="coordinator", mode="bogus"),
            ),
        )
        self._expect_http(
            409,
            lambda: api.set_graph_router(
                "demo", api.GraphRouterRequest(agent="coordinator", targets=["ghost"]),
            ),
        )

    def test_coordinator_is_protected_and_names_are_validated(self) -> None:
        """Removing the coordinator is a 400; unsafe names are rejected."""
        _install_live_swarm()
        self._expect_http(400, lambda: api.remove_graph_agent("demo", name="coordinator"))
        self._expect_http(
            400,
            lambda: api.add_graph_agent(
                "demo", api.GraphAgentRequest(name="bad name!", system_prompt="p"),
            ),
        )
        self._expect_http(
            400,
            lambda: api.add_graph_connection(
                "demo", api.GraphConnectionRequest(source="coordinator", target="bad name!"),
            ),
        )


if __name__ == "__main__":
    unittest.main()
