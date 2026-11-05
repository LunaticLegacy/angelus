"""The console entity-graph payload is a typed projection, not a dict bag.

The graph belongs to ``graph_memory``; every context handler answers
``graph_projection()`` so a handler without a long-term graph reports an empty
projection instead of raising ``AttributeError`` on ``handler.store``.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from angelus.modules.console_module.projection_service import ConsoleProjectionService
from llmfetcher.context_handlers.linear import ContextHandlerLinear
from llmfetcher.graph_memory import GraphContextHandler, GraphStore
from llmfetcher.graph_memory.projection import ContextGraphProjection

WIRE_KEYS = {
    "available",
    "stale",
    "truncated",
    "node_count",
    "edge_count",
    "community_count",
    "nodes",
    "edges",
    "communities",
}


class _Swarm:
    def __init__(self, agent: object | None) -> None:
        self._agent = agent

    def get_agent(self, name: str) -> object | None:
        return self._agent


class _Sessions:
    def __init__(self, session: object) -> None:
        self._session = session

    def get(self, session_id: str) -> object:
        return self._session


class _Workspaces:
    def __init__(self, state_path: Path) -> None:
        self._state_path = state_path

    def get(self, session_id: str) -> object:
        return SimpleNamespace(state_path=self._state_path)


class _Core:
    def __init__(self, session: object, state_path: Path) -> None:
        self.sessions = _Sessions(session)
        self.workspaces = _Workspaces(state_path)


def _service(handler: object | None, state_path: Path) -> ConsoleProjectionService:
    session = SimpleNamespace(swarm=_Swarm(handler))
    return ConsoleProjectionService(_Core(session, state_path))


class ContextGraphProjectionTests(unittest.TestCase):
    def test_linear_handler_reports_an_empty_projection(self) -> None:
        """A handler without an entity graph answers empty instead of raising."""
        handler = ContextHandlerLinear(None)

        projection = handler.graph_projection()

        self.assertFalse(projection.available)
        self.assertEqual(0, projection.node_count)
        self.assertEqual(WIRE_KEYS, set(projection.to_json()))

    def test_console_context_graph_survives_a_linear_agent(self) -> None:
        """The route that used to read ``handler.store`` now projects any handler."""
        with tempfile.TemporaryDirectory() as directory:
            handler = ContextHandlerLinear(None)
            service = _service(SimpleNamespace(context_handler=handler), Path(directory))

            result = service.context_graph("session", "coordinator")

            self.assertEqual("coordinator", result["agent"])
            graph = result["graph"]
            self.assertIsInstance(graph, dict)
            self.assertFalse(graph["available"])
            self.assertEqual(WIRE_KEYS, set(graph))

    def test_graph_handler_projects_nodes_edges_and_staleness(self) -> None:
        """The graph handler maps its store without leaking embeddings."""
        handler = GraphContextHandler(compacting_fetcher=None)
        store = handler.store
        left = store.upsert_entity("GraphStore", "class", aliases=["graph_store"])
        right = store.upsert_entity("ContextHandler", "class")
        store.upsert_relation(left.id, right.id, "implements", timeline=3, evidence=[3])
        handler.linear.context_editing["graph_stale"] = True

        projection = handler.graph_projection()
        payload = projection.to_json()

        self.assertTrue(projection.available)
        self.assertEqual(2, projection.node_count)
        self.assertEqual(1, projection.edge_count)
        self.assertTrue(projection.stale)
        self.assertNotIn("embedding", json.dumps(payload))
        self.assertEqual(list(left.aliases), payload["nodes"][0]["aliases"])  # type: ignore[index]

    def test_persisted_generation_decodes_into_the_same_projection(self) -> None:
        """A role that cannot be materialised reads the committed companion."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            agent_dir = root / "agents" / "coordinator"
            agent_dir.mkdir(parents=True)
            store = GraphStore()
            store.upsert_entity("Alpha", "concept")
            companion = "context.json.graph.abc"
            (agent_dir / companion).write_text(json.dumps(store.to_dict()), encoding="utf-8")
            (agent_dir / "context.json").write_text(
                json.dumps({
                    "schema_version": 3,
                    "storage": "sqlite",
                    "database": "context.json.sqlite3",
                    "graph_checkpoint": companion,
                    "context_editing": {"graph_stale": True},
                }),
                encoding="utf-8",
            )
            service = _service(None, root)

            projection = service._persisted_graph_projection("session", "coordinator")

            self.assertEqual(1, projection.node_count)
            self.assertTrue(projection.stale)
            self.assertEqual(ContextGraphProjection.empty().to_json().keys(), projection.to_json().keys())


if __name__ == "__main__":
    unittest.main()
