"""Host-supplied knowledge corpus behind the per-Agent pin surface.

The kernel owns the durable pin document and the request-time rendering, but
never the documents themselves. An embedding application supplies a corpus;
the CTF product corpus is one implementation, a test fixture is another.
"""

from __future__ import annotations

from typing import Protocol


class KnowledgeDocument(Protocol):
    """One document a corpus can resolve by its stable relative path."""

    path: str
    title: str
    content: str


class KnowledgeCorpus(Protocol):
    """Read-only document source a host binds to the pin service."""

    def directions(self) -> dict[str, int]:
        """Return the visible document counts keyed by direction name."""
        ...

    def read(self, path: str) -> KnowledgeDocument:
        """Resolve one document.

        Args:
            path: Stable path supplied by the caller or stored in a pin list.

        Returns:
            The resolved document.

        Raises:
            KeyError: If no document exists at that path.
            ValueError: If the path is rejected as malformed.
        """
        ...


__all__ = ["KnowledgeCorpus", "KnowledgeDocument"]
