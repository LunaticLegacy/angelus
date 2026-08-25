"""Regression coverage for external-history workspace bootstrap."""

from __future__ import annotations

import json
from pathlib import Path

from angelus import external_agents, storage
from angelus.external_providers.claude_code import ClaudeCodeProvider


def test_imported_history_seeds_the_coordinator_checkpoint(monkeypatch, tmp_path: Path) -> None:
    """Create an import that the next Agent turn can load as real context.

    Args:
        monkeypatch: Pytest helper that redirects Angelus' local workspace.
        tmp_path: Temporary state and bound-project parent directory.
    """
    state_root = tmp_path / "state"
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr(storage, "WORKSPACE_ROOT", state_root)
    monkeypatch.setattr(storage, "WORKSPACE_INDEX", state_root / "sessions.json")
    events = [
        {"event": "external_agent.message.completed", "role": "user", "content": "Fix the failed login", "sequence": 0},
        {"event": "external_agent.message.completed", "role": "assistant", "content": "I found the token parser failure.", "sequence": 1},
        {"event": "external_agent.raw", "raw": {"tool": "shell"}, "sequence": 2},
    ]

    imported = external_agents.import_events(
        "Claude handoff", str(project), "claude-code", events,
        external_agents.ConversionReport("claude-code"), "claude-session-1",
    )

    checkpoint_path = storage._context_path(imported["id"], imported["id"], "coordinator")
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert [message["content"] for message in checkpoint["messages"]] == [
        "Fix the failed login", "I found the token parser failure.",
    ]
    assert checkpoint["imported_context"]["active_messages"] == 2
    assert imported["meta"]["context_bootstrap"]["active_messages"] == 2


def test_claude_export_history_reads_only_discovered_transcript(tmp_path: Path) -> None:
    """Export normalized history without treating transcript records as commands.

    Args:
        tmp_path: Temporary Claude configuration root with one transcript.
    """
    transcript = tmp_path / "projects" / "demo" / "claude-session.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text("\n".join([
        json.dumps({"sessionId": "claude-session", "type": "user", "cwd": "/project", "message": {"content": "Investigate login"}}),
        json.dumps({"sessionId": "claude-session", "type": "assistant", "message": {"content": [{"type": "text", "text": "Parser rejects an empty token."}]}}),
        json.dumps({"sessionId": "claude-session", "type": "tool_use", "message": {"name": "Bash"}}),
    ]), encoding="utf-8")
    provider = ClaudeCodeProvider(history_root=tmp_path, sdk=object())

    history = provider.export_history("claude-session")

    assert [(item["role"], item["content"]) for item in history] == [
        ("user", "Investigate login"), ("assistant", "Parser rejects an empty token."),
    ]


def test_claude_history_rebuild_excludes_cli_artifacts_and_sidechains(tmp_path: Path) -> None:
    """Keep a continuation transcript to the human-visible main conversation.

    Args:
        tmp_path: Temporary Claude configuration root with one mixed transcript.
    """
    transcript = tmp_path / "projects" / "demo" / "claude-session.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text("\n".join([
        json.dumps({"sessionId": "claude-session", "type": "user", "isMeta": True, "message": {"role": "user", "content": "<local-command-caveat>ignore</local-command-caveat>"}}),
        json.dumps({"sessionId": "claude-session", "type": "user", "message": {"role": "user", "content": "Repair the login flow"}}),
        json.dumps({"sessionId": "claude-session", "type": "assistant", "message": {"role": "assistant", "model": "<synthetic>", "content": [{"type": "text", "text": "No response requested."}]}}),
        json.dumps({"sessionId": "claude-session", "type": "assistant", "message": {"role": "assistant", "content": [{"type": "thinking", "thinking": "hidden"}]}}),
        json.dumps({"sessionId": "claude-session", "type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "The token parser needs a guard."}]}}),
        json.dumps({"sessionId": "claude-session", "type": "assistant", "isSidechain": True, "message": {"role": "assistant", "content": [{"type": "text", "text": "Ignore this branch."}]}}),
        json.dumps({"sessionId": "claude-session", "type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "The token parser needs a guard."}]}}),
    ]), encoding="utf-8")
    provider = ClaudeCodeProvider(history_root=tmp_path, sdk=object())

    sessions = provider.discover()
    history = provider.export_history("claude-session")

    assert sessions[0].title == "Repair the login flow"
    assert [(item["role"], item["content"]) for item in history] == [
        ("user", "Repair the login flow"),
        ("assistant", "The token parser needs a guard."),
    ]
