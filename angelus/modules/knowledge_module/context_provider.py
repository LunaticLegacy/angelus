"""Module-owned context: corpus directions plus this Agent's pinned documents.

The corpus is read-only at request time; only the pin list is mutable, and it
is owned by :class:`KnowledgeInjectionService` so the Agent tools and the
Session UI always see the same document.
"""

from __future__ import annotations

from typing import Sequence

from llmfetcher.context_handlers import (
    ContextBlock,
    ContextPosition,
    ContextProvider,
    ContextSnapshot,
)

from ..context_module import ContextProviderRegistration, ContextProviderRequest
from .injection import KnowledgeInjectionService

MAX_ENTRY_CHARS = 4000
MAX_TOTAL_CHARS = 12000


class KnowledgeContextProvider:
    """Project the corpus directions and the Agent's pinned documents.

    Args:
        session_id: Session owning the durable pin list.
        agent_name: Agent whose pins this source represents.
        injection: Process-owned service that owns the pin document.
    """

    provider_id = "angelus.knowledge"

    def __init__(self, session_id: str, agent_name: str, injection: KnowledgeInjectionService) -> None:
        self._session_id = session_id
        self._agent_name = agent_name
        self._injection = injection

    @property
    def source_id(self) -> str:
        """Return the stable Composer source identity."""
        return self.provider_id

    def build_blocks(self, snapshot: ContextSnapshot) -> Sequence[ContextBlock]:
        """Render one bounded block from the bound corpus and the pin list.

        Args:
            snapshot: Composer snapshot for the request being assembled.

        Returns:
            One persistent system block, or nothing when no corpus is bound.
        """
        if not self._injection.available:
            return []
        corpus = self._injection.corpus
        counts = corpus.directions()
        directions = ", ".join(
            f"{name} ({count})" for name, count in sorted(counts.items())
        ) or "(empty)"
        pinned = self._injection.read(self._session_id, self._agent_name)
        sections = [
            "<angelus_knowledge>",
            f"<agent>{self._agent_name}</agent>",
            f"<directions>{directions}</directions>",
            "<usage>Pinned documents below are already in context. "
            "Use the knowledge tools to search or read more.</usage>",
        ]
        truncated = False
        if not pinned:
            sections.append("<pinned>none</pinned>")
        else:
            sections.append(f"<pinned count=\"{len(pinned)}\">")
            used = 0
            shown = 0
            for path in pinned:
                budget = min(MAX_ENTRY_CHARS, MAX_TOTAL_CHARS - used)
                if budget <= 0:
                    truncated = True
                    break
                try:
                    entry = corpus.read(path)
                except KeyError:
                    sections.append(f"<missing path=\"{path}\" />")
                    continue
                content = entry.content[:budget]
                sections.append(f"<document path=\"{entry.path}\" title=\"{entry.title}\">")
                sections.append(content.rstrip())
                if len(entry.content) > budget:
                    sections.append("<truncated />")
                    truncated = True
                sections.append("</document>")
                used += len(content)
                shown += 1
            if shown < len(pinned):
                truncated = True
            if truncated:
                sections.append(f"<truncated shown=\"{shown}\" total=\"{len(pinned)}\" />")
            sections.append("</pinned>")
        sections.append("</angelus_knowledge>")
        return [ContextBlock(
            role="system",
            content="\n".join(sections),
            source=self.source_id,
            position=ContextPosition.PERSISTENT,
            persistent=True,
            metadata={
                "agent": self._agent_name,
                "pinned": len(pinned),
                "directions": len(counts),
                "truncated": truncated if pinned else False,
            },
        )]


class KnowledgeContextFactory:
    """Materialize the knowledge source for one Agent."""

    def __init__(self, injection: KnowledgeInjectionService) -> None:
        self._injection = injection

    def build(self, request: ContextProviderRequest) -> Sequence[ContextProvider]:
        """Return the Agent's knowledge source.

        Args:
            request: Live Session, grants and Agent identity.

        Returns:
            The single knowledge source, or nothing when no corpus is bound.
        """
        if not self._injection.available:
            return ()
        return (KnowledgeContextProvider(
            request.workspace.session_id,
            request.agent_name,
            self._injection,
        ),)


def knowledge_context_registration(injection: KnowledgeInjectionService) -> ContextProviderRegistration:
    """Return the knowledge source registration for the process registry.

    Args:
        injection: Process-owned pin service shared by every Agent.

    Returns:
        Registration gated on the pin Tool grant, so a host without pins
        injects nothing even when a corpus is bound.
    """
    return ContextProviderRegistration(
        id=KnowledgeContextProvider.provider_id,
        factory=KnowledgeContextFactory(injection),
        gates=(("knowledge", "knowledge_pin"),),
    )


__all__ = [
    "KnowledgeContextFactory",
    "KnowledgeContextProvider",
    "knowledge_context_registration",
]
