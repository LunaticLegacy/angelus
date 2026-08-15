"""Regression coverage for browser hydration from Agent context files."""

import json
import tempfile
from pathlib import Path

from angelus import webapp


def test_session_history_returns_display_turns_and_bounded_tool_results() -> None:
    """Restore user/assistant text together with persisted tool audit data."""
    with tempfile.TemporaryDirectory() as directory:
        original_root = webapp.WORKSPACE_ROOT
        webapp.WORKSPACE_ROOT = Path(directory)
        try:
            path = webapp._context_path("default", "session")
            path.parent.mkdir(exist_ok=True)
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


def test_agent_history_rebuilds_all_runs_and_completed_tools_from_events() -> None:
    """Keep every browser prompt after Agent context compaction."""
    with tempfile.TemporaryDirectory() as directory:
        original_root = webapp.WORKSPACE_ROOT
        webapp.WORKSPACE_ROOT = Path(directory)
        try:
            session_path = webapp._session_path("doc", "doc")
            session_path.mkdir(parents=True, exist_ok=True)
            events = [
                {"event": "lifecycle", "type": "agent:start", "agent": "coordinator", "message": "First"},
                {"event": "lifecycle", "type": "agent:tools_completed", "agent": "coordinator", "data": {
                    "round": 1,
                    "tool_calls": [{"name": "shell", "args": {"command": "pwd"}, "result": "workspace", "ok": True}],
                }},
                {"event": "lifecycle", "type": "agent:round", "agent": "coordinator", "data": {
                    "round": 1, "assistant_content": "Done", "reasoning_content": "Check", "tool_calls": [],
                }},
                {"event": "result", "content": "Done", "reasoning": "Check"},
                {"event": "lifecycle", "type": "agent:start", "agent": "coordinator", "message": "Second"},
                {"event": "lifecycle", "type": "agent:round", "agent": "coordinator", "data": {
                    "round": 1, "assistant_content": "Again", "reasoning_content": "Continue", "tool_calls": [],
                }},
            ]
            (session_path / "events.ndjson").write_text(
                "\n".join(json.dumps(event) for event in events), encoding="utf-8",
            )

            history = webapp._read_agent_history("doc", "doc", "coordinator")

            assert [turn["role"] for turn in history] == ["user", "assistant", "user", "assistant"]
            assert [turn["content"] for turn in history if turn["role"] == "user"] == ["First", "Second"]
            assert history[1]["tools"] == [{
                "name": "shell", "arguments": {"command": "pwd"}, "result": "workspace",
            }]
            assert history[1]["reasoning_html"] == "<p>Check</p>\n"
        finally:
            webapp.WORKSPACE_ROOT = original_root


def test_aggregate_history_prefers_durable_events_and_restores_steer() -> None:
    """The aggregate chat uses its append-only log, not a stale transcript."""
    with tempfile.TemporaryDirectory() as directory:
        original_root = webapp.WORKSPACE_ROOT
        webapp.WORKSPACE_ROOT = Path(directory)
        try:
            session_path = webapp._session_path("doc", "doc")
            session_path.mkdir(parents=True, exist_ok=True)
            (session_path / "conversation.json").write_text(json.dumps({"messages": [
                {"role": "user", "content": "stale"},
            ]}), encoding="utf-8")
            events = [
                {"event": "run_started", "message": "Current prompt"},
                {"event": "lifecycle", "type": "agent:start", "agent": "coordinator", "message": "Current prompt"},
                {"event": "lifecycle", "type": "agent:steer_applied", "agent": "coordinator", "data": {"messages": ["Change direction"]}},
                {"event": "result", "content": "Current answer", "reasoning": ""},
            ]
            (session_path / "events.ndjson").write_text(
                "\n".join(json.dumps(event) for event in events), encoding="utf-8",
            )

            history = webapp._read_agent_history("doc", "doc", "all")

            assert [(turn["role"], turn["content"]) for turn in history] == [
                ("user", "Current prompt"), ("steer", "Change direction"), ("assistant", "Current answer"),
            ]
        finally:
            webapp.WORKSPACE_ROOT = original_root


def test_agent_history_uses_context_when_no_durable_events_exist() -> None:
    """Retain compatibility with Agent contexts created before event logs."""
    with tempfile.TemporaryDirectory() as directory:
        original_root = webapp.WORKSPACE_ROOT
        webapp.WORKSPACE_ROOT = Path(directory)
        try:
            context = webapp._context_path("legacy", "legacy", "worker")
            context.write_text(json.dumps({"messages": [
                {"role": "user", "content": "Old prompt"},
                {"role": "assistant", "content": "Old answer", "content_reasoning": "Old thought"},
            ]}), encoding="utf-8")

            history = webapp._read_agent_history("legacy", "legacy", "worker")

            assert [turn["content"] for turn in history] == ["Old prompt", "Old answer"]
            assert history[1]["reasoning_html"] == "<p>Old thought</p>\n"
        finally:
            webapp.WORKSPACE_ROOT = original_root
