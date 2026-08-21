"""Regression coverage for rebuilding a completed Swarm after process loss."""

from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path

from llmfetcher import Agent

from angelus import runtime, storage
from angelus.classes import ActiveRun, BrowserRunControl, RunConfig


class SwarmRestartRecoveryTests(unittest.TestCase):
    """Verify local snapshots retain graph identities without retaining keys."""

    def test_restore_rebuilds_worker_and_task_bus_after_process_restart(self) -> None:
        """A new ``ActiveRun`` restores terminal-ready Swarm topology from disk."""
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(directory)
            config = RunConfig(
                model="test-model", api_key="ephemeral-key", enable_swarm=True,
            )
            first_active = ActiveRun(control=BrowserRunControl())
            try:
                swarm = runtime._build_swarm(config, "demo", "demo", first_active)
                coordinator = swarm.get_agent("coordinator")
                self.assertIsNotNone(coordinator)
                worker = Agent(
                    llm_fetcher=coordinator.llm_fetcher,  # type: ignore[union-attr]
                    system_prompt="Worker-specific recovery prompt",
                )
                swarm.dispatch_task(
                    agent_name="worker", agent_instance=worker,
                    objective="Inspect the recovery path", handoff="bounded",
                    reply_to="coordinator",
                )
                swarm.finalize_tasks()
                runtime._persist_swarm_snapshot(swarm, "demo", "demo")

                restored_active = ActiveRun(control=BrowserRunControl())
                restored = runtime._restore_swarm(
                    config, "demo", "demo", restored_active,
                )

                self.assertIsNotNone(restored)
                self.assertEqual(restored.dispatched_agent_names(), ("worker",))  # type: ignore[union-attr]
                restored_worker = restored.get_agent("worker")  # type: ignore[union-attr]
                self.assertEqual(restored_worker.system_prompt, "Worker-specific recovery prompt")
                self.assertIn("report_task", {
                    tool.name for tool in restored_worker.tool_handler.get_all_tools()
                })
                snapshot = runtime._swarm_snapshot_path("demo", "demo").read_text(encoding="utf-8")
                self.assertNotIn("ephemeral-key", snapshot)
            finally:
                storage.WORKSPACE_ROOT = original_root

    def test_current_threshold_overwrites_retained_context_checkpoint(self) -> None:
        """Topology context cards must expose the threshold selected for this turn."""
        with tempfile.TemporaryDirectory() as directory:
            original_root = storage.WORKSPACE_ROOT
            storage.WORKSPACE_ROOT = Path(directory)
            config = RunConfig(
                model="test-model", api_key="ephemeral-key", enable_swarm=True,
                max_context_threshold=8192,
            )
            active = ActiveRun(control=BrowserRunControl())
            try:
                swarm = runtime._build_swarm(config, "demo", "demo", active)
                coordinator = swarm.get_agent("coordinator")
                self.assertIsNotNone(coordinator)
                coordinator.set_context_threshold(262144, persist=True)  # type: ignore[union-attr]

                synchronized = runtime._synchronize_swarm_context_threshold(swarm, config)

                context_path = storage._context_path("demo", "demo", "coordinator")
                stored = json.loads(context_path.read_text(encoding="utf-8"))
                self.assertIn("coordinator", synchronized)
                self.assertEqual(stored["compress_threshold"], 8192)
            finally:
                storage.WORKSPACE_ROOT = original_root


if __name__ == "__main__":
    unittest.main()
