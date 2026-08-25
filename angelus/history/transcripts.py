"""Session transcript projections and legacy-state migration."""

from __future__ import annotations

import ast
import json
import shutil
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable, Iterator

from .. import storage
from ..markdown import render_markdown
from ..storage import (
    _conversation_path,
    _context_path,
    _iter_session_event_log,
    _persist_json,
    _safe_id,
    _session_id_from_name,
    _session_path,
    _write_workspaces,
)

def _display_tool_result(value: Any) -> Any:
    """Recover structured tool data for every browser transcript path.

    Args:
        value: Raw event value, JSON text, legacy Python ``str(dict)`` text,
            or ordinary stdout captured in a persisted Agent context.

    Returns:
        JSON-compatible structured data when ``value`` is an object/array or
        safely decodes to one. Other values are returned unchanged so stdout
        reaches the shared frontend renderer verbatim.

    Notes:
        Earlier contexts stored tool results with ``str(value)``. Parsing is
        deliberately limited to JSON and :func:`ast.literal_eval`, never
        runtime evaluation, so historical dict/list results regain hierarchy
        without executing persisted content.
    """
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or len(text) > 2_000_000 or text[0] not in "[{":
        return value
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        try:
            decoded = ast.literal_eval(text)
        except (SyntaxError, ValueError, MemoryError, RecursionError):
            return value
    return decoded if isinstance(decoded, (dict, list)) else value



def _history_context_paths(workspace_id: str, session_id: str) -> list[Path]:
    """Return current and legacy context locations in restoration priority.

    Args:
        workspace_id: Internal partition that owned the historical chat.
        session_id: Browser-stable identifier for that chat.

    Returns:
        Ordered paths beginning with the current coordinator context, followed
        by pre-session-directory workspace and application-wide legacy files.
        This is read-only compatibility; newly created runs write only the
        first path.
    """
    workspace_id = _safe_id(workspace_id, "workspace")
    session_id = _safe_id(session_id, "session")
    return [
        _context_path(workspace_id, session_id),
        storage.WORKSPACE_ROOT / workspace_id / f"{session_id}.json",
    ]

def _read_session_history(workspace_id: str, session_id: str) -> list[dict[str, Any]]:
    """Read display-safe user and assistant turns from persisted context.

    Args:
        workspace_id: Internal workspace identifier owning the context file.
        session_id: Browser-stable session identifier.

    Returns:
        Ordered chat turns. Assistant tool call names, arguments, and bounded
        persisted results are included for inspection; compacted internal
        context is excluded.
    """
    raw: dict[str, Any] | None = None
    try:
        candidate = json.loads(_conversation_path(workspace_id, session_id).read_text(encoding="utf-8"))
        if isinstance(candidate, dict):
            raw = candidate
    except (OSError, json.JSONDecodeError):
        pass
    # This fallback only supports pre-migration installations. New sessions
    # always use conversation.json and therefore have one unambiguous source.
    if raw is None:
        for context_path in _history_context_paths(workspace_id, session_id):
            try:
                candidate = json.loads(context_path.read_text(encoding="utf-8"))
                if isinstance(candidate, dict):
                    raw = candidate
                    break
            except (OSError, json.JSONDecodeError):
                continue
    if raw is None:
        return []
    messages = raw.get("messages", [])
    history: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict) or message.get("role") not in {"user", "assistant", "steer"}:
            continue
        content = str(message.get("content", ""))
        reasoning = str(message.get("reasoning", message.get("content_reasoning", "")))
        if not content and not reasoning:
            continue
        tool_calls = []
        for item in message.get("tool_calls", []):
            if not isinstance(item, dict) or not isinstance(item.get("call"), dict):
                continue
            call = item["call"]
            tool_calls.append({
                "name": str(call.get("name", "unknown")),
                "arguments": call.get("arguments", {}),
                "result": _display_tool_result(item.get("result", "")),
            })
        turn: dict[str, Any] = {"role": message["role"], "content": content, "reasoning": reasoning, "tools": tool_calls}
        if message["role"] == "assistant":
            turn["content_html"] = message.get("content_html") or render_markdown(content)
            turn["reasoning_html"] = message.get("reasoning_html") or render_markdown(reasoning)
        history.append(turn)
    return history

