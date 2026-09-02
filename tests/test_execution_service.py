"""Regression coverage for Session-swarm execution outcome ownership."""
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from angelus.core import AngelusCore
from angelus.modules.execution_module import ExecutionState
from llmfetcher.swarm_module import AgentFailure


class _FailingSwarm:
    """Minimal graph facade that reports an unsuccessful root Agent."""

    def __init__(self) -> None:
        """Create a facade with hook-registration accounting."""
        self.hooks: list[object] = []

    def add_hook(self, hook: object) -> None:
        """Retain a hook supplied by the execution service.

        Args:
            hook: Callback to retain for this simulated run.

        Returns:
            None.
        """
        self.hooks.append(hook)

    def remove_hook(self, hook: object) -> bool:
        """Remove one retained hook.

        Args:
            hook: Exact callback to remove.

        Returns:
            Whether the callback was registered.
        """
        if hook not in self.hooks:
            return False
        self.hooks.remove(hook)
        return True

    def run(self, _message: str, *, control: object) -> dict[str, object]:
        """Return the graph's normal non-fatal root failure marker.

        Args:
            _message: User instruction, unused by this deterministic double.
            control: Attempt controller passed through by the service.

        Returns:
            Output map containing the failed coordinator marker.
        """
        return {"coordinator": AgentFailure("coordinator", "provider unavailable")}


class ExecutionServiceTests(unittest.TestCase):
    """Ensure graph-level root failures become terminal attempt failures."""

    def test_root_agent_failure_marks_attempt_failed_and_removes_hook(self) -> None:
        """A coordinator AgentFailure cannot be recorded as completed output."""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "project").mkdir()
            core = AngelusCore(state_root=root / "state")
            core.session_service.create("demo", "Demo", root / "project")
            session = core.sessions.get("demo")
            swarm = _FailingSwarm()
            session.swarm = swarm  # type: ignore[assignment]
            session.agents = [object()]  # type: ignore[list-item]
            core.session_service.ensure_coordinator = lambda _session_id: None  # type: ignore[method-assign]

            core.execution_service.start("demo", "hello")
            self.assertTrue(session.execution.wait(1.0))
            snapshot = session.execution.snapshot()
            self.assertEqual(snapshot.state, ExecutionState.FAILED)
            self.assertIn("provider unavailable", snapshot.error or "")
            self.assertEqual(swarm.hooks, [])


if __name__ == "__main__":
    unittest.main()
