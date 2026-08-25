"""Typed response models for history and context inspection."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

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

