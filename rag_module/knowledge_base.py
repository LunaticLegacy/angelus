"""Backward-compatible import shim for the refactored knowledge package.

Existing code that imports `KnowledgeBase`, `KnowledgeHit`, or
`KnowledgeIndexEntry` from `knowledge_base.py` can keep doing so while the real
implementation lives in the `knowledge` package.
"""

from __future__ import annotations

from .knowledge import (
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeHit,
    KnowledgeIndexEntry,
    RetrievalQuery,
    VectorHit,
)

__all__ = [
    'KnowledgeBase',
    'KnowledgeChunk',
    'KnowledgeDocument',
    'KnowledgeHit',
    'KnowledgeIndexEntry',
    'RetrievalQuery',
    'VectorHit',
]
