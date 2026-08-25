"""Token-usage summaries and compacted-context archive projections."""

from __future__ import annotations

import json
from typing import Any, Iterable

from ..storage import _safe_id, _session_path

def _empty_usage() -> dict[str, int]:
    """Return the complete token-usage shape used by session aggregations."""
    return {"input": 0, "output": 0, "total": 0, "cached": 0, "reasoning": 0}

def _usage_from_events(events: Iterable[dict[str, Any]]) -> tuple[dict[str, int], dict[str, dict[str, int]]]:
    """Aggregate usage events into (session-wide, per-agent) token dicts.

    Ledger deltas (``agent:usage`` / ``agent:internal_usage``) are preferred
    when present; otherwise the display-only ``agent:round.round_usage``
    payload is used so legacy logs stay supported.

    The log is consumed in a single streaming pass.  Only the filtered
    ``(agent, usage)`` records are retained while deciding which source wins,
    so a multi-hundred-MB ``events.ndjson`` never needs to be fully resident.
    """
    ledger: list[tuple[str, dict[str, Any]]] = []
    rounds: list[tuple[str, dict[str, Any]]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("event") != "lifecycle":
            continue
        event_type = event.get("type")
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        agent = str(event.get("agent") or "unknown")
        if event_type in {"agent:usage", "agent:internal_usage"}:
            usage = data.get("usage")
            if isinstance(usage, dict):
                ledger.append((agent, usage))
        elif event_type == "agent:round":
            usage = data.get("round_usage")
            if isinstance(usage, dict):
                rounds.append((agent, usage))
    source = ledger if ledger else rounds
    total = _empty_usage()
    by_agent: dict[str, dict[str, int]] = {}
    for agent, usage in source:
        agent_usage = by_agent.setdefault(agent, _empty_usage())
        for key in total:
            value = usage.get(key, 0)
            if isinstance(value, (int, float)):
                tokens = max(0, int(value))
                total[key] += tokens
                agent_usage[key] += tokens
    return total, by_agent


def _current_run_window(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the durable events of the most recent lifecycle run.

    The "本次" (this lifecycle) window starts at the last ``run_started``
    record and ends at the first user steering message
    (``agent:steer_applied``), the run's ``done`` marker, or the end of the
    log, whichever comes first.  Rounds emitted after a steering message are
    "steer work" and must not inflate the current-lifecycle total.

    Legacy logs without a ``run_started`` marker have no run boundary, so the
    whole log is treated as a single window to keep the summary well-defined.

    The input may be any iterable; the returned window is a materialized list
    only when the caller genuinely needs the records.  Hot usage aggregation
    should prefer :func:`_usage_from_events` on a bounded window instead.
    """
    start = None
    index = 0
    for event in events:
        if event.get("event") == "run_started":
            start = index
        index += 1
    if start is None:
        return list(events)
    # Re-iterate to slice the window.  Callers with a one-shot iterator should
    # use the streaming summary instead; this helper keeps its list contract
    # for legacy tests and callers that already hold the records.
    window: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        if index < start:
            continue
        if index > start and (
            event.get("event") == "done"
            or (
                event.get("event") == "lifecycle"
                and event.get("type") == "agent:steer_applied"
            )
        ):
            break
        window.append(event)
    return window


def _session_usage_summary(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate the canonical per-call token ledger for a browser session.

    Args:
        events: Chronological or reverse-chronological durable event records.
            New logs contribute ``agent:usage`` and ``agent:internal_usage``
            lifecycle records.  Old logs without either retain the
            ``agent:round.round_usage`` compatibility path.  Any iterable is
            accepted; hot endpoints pass the streaming event-log iterator so a
            large log is never fully materialized.

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
    total = _empty_usage()
    by_agent: dict[str, dict[str, int]] = {}
    run_total = _empty_usage()
    run_by_agent: dict[str, dict[str, int]] = {}
    round_usage = _empty_usage()

    # Single streaming pass.  Ledger deltas win over round payloads, but the
    # decision is only known after the whole log is scanned, so both candidate
    # sources are accumulated as compact (agent, usage) records.
    ledger: list[tuple[str, dict[str, Any]]] = []
    rounds: list[tuple[str, dict[str, Any]]] = []
    # Current-run window tracking: the window starts at the last run_started
    # and ends at the first done/steer_applied after it.  Events before the
    # last run_started are ignored; steer work after the boundary is excluded.
    # Legacy logs without any run_started have no boundary, so the whole log
    # is treated as one window (matching the previous list-based semantics).
    seen_run_started = False
    in_run = False
    run_ledger: list[tuple[str, dict[str, Any]]] = []
    run_rounds: list[tuple[str, dict[str, Any]]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        event_kind = event.get("event")
        event_type = event.get("type")
        data = event.get("data")
        is_usage = event_kind == "lifecycle" and event_type in {"agent:usage", "agent:internal_usage"}
        is_round = event_kind == "lifecycle" and event_type == "agent:round"
        if event_kind == "run_started":
            seen_run_started = True
            in_run = True
            run_ledger = []
            run_rounds = []
            continue
        if in_run and (
            event_kind == "done"
            or (event_kind == "lifecycle" and event_type == "agent:steer_applied")
        ):
            in_run = False
            continue
        if is_usage and isinstance(data, dict) and isinstance(data.get("usage"), dict):
            ledger.append((str(event.get("agent") or "unknown"), data["usage"]))
            if in_run or not seen_run_started:
                run_ledger.append((str(event.get("agent") or "unknown"), data["usage"]))
        elif is_round and isinstance(data, dict) and isinstance(data.get("round_usage"), dict):
            rounds.append((str(event.get("agent") or "unknown"), data["round_usage"]))
            if in_run or not seen_run_started:
                run_rounds.append((str(event.get("agent") or "unknown"), data["round_usage"]))
            # Newest completed round wins for the "本轮" line.
            for key in round_usage:
                value = data["round_usage"].get(key, 0)
                if isinstance(value, (int, float)):
                    round_usage[key] = max(0, int(value))

    def _aggregate(source: list[tuple[str, dict[str, Any]]]) -> tuple[dict[str, int], dict[str, dict[str, int]]]:
        agg_total = _empty_usage()
        agg_by_agent: dict[str, dict[str, int]] = {}
        for agent, usage in source:
            agent_usage = agg_by_agent.setdefault(agent, _empty_usage())
            for key in agg_total:
                value = usage.get(key, 0)
                if isinstance(value, (int, float)):
                    tokens = max(0, int(value))
                    agg_total[key] += tokens
                    agent_usage[key] += tokens
        return agg_total, agg_by_agent

    source = ledger if ledger else rounds
    total, by_agent = _aggregate(source)
    run_source = run_ledger if run_ledger else run_rounds
    run_total, run_by_agent = _aggregate(run_source)

    agents = [
        {"id": agent, "usage": usage}
        for agent, usage in sorted(by_agent.items(), key=lambda item: (-item[1]["total"], item[0]))
    ]
    for agent in agents:
        agent["run"] = run_by_agent.get(agent["id"], _empty_usage())
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
