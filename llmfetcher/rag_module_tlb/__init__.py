"""Hierarchical TLB-like RAG retrieval module.

Provides a Translation Lookaside Buffer (TLB) inspired RAG system that traverses
a hierarchical file tree using ``INDEX.md`` files as page-table entries.
Exposes the ``TLBRAGHandler`` class for direct use and ``create_tlb_rag_tool``
for registration as an Agent tool.
"""

from .type import TLBResult, NormalizedIntent, LeafFile, CacheCandidate
from .core import TLBRAGHandler
from .tlb_rag_tool import create_tlb_rag_tool

__all__ = [
    "TLBRAGHandler",
    "TLBResult",
    "NormalizedIntent",
    "LeafFile",
    "CacheCandidate",
    "create_tlb_rag_tool",
]