def _turns_from_legacy_context(path: Path) -> list[dict[str, Any]]:
    """Extract browser-safe transcript turns from one old Agent context file.

    Args:
        path: JSON context produced by a legacy ``ContextHandler``.

    Returns:
        Ordered user and assistant turns, or an empty list when the file is
        unreadable or does not contain display messages.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    turns: list[dict[str, Any]] = []
    for message in raw.get("messages", []) if isinstance(raw, dict) else []:
        if not isinstance(message, dict) or message.get("role") not in {"user", "assistant", "steer"}:
            continue
        tools = [
            {"name": str(item.get("call", {}).get("name", "unknown")), "arguments": item.get("call", {}).get("arguments", {}), "result": _display_tool_result(item.get("result", ""))}
            for item in message.get("tool_calls", [])
            if isinstance(item, dict) and isinstance(item.get("call"), dict)
        ]
        turns.append({"role": message["role"], "content": str(message.get("content", "")), "reasoning": str(message.get("content_reasoning", "")), "tools": tools})
    return turns

def _turns_from_event_log(path: Path) -> list[dict[str, Any]]:
    """Recover a minimal chat transcript from durable swarm event records.

    Args:
        path: NDJSON event log belonging to a session without Agent context.

    Returns:
        User graph-start messages and final result messages in log order.
    """
    turns: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return turns
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("event") == "run_started" and event.get("message"):
            turns.append({"role": "user", "content": str(event["message"]), "reasoning": "", "tools": []})
        elif event.get("event") == "lifecycle" and event.get("type") == "graph:start":
            turns.append({"role": "user", "content": str(event.get("message", "")), "reasoning": "", "tools": []})
        elif event.get("event") == "lifecycle" and event.get("type") == "agent:steer_applied":
            data = event.get("data") if isinstance(event.get("data"), dict) else {}
            for message in data.get("messages", []):
                if isinstance(message, str) and message:
                    turns.append({"role": "steer", "content": message, "reasoning": "", "tools": []})
        elif event.get("event") == "result":
            turns.append({"role": "assistant", "content": str(event.get("content", "")), "reasoning": str(event.get("reasoning", "")), "tools": []})
    return turns

def migrate_legacy_state() -> None:
    """Migrate all `.llmfetcher` data into independent `workspace` sessions.

    The migration runs once when the new registry is absent. Each legacy
    workspace becomes one session directory named after its display name;
    all nested artifacts are copied, newest conflicting context is selected,
    and the original tree is moved into a dated migration backup only after
    the new registry and session transcripts have been written.
    """
    legacy_root = storage.PROJECT_ROOT / ".llmfetcher"
    if storage.WORKSPACE_INDEX.exists() or not legacy_root.is_dir():
        return
    try:
        legacy_records = json.loads((legacy_root / "workspaces.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        legacy_records = []
    records: list[dict[str, str]] = []
    used: set[str] = set()
    for item in legacy_records if isinstance(legacy_records, list) else []:
        if not isinstance(item, dict) or not item.get("id") or not item.get("name"):
            continue
        source = legacy_root / "workspaces" / str(item["id"])
        is_default = str(item["id"]) == "default"
        session_id = "default" if is_default else _session_id_from_name(str(item["name"]), used)
        display_name = "default" if is_default else str(item["name"])
        used.add(session_id)
        target = storage.STATE_ROOT / session_id
        target.mkdir(parents=True, exist_ok=True)
        # Copy nested session artifacts first; reports and logs are preserved verbatim.
        for nested in (source / "sessions").glob("*") if (source / "sessions").is_dir() else []:
            if nested.is_dir():
                shutil.copytree(nested, target, dirs_exist_ok=True)
        contexts = sorted(source.glob("*.json"), key=lambda candidate: candidate.stat().st_mtime, reverse=True) if source.is_dir() else []
        contexts = [candidate for candidate in contexts if not candidate.name.endswith(".plan.json")]
        turns: list[dict[str, Any]] = []
        if contexts:
            context_target = target / "contexts" / "coordinator.json"
            context_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(contexts[0], context_target)
            turns = _turns_from_legacy_context(contexts[0])
        plan_files = sorted(source.glob("*.plan.json"), key=lambda candidate: candidate.stat().st_mtime, reverse=True) if source.is_dir() else []
        if plan_files and not (target / "task-plan.json").exists():
            shutil.copy2(plan_files[0], target / "task-plan.json")
        if not turns:
            turns = _turns_from_event_log(target / "events.ndjson")
        _persist_json(target / "conversation.json", {"messages": turns})
        _persist_json(target / "metadata.json", {"id": session_id, "name": display_name, "legacy_workspace_id": str(item["id"])})
        records.append({"id": session_id, "name": display_name})
    # Preserve historical global contexts as their own recoverable sessions.
    global_contexts = legacy_root / "sessions"
    for context in global_contexts.glob("*.json") if global_contexts.is_dir() else []:
        session_id = _session_id_from_name(f"legacy-{context.stem}", used)
        used.add(session_id)
        target = storage.STATE_ROOT / session_id
        (target / "contexts").mkdir(parents=True, exist_ok=True)
        shutil.copy2(context, target / "contexts" / "coordinator.json")
        _persist_json(target / "conversation.json", {"messages": _turns_from_legacy_context(context)})
        _persist_json(target / "metadata.json", {"id": session_id, "name": session_id, "legacy_global_session_id": context.stem})
        records.append({"id": session_id, "name": session_id})
    if (legacy_root / "connectors.json").exists():
        shutil.copy2(legacy_root / "connectors.json", storage.CONNECTOR_INDEX)
    _write_workspaces(records or [{"id": "default", "name": "default"}])
    backup = storage.STATE_ROOT / f"migration-backup-{int(time.time())}"
    shutil.move(str(legacy_root), str(backup))

def _iter_agent_turns_from_events(
    workspace_id: str,
    session_id: str,
    agent_name: str,
) -> Iterator[dict[str, Any]]:
    """Stream an Agent transcript from the append-only lifecycle log.

    Args:
        workspace_id: Internal storage partition owning ``events.ndjson``.
        session_id: Browser-stable identifier for the current chat.
        agent_name: Graph Agent whose model rounds should be included.

    Yields:
        Chronological user prompts and assistant rounds with rendered Markdown
        and completed tool evidence. A coordinator result identical to its
        final model round is emitted only once.
    """
    completed_tools: dict[tuple[str, int], list[dict[str, Any]]] = {}
    last_assistant: tuple[str, str] | None = None
    last_user: str | None = None
    # One round-identity tracker per Agent, reset at its ``agent:start``.
    # The graph used to relay each Agent event through two hook paths, so the
    # durable log may contain an immediate second copy of every round.  A round
    # that exactly repeats the previous (agent, round, content, reasoning) is
    # that duplicate, not a real new model step.
    last_round: dict[str, tuple[int, str, str]] = {}

    for event in _iter_session_event_log(workspace_id, session_id):
        event_kind = str(event.get("event", ""))
        event_type = str(event.get("type", ""))
        event_agent = str(event.get("agent") or "coordinator")
        data = event.get("data") if isinstance(event.get("data"), dict) else {}

        # Browser submissions are persisted before the Agent begins. This is
        # the canonical user turn for new sessions.
        if event_kind == "run_started":
            content = str(event.get("message", ""))
            if content:
                yield {"role": "user", "content": content, "reasoning": "", "tools": []}
                last_user = content
            continue

        # Agent starts delimit one run boundary for round deduplication.
        # Coordinator starts also delimit real browser submissions; showing
        # those in every Agent filter preserves the user-side conversation.
        if event_kind == "lifecycle" and event_type == "agent:start":
            last_round.pop(event_agent, None)
            if event_agent != "coordinator":
                continue
            content = str(event.get("message", ""))
            # Old logs have only agent:start; new logs also have run_started.
            if content and content != last_user:
                yield {"role": "user", "content": content, "reasoning": "", "tools": []}
                last_user = content
            last_assistant = None
            continue

        if (
            event_kind == "lifecycle"
            and event_type == "agent:steer_applied"
            and event_agent == "coordinator"
            and agent_name == "coordinator"
        ):
            messages = data.get("messages", [])
            if isinstance(messages, list):
                for message in messages:
                    if isinstance(message, str) and message:
                        yield {"role": "steer", "content": message, "reasoning": "", "tools": []}
            continue

        # Tool completion precedes its matching model-round event, allowing
        # the detailed message to carry both request arguments and results.
        if event_kind == "lifecycle" and event_type == "agent:tools_completed":
            round_number = data.get("round")
            if event_agent == agent_name and isinstance(round_number, int):
                completed_tools[(event_agent, round_number)] = _display_tools_from_event(data)
            continue
        if event_kind == "lifecycle" and event_type == "agent:round" and event_agent == agent_name:
            content = str(data.get("assistant_content", ""))
            reasoning = str(data.get("reasoning_content", ""))
            tools = completed_tools.pop((event_agent, data.get("round")), [])
            if not content and not reasoning and not tools:
                continue
            round_number = data.get("round")
            previous_round = last_round.get(event_agent)
            if (
                isinstance(round_number, int)
                and previous_round is not None
                and previous_round == (round_number, content, reasoning)
            ):
                # Immediate duplicate copy of the same round (legacy double-write).
                continue
            turn = {"role": "assistant", "content": content, "reasoning": reasoning, "tools": tools}
            turn["content_html"] = render_markdown(content)
            turn["reasoning_html"] = render_markdown(reasoning)
            round_usage = data.get("round_usage")
            if isinstance(round_usage, dict):
                turn["usage"] = round_usage
            if isinstance(data.get("model_duration_ms"), (int, float)):
                turn["model_duration_ms"] = data["model_duration_ms"]
            # The round's end time is the durable event timestamp; the start is
            # end minus the full round duration, so the token footer can show
            # the block's time span without a separate start event.
            if isinstance(event.get("timestamp"), (int, float)):
                turn["timestamp"] = float(event["timestamp"])
            if isinstance(data.get("duration_ms"), (int, float)):
                turn["duration_ms"] = data["duration_ms"]
            yield turn
            last_assistant = (content, reasoning)
            if isinstance(round_number, int):
                last_round[event_agent] = (round_number, content, reasoning)
            continue

        # The top-level result repeats the coordinator's final model round in
        # normal runs, but remains necessary for old or partial event logs.
        if event_kind == "result" and agent_name == "coordinator":
            content = str(event.get("content", ""))
            reasoning = str(event.get("reasoning", ""))
            if (not content and not reasoning) or last_assistant == (content, reasoning):
                continue
            turn = {"role": "assistant", "content": content, "reasoning": reasoning, "tools": []}
            turn["content_html"] = render_markdown(content)
            turn["reasoning_html"] = render_markdown(reasoning)
            usage = event.get("usage")
            if isinstance(usage, dict):
                turn["usage"] = usage
            yield turn
            last_assistant = (content, reasoning)


def _agent_turns_from_events(
    workspace_id: str,
    session_id: str,
    agent_name: str,
) -> list[dict[str, Any]]:
    """Reconstruct an Agent transcript from the append-only lifecycle log.

    Args:
        workspace_id: Internal storage partition owning ``events.ndjson``.
        session_id: Browser-stable identifier for the current chat.
        agent_name: Graph Agent whose model rounds should be included.

    Returns:
        Chronological user prompts and assistant rounds with rendered Markdown
        and completed tool evidence. A coordinator result identical to its
        final model round is emitted only once.
    """
    return list(_iter_agent_turns_from_events(workspace_id, session_id, agent_name))


def _paginate_turns(
    turns: list[dict[str, Any]],
    *,
    before: int | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Slice a fully materialized turn list into a newest-first page.

    Args:
        turns: Chronological display turns (oldest first).
        before: Exclusive chronological turn index to page before. ``None``
            starts from the newest turn.
        limit: Maximum number of turns to return, clamped to ``1..500``.

    Returns:
        ``{messages, total, next_before}`` where ``messages`` is the newest
        ``limit`` turns strictly before ``before`` (oldest-first order
        preserved), ``total`` is the full turn count, and ``next_before`` is
        the exclusive index of the next older page or ``None`` when the
        beginning has been reached.
    """
    page_limit = max(1, min(int(limit), 500))
    total = len(turns)
    end = total if before is None else max(0, min(int(before), total))
    start = max(0, end - page_limit)
    return {
        "messages": turns[start:end],
        "total": total,
        "next_before": start if start else None,
    }


