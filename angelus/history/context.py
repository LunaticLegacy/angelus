"""Read-only Agent context, request and graph inspection projections."""

from __future__ import annotations

import json
from typing import Any

from ..context_stats import estimate_context_length
from ..storage import _read_session_event_log, _safe_id, _session_path
from .models import (
    AgentContextMetadata,
    AgentContextPreview,
    ContextGraphCommunity,
    ContextGraphEdge,
    ContextGraphNode,
    ContextGraphSnapshot,
    RemoteRequestStats,
)

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

