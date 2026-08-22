"""ProductAdapter spike: normalize real claude/codex transcripts.

This is a *spike* — it validates the adapter contract against real data and is
not production code. Each adapter yields normalized events (see README schema).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _iso_to_epoch(iso: str | None) -> float | None:
    """Convert an ISO-8601 timestamp to a Unix epoch float (best effort)."""
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return None


def _truncate(text: str | None, limit: int = 2000) -> str | None:
    if text is None:
        return None
    text = str(text)
    return text if len(text) <= limit else text[:limit] + "…"


def _extract_text(content: Any) -> str | None:
    """Extract plain text from a content array or string."""
    if content is None:
        return None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            elif block.get("type") == "input_text":
                parts.append(str(block.get("text", "")))
            elif block.get("type") == "output_text":
                parts.append(str(block.get("text", "")))
        return "\n".join(parts) if parts else None
    return None


# ---------------------------------------------------------------------------
# Claude Code adapter
# ---------------------------------------------------------------------------

class ClaudeAdapter:
    """Parse `~/.claude/projects/<cwd-hash>/<session>.jsonl` transcript lines."""

    product = "claude"

    def iter_events(self, path: Path) -> Iterator[dict[str, Any]]:
        seq = 0
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(rec, dict):
                    continue
                rtype = rec.get("type")
                ts = _iso_to_epoch(rec.get("timestamp"))
                session_id = rec.get("sessionId") or path.stem

                def emit(**fields):
                    nonlocal seq
                    event = {
                        "product": self.product,
                        "session_id": session_id,
                        "seq": seq,
                        "ts": ts,
                        "raw_type": rtype,
                        **fields,
                    }
                    seq += 1
                    return event

                if rtype == "user":
                    message = rec.get("message") or {}
                    content = message.get("content") if isinstance(message, dict) else rec.get("message")
                    yield emit(
                        kind="user", role="user",
                        content=_truncate(_extract_text(content)),
                    )
                elif rtype == "assistant":
                    message = rec.get("message") or {}
                    if not isinstance(message, dict):
                        continue
                    content_blocks = message.get("content") or []
                    usage = message.get("usage")
                    model = message.get("model")
                    if rec.get("isApiErrorMessage") or rec.get("error"):
                        yield emit(
                            kind="error", role="assistant",
                            content=_truncate(_extract_text(content_blocks)),
                            model=model, error=str(rec.get("error") or "api_error"),
                        )
                        continue
                    for block in content_blocks:
                        if not isinstance(block, dict):
                            continue
                        btype = block.get("type")
                        if btype == "text":
                            yield emit(
                                kind="assistant", role="assistant",
                                content=_truncate(block.get("text")),
                                model=model, usage=usage,
                            )
                        elif btype == "tool_use":
                            yield emit(
                                kind="tool_call", role="assistant",
                                tool=block.get("name"),
                                tool_input=block.get("input"),
                                tool_call_id=block.get("id"),
                                model=model, usage=usage,
                            )
                        elif btype == "thinking":
                            yield emit(
                                kind="reasoning", role="assistant",
                                content=_truncate(block.get("thinking")),
                                model=model,
                            )
                elif rtype == "system":
                    yield emit(
                        kind="meta", role="system",
                        content=_truncate(rec.get("subtype") or rec.get("message")),
                    )


# ---------------------------------------------------------------------------
# Codex adapter
# ---------------------------------------------------------------------------

class CodexAdapter:
    """Parse `~/.codex/sessions/<date>/rollout-*.jsonl` transcript lines."""

    product = "codex"

    def iter_events(self, path: Path) -> Iterator[dict[str, Any]]:
        seq = 0
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(rec, dict):
                    continue
                rtype = rec.get("type")
                ts = _iso_to_epoch(rec.get("timestamp"))
                session_id = rec.get("session_id") or path.stem

                def emit(**fields):
                    nonlocal seq
                    event = {
                        "product": self.product,
                        "session_id": session_id,
                        "seq": seq,
                        "ts": ts,
                        "raw_type": rtype,
                        **fields,
                    }
                    seq += 1
                    return event

                if rtype == "response_item":
                    payload = rec.get("payload") or {}
                    ptype = payload.get("type")
                    if ptype == "message":
                        role = payload.get("role")
                        if role == "assistant":
                            kind = "assistant"
                        elif role == "user":
                            kind = "user"
                        else:
                            # developer/system prompts are harness context, not
                            # user turns; keep them as meta for the ledger.
                            kind = "meta"
                        yield emit(
                            kind=kind, role=role,
                            content=_truncate(_extract_text(payload.get("content"))),
                        )
                    elif ptype == "reasoning":
                        yield emit(
                            kind="reasoning", role="assistant",
                            content=_truncate(payload.get("content")),
                        )
                    elif ptype == "function_call":
                        args = payload.get("arguments")
                        try:
                            parsed_args = json.loads(args) if isinstance(args, str) else args
                        except json.JSONDecodeError:
                            parsed_args = {"_raw": args}
                        yield emit(
                            kind="tool_call", role="assistant",
                            tool=payload.get("name"),
                            tool_input=parsed_args,
                            tool_call_id=payload.get("call_id"),
                        )
                    elif ptype == "function_call_output":
                        yield emit(
                            kind="tool_result", role="tool",
                            tool_call_id=payload.get("call_id"),
                            tool_output=_truncate(payload.get("output")),
                        )
                elif rtype == "event_msg":
                    payload = rec.get("payload") or {}
                    ptype = payload.get("type")
                    if ptype == "task_started":
                        yield emit(
                            kind="meta", role="system",
                            content=f"task_started turn={payload.get('turn_id')}",
                            usage={"model_context_window": payload.get("model_context_window")},
                        )
                    elif ptype == "task_complete":
                        yield emit(
                            kind="meta", role="system",
                            content="task_complete",
                        )
                elif rtype == "session_meta":
                    payload = rec.get("payload") or {}
                    yield emit(
                        kind="meta", role="system",
                        content=f"session_meta cwd={payload.get('cwd')}",
                        model=payload.get("cli_version"),
                    )
                elif rtype == "turn_context":
                    yield emit(
                        kind="meta", role="system",
                        content="turn_context",
                    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

ADAPTERS: dict[str, Any] = {
    "claude": ClaudeAdapter(),
    "codex": CodexAdapter(),
}


def discover_transcripts() -> dict[str, list[Path]]:
    """Locate real transcript files on this machine (best effort)."""
    home = Path.home()
    found: dict[str, list[Path]] = {"claude": [], "codex": []}
    claude_root = home / ".claude" / "projects"
    if claude_root.is_dir():
        found["claude"] = sorted(claude_root.glob("*/*.jsonl"))
    codex_root = home / ".codex" / "sessions"
    if codex_root.is_dir():
        found["codex"] = sorted(codex_root.glob("**/*.jsonl"))
    return found
