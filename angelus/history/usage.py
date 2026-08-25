"""Token-usage summaries and compacted-context archive projections."""

from __future__ import annotations

import json
from typing import Any

from ..storage import _safe_id, _session_path

def _empty_usage() -> dict[str, int]:
    """Return the complete token-usage shape used by session aggregations."""
    return {"input": 0, "output": 0, "total": 0, "cached": 0, "reasoning": 0}

def _usage_from_events(events: list[dict[str, Any]]) -> tuple[dict[str, int], dict[str, dict[str, int]]]:
    """Aggregate usage events into (session-wide, per-agent) token dicts.

    Ledger deltas (``agent:usage`` / ``agent:internal_usage``) are preferred
    when present; otherwise the display-only ``agent:round.round_usage``
    payload is used so legacy logs stay supported.
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
    return total, by_agent


def _current_run_window(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the durable events of the most recent lifecycle run.

    The "本次" (this lifecycle) window starts at the last ``run_started``
    record and ends at the first user steering message
    (``agent:steer_applied``), the run's ``done`` marker, or the end of the
    log, whichever comes first.  Rounds emitted after a steering message are
    "steer work" and must not inflate the current-lifecycle total.

    Legacy logs without a ``run_started`` marker have no run boundary, so the
    whole log is treated as a single window to keep the summary well-defined.
    """
    start = None
    for index, event in enumerate(events):
        if event.get("event") == "run_started":
            start = index
    if start is None:
        return list(events)
    for end in range(start + 1, len(events)):
        event = events[end]
        if event.get("event") == "done":
            return events[start:end]
        if (
            event.get("event") == "lifecycle"
            and event.get("type") == "agent:steer_applied"
        ):
            return events[start:end]
    return events[start:]


def _session_usage_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate the canonical per-call token ledger for a browser session.

    Args:
        events: Chronological or reverse-chronological durable event records.
            New logs contribute ``agent:usage`` and ``agent:internal_usage``
            lifecycle records.  Old logs without either retain the
            ``agent:round.round_usage`` compatibility path.

    Returns:
        A mapping with session-wide ``usage``, per-agent usage records, a
        ``run`` mapping carrying the most recent lifecycle's usage (the "+X"
        line shown in the usage tiles, with steering rounds excluded), and a
        ``round`` mapping carrying the most recently completed model round's
        per-call usage.

    Ledger records are deltas, one for each provider call.  This means hidden
    compaction and graph calls are visible, while the summary does not sum the
    duplicate per-round display payload.
    """
    total, by_agent = _usage_from_events(events)
    agents = [
        {"id": agent, "usage": usage}
        for agent, usage in sorted(by_agent.items(), key=lambda item: (-item[1]["total"], item[0]))
    ]
    run_total, run_by_agent = _usage_from_events(_current_run_window(events))
    for agent in agents:
        agent["run"] = run_by_agent.get(agent["id"], _empty_usage())
    # Per-round usage for the legacy "本轮" line: the most recently completed
    # model round.  Scanned newest-first so the latest ``agent:round`` wins;
    # the ``round_usage`` payload is the same one that backs chat-message token
    # stats, so the usage tile stays consistent with the transcript.
    round_usage = _empty_usage()
    for event in reversed(events):
        if event.get("event") != "lifecycle" or event.get("type") != "agent:round":
            continue
        data = event.get("data")
        usage = data.get("round_usage") if isinstance(data, dict) else None
        if not isinstance(usage, dict):
            continue
        for key in round_usage:
            value = usage.get(key, 0)
            if isinstance(value, (int, float)):
                round_usage[key] = max(0, int(value))
        break
    return {"usage": total, "run": run_total, "agents": agents, "round": round_usage}


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