def _agent_turns_page(
    workspace_id: str,
    session_id: str,
    agent_name: str,
    *,
    before: int | None = None,
    limit: int = 100,
    _path_resolver: Callable[[str, str], Path] | None = None,
) -> dict[str, Any]:
    """Return a bounded page of one Agent's display transcript.

    Streams the durable event log and keeps only the newest ``limit`` turns
    strictly before the ``before`` cursor, so a long session never needs to be
    fully materialized just to render the latest page.  The cursor is an
    exclusive chronological turn index matching ``_archived_context_page``.

    Args:
        workspace_id: Internal storage partition owning ``events.ndjson``.
        session_id: Browser-stable identifier for the current chat.
        agent_name: Selected graph Agent, or ``all`` for the canonical chat.
        before: Exclusive chronological turn index to page before.
        limit: Maximum number of turns to return, clamped to ``1..500``.
        _path_resolver: Optional compatibility hook for resolving a legacy
            fallback context path; ordinary callers leave it unset.

    Returns:
        ``{messages, total, next_before}`` with ``messages`` in chronological
        order (oldest first within the page).
    """
    page_limit = max(1, min(int(limit), 500))
    is_all = agent_name in {"", "all"}
    if is_all:
        source = _iter_agent_turns_from_events(workspace_id, session_id, "coordinator")
    else:
        safe_agent = _safe_id(agent_name, "agent")
        source = _iter_agent_turns_from_events(workspace_id, session_id, safe_agent)

    page: list[dict[str, Any]] = []
    total = 0
    saw_user = False
    end = None if before is None else max(0, int(before))
    for turn in source:
        total += 1
        if turn.get("role") == "user":
            saw_user = True
        if end is not None and total > end:
            continue
        page.append(turn)
        if len(page) > page_limit:
            page.pop(0)

    # Legacy fallbacks for incomplete or empty event logs.
    if is_all:
        if not saw_user:
            return _paginate_turns(
                _read_session_history(workspace_id, session_id),
                before=before, limit=page_limit,
            )
    elif total == 0:
        # External imports deliberately persist display turns rather than
        # synthesizing Angelus lifecycle rounds.  The Coordinator filter is
        # still the owner of that imported conversation, so present the same
        # formatted projection instead of an empty Agent trace.
        if safe_agent == "coordinator":
            imported_turns = _read_session_history(workspace_id, session_id)
            if imported_turns:
                return _paginate_turns(imported_turns, before=before, limit=page_limit)
        context_path = (_path_resolver or _session_path)(workspace_id, session_id) / "contexts" / f"{safe_agent}.json"
        legacy = _turns_from_legacy_context(context_path)
        for turn in legacy:
            if turn.get("role") == "assistant":
                turn["content_html"] = render_markdown(str(turn.get("content", "")))
                turn["reasoning_html"] = render_markdown(str(turn.get("reasoning", "")))
        return _paginate_turns(legacy, before=before, limit=page_limit)

    if end is None:
        next_before = max(0, total - page_limit) if total > page_limit else None
    else:
        next_before = max(0, end - page_limit) if end > page_limit else None
    return {"messages": page, "total": total, "next_before": next_before}


