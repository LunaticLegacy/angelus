"""Regression coverage for browser-configured context compaction."""

from __future__ import annotations

import unittest

from llmfetcher import webapp


class WebAppContextThresholdTests(unittest.TestCase):
    """Ensure the browser context setting reaches newly built Agents."""

    def test_default_context_threshold_is_262144_characters(self) -> None:
        """Keep the documented default compaction threshold stable."""
        self.assertEqual(webapp.RunConfig(model="demo").max_context_threshold, 262144)

    def test_build_agent_uses_browser_context_threshold(self) -> None:
        """Pass a session's configured threshold into its history handler."""
        config = webapp.RunConfig(
            model="demo",
            api_key="test-key",
            max_context_threshold=8192,
        )
        agent = webapp._build_agent(config, "context-test", "context-test")

        self.assertEqual(agent.max_context_threshold, 8192)
        self.assertEqual(agent.context_handler.compress_threshold, 8192)

    def test_context_threshold_rejects_unusable_values(self) -> None:
        """Reject values too small to retain a useful conversation history."""
        with self.assertRaises(ValueError):
            webapp.RunConfig(model="demo", max_context_threshold=1023)


if __name__ == "__main__":
    unittest.main()
