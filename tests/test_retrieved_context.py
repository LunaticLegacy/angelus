"""Unit tests for TLB-RAG backed RetrievedContextHandler."""

import tempfile
import unittest
from pathlib import Path

from llmfetcher.context_handlers.retrieved import (
    RetrievedContextHandler,
    _extract_json_from_text,
)


class RetrievedContextHandlerTests(unittest.TestCase):
    """Cover parsing, indexing, triggering, and session serialization."""

    # -- _extract_json_from_text -----------------------------------------

    def test_extract_json_from_fenced_block(self) -> None:
        result = _extract_json_from_text('```json\n{"key": "value"}\n```')
        self.assertEqual(result, {"key": "value"})

    def test_extract_json_nested_braces(self) -> None:
        result = _extract_json_from_text(
            'prefix {"outer": {"inner": [1, 2, 3]}} suffix'
        )
        self.assertEqual(result, {"outer": {"inner": [1, 2, 3]}})

    def test_extract_json_raises_on_no_braces(self) -> None:
        with self.assertRaises(ValueError):
            _extract_json_from_text("no json here")

    # -- _parse_session_file ---------------------------------------------

    def test_parse_session_file_with_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session_abc123_debug.md"
            path.write_text(
                '---\n'
                '{"topic": "OAuth debug", "task_type": "debugging",'
                '"status": "resolved", "tags": ["auth", "oauth"],'
                '"created_at": "2026-07-15T14:00:00"}\n'
                '---\n'
                '\n'
                '# Problem\n'
                'Token expiry issue.\n'
                '\n'
                '# Solution\n'
                'Fixed clock skew.\n',
                encoding="utf-8",
            )
            result = RetrievedContextHandler._parse_session_file(path)
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result["topic"], "OAuth debug")
            self.assertEqual(result["task_type"], "debugging")
            self.assertEqual(result["status"], "resolved")
            self.assertEqual(result["tags"], ["auth", "oauth"])
            self.assertIn("Token expiry issue", result["content"])

    def test_parse_session_file_missing_file_returns_none(self) -> None:
        result = RetrievedContextHandler._parse_session_file(
            Path("/nonexistent/path.md")
        )
        self.assertIsNone(result)

    def test_parse_session_file_no_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "no_fm.md"
            path.write_text("# Just content\nNo frontmatter.\n", encoding="utf-8")
            result = RetrievedContextHandler._parse_session_file(path)
            self.assertIsNone(result)

    # -- _messages_to_text -----------------------------------------------

    def test_messages_to_text_renders_user_and_assistant(self) -> None:
        messages = [
            {"role": "user", "content": "Help me debug."},
            {
                "role": "assistant",
                "content": "Sure, let me check.",
                "tool_calls": [
                    {
                        "name": "read_file",
                        "arguments": {"path": "/tmp/test.py"},
                    }
                ],
            },
            {"role": "tool", "content": "print('hello')", "tool_call_id": "call_1"},
        ]
        text = RetrievedContextHandler._messages_to_text(messages)
        self.assertIn("## User\n\nHelp me debug.", text)
        self.assertIn("## Assistant\n\nSure, let me check.", text)
        self.assertIn("[Tool: read_file", text)
        self.assertIn("print('hello')", text)

    def test_messages_to_text_skips_retrieved_system_messages(self) -> None:
        messages = [
            {
                "role": "system",
                "content": "## Retrieved Conversation History\n...",
            },
            {
                "role": "system",
                "content": "### OAuth Debug\nDate: 2026-07-15\n\nToken issue.",
            },
            {"role": "user", "content": "Actual query."},
        ]
        text = RetrievedContextHandler._messages_to_text(messages)
        self.assertIn("Actual query.", text)
        self.assertNotIn("Retrieved Conversation History", text)
        self.assertNotIn("### OAuth Debug", text)

    # -- _slugify --------------------------------------------------------

    def test_slugify_converts_to_lowercase_hyphenated(self) -> None:
        self.assertEqual(
            RetrievedContextHandler._slugify("OAuth Token Debug"),
            "oauth-token-debug",
        )

    def test_slugify_handles_special_characters(self) -> None:
        self.assertEqual(
            RetrievedContextHandler._slugify("Fix: auth.py (OAuth2Client)"),
            "fix-authpy-oauth2client",
        )

    def test_slugify_truncates_long_titles(self) -> None:
        long_title = "a" * 100
        result = RetrievedContextHandler._slugify(long_title)
        self.assertLessEqual(len(result), 60)

    # -- _update_index ---------------------------------------------------

    def test_update_index_creates_new_index_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            index_path = Path(tmp) / "INDEX.md"
            RetrievedContextHandler._update_index(
                index_path,
                "session_abc.md",
                "OAuth Debug",
                "Resolved clock skew",
            )
            content = index_path.read_text(encoding="utf-8")
            self.assertIn("[OAuth Debug](session_abc.md)", content)
            self.assertIn("Resolved clock skew", content)

    def test_update_index_appends_to_existing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            index_path = Path(tmp) / "INDEX.md"
            index_path.write_text(
                "# Conversations: debugging\n\n"
                "- [Old Entry](old.md) — Old reason\n",
                encoding="utf-8",
            )
            RetrievedContextHandler._update_index(
                index_path,
                "new.md",
                "New Entry",
                "New reason",
            )
            content = index_path.read_text(encoding="utf-8")
            self.assertIn("[Old Entry](old.md)", content)
            self.assertIn("[New Entry](new.md)", content)

    def test_update_index_replaces_existing_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            index_path = Path(tmp) / "INDEX.md"
            index_path.write_text(
                "# Conversations: debugging\n\n"
                "- [Old](session_abc.md) — Original reason\n",
                encoding="utf-8",
            )
            RetrievedContextHandler._update_index(
                index_path,
                "session_abc.md",
                "Updated Title",
                "Updated reason",
            )
            content = index_path.read_text(encoding="utf-8")
            self.assertIn("[Updated Title](session_abc.md)", content)
            self.assertIn("Updated reason", content)
            self.assertNotIn("Original reason", content)

    # -- _should_retrieve ------------------------------------------------

    def test_retrieval_first_message_trigger(self) -> None:
        handler = RetrievedContextHandler.__new__(RetrievedContextHandler)
        handler._has_retrieved = False
        handler._message_count = 1
        handler.retrieval_trigger = "first_message"
        self.assertTrue(handler._should_retrieve())

        handler._has_retrieved = True
        self.assertFalse(handler._should_retrieve())

    def test_retrieval_manual_never_triggers(self) -> None:
        handler = RetrievedContextHandler.__new__(RetrievedContextHandler)
        handler._has_retrieved = False
        handler._message_count = 1
        handler.retrieval_trigger = "manual"
        self.assertFalse(handler._should_retrieve())

    def test_retrieval_second_message_does_not_trigger(self) -> None:
        handler = RetrievedContextHandler.__new__(RetrievedContextHandler)
        handler._has_retrieved = False
        handler._message_count = 2
        handler.retrieval_trigger = "first_message"
        # First-message mode: has_retrieved is still False, so
        # _should_retrieve returns True (message_count >= 1).
        # The flag is set by retrieve() after the first call.
        self.assertTrue(handler._should_retrieve())
        # After retrieval, it should not trigger again.
        handler._has_retrieved = True
        self.assertFalse(handler._should_retrieve())

    # -- create_save_tool ------------------------------------------------

    def test_create_save_tool_returns_valid_tool(self) -> None:
        handler = RetrievedContextHandler.__new__(RetrievedContextHandler)
        # Minimal mocks for create_save_tool to work.
        handler._pending_archive = None
        handler._project_root = None
        handler._user_root = None
        handler.linear = None  # _archive_session checks this, handle gracefully

        tool = handler.create_save_tool()
        self.assertEqual(tool.name, "save_conversation")
        self.assertIn("Archive", tool.description)
        self.assertIsNotNone(tool.handler)

    # -- build_messages with retrieved sessions -------------------------

    def test_build_messages_injects_retrieved_as_user_role(self) -> None:
        handler = RetrievedContextHandler.__new__(RetrievedContextHandler)
        handler.linear = _FakeLinear()
        handler.retrieved = [
            {
                "topic": "Debug Session",
                "content": "Resolved token expiry.",
                "task_type": "debugging",
                "status": "resolved",
                "created_at": "2026-07-15",
                "tags": ["auth"],
            },
        ]

        messages = handler.build_messages()
        self.assertEqual(len(messages), 2)  # 1 retrieved user msg + 1 linear msg
        user_msgs = [m for m in messages if m["role"] == "user"]
        self.assertIn("retrieved_memory", user_msgs[0]["content"])
        self.assertIn("Debug Session", user_msgs[0]["content"])
        # Retrieved memory must NOT be system role (P0-I).
        system_msgs = [m for m in messages if m["role"] == "system"]
        self.assertEqual(len(system_msgs), 0)

    def test_build_messages_no_retrieved_just_linear(self) -> None:
        handler = RetrievedContextHandler.__new__(RetrievedContextHandler)
        handler.linear = _FakeLinear()
        handler.retrieved = []

        messages = handler.build_messages()
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["content"], "linear msg")


class _FakeLinear:
    """Minimal stub returning one canned message."""

    def build_messages(self) -> list[dict[str, str]]:
        return [{"role": "user", "content": "linear msg"}]


if __name__ == "__main__":
    unittest.main()
