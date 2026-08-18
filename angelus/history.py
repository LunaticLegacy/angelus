"""Session transcript, archive, usage and legacy-migration rebuilds."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .markdown import render_markdown
from . import storage
from .storage import (
    _conversation_path,
    _context_path,
    _persist_json,
    _read_session_event_log,
    _safe_id,
    _session_id_from_name,
    _session_path,
    _write_workspaces,
)



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
                "result": str(item.get("result", "")),
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
            {"name": str(item.get("call", {}).get("name", "unknown")), "arguments": item.get("call", {}).get("arguments", {}), "result": str(item.get("result", ""))}
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

def _empty_usage() -> dict[str, int]:
    """Return the complete token-usage shape used by session aggregations."""
    return {"input": 0, "output": 0, "total": 0, "cached": 0, "reasoning": 0}

def _session_usage_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate the canonical per-call token ledger for a browser session.

    Args:
        events: Chronological or reverse-chronological durable event records.
            New logs contribute ``agent:usage`` and ``agent:internal_usage``
            lifecycle records.  Old logs without either retain the
            ``agent:round.round_usage`` compatibility path.

    Returns:
        A mapping with session-wide ``usage`` and per-agent usage records.

    Ledger records are deltas, one for each provider call.  This means hidden
    compaction and graph calls are visible, while the summary does not sum the
    duplicate per-round display payload.
    """
    ledger_events = [
        event for event in events
        if event.get("event") == "lifecycle"
        and event.get("type") in {"agent:usage", "agent:internal_usage"}
    ]
    source_events = ledger_events or [
        event for event in events
        if event.get("event") == "lifecycle" and event.get("type") == "agent:round"
    ]
    total = _empty_usage()
    by_agent: dict[str, dict[str, int]] = {}
    for event in source_events:
        agent = str(event.get("agent") or "unknown")
        data = event.get("data")
        usage = (
            data.get("usage") if ledger_events and isinstance(data, dict)
            else data.get("round_usage") if isinstance(data, dict) else None
        )
        if not isinstance(usage, dict):
            continue
        agent_usage = by_agent.setdefault(agent, _empty_usage())
        for key in total:
            value = usage.get(key, 0)
            if isinstance(value, (int, float)):
                tokens = max(0, int(value))
                total[key] += tokens
                agent_usage[key] += tokens
    agents = [
        {"id": agent, "usage": usage}
        for agent, usage in sorted(by_agent.items(), key=lambda item: (-item[1]["total"], item[0]))
    ]
    return {"usage": total, "agents": agents}

