"""Deterministic keyword scoring for knowledge documents."""

from __future__ import annotations

from pathlib import Path

from .models import KnowledgeChunk, KnowledgeDocument
from .text_utils import TextTools


class KeywordRetriever:
    """Scores documents using deterministic title, path, and content matches.

    This class preserves the old count-based scoring semantics while removing
    keyword logic from the facade and vector-store code.
    """

    def __init__(self, text: TextTools) -> None:
        """Initialize the keyword retriever.

        Args:
            text: Text helper used for shared term extraction.
        """
        # Keep a shared text helper so query normalization stays consistent with
        # task-policy and excerpt-building code.
        self.text = text

    def extract_terms(self, values: list[str]) -> list[str]:
        """Extract searchable keyword terms from text values.

        Args:
            values: Text fields such as query text, task name, target, and file
                descriptions.

        Returns:
            Unique normalized terms in first-seen order.
        """
        # Delegate tokenization to the shared text helper so all retrievers use
        # the same technical-token and Chinese-phrase rules.
        return self.text.extract_terms(values)

    def score_document(self, document: KnowledgeDocument, terms: list[str]) -> int:
        """Score a document using deterministic keyword matching.

        Args:
            document: Parsed knowledge document to score.
            terms: Normalized keyword terms extracted from the query.

        Returns:
            Integer keyword score. Higher values indicate stronger deterministic
            lexical relevance.
        """
        # Normalize title, root-relative path, and content once to avoid repeated
        # lowercase conversions inside the term loop.
        title_lower = document.title.lower()
        path_lower = document.root_relative_path.lower()
        content_lower = document.content.lower()
        score = 0

        # Preserve the old weighting: title hits are strongest, path hits are
        # medium strength, and content occurrences are capped per term.
        for term in terms:
            if term in title_lower:
                score += 12
            if term in path_lower:
                score += 8
            occurrences: int = content_lower.count(term) # 匹配关键词的次数
            if occurrences:
                score += min(occurrences, 6) * 3
        return score

    def score_chunk(self, chunk: KnowledgeChunk, terms: list[str]) -> int:
        """Score a chunk using deterministic keyword matching.

        Args:
            chunk: Chunk produced from a parsed markdown document.
            terms: Normalized keyword terms extracted from the query.

        Returns:
            Integer keyword score for the chunk body and its metadata.
        """
        # Reuse the document scorer by folding in the source title, chunk title,
        # heading path, and body content so chunk hits still benefit from the
        # old lexical ranking model.
        combined_title = ' '.join(
            value
            for value in [chunk.source_title, chunk.chunk_title, chunk.heading_path]
            if value
        )
        synthetic_document = KnowledgeDocument(
            absolute_path=Path(chunk.source_path),
            root_relative_path=chunk.source_path,
            repository_relative_path=chunk.source_path,
            title=combined_title or chunk.source_title,
            content=chunk.content,
        )
        return self.score_document(synthetic_document, terms)
