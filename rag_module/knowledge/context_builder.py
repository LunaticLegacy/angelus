"""Prompt-context construction for retrieved knowledge hits."""

from __future__ import annotations

from .models import KnowledgeHit


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

    def build(self, hits: list[KnowledgeHit]) -> str:
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
            return '未找到匹配当前任务的知识条目。需要时可调用 `search_knowledge` 手动检索。'

        # Split strategy hits from normal knowledge hits so strategy cards remain
        # first in the generated prompt context.
        strategy_hits = [hit for hit in hits if hit.path.startswith(self.strategy_prefix)]
        knowledge_hits = [hit for hit in hits if not hit.path.startswith(self.strategy_prefix)]

        # Start with the original policy sentence that defines source priority for
        # the downstream agent.
        lines = ['以下是与当前任务最相关的本地知识摘要。使用顺序必须是：解题策略优先，本地专题知识第二，互联网资料第三。']

        # Render strategy hits first because they are intended to control overall
        # solving approach rather than provide isolated facts.
        if strategy_hits:
            lines.append('优先策略：')
            for index, hit in enumerate(strategy_hits, start=1):
                lines.append(f'{index}. {hit.title} ({hit.path})')
                lines.append(f'   {hit.excerpt}')

        # Render non-strategy knowledge after strategy cards, preserving the old
        # two-section prompt layout.
        if knowledge_hits:
            lines.append('相关知识：')
            for index, hit in enumerate(knowledge_hits, start=1):
                lines.append(f'{index}. {hit.title} ({hit.path})')
                lines.append(f'   {hit.excerpt}')

        # Append the original escalation rule so local retrieval remains preferred
        # over web search in the agent's subsequent workflow.
        lines.append('如果策略卡和本地知识仍不足以支撑下一步，再调用 `search_knowledge` 细化检索；只有本地策略与知识都不够时，才升级到 `search_web`。')
        return '\n'.join(lines)
