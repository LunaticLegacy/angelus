"""Regression coverage for Angelus Agent construction defaults."""

from __future__ import annotations

from unittest.mock import patch
import unittest

from llmfetcher import LLMBackendConfig

from angelus.modules.session_module.agent_handler import create_agent


class AgentDefaultTests(unittest.TestCase):
    """Ensure product defaults reach llmfetcher instead of remaining UI-only."""

    def test_agents_stream_by_default(self) -> None:
        """The factory opts every Session-created Agent into streaming.

        Returns:
            ``None`` after inspecting the Agent construction call.
        """
        with patch("angelus.modules.session_module.agent_handler.LLMFetcher"), patch(
            "angelus.modules.session_module.agent_handler.Agent",
        ) as agent_class:
            create_agent(
                [LLMBackendConfig(name="test", provider="openai", model="model", api_key="key")],
                [],
                system_prompt="test",
                context_handler=object(),
            )
        self.assertTrue(agent_class.call_args.kwargs["default_stream"])


if __name__ == "__main__":
    unittest.main()
