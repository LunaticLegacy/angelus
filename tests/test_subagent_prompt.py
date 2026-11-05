"""Regression coverage for the subagent report instruction."""
from __future__ import annotations

import unittest

from llmfetcher.swarm_module.execution_graph import ExecutionGraph
from llmfetcher.swarm_module.task_bus import (
    SUBAGENT_REPORT_INSTRUCTION,
    append_subagent_report_instruction,
)


class _Worker:
    def __init__(self, system_prompt: str) -> None:
        self.system_prompt = system_prompt
        self.hooks: list[object] = []

    def add_hook(self, hook: object) -> None:
        self.hooks.append(hook)


class SubagentPromptTests(unittest.TestCase):
    def test_instruction_is_appended_at_the_end_once(self) -> None:
        prompt = "You are a worker."
        decorated = append_subagent_report_instruction(prompt)

        self.assertTrue(decorated.startswith("You are a worker."))
        self.assertTrue(decorated.endswith(SUBAGENT_REPORT_INSTRUCTION))
        self.assertEqual(decorated, append_subagent_report_instruction(decorated))
        self.assertEqual(1, decorated.count(SUBAGENT_REPORT_INSTRUCTION))

    def test_blank_prompt_uses_the_instruction(self) -> None:
        self.assertEqual(
            SUBAGENT_REPORT_INSTRUCTION,
            append_subagent_report_instruction("   "),
        )

    def test_dispatch_task_extends_the_worker_system_prompt(self) -> None:
        graph = ExecutionGraph()
        agent = _Worker("You are a worker.")

        graph.dispatch_task(
            agent_name="worker",
            agent_instance=agent,
            objective="Inspect the target.",
            handoff="",
            reply_to="coordinator",
        )

        self.assertTrue(agent.system_prompt.endswith(SUBAGENT_REPORT_INSTRUCTION))


if __name__ == "__main__":
    unittest.main()
