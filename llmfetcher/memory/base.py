"""Abstract contracts for retrieval-backed Agent memory."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class MemoryItem:
    """One retrieved or persisted memory fragment.

    Args:
        content: Text injected into the model context.
        score: Provider-specific relevance score, where larger is better.
        memory_id: Stable provider identifier.
        metadata: Optional source and tenancy metadata.
    """

    content: str
    score: float = 0.0
    memory_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class MemoryProvider(Protocol):
    """Protocol implemented by vector, hybrid, or remote memory stores."""

    def search(self, query: str, *, limit: int = 5, namespace: str = "") -> list[MemoryItem]:
        """Return memories relevant to a query."""

    def add(self, item: MemoryItem, *, namespace: str = "") -> None:
        """Persist one memory item in a namespace."""
