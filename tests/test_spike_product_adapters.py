"""Regression tests for the ProductAdapter spike (unified transcript schema)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SPIKE_DIR = Path(__file__).resolve().parent.parent / "scripts" / "spike_product_adapters"
if str(SPIKE_DIR) not in sys.path:
    sys.path.insert(0, str(SPIKE_DIR))

from adapters import ClaudeAdapter, CodexAdapter  # noqa: E402


CLAUDE_LINES = [
    {"type": "user", "message": {"role": "user", "content": "在吗？"},
     "timestamp": "2026-08-22T11:04:28.901Z", "sessionId": "s1"},
    {"type": "assistant", "message": {
        "role": "assistant", "model": "claude-x",
        "content": [
            {"type": "text", "text": "你好"},
            {"type": "tool_use", "name": "Read", "input": {"file_path": "a.py"}, "id": "call-1"},
        ],
    }, "timestamp": "2026-08-22T11:04:29.000Z", "sessionId": "s1"},
]

CODEX_LINES = [
    {"type": "session_meta", "timestamp": "2026-04-03T09:46:34.418Z",
     "payload": {"cwd": "/tmp", "cli_version": "0.118.0"}},
    {"type": "response_item", "timestamp": "2026-04-03T09:46:34.420Z",
     "payload": {"type": "message", "role": "user",
                 "content": [{"type": "input_text", "text": "build it"}]}},
    {"type": "response_item", "timestamp": "2026-04-03T09:46:43.161Z",
     "payload": {"type": "function_call", "name": "exec_command",
                 "arguments": '{"cmd":"ls"}', "call_id": "call_q1"}},
    {"type": "response_item", "timestamp": "2026-04-03T09:46:43.245Z",
     "payload": {"type": "function_call_output", "call_id": "call_q1", "output": "ok"}},
]


def _write(tmp_path: Path, lines: list[dict]) -> Path:
    path = tmp_path / "transcript.jsonl"
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")
    return path


def test_claude_adapter_normalizes_user_and_tool_use(tmp_path) -> None:
    path = _write(tmp_path, CLAUDE_LINES)
    events = list(ClaudeAdapter().iter_events(path))
    kinds = [e["kind"] for e in events]
    assert kinds == ["user", "assistant", "tool_call"]
    assert events[0]["content"] == "在吗？"
    assert events[1]["model"] == "claude-x"
    assert events[2]["tool"] == "Read"
    assert events[2]["tool_call_id"] == "call-1"
    assert [e["seq"] for e in events] == [0, 1, 2]


def test_codex_adapter_normalizes_tool_round_trip(tmp_path) -> None:
    path = _write(tmp_path, CODEX_LINES)
    events = list(CodexAdapter().iter_events(path))
    kinds = [e["kind"] for e in events]
    assert kinds == ["meta", "user", "tool_call", "tool_result"]
    assert events[2]["tool"] == "exec_command"
    assert events[2]["tool_input"] == {"cmd": "ls"}
    assert events[3]["tool_call_id"] == "call_q1"
    assert events[3]["tool_output"] == "ok"
    assert [e["seq"] for e in events] == [0, 1, 2, 3]


def test_codex_developer_message_is_meta_not_user(tmp_path) -> None:
    lines = [
        {"type": "response_item", "timestamp": "2026-04-03T09:46:34.420Z",
         "payload": {"type": "message", "role": "developer",
                     "content": [{"type": "input_text", "text": "system prompt"}]}},
    ]
    path = _write(tmp_path, lines)
    events = list(CodexAdapter().iter_events(path))
    assert events[0]["kind"] == "meta"
    assert events[0]["role"] == "developer"
