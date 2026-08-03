"""Type definitions for the TLB-like hierarchical RAG module.

This module defines dataclasses for retrieval results, TLB cache entries,
and read traces used by the hierarchical file-tree traversal system.
"""

from dataclasses import dataclass, field


@dataclass
class NormalizedIntent:
    """A normalized retrieval intent decomposed into structured fields.

    Analogous to a virtual address in a TLB system — breaks down a user query
    into namespace, entity type, entity name, information type, and aspects.

    Attributes:
        namespace: The logical namespace or domain of the intent (e.g. module,
            package, or project name). ``None`` if not applicable.
        entity_type: The kind of entity being looked up (e.g. "class",
            "function", "module"). ``None`` if not applicable.
        entity: The specific entity name. ``None`` if not applicable.
        information_type: The kind of information sought (e.g. "signature",
            "usage", "definition").
        aspects: Specific sub-aspects or facets of the information type.
    """

    namespace: str | None = None
    entity_type: str | None = None
    entity: str | None = None
    information_type: str = ""
    aspects: list[str] = field(default_factory=list)


@dataclass
class LeafFile:
    """A resolved leaf file containing the requested information.

    Analogous to a resolved physical page in a TLB system.

    Attributes:
        path: Absolute path to the leaf file.
        reason: Why this file was selected as relevant.
    """

    path: str = ""
    reason: str = ""


@dataclass
class CacheCandidate:
    """A model-reported suggestion for a TLB cache entry.

    This is untrusted — the runtime validates it before writing to cache.

    Attributes:
        intent_key: The normalized intent key suggested by the model.
        node_path: The resolved file path suggested by the model.
    """

    intent_key: str = ""
    node_path: str = ""


@dataclass
class TLBEntry:
    """A verified runtime TLB cache entry mapping a query key to a file path.

    Attributes:
        query_key: Deterministic normalized query key.
        node_path: Verified absolute path within the knowledge root.
        entry_kind: ``"route"`` for an INDEX.md start node, ``"leaf"`` for a
            resolved leaf file.
        file_mtime_ns: File modification time in nanoseconds at cache time.
        file_size: File size in bytes at cache time.
        file_hash: SHA-256 hex digest of file content at cache time.
        created_at: Unix timestamp when the entry was created.
    """

    query_key: str
    node_path: str
    entry_kind: str  # "route" | "leaf"
    file_mtime_ns: int
    file_size: int
    file_hash: str
    created_at: float


@dataclass
class ReadTraceEntry:
    """A single file read recorded by the runtime during a worker traversal.

    Attributes:
        resolved_path: Absolute resolved path of the file read.
        is_index: ``True`` if the file is named INDEX.md.
        byte_size: Number of bytes read.
        mtime_ns: File modification time in nanoseconds at read time.
        sha256: SHA-256 hex digest of the file content.
        success: ``True`` if the read succeeded.
        error: Error message if the read failed, or ``None``.
    """

    resolved_path: str
    is_index: bool
    byte_size: int
    mtime_ns: int
    sha256: str
    success: bool
    error: str | None = None


# Allowed status values for TLBResult.
_VALID_STATUSES = frozenset({
    "resolved",
    "retrieval_miss",
    "root_unreachable",
    "ambiguous_entity",
    "parse_error",
})


# Valid entry_kind values for TLBEntry.
_VALID_ENTRY_KINDS = frozenset({"route", "leaf"})


@dataclass
class TLBResult:
    """The complete result of a TLB-like hierarchical RAG retrieval.

    Fields marked ``(runtime)`` are set or corrected by the runtime after
    the worker agent completes — they override any model-reported values.

    Attributes:
        status: Outcome status. Must be one of the values in
            ``_VALID_STATUSES``.
        normalized_intent: The decomposed retrieval intent, or ``None``.
        tlb_hit: ``(runtime)`` ``True`` if the runtime resolved this query
            from a validated cache entry without a full page-table walk.
        resolved: ``True`` if the retrieval successfully located leaf files.
        start_node: Path to the root ``INDEX.md`` where traversal began, or
            ``None``.
        visited_indexes: ``(runtime)`` Ordered list of INDEX.md paths
            actually visited, derived from the read trace.
        rejected_branches: Model-reported branches explored and rejected.
            Marked as model-provided, not runtime-verified.
        leaf_files: ``(runtime)`` Verified leaf files — each path has been
            validated to exist within root and to have been actually read.
        cache_candidate: A model-suggested intent-to-path mapping. Runtime
            validates before writing to cache.
        error: Error message if status indicates failure, or ``None``.
    """

    status: str = ""
    normalized_intent: NormalizedIntent | None = None
    tlb_hit: bool = False
    resolved: bool = False
    start_node: str | None = None
    visited_indexes: list[str] = field(default_factory=list)
    rejected_branches: list[str] = field(default_factory=list)
    leaf_files: list[LeafFile] = field(default_factory=list)
    cache_candidate: CacheCandidate | None = None
    error: str | None = None
