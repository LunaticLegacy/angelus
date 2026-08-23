"""Session transcript, archive, usage and legacy-migration rebuilds."""

from __future__ import annotations

import ast
import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .markdown import render_markdown
from .context_stats import estimate_context_length
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


@dataclass(frozen=True)
class AgentContextMetadata:
    """Schema for one provider message represented in an Agent context preview.

    Attributes:
        index: One-based chronological position in this preview response's
            ``messages`` list. It is the snapshot-scoped selection key
            reserved for a future explicit context-editing tool; a later
            checkpoint may assign different indices.
        source: Agent checkpoint/identity or the tool that produced the entry.
        type: Provider message kind, such as ``user``, ``assistant``,
            ``tool``, or ``abstract``.
        length: Character count of the exact rendered message content.
        timeline: Persisted source timeline or compacted timeline range.
    """

    index: int
    source: str
    type: str
    length: int
    timeline: str


@dataclass(frozen=True)
class RemoteRequestStats:
    """Live size summary for one captured remote-request snapshot."""

    messages: int
    characters: int
    tool_schemas: int
    tool_schema_characters: int
    estimated_tokens: int


@dataclass(frozen=True)
class AgentContextPreview:
    """Schema returned to the workbench for one Agent context inspection.

    The model-facing message and tool payload fields deliberately remain JSON
    objects: they are provider- and plugin-extensible.  This envelope fixes
    the stable application contract around those payloads so callers no
    longer infer response keys from an untyped mapping.

    Attributes:
        messages: Chronological provider-neutral messages reconstructed from
            the saved Agent checkpoint.
        metadata: One provenance record for each item in ``messages``.
        request: Latest captured :class:`RemoteRequestSnapshot` serialized at
            the Angelus/llmfetcher boundary, or ``None`` for older sessions.
        total: Number of messages in the saved checkpoint.
    """

    messages: list[dict[str, Any]]
    metadata: list[AgentContextMetadata]
    request: dict[str, Any] | None
    total: int
    stats: RemoteRequestStats | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the stable response envelope for FastAPI and JSON.

        Returns:
            A JSON-compatible mapping with metadata converted from its
            dataclass schema while leaving provider-extensible payloads intact.
        """
        return {
            "messages": self.messages,
            "metadata": [asdict(item) for item in self.metadata],
            "request": self.request,
            "total": self.total,
            "stats": asdict(self.stats) if self.stats is not None else None,
        }


@dataclass(frozen=True)
class ContextGraphNode:
    """Browser-safe schema for one persisted long-term-memory entity."""

    id: str
    name: str
    entity_type: str
    summary: str
    aliases: list[str]
    first_seen: int
    last_seen: int
    freq: int


@dataclass(frozen=True)
class ContextGraphEdge:
    """Browser-safe schema for one relation between visible graph entities."""

    source_id: str
    target_id: str
    relation: str
    weight: float
    first_seen: int
    last_seen: int
    valid: bool
    evidence: list[int]


@dataclass(frozen=True)
class ContextGraphCommunity:
    """Browser-safe schema for one bounded persisted graph community."""

    level: int
    community_id: str
    summary: str
    member_entity_ids: list[str]


@dataclass(frozen=True)
class ContextGraphSnapshot:
    """Bounded API schema for an Agent's persisted long-term memory graph.

    Attributes:
        available: Whether an inspectable graph snapshot is currently usable.
        node_count: Total persisted entities before UI bounding.
        edge_count: Total persisted relations before UI filtering.
        community_count: Total persisted graph communities.
        truncated: Whether visible nodes were bounded by the API limit.
        nodes: Display-safe entity records.
        edges: Display-safe relations whose endpoints are both visible.
        communities: Bounded graph-community summaries.
        stale: Whether a context edit invalidated this graph until the next
            Agent checkpoint rebuilds it.
    """

    available: bool
    node_count: int
    edge_count: int
    community_count: int
    truncated: bool
    nodes: list[ContextGraphNode]
    edges: list[ContextGraphEdge]
    communities: list[ContextGraphCommunity]
    stale: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize the graph snapshot for FastAPI without leaking storage data."""
        return asdict(self)


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