def _display_tools_from_event(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize completed lifecycle tool calls for browser display.

    Args:
        data: ``agent:tools_completed`` event data.

    Returns:
        Safe tool name, argument, and persisted result mappings in call order.
    """
    tools: list[dict[str, Any]] = []
    for item in data.get("tool_calls", []):
        if not isinstance(item, dict):
            continue
        tool = {
            "name": str(item.get("name", "unknown")),
            "arguments": item.get("args", {}),
            "result": _display_tool_result(item.get("result", "")),
        }
        # Per-tool wall-clock timing is optional so older durable logs (and
        # synthetic events) still render without a duration badge.
        if isinstance(item.get("duration_ms"), (int, float)):
            tool["duration_ms"] = item["duration_ms"]
        tools.append(tool)
    return tools

def _read_agent_history(workspace_id: str, session_id: str, agent_name: str) -> list[dict[str, Any]]:
    """Read one Agent's complete display transcript from durable events.

    Args:
        workspace_id: Internal storage partition owning the session.
        session_id: Browser-stable identifier for the current chat.
        agent_name: Selected graph Agent, or ``all`` for the canonical chat.

    Returns:
        Chronological user prompts and detailed Agent turns. Event history is
        preferred because an Agent context may discard old turns during
        compaction; legacy contexts remain a fallback for older sessions.
    """
    if agent_name in {"", "all"}:
        turns = _agent_turns_from_events(workspace_id, session_id, "coordinator")
        # A result-only legacy trace is not a complete transcript; keep its
        # conversation projection as the compatibility source in that case.
        if any(turn.get("role") == "user" for turn in turns):
            return turns
        return _read_session_history(workspace_id, session_id)
    agent_name = _safe_id(agent_name, "agent")
    turns = _agent_turns_from_events(workspace_id, session_id, agent_name)
    if turns:
        return turns
    context_path = _session_path(workspace_id, session_id) / "contexts" / f"{agent_name}.json"
    turns = _turns_from_legacy_context(context_path)
    for turn in turns:
        if turn.get("role") == "assistant":
            turn["content_html"] = render_markdown(str(turn.get("content", "")))
            turn["reasoning_html"] = render_markdown(str(turn.get("reasoning", "")))
    return turns
