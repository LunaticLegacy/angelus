"""Durable, incrementally maintained browser-transcript projection."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Any

from ..markdown import render_markdown
from ..storage import _read_previous_line, _safe_id, _session_path
from .transcripts import _display_tools_from_event

_PROJECTION_NAME = "display-turns.ndjson"
_CHECKPOINT_NAME = "display-turns.checkpoint.json"
_VERSION = 1
_locks: dict[Path, threading.Lock] = {}
_locks_guard = threading.Lock()


def _projection_lock(path: Path) -> threading.Lock:
    """Return the process-local serialization lock for one projection.

    Args:
        path: Session directory containing the projection files.

    Returns:
        A stable lock shared by every projection request for ``path``.
    """
    with _locks_guard:
        return _locks.setdefault(path, threading.Lock())


def _empty_checkpoint() -> dict[str, Any]:
    """Create the initial incremental event-reducer state.

    Returns:
        JSON-serializable offsets, counters, deduplication state, and pending
        tool calls for an empty event log.
    """
    return {
        "version": _VERSION,
        "event_offset": 0,
        "projection_length": 0,
        "shared_count": 0,
        "agent_counts": {},
        "last_user": None,
        "last_assistant": {},
        "last_round": {},
        "pending_tools": {},
        "event_tail_hash": hashlib.sha256(b"").hexdigest(),
        "projection_mtime_ns": 0,
    }


def _atomic_checkpoint(path: Path, checkpoint: dict[str, Any]) -> None:
    """Atomically commit reducer state after projection bytes are durable.

    Args:
        path: Destination checkpoint JSON path.
        checkpoint: Fully serializable reducer state to commit.

    Side Effects:
        Replaces ``path`` and fsyncs both the file and its parent directory.
    """
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(checkpoint, handle, ensure_ascii=False, separators=(",", ":"))
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _load_checkpoint(session_path: Path, event_size: int) -> dict[str, Any] | None:
    """Load and validate one committed projection checkpoint.

    Args:
        session_path: Directory owning the event log and projection.
        event_size: Current authoritative event-log byte length.

    Returns:
        Validated checkpoint, or ``None`` when a complete rebuild is needed.
    """
    projection_path = session_path / _PROJECTION_NAME
    checkpoint_path = session_path / _CHECKPOINT_NAME
    try:
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        projection_stat = projection_path.stat()
        projection_size = projection_stat.st_size
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(checkpoint, dict) or checkpoint.get("version") != _VERSION:
        return None
    event_offset = checkpoint.get("event_offset")
    projection_length = checkpoint.get("projection_length")
    if not isinstance(event_offset, int) or not 0 <= event_offset <= event_size:
        return None
    if not isinstance(projection_length, int) or not 0 <= projection_length <= projection_size:
        return None
    saved_mtime = checkpoint.get("projection_mtime_ns")
    if projection_size == projection_length and saved_mtime != projection_stat.st_mtime_ns:
        return None
    try:
        with (session_path / "events.ndjson").open("rb") as handle:
            handle.seek(max(0, event_offset - 4096))
            event_tail = handle.read(min(4096, event_offset))
    except OSError:
        event_tail = b""
    if checkpoint.get("event_tail_hash") != hashlib.sha256(event_tail).hexdigest():
        return None

    # Discard a projection tail written before a crash but not checkpointed.
    if projection_size != projection_length:
        with projection_path.open("r+b") as handle:
            handle.truncate(projection_length)
            handle.flush()
            os.fsync(handle.fileno())
    return checkpoint


def _append_turn(checkpoint: dict[str, Any], turns: list[dict[str, Any]], turn: dict[str, Any]) -> None:
    """Stage one raw display turn and update checkpoint counters.

    Args:
        checkpoint: Mutable reducer state for the current synchronization.
        turns: Mutable batch of projection records awaiting durable append.
        turn: Raw display message with an ``agent`` visibility scope.

    Side Effects:
        Appends to ``turns`` and increments the appropriate total counter.
    """
    turns.append(turn)
    agent = str(turn.get("agent", "*"))
    if agent == "*":
        checkpoint["shared_count"] = int(checkpoint.get("shared_count", 0)) + 1
    else:
        counts = checkpoint.setdefault("agent_counts", {})
        counts[agent] = int(counts.get(agent, 0)) + 1


def _reduce_event(checkpoint: dict[str, Any], event: dict[str, Any]) -> list[dict[str, Any]]:
    """Reduce one durable lifecycle event into zero or more raw turns.

    Args:
        checkpoint: Mutable cross-event pairing and deduplication state.
        event: Parsed dictionary from one complete NDJSON record.

    Returns:
        Display turns created by the event, without rendered Markdown.
    """
    turns: list[dict[str, Any]] = []
    kind = str(event.get("event", ""))
    event_type = str(event.get("type", ""))
    agent = str(event.get("agent") or "coordinator")
    data = event.get("data") if isinstance(event.get("data"), dict) else {}

    if kind == "run_started":
        content = str(event.get("message", ""))
        if content:
            _append_turn(checkpoint, turns, {"agent": "*", "role": "user", "content": content, "reasoning": "", "tools": []})
            checkpoint["last_user"] = content
        return turns

    if kind == "lifecycle" and event_type == "agent:start":
        checkpoint.setdefault("last_round", {}).pop(agent, None)
        if agent == "coordinator":
            content = str(event.get("message", ""))
            if content and content != checkpoint.get("last_user"):
                _append_turn(checkpoint, turns, {"agent": "*", "role": "user", "content": content, "reasoning": "", "tools": []})
                checkpoint["last_user"] = content
            checkpoint.setdefault("last_assistant", {}).pop("coordinator", None)
        return turns

    if kind == "lifecycle" and event_type == "agent:steer_applied" and agent == "coordinator":
        messages = data.get("messages", [])
        for message in messages if isinstance(messages, list) else []:
            if isinstance(message, str) and message:
                _append_turn(checkpoint, turns, {"agent": "coordinator", "role": "steer", "content": message, "reasoning": "", "tools": []})
        return turns

    if kind == "lifecycle" and event_type == "agent:tools_completed":
        round_number = data.get("round")
        if isinstance(round_number, int):
            checkpoint.setdefault("pending_tools", {})[f"{agent}\0{round_number}"] = _display_tools_from_event(data)
        return turns

    if kind == "lifecycle" and event_type == "agent:round":
        content = str(data.get("assistant_content", ""))
        reasoning = str(data.get("reasoning_content", ""))
        round_number = data.get("round")
        tools = checkpoint.setdefault("pending_tools", {}).pop(f"{agent}\0{round_number}", [])
        identity = [round_number, content, reasoning]
        if not content and not reasoning and not tools:
            return turns
        if isinstance(round_number, int) and checkpoint.setdefault("last_round", {}).get(agent) == identity:
            return turns
        turn: dict[str, Any] = {"agent": agent, "role": "assistant", "content": content, "reasoning": reasoning, "tools": tools}
        for source, target in (("round_usage", "usage"), ("model_duration_ms", "model_duration_ms"), ("duration_ms", "duration_ms")):
            if source in data:
                turn[target] = data[source]
        if isinstance(event.get("timestamp"), (int, float)):
            turn["timestamp"] = float(event["timestamp"])
        _append_turn(checkpoint, turns, turn)
        checkpoint.setdefault("last_assistant", {})[agent] = [content, reasoning]
        if isinstance(round_number, int):
            checkpoint.setdefault("last_round", {})[agent] = identity
        return turns

    if kind == "result":
        content = str(event.get("content", ""))
        reasoning = str(event.get("reasoning", ""))
        identity = [content, reasoning]
        if (content or reasoning) and checkpoint.setdefault("last_assistant", {}).get("coordinator") != identity:
            turn = {"agent": "coordinator", "role": "assistant", "content": content, "reasoning": reasoning, "tools": []}
            if isinstance(event.get("usage"), dict):
                turn["usage"] = event["usage"]
            _append_turn(checkpoint, turns, turn)
            checkpoint["last_assistant"]["coordinator"] = identity
    return turns


def _synchronize_projection(session_path: Path) -> dict[str, Any]:
    """Bring one projection checkpoint to the latest complete event record.

    Args:
        session_path: Validated session directory containing ``events.ndjson``.

    Returns:
        Committed reducer checkpoint after recovery and incremental processing.

    Side Effects:
        May rebuild or append/fsync the projection and atomically replace its
        checkpoint. An incomplete final event line remains for the next call.
    """
    session_path.mkdir(parents=True, exist_ok=True)
    event_path = session_path / "events.ndjson"
    projection_path = session_path / _PROJECTION_NAME
    try:
        event_size = event_path.stat().st_size
    except OSError:
        event_size = 0
    checkpoint = _load_checkpoint(session_path, event_size)
    if checkpoint is None:
        checkpoint = _empty_checkpoint()
        with projection_path.open("wb") as handle:
            handle.flush()
            os.fsync(handle.fileno())

    start_offset = int(checkpoint["event_offset"])
    consumed = start_offset
    staged: list[dict[str, Any]] = []
    try:
        with event_path.open("rb") as handle:
            handle.seek(start_offset)
            while True:
                line_start = handle.tell()
                line = handle.readline()
                if not line:
                    break
                if not line.endswith(b"\n"):
                    consumed = line_start
                    break
                consumed = handle.tell()
                try:
                    event = json.loads(line)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if isinstance(event, dict):
                    staged.extend(_reduce_event(checkpoint, event))
    except OSError:
        consumed = 0

    # Make every staged projection record durable before publishing its state.
    if staged:
        with projection_path.open("ab") as handle:
            for turn in staged:
                handle.write(json.dumps(turn, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
    checkpoint["event_offset"] = consumed
    projection_stat = projection_path.stat()
    checkpoint["projection_length"] = projection_stat.st_size
    checkpoint["projection_mtime_ns"] = projection_stat.st_mtime_ns
    try:
        with event_path.open("rb") as handle:
            handle.seek(max(0, consumed - 4096))
            event_tail = handle.read(min(4096, consumed))
    except OSError:
        event_tail = b""
    checkpoint["event_tail_hash"] = hashlib.sha256(event_tail).hexdigest()
    _atomic_checkpoint(session_path / _CHECKPOINT_NAME, checkpoint)
    return checkpoint


def _visible(turn: dict[str, Any], agent_name: str) -> bool:
    """Return whether one projection record belongs in an Agent filter.

    Args:
        turn: Raw projection record with an ``agent`` scope.
        agent_name: Selected Agent or ``all`` for coordinator aggregation.

    Returns:
        ``True`` for shared user turns and the selected Agent's own turns.
    """
    selected = "coordinator" if agent_name in {"", "all"} else agent_name
    return turn.get("agent") in {"*", selected}


def _render_turn(turn: dict[str, Any]) -> dict[str, Any]:
    """Strip projection metadata and render Markdown for one returned turn.

    Args:
        turn: Raw persisted display record.

    Returns:
        Browser response message, with assistant HTML generated on demand.
    """
    rendered = {key: value for key, value in turn.items() if key != "agent"}
    if rendered.get("role") == "assistant":
        rendered["content_html"] = render_markdown(str(rendered.get("content", "")))
        rendered["reasoning_html"] = render_markdown(str(rendered.get("reasoning", "")))
    return rendered


def transcript_page(
    workspace_id: str,
    session_id: str,
    agent_name: str,
    *,
    cursor: str | None = None,
    before: int | None = None,
    limit: int = 200,
    path_resolver: Any = None,
) -> dict[str, Any]:
    """Return a cursor page from an incrementally maintained transcript.

    Args:
        workspace_id: Storage partition owning the session.
        session_id: Browser-stable session identifier.
        agent_name: Selected Agent or ``all`` for coordinator aggregation.
        cursor: Opaque projection byte cursor returned by an earlier page.
        before: Deprecated exclusive visible-turn index used by old clients.
        limit: Maximum returned messages, clamped to ``1..500``.
        path_resolver: Optional session-path resolver retained for test patches.

    Returns:
        Chronological messages, filtered total, opaque older cursor,
        ``has_more``, and the deprecated ``next_before`` compatibility index.

    Raises:
        ValueError: If ``cursor`` is not a valid projection byte boundary.
    """
    safe_workspace = workspace_id if "/" in workspace_id else _safe_id(workspace_id, "workspace")
    safe_session = _safe_id(session_id, "session")
    safe_agent = "all" if agent_name in {"", "all"} else _safe_id(agent_name, "agent")
    # Legacy test/integration hooks historically supplied an absolute storage
    # partition as ``workspace_id``; retain that read path without weakening
    # the validated browser API identifiers.
    session_path = Path(safe_workspace) / safe_session if "/" in safe_workspace else (path_resolver or _session_path)(safe_workspace, safe_session)
    page_limit = max(1, min(int(limit), 500))
    with _projection_lock(session_path):
        checkpoint = _synchronize_projection(session_path)
        projection_path = session_path / _PROJECTION_NAME
        total = int(checkpoint.get("shared_count", 0)) + int(checkpoint.get("agent_counts", {}).get("coordinator" if safe_agent == "all" else safe_agent, 0))
        projection_length = int(checkpoint["projection_length"])
        if cursor is not None:
            try:
                position = int(cursor)
            except (TypeError, ValueError) as exc:
                raise ValueError("Invalid transcript cursor") from exc
            if not 0 <= position <= projection_length:
                raise ValueError("Invalid transcript cursor")
        elif before is not None:
            target = max(0, min(int(before), total))
            position = projection_length
            visible_after = total
            with projection_path.open("rb") as handle:
                while visible_after > target:
                    record = _read_previous_line(handle, position)
                    if record is None:
                        position = 0
                        break
                    position, raw = record
                    try:
                        turn = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(turn, dict) and _visible(turn, safe_agent):
                        visible_after -= 1
        else:
            position = projection_length

        selected: list[tuple[int, dict[str, Any]]] = []
        has_more = False
        with projection_path.open("rb") as handle:
            scan = position
            while scan > 0:
                record = _read_previous_line(handle, scan)
                if record is None:
                    break
                scan, raw = record
                try:
                    turn = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(turn, dict) or not _visible(turn, safe_agent):
                    continue
                if len(selected) == page_limit:
                    has_more = True
                    break
                selected.append((scan, turn))

        messages = [_render_turn(turn) for _, turn in reversed(selected)]
        next_cursor = str(selected[-1][0]) if selected and has_more else None
        next_before = max(0, (total if before is None else int(before)) - len(selected)) if has_more else None
        return {"messages": messages, "total": total, "next_cursor": next_cursor, "has_more": has_more, "next_before": next_before}