def _agent_context_preview(session_id: str, agent_name: str) -> AgentContextPreview:
    """Return context metadata and the latest exact remote request snapshot.

    Args:
        session_id: Browser-visible session that owns the context file.
        agent_name: Agent identity used in ``contexts/<agent>.json``.

    Returns:
        Chronological provider-neutral checkpoint messages, the latest
        captured remote-request snapshot when available, the number of
        checkpoint messages, and one metadata record per checkpoint message.
        Checkpoint messages are inspection evidence only: callers must render
        ``request`` alone as an exact remote request, because a checkpoint
        cannot include transient system prompts, a future user draft, graph
        retrieval, or the provider-prepared ``tools`` array.

    Side Effects:
        Reads one context JSON file only. The handler is constructed solely to
        deserialize and render the checkpoint; it never compacts, saves, or
        calls a model.
    """
    safe_session = _safe_id(session_id, "session")
    safe_agent = _safe_id(agent_name, "agent")
    path = _session_path(safe_session, safe_session) / "contexts" / f"{safe_agent}.json"
    if not path.is_file():
        return AgentContextPreview(messages=[], metadata=[], request=None, total=0)

    # Reuse the runtime's linear serializer so the preview keeps compacted
    # abstracts, tool-call shapes, and request-side tool-output limits.
    from llmfetcher.context_handlers.linear import ContextHandlerLinear

    handler = ContextHandlerLinear(compacting_llmfetcher_handler=object())
    if not handler.load(path):
        return AgentContextPreview(messages=[], metadata=[], request=None, total=0)
    messages = handler.build_messages()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {}

    def timeline_label(value: Any) -> str:
        """Format one persisted timeline or compacted range for display."""
        if isinstance(value, list):
            values = [item for item in value if isinstance(item, int) and not isinstance(item, bool)]
            if values:
                return str(values[0]) if len(values) == 1 else f"{values[0]}–{values[-1]}"
        if isinstance(value, int) and not isinstance(value, bool):
            return str(value)
        return "—"

    metadata: list[AgentContextMetadata] = []
    message_index = 0
    abstract = raw.get("abstract") if isinstance(raw, dict) else None
    if isinstance(abstract, dict) and message_index < len(messages):
        rendered = messages[message_index]
        metadata.append(AgentContextMetadata(
            index=message_index + 1,
            source=f"{safe_agent} · checkpoint",
            type="abstract",
            length=len(str(rendered.get("content", ""))),
            timeline=timeline_label(abstract.get("source_timeline", [])),
        ))
        message_index += 1

    # Mirror ContextHandlerLinear's assistant/tool expansion so each visible
    # provider message gets provenance without changing the persisted context.
    source_messages = raw.get("messages", []) if isinstance(raw, dict) else []
    for item in source_messages if isinstance(source_messages, list) else []:
        if not isinstance(item, dict) or message_index >= len(messages):
            continue
        role = str(item.get("role", "assistant"))
        timeline = timeline_label(item.get("timeline"))
        rendered = messages[message_index]
        metadata.append(AgentContextMetadata(
            index=message_index + 1,
            source=safe_agent,
            type=role,
            length=len(str(rendered.get("content", ""))),
            timeline=timeline,
        ))
        message_index += 1
        if role != "assistant" or not isinstance(item.get("tool_calls"), list):
            continue
        for tool in item["tool_calls"]:
            if not isinstance(tool, dict) or message_index >= len(messages):
                continue
            call = tool.get("call", {})
            tool_name = str(call.get("name", "tool")) if isinstance(call, dict) else "tool"
            rendered = messages[message_index]
            metadata.append(AgentContextMetadata(
                index=message_index + 1,
                source=f"tool · {tool_name}",
                type="tool",
                length=len(str(rendered.get("content", ""))),
                timeline=timeline,
            ))
            message_index += 1
    request: dict[str, Any] | None = None
    request_round: int | None = None
    for event in reversed(_read_session_event_log(safe_session, safe_session)):
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        if event.get("event") == "lifecycle" and event.get("type") == "agent:remote_request" and event.get("agent") == safe_agent and isinstance(data.get("request"), dict):
            request = data["request"]
            request_round = data.get("round") if isinstance(data.get("round"), int) else None
            break
    stats: RemoteRequestStats | None = None
    if request is not None:
        # The visible request body and its metadata must describe the same
        # snapshot. Checkpoint provenance is intentionally not reused here.
        messages = [item for item in request.get("messages", []) if isinstance(item, dict)]
        request_timeline = f"round {request_round}" if request_round is not None else "request"
        metadata = [AgentContextMetadata(
            index=index,
            source=f"{safe_agent} · remote request",
            type=str(message.get("role", "unknown")),
            length=len(json.dumps(message, ensure_ascii=False, default=str)),
            timeline=request_timeline,
        ) for index, message in enumerate(messages, start=1)]
        tool_schemas = [item for item in request.get("tools", []) if isinstance(item, dict)]
        estimate = estimate_context_length(messages, tool_schemas)
        stats = RemoteRequestStats(
            estimate.messages,
            estimate.characters,
            estimate.tool_schemas,
            estimate.tool_schema_characters,
            estimate.estimated_tokens,
        )
    return AgentContextPreview(
        messages=messages,
        metadata=metadata,
        request=request,
        total=len(messages),
        stats=stats,
    )

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
            usage = event.get("usage")
            if isinstance(usage, dict):
                turn["usage"] = usage
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
            "result": _display_tool_result(item.get("result", "")),
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
        ``compacted``, ``threshold``, ``round`` and ``ratio`` keys, plus the
        unified ``estimated_tokens`` proxy and ``tool_schema_characters``
        (always zero here because a checkpoint has no standalone tools
        snapshot). Missing or malformed context files yield all-zero
        defaults so the UI can render an empty state instead of failing.
    """
    stats = {
        "messages": 0,
        "characters": 0,
        "abstract_characters": 0,
        "compacted": False,
        "threshold": 0,
        "round": 0,
        "ratio": 0.0,
        "estimated_tokens": 0,
        "tool_schema_characters": 0,
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
        estimate = estimate_context_length(messages)
        stats["messages"] = estimate.messages
        stats["characters"] = estimate.characters
        stats["estimated_tokens"] = estimate.estimated_tokens
        stats["tool_schema_characters"] = estimate.tool_schema_characters

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


def _agent_compaction_input_preview(session_id: str, agent_name: str) -> dict[str, Any]:
    """Return the exact text the context compactor would send for one Agent.

    Reads the Agent's persisted linear-context JSON
    (``contexts/<agent>.json``) and rebuilds the newest-first,
    budget-bounded transcript that ``ContextHandlerLinear``
    ``_build_compaction_input()`` produces for a summary request. This is a
    live input preview: it reflects the current checkpoint exactly as the
    compactor would serialize it, without invoking any model or mutating
    persisted state.

    Args:
        session_id: Browser-stable session identity.
        agent_name: Graph Agent whose context file is read.

    Returns:
        Dict with ``text`` (the bounded transcript), ``characters``,
        ``threshold``, ``round``, ``messages`` (total serialized entries),
        ``omitted`` (entries dropped by the compaction budget), and
        ``estimated_tokens``. Missing or malformed context files yield an
        empty ``text`` with zeroed metadata so the UI can render an empty
        state instead of failing.
    """
    empty = {
        "text": "",
        "characters": 0,
        "threshold": 0,
        "round": 0,
        "messages": 0,
        "omitted": 0,
        "estimated_tokens": 0,
    }
    try:
        safe_session = _safe_id(session_id, "session")
        safe_agent = _safe_id(agent_name, "agent")
        path = _session_path(safe_session, safe_session) / "contexts" / f"{safe_agent}.json"
        if not path.is_file():
            return empty

        # Reuse the runtime's linear serializer so the preview matches the
        # exact compaction input, including compacted abstracts and
        # request-side tool-output limits.
        from llmfetcher.context_handlers.linear import ContextHandlerLinear

        handler = ContextHandlerLinear(compacting_llmfetcher_handler=object())
        if not handler.load(path):
            return empty

        serialized_entries = [
            json.dumps(entry, ensure_ascii=False, default=str)
            for entry in handler.build_messages()
        ]
        # Mirror _build_compaction_input's newest-first retention so the
        # omitted count matches the rendered text exactly.
        retained = 0
        used = 0
        limit = handler.compaction_input_char_limit
        for entry in reversed(serialized_entries):
            addition = len(entry) + 2
            if retained and used + addition > limit:
                break
            if not retained and len(entry) > limit:
                retained = 1
                used = limit
                break
            retained += 1
            used += addition
        text = handler._build_compaction_input()
        return {
            "text": text,
            "characters": len(text),
            "threshold": handler.compress_threshold,
            "round": handler._round,
            "messages": len(serialized_entries),
            "omitted": len(serialized_entries) - retained,
            "estimated_tokens": (len(text) + 3) // 4,
        }
    except (OSError, ValueError, json.JSONDecodeError):
        return empty


def _agent_context_graph(
    session_id: str,
    agent_name: str,
    *,
    limit: int = 60,
) -> ContextGraphSnapshot:
    """Return a bounded, browser-safe snapshot of one Agent's memory graph.

    Args:
        session_id: Browser-stable session that owns the Agent context files.
        agent_name: Graph-local Agent identity used in the context filename.
        limit: Maximum number of most-recent entities to expose. It is clamped
            to ``1..120`` so a large persisted graph cannot overload the UI.

    Returns:
        A read-only graph view containing display-safe entity, relation, and
        community fields plus total counts. Missing, legacy, or malformed
        companion files return the same empty shape with ``available=False``.

    Side Effects:
        Reads ``contexts/<agent>.json.graph.json`` only; it never changes
        persisted context or graph state.
    """
    def _integer(value: Any, default: int = 0) -> int:
        """Convert persisted numeric metadata without trusting old graph files."""
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _number(value: Any) -> float:
        """Convert a persisted relation weight while preserving an empty fallback."""
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    empty = ContextGraphSnapshot(False, 0, 0, 0, False, [], [], [])
    try:
        safe_session = _safe_id(session_id, "session")
        safe_agent = _safe_id(agent_name, "agent")
        context_path = _session_path(safe_session, safe_session) / "contexts" / f"{safe_agent}.json"
        try:
            context = json.loads(context_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            context = {}
        if isinstance(context, dict) and bool(
            (context.get("context_editing") or {}).get("graph_stale")
        ):
            return ContextGraphSnapshot(False, 0, 0, 0, False, [], [], [], stale=True)
        path = context_path.with_name(f"{context_path.name}.graph.json")
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return empty
    if not isinstance(raw, dict):
        return empty

    # Normalize persisted data before filtering it, keeping the browser API
    # independent from GraphStore's in-memory dataclasses.
    raw_nodes = raw.get("nodes", {})
    raw_edges = raw.get("edges", [])
    raw_communities = raw.get("communities", {})
    node_items = [item for item in raw_nodes.values() if isinstance(item, dict)] if isinstance(raw_nodes, dict) else []
    edge_items = [item for item in raw_edges if isinstance(item, dict)] if isinstance(raw_edges, list) else []
    community_items = [
        item
        for items in raw_communities.values()
        if isinstance(items, list)
        for item in items
        if isinstance(item, dict)
    ] if isinstance(raw_communities, dict) else []
    bounded_limit = max(1, min(_integer(limit, 60), 120))
    node_items.sort(key=lambda item: (
        -_integer(item.get("last_seen", 0)),
        -_integer(item.get("freq", 0)),
        str(item.get("name", "")).casefold(),
    ))
    visible = node_items[:bounded_limit]
    visible_ids = {str(item.get("id", "")) for item in visible}
    return ContextGraphSnapshot(
        available=True, node_count=len(node_items), edge_count=len(edge_items),
        community_count=len(community_items), truncated=len(node_items) > len(visible),
        nodes=[ContextGraphNode(str(item.get("id", "")), str(item.get("name", item.get("id", ""))), str(item.get("entity_type", "concept")), str(item.get("summary", ""))[:1_000], [str(alias)[:200] for alias in item.get("aliases", []) if isinstance(alias, str)][:12], _integer(item.get("first_seen", 0)), _integer(item.get("last_seen", 0)), _integer(item.get("freq", 0))) for item in visible],
        edges=[ContextGraphEdge(str(item.get("source_id", "")), str(item.get("target_id", "")), str(item.get("relation", "related_to")), _number(item.get("weight", 0)), _integer(item.get("first_seen", 0)), _integer(item.get("last_seen", 0)), bool(item.get("valid", True)), [int(value) for value in item.get("evidence", []) if isinstance(value, int) and not isinstance(value, bool)][:20]) for item in edge_items if str(item.get("source_id", "")) in visible_ids and str(item.get("target_id", "")) in visible_ids],
        communities=[ContextGraphCommunity(_integer(item.get("level", 0)), str(item.get("community_id", "")), str(item.get("summary", ""))[:1_000], [str(value) for value in item.get("member_entity_ids", []) if isinstance(value, str)][:30]) for item in community_items[:12]],
    )

__all__ = [
    "_history_context_paths",
    "AgentContextMetadata",
    "RemoteRequestStats",
    "AgentContextPreview",
    "ContextGraphNode",
    "ContextGraphEdge",
    "ContextGraphCommunity",
    "ContextGraphSnapshot",
    "_read_session_history",
    "_turns_from_legacy_context",
    "_turns_from_event_log",
    "migrate_legacy_state",
    "_empty_usage",
    "_session_usage_summary",
    "_archived_context_page",
    "_agent_context_preview",
    "_agent_turns_from_events",
    "_display_tools_from_event",
    "_read_agent_history",
    "_agent_context_stats",
    "_agent_context_graph",
    "render_markdown",
]
