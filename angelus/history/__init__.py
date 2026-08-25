"""Stable history facade split by projection responsibility.

Existing callers can continue importing symbols from :mod:`angelus.history`;
the implementation lives in focused modules so transcript, usage, and context
inspection changes no longer share one oversized source file.
"""

from typing import Any

from ..markdown import render_markdown
from ..storage import _session_path
from .context import (
    _agent_compaction_input_preview,
    _agent_context_graph,
    _agent_context_preview,
    _agent_context_stats,
)
from .models import (
    AgentContextMetadata,
    AgentContextPreview,
    ContextGraphCommunity,
    ContextGraphEdge,
    ContextGraphNode,
    ContextGraphSnapshot,
    RemoteRequestStats,
)
from . import transcripts as _transcripts
from .projection import transcript_page as _transcript_projection_page
from .transcripts import (
    _agent_turns_from_events,
    _display_tool_result,
    _display_tools_from_event,
    _history_context_paths,
    _iter_agent_turns_from_events,
    _paginate_turns,
    _read_agent_history,
    _read_session_history,
    _turns_from_event_log,
    _turns_from_legacy_context,
    migrate_legacy_state,
)
from .usage import (
    _archived_context_page,
    _current_run_window,
    _empty_usage,
    _session_usage_summary,
    _usage_from_events,
)


def _agent_turns_page(
    workspace_id: str,
    session_id: str,
    agent_name: str,
    *,
    cursor: str | None = None,
    before: int | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    """Return a transcript page while preserving facade-level patchability.

    Args:
        workspace_id: Internal storage partition owning the event log.
        session_id: Browser-stable session identifier.
        agent_name: Selected graph Agent or ``all`` for the canonical chat.
        cursor: Opaque projection cursor returned by the previous page.
        before: Deprecated exclusive chronological turn index.
        limit: Maximum returned turns, clamped by the implementation.

    Returns:
        A mapping containing chronological messages, total count, and the next
        older-page cursor.

    Notes:
        Older tests and integrations patch ``angelus.history._session_path``.
        The facade passes that hook explicitly into the focused transcript
        module so the package split remains compatible and thread-safe.
    """
    return _transcript_projection_page(
        workspace_id,
        session_id,
        agent_name,
        cursor=cursor,
        before=before,
        limit=limit,
        path_resolver=_session_path,
    )

__all__ = [
    "AgentContextMetadata",
    "RemoteRequestStats",
    "AgentContextPreview",
    "ContextGraphNode",
    "ContextGraphEdge",
    "ContextGraphCommunity",
    "ContextGraphSnapshot",
    "_history_context_paths",
    "_read_session_history",
    "_turns_from_legacy_context",
    "_turns_from_event_log",
    "migrate_legacy_state",
    "_empty_usage",
    "_session_usage_summary",
    "_archived_context_page",
    "_agent_context_preview",
    "_iter_agent_turns_from_events",
    "_agent_turns_from_events",
    "_paginate_turns",
    "_agent_turns_page",
    "_display_tools_from_event",
    "_read_agent_history",
    "_agent_context_stats",
    "_agent_compaction_input_preview",
    "_agent_context_graph",
    "render_markdown",
]
