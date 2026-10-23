"""Concurrency regression coverage for the live swarm-graph write path.

When an attempt is active the gateway persists the blueprint and then applies
the mutation to the live ``AgentSwarm``. A rejection must roll back only its
own snapshot, and a live rejection must also remove the node it added.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import threading
import unittest
from unittest.mock import patch

from angelus.core import AngelusCore
from angelus.modules.console_module import ConsoleDomainError
from angelus.modules.execution_module import ExecutionState
from llmfetcher.swarm_module.snapshots import SwarmViewSnapshot


class _Execution:
    """Minimal attempt façade that makes the gateway take the live path."""

    def __init__(self) -> None:
        self.root = Path(".")

    def snapshot(self) -> SimpleNamespace:
        """Return an active attempt so ``_is_live`` is true."""
        return SimpleNamespace(
            state=ExecutionState.RUNNING, execution_id="exec-test"
        )


class _LiveSwarm:
    """Record live mutations without constructing real Agents."""

    def __init__(self) -> None:
        self.added: list[str] = []
        self.removed: list[str] = []
        self.reject = False

    def view_snapshot(self) -> SwarmViewSnapshot:
        """Return an empty live view accepted by the gateway."""
        return SwarmViewSnapshot(
            nodes=(),
            edges=(),
            max_concurrency_agents=3,
            assignments={},
            task_states={},
            node_states={},
        )

    def dynamic_add_agent(self, name: str, _agent: object) -> str:
        """Accept one live node unless the test flips ``reject``."""
        if self.reject:
            return "Error: rejected"
        self.added.append(name)
        return f"Added: {name}"

    def dynamic_remove_agent(self, name: str) -> str:
        """Record live rollback of a node."""
        self.removed.append(name)
        return f"Removed: {name}"


class SwarmGraphLiveConcurrencyTests(unittest.TestCase):
    def _core(self, directory: str) -> AngelusCore:
        """Build a Session whose attempt is active and whose projector is inert."""
        root = Path(directory)
        (root / "project").mkdir()
        core = AngelusCore(state_root=root / "state")
        core.session_service.create("demo", "Demo", root / "project")
        session = core.sessions.get("demo")
        session.execution = _Execution()  # type: ignore[assignment]
        core.swarm_graph._projector = SimpleNamespace(
            project=lambda *args, **kwargs: {
                "nodes": [],
                "edges": [],
                "state": "running",
            }
        )
        return core

    def test_live_add_persists_the_blueprint_and_the_live_node(self) -> None:
        """An accepted live mutation reaches both the durable and live graphs."""
        with TemporaryDirectory() as directory:
            core = self._core(directory)
            session = core.sessions.get("demo")
            swarm = _LiveSwarm()
            session.swarm = swarm  # type: ignore[assignment]
            sentinel = object()

            with patch.object(
                core.session_service, "create_runtime_worker", return_value=sentinel
            ):
                core.swarm_graph.add_agent("demo", "worker", "prompt")

            self.assertIn("worker", session.console.blueprint().workers)
            self.assertEqual(["worker"], swarm.added)
            self.assertIn(sentinel, session.agents)

    def test_live_rejection_removes_the_node_it_added(self) -> None:
        """A live rejection restores the blueprint and rolls back the live node."""
        with TemporaryDirectory() as directory:
            core = self._core(directory)
            session = core.sessions.get("demo")
            swarm = _LiveSwarm()
            swarm.reject = True
            session.swarm = swarm  # type: ignore[assignment]

            with patch.object(
                core.session_service, "create_runtime_worker", return_value=object()
            ):
                with self.assertRaises(ConsoleDomainError):
                    core.swarm_graph.add_agent("demo", "worker", "prompt")

            self.assertNotIn("worker", session.console.blueprint().workers)
            self.assertEqual(["worker"], swarm.removed)

    def test_rejected_live_add_does_not_erase_a_concurrent_success(self) -> None:
        """A duplicate rejection must not roll back another thread's worker."""
        with TemporaryDirectory() as directory:
            core = self._core(directory)
            session = core.sessions.get("demo")
            swarm = _LiveSwarm()
            session.swarm = swarm  # type: ignore[assignment]
            with patch.object(
                core.session_service, "create_runtime_worker", return_value=object()
            ):
                core.swarm_graph.add_agent("demo", "existing", "prompt")
                barrier = threading.Barrier(2)

                def add(name: str) -> str:
                    barrier.wait(10)
                    try:
                        core.swarm_graph.add_agent("demo", name, "prompt")
                        return "ok"
                    except ConsoleDomainError:
                        return "rejected"

                with ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(pool.map(add, ("existing", "fresh")))

            workers = set(session.console.blueprint().workers)
            self.assertEqual(["ok", "rejected"], sorted(results))
            self.assertIn("existing", workers)
            self.assertIn("fresh", workers)


if __name__ == "__main__":
    unittest.main()
