"""Concurrency regression coverage for the single swarm-graph write path.

The gateway serialises every topology mutation on the Session's
``console/state.json`` transaction, so concurrent writes must all survive and
a rejected write must roll back only its own snapshot.  Without that lock a
rejected duplicate could restore a stale blueprint and erase another thread's
committed worker.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import threading
import unittest

from angelus.core import AngelusCore
from angelus.modules.console_module import ConsoleDomainError


class SwarmGraphConcurrencyTests(unittest.TestCase):
    def _core(self, directory: str) -> AngelusCore:
        """Build one Session with a coordinator and a connector-backed profile.

        Returns:
            A core whose ``swarm_graph`` can materialize a live swarm.
        """
        root = Path(directory) / "state"
        project = Path(directory) / "project"
        project.mkdir()
        core = AngelusCore(state_root=root)
        core.session_service.create("alpha", "Alpha", project)
        connector = core.settings_service.create_connector(
            {
                "name": "Test",
                "provider": "openai",
                "model": "test-model",
                "api_url": "",
                "api_key": "secret",
            }
        )
        profile = core.settings_service.session_profile("alpha")["effective"]
        profile["connector_id"] = connector.id
        core.settings_service.replace_session_profile("alpha", profile)
        core.session_service.ensure_coordinator("alpha")
        return core

    def test_concurrent_add_agent_keeps_every_worker(self) -> None:
        """Six parallel adds must all reach the durable blueprint."""
        with TemporaryDirectory() as directory:
            core = self._core(directory)
            names = [f"worker{index}" for index in range(4)]
            barrier = threading.Barrier(len(names))

            def add(name: str) -> None:
                barrier.wait(10)
                core.swarm_graph.add_agent("alpha", name, f"prompt for {name}")

            with ThreadPoolExecutor(max_workers=len(names)) as pool:
                list(pool.map(add, names))

            session = core.sessions.get("alpha")
            self.assertEqual(set(names), set(session.console.blueprint().workers))
            document = json.loads(
                (Path(directory) / "state" / "sessions" / "alpha" / "console" / "state.json")
                .read_text(encoding="utf-8")
            )
            self.assertEqual(set(names), set(document["workers"]))

    def test_rejected_add_does_not_erase_a_concurrent_success(self) -> None:
        """A duplicate rejection must not roll back another thread's worker."""
        with TemporaryDirectory() as directory:
            core = self._core(directory)
            core.swarm_graph.add_agent("alpha", "existing", "prompt")
            barrier = threading.Barrier(2)

            def add(name: str) -> str:
                barrier.wait(10)
                try:
                    core.swarm_graph.add_agent("alpha", name, "prompt")
                    return "ok"
                except ConsoleDomainError:
                    return "rejected"

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(add, ("existing", "fresh")))

            workers = set(core.sessions.get("alpha").console.blueprint().workers)
            self.assertEqual(["ok", "rejected"], sorted(results))
            self.assertIn("existing", workers)
            self.assertIn("fresh", workers)

    def test_concurrent_connections_keep_both_edges(self) -> None:
        """Two parallel edge additions must both persist."""
        with TemporaryDirectory() as directory:
            core = self._core(directory)
            for name in ("left", "middle", "right"):
                core.swarm_graph.add_agent("alpha", name, "prompt")
            barrier = threading.Barrier(2)

            def connect(pair: tuple[str, str]) -> None:
                barrier.wait(10)
                core.swarm_graph.add_connection("alpha", pair[0], pair[1])

            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(connect, (("left", "middle"), ("middle", "right"))))

            edges = {
                (edge.source, edge.target)
                for edge in core.sessions.get("alpha").console.blueprint().connections
            }
            self.assertIn(("left", "middle"), edges)
            self.assertIn(("middle", "right"), edges)


if __name__ == "__main__":
    unittest.main()
