"""Regression coverage for browser hydration from Agent context files."""

import json
import tempfile
from pathlib import Path

from llmfetcher import webapp


def test_session_history_returns_display_turns_and_bounded_tool_results() -> None:
    """Restore user/assistant text together with persisted tool audit data."""
    with tempfile.TemporaryDirectory() as directory:
        original_root = webapp.WORKSPACE_ROOT
        webapp.WORKSPACE_ROOT = Path(directory)
        try:
            path = webapp._context_path("default", "session")
            path.parent.mkdir()
            path.write_text(json.dumps({"messages": [
                {"role": "user", "content": "Hello", "content_reasoning": ""},
                {"role": "assistant", "content": "# Hi", "content_reasoning": "Thinking", "tool_calls": [{"call": {"name": "lookup", "arguments": {"q": "test"}}, "result": "secret"}]},
            ]}), encoding="utf-8")
            history = webapp._read_session_history("default", "session")
            assert history[0]["content"] == "Hello"
            assert "<h1>Hi</h1>" in history[1]["content_html"]
            assert history[1]["tools"] == [{"name": "lookup", "arguments": {"q": "test"}, "result": "secret"}]
        finally:
            webapp.WORKSPACE_ROOT = original_root


def test_context_path_creates_agent_context_directory() -> None:
    """Provision the parent directory required for Agent context persistence."""
    with tempfile.TemporaryDirectory() as directory:
        original_root = webapp.WORKSPACE_ROOT
        webapp.WORKSPACE_ROOT = Path(directory)
        try:
            path = webapp._context_path("default", "session", "coordinator")
            assert path == Path(directory) / "default" / "contexts" / "coordinator.json"
            assert path.parent.is_dir()
        finally:
            webapp.WORKSPACE_ROOT = original_root


def test_session_history_falls_back_to_pre_session_directory_context() -> None:
    """Restore chats written before per-Agent session directories existed."""
    with tempfile.TemporaryDirectory() as directory:
        original_root = webapp.WORKSPACE_ROOT
        webapp.WORKSPACE_ROOT = Path(directory)
        try:
            legacy = webapp.WORKSPACE_ROOT / "default" / "session.json"
            legacy.parent.mkdir(parents=True)
            legacy.write_text(json.dumps({"messages": [
                {"role": "user", "content": "Legacy", "content_reasoning": ""},
            ]}), encoding="utf-8")
            assert webapp._read_session_history("default", "session") == [{
                "role": "user", "content": "Legacy", "reasoning": "", "tools": [],
            }]
        finally:
            webapp.WORKSPACE_ROOT = original_root
