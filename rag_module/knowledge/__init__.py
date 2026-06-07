"""Local knowledge-base package with a facade-oriented public API."""

from __future__ import annotations

from .facade import KnowledgeBase
from .models import KnowledgeDocument, KnowledgeHit, KnowledgeIndexEntry, RetrievalQuery, VectorHit

__all__ = [
    'KnowledgeBase',
    'KnowledgeDocument',
    'KnowledgeHit',
    'KnowledgeIndexEntry',
    'RetrievalQuery',
    'VectorHit',
]