def _archived_context_page(
    workspace_id: str,
    session_id: str,
    agent_name: str = "coordinator",
    *,
    before: int | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Return a bounded, read-only page of compacted raw context evidence.

    ``ContextHandlerLinear`` stores messages removed from the active prompt in
    its append-only ``archive`` list.  The archive is intentionally separate
    from the current transcript: it is evidence for retrieval and audit, not
    material which should be re-injected into every model request.  Contexts
    written before that field was introduced simply return an empty page.

    The cursor is an exclusive chronological archive offset, matching the
    event-log API.  Returned items are newest first so callers can show the
    most recently compacted evidence without loading a whole long session.
    """
    workspace_id = _safe_id(workspace_id, "workspace")
    session_id = _safe_id(session_id, "session")
    agent_name = _safe_id(agent_name, "agent")
    context_path = _session_path(workspace_id, session_id) / "contexts" / f"{agent_name}.json"
    try:
        raw = json.loads(context_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {}

    archive = raw.get("archive", []) if isinstance(raw, dict) else []
    if not isinstance(archive, list):
        archive = []
    evidence: list[dict[str, Any]] = []
    for item in archive:
        if not isinstance(item, dict):
            continue
        timeline = item.get("timeline")
        role = item.get("role")
        # Do not manufacture provenance for malformed or pre-schema entries.
        if not isinstance(timeline, int) or isinstance(timeline, bool) or not isinstance(role, str):
            continue
        tool_calls = item.get("tool_calls", [])
        evidence.append({
            "timeline": timeline,
            "role": role,
            "content": str(item.get("content", "")),
            "reasoning": str(item.get("content_reasoning", "")),
            "tool_calls": tool_calls if isinstance(tool_calls, list) else [],
            "tags": item.get("tags", []) if isinstance(item.get("tags", []), list) else [],
        })

    page_limit = max(1, min(limit, 500))
    end = len(evidence) if before is None else max(0, min(before, len(evidence)))
    start = max(0, end - page_limit)
    return {
        "evidence": list(reversed(evidence[start:end])),
        "total": len(evidence),
        "next_before": start if start else None,
    }

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
    turns: list[dict[str, Any]] = []
    completed_tools: dict[tuple[str, int], list[dict[str, Any]]] = {}
    last_assistant: tuple[str, str] | None = None
    last_user: str | None = None
    # One round-identity tracker per Agent, reset at its ``agent:start``.
    # The graph used to relay each Agent event through two hook paths, so the
    # durable log may contain an immediate second copy of every round.  A round
    # that exactly repeats the previous (agent, round, content, reasoning) is
    # that duplicate, not a real new model step.
    last_round: dict[str, tuple[int, str, str]] = {}

    for event in _read_session_event_log(workspace_id, session_id):
        event_kind = str(event.get("event", ""))
        event_type = str(event.get("type", ""))
        event_agent = str(event.get("agent") or "coordinator")
        data = event.get("data") if isinstance(event.get("data"), dict) else {}

        # Browser submissions are persisted before the Agent begins. This is
        # the canonical user turn for new sessions.
        if event_kind == "run_started":
            content = str(event.get("message", ""))
            if content:
                turns.append({"role": "user", "content": content, "reasoning": "", "tools": []})
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
                turns.append({"role": "user", "content": content, "reasoning": "", "tools": []})
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
                        turns.append({"role": "steer", "content": message, "reasoning": "", "tools": []})
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
            turns.append(turn)
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
            turns.append(turn)
            last_assistant = (content, reasoning)
    return turns

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
        tools.append({
            "name": str(item.get("name", "unknown")),
            "arguments": item.get("args", {}),
            "result": str(item.get("result", "")),
        })
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

def _agent_context_stats(session_id: str, agent_name: str) -> dict[str, Any]:
    """Return current context-length statistics for one Agent.

    Reads the Agent's persisted linear-context JSON
    (``contexts/<agent>.json``) and summarizes the retained conversation:
    message count, estimated character size of retained messages, the
    compacted abstract size (when compaction already ran), the compaction
    threshold, and the estimated ratio of current size to that threshold.

    Args:
        session_id: Browser-stable session identity.
        agent_name: Graph Agent whose context file is read.

    Returns:
        Dict with ``messages``, ``characters``, ``abstract_characters``,
        ``compacted``, ``threshold``, ``round`` and ``ratio`` keys. Missing
        or malformed context files yield all-zero defaults so the UI can
        render an empty state instead of failing.
    """
    stats = {
        "messages": 0,
        "characters": 0,
        "abstract_characters": 0,
        "compacted": False,
        "threshold": 0,
        "round": 0,
        "ratio": 0.0,
    }
    try:
        safe_session = _safe_id(session_id, "session")
        safe_agent = _safe_id(agent_name, "agent")
        path = _session_path(safe_session, safe_session) / "contexts" / f"{safe_agent}.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return stats

    if not isinstance(raw, dict):
        return stats

    messages = raw.get("messages", [])
    if isinstance(messages, list):
        stats["messages"] = len(messages)
        stats["characters"] = sum(
            len(json.dumps(msg, ensure_ascii=False, default=str))
            for msg in messages
            if isinstance(msg, dict)
        )

    abstract = raw.get("abstract")
    if isinstance(abstract, dict):
        stats["compacted"] = True
        stats["abstract_characters"] = len(
            json.dumps(abstract, ensure_ascii=False, default=str)
        )

    threshold = raw.get("compress_threshold")
    if isinstance(threshold, (int, float)) and threshold > 0:
        stats["threshold"] = int(threshold)

    round_value = raw.get("round")
    if isinstance(round_value, (int, float)) and not isinstance(round_value, bool):
        stats["round"] = int(round_value)

    # Estimated ratio of retained context to the compaction threshold.
    total_chars = stats["characters"] + stats["abstract_characters"]
    if stats["threshold"] > 0:
        stats["ratio"] = round(min(1.0, total_chars / stats["threshold"]), 4)

    return stats

__all__ = [
    "_history_context_paths",
    "_read_session_history",
    "_turns_from_legacy_context",
    "_turns_from_event_log",
    "migrate_legacy_state",
    "_empty_usage",
    "_session_usage_summary",
    "_archived_context_page",
    "_agent_turns_from_events",
    "_display_tools_from_event",
    "_read_agent_history",
    "_agent_context_stats",
    "render_markdown",
]
