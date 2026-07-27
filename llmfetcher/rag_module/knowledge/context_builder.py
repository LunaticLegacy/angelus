"""Prompt-context construction for retrieved knowledge hits."""

from __future__ import annotations

from .models import KnowledgeHit
from .prompt import MESSAGE_NOT_HIT, MESSAGE_HIT_HEADER, MESSAGE_HIT_END

from typing import List

class TaskContextBuilder:
    """Formats retrieval results into task-oriented prompt context.

    This class keeps agent prompt policy separate from retrieval and indexing
    infrastructure.
    """

    def __init__(self, *, strategy_prefix: str) -> None:
        """Initialize the context builder.

        Args:
            strategy_prefix: Repository-relative prefix used to classify strategy
                hits before normal knowledge hits.
        """
        # Store the prefix rather than importing configuration globally, keeping
        # this formatter easy to test in isolation.
        self.strategy_prefix = strategy_prefix

    def build(self, hits: List[KnowledgeHit]) -> str:
        """Build system-prompt context from ranked knowledge hits.

        Args:
            hits: Ranked knowledge hits returned by task-aware retrieval.

        Returns:
            Chinese prompt-context string. When no hits are available, returns the
            same fallback message as the original implementation.
        """
        # Preserve the old no-hit behavior so agents still receive a clear manual
        # search instruction when prefetch retrieval fails.
        if not hits:
            return MESSAGE_NOT_HIT

        # Split strategy hits from normal knowledge hits so strategy cards remain
        # first in the generated prompt context.
        strategy_hits = [hit for hit in hits if hit.path.startswith(self.strategy_prefix)]
        knowledge_hits = [hit for hit in hits if not hit.path.startswith(self.strategy_prefix)]

        # Start with the original policy sentence that defines source priority for
        # the downstream agent.a message
        lines: List[str] = []
        lines.append(MESSAGE_HIT_HEADER)

        # Render strategy hits first because they are intended to control overall
        # solving approach rather than provide isolated facts.
        if strategy_hits:
            lines.append('Strategies: ')
            for index, hit in enumerate(strategy_hits, start=1):
                chunk_suffix = f' / {hit.chunk_title}' if hit.chunk_title else ''
                chunk_span = f' chunk {hit.chunk_index + 1}' if hit.chunk_key else ''
                lines.append(f'{index}. {hit.title}{chunk_suffix} ({hit.path}{chunk_span})')
                lines.append(f'   {hit.excerpt}')

        # Render non-strategy knowledge after strategy cards, preserving the old
        # two-section prompt layout.
        if knowledge_hits:
            lines.append('Relative knowledges: ')
            for index, hit in enumerate(knowledge_hits, start=1):
                chunk_suffix = f' / {hit.chunk_title}' if hit.chunk_title else ''
                chunk_span = f' chunk {hit.chunk_index + 1}' if hit.chunk_key else ''
                lines.append(f'{index}. {hit.title}{chunk_suffix} ({hit.path}{chunk_span})')
                lines.append(f'   {hit.excerpt}')

        # Append the original escalation rule so local retrieval remains preferred
        # over web search in the agent's subsequent workflow.
        lines.append(MESSAGE_HIT_END)
        return '\n'.join(lines)
