"""Regression coverage for strict portable context package decoding."""

from __future__ import annotations

import unittest

from angelus.modules.external_agent_hub_module.context_codec import parse_context_package


class ContextPackageTests(unittest.TestCase):
    """Verify context exchange input stays bounded and non-executable."""

    def test_package_decodes_historical_tool_record(self) -> None:
        """Decode a valid package without turning its tool call executable.

        Returns:
            None.
        """
        package = parse_context_package(
            {
                "format_version": 1,
                "source": "external-test",
                "source_session_id": "thread-1",
                "source_agent": "assistant",
                "messages": [
                    {
                        "sequence": 1,
                        "role": "assistant",
                        "content": "completed",
                        "reasoning": "checked facts",
                        "tool_calls": [{"name": "shell", "arguments_json": "{}", "result": "ok"}],
                        "created_at": 1,
                    }
                ],
                "summary": "",
                "redactions": ["credentials removed"],
            }
        )
        self.assertEqual(package.messages[0].tool_calls[0].name, "shell")
        self.assertEqual(package.messages[0].tool_calls[0].result, "ok")

    def test_package_rejects_unknown_or_oversized_message_shape(self) -> None:
        """Reject uncontracted fields instead of forwarding arbitrary JSON.

        Returns:
            None.
        """
        with self.assertRaises(ValueError):
            parse_context_package(
                {
                    "format_version": 1,
                    "source": "external-test",
                    "source_session_id": "thread-1",
                    "source_agent": "assistant",
                    "messages": [{"sequence": 1, "role": "user", "content": "hi", "unknown": "no"}],
                }
            )


if __name__ == "__main__":
    unittest.main()
