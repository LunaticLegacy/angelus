"""Type definitions for the TLB-like hierarchical RAG module.

This module defines the dataclasses that represent retrieval results from a
Translation Lookaside Buffer (TLB) style hierarchical file-tree traversal.
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
    """A proposed TLB cache entry mapping an intent to a file path.

    Attributes:
        intent_key: The normalized intent key (analogous to a virtual page number).
        node_path: The resolved file path (analogous to a physical frame number).
    """

    intent_key: str = ""
    node_path: str = ""


@dataclass
class TLBResult:
    """The complete result of a TLB-like hierarchical RAG retrieval.

    Maps to the JSON response schema returned by the worker agent after
    traversing the file tree.

    Attributes:
        status: Outcome status — one of ``"resolved"``, ``"retrieval_miss"``,
            ``"root_unreachable"``, ``"ambiguous_entity"``, or
            ``"invalid_cache_entry"``.
        normalized_intent: The decomposed retrieval intent, or ``None`` if
            normalization failed.
        tlb_hit: ``True`` if the intent was resolved from the route cache
            without a full traversal.
        resolved: ``True`` if the retrieval successfully located leaf files.
        start_node: Path to the root ``INDEX.md`` where traversal began, or
            ``None``.
        visited_indexes: Ordered list of ``INDEX.md`` paths visited during
            traversal.
        rejected_branches: Branches that were explored and rejected as
            irrelevant.
        leaf_files: The resolved leaf files containing the target information.
        cache_candidate: A proposed intent-to-path mapping for future TLB
            caching, or ``None``.
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
