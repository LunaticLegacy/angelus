"""Text normalization helpers shared by knowledge-base components."""

from __future__ import annotations

import re
from typing import Sequence


class TextTools:
    """Provides reusable text extraction and excerpt helpers.

    This class contains pure text-processing behavior so loaders, retrievers,
    and vector stores do not duplicate regular expressions or excerpt rules.
    """

    def __init__(self, *, excerpt_chars: int, embedding_max_chars: int) -> None:
        """Initialize text helper limits.

        Args:
            excerpt_chars: Maximum number of characters returned by excerpts.
            embedding_max_chars: Maximum number of normalized content characters
                included in semantic documents.
        """
        # Store limits from configuration so all text helpers share the same
        # truncation behavior as the original monolithic implementation.
        self.excerpt_chars = excerpt_chars
        self.embedding_max_chars = embedding_max_chars

    def extract_terms(self, values: Sequence[str]) -> list[str]:
        """Extract normalized keyword terms from arbitrary text values.

        The method preserves the old tokenization rule: ASCII technical tokens
        and contiguous Chinese phrases of length at least two are retained.

        Args:
            values: Text values whose terms should be merged and deduplicated in
                first-seen order.

        Returns:
            A list of lowercase unique search terms.
        """
        # Maintain deterministic ordering by using a list for output and a set
        # only for membership checks.
        terms: list[str] = []
        seen: set[str] = set()

        # Walk each input independently so empty or None-like strings are simply
        # ignored without affecting the rest of the query.
        for value in values:
            for raw_term in re.findall(r'[A-Za-z0-9_./+-]+|[\u4e00-\u9fff]{2,}', value or ''):
                term = raw_term.strip().lower()
                if len(term) < 2 or term in seen:
                    continue
                seen.add(term)
                terms.append(term)

        # Return only unique meaningful terms, preserving compatibility with the
        # previous keyword scoring behavior.
        return terms

    def build_excerpt(self, content: str, terms: Sequence[str]) -> str:
        """Build a short excerpt from Markdown content.

        The method first prefers a non-heading line containing any query term,
        then falls back to the first usable non-heading line.

        Args:
            content: Raw Markdown document content.
            terms: Normalized query terms used to select the best excerpt line.

        Returns:
            A trimmed excerpt string, or an empty string when no usable line is
            available.
        """
        # Normalize the document into non-empty candidate lines while preserving
        # original line-level ordering for deterministic excerpt selection.
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        lowered_terms = [term.lower() for term in terms]

        # Prefer a line that mentions one of the query terms, because that keeps
        # the displayed result connected to the user's requested topic.
        for line in lines:
            if line.startswith('#') or self.should_skip_excerpt_line(line):
                continue
            if any(term in line.lower() for term in lowered_terms):
                return self.trim_excerpt(line)

        # Fall back to the first usable line so semantic-only hits still show a
        # meaningful preview even when no keyword term appears in the excerpt.
        for line in lines:
            if line.startswith('#') or self.should_skip_excerpt_line(line):
                continue
            return self.trim_excerpt(line)

        # Return the same empty fallback as the old implementation when a file
        # contains only headings, tables, or ignored references.
        return ''

    def should_skip_excerpt_line(self, line: str) -> bool:
        """Return whether a line is unsuitable for excerpt display.

        Args:
            line: Candidate Markdown line after whitespace trimming.

        Returns:
            `True` when the line should be skipped, otherwise `False`.
        """
        # Normalize once so the skip rules are case-insensitive and unaffected
        # by accidental leading or trailing whitespace.
        normalized = line.strip().lower()
        if not normalized:
            return True

        # Preserve the original behavior that hides internal prompt/kb reference
        # lists from user-facing excerpts.
        if normalized.startswith('- `prompts/') or normalized.startswith('- `kb/'):
            return True

        # Preserve the old table-skip behavior because table rows are usually
        # poor standalone excerpts.
        if normalized.startswith('| ') or normalized.startswith('|'):
            return True
        return False

    def trim_excerpt(self, text: str) -> str:
        """Normalize and trim an excerpt string.

        Args:
            text: Raw excerpt text selected from a Markdown line.

        Returns:
            Whitespace-normalized excerpt capped at `excerpt_chars`.
        """
        # Collapse internal whitespace to keep prompt context compact and stable
        # across Markdown formatting differences.
        normalized = re.sub(r'\s+', ' ', text).strip()
        if len(normalized) <= self.excerpt_chars:
            return normalized

        # Match the old truncation style by reserving three characters for the
        # ellipsis and avoiding trailing whitespace before it.
        return normalized[: self.excerpt_chars - 3].rstrip() + '...'

    def build_semantic_document(self, *, title: str, relative_path: str, content: str) -> str:
        """Build the text payload stored in the semantic vector index.

        Args:
            title: Parsed document title.
            relative_path: Repository-relative Markdown path.
            content: Raw Markdown document content.

        Returns:
            Semantic document string containing title, path, and truncated body.
        """
        # Normalize whitespace before truncation so semantically equivalent
        # Markdown formatting produces stable vector input length.
        cleaned_content = re.sub(r'\s+', ' ', content).strip()
        if len(cleaned_content) > self.embedding_max_chars:
            cleaned_content = cleaned_content[: self.embedding_max_chars].rstrip()

        # Preserve the old semantic document shape so existing embeddings are
        # conceptually equivalent after a rebuild.
        return f'{title}\n\n{relative_path}\n\n{cleaned_content}'

    def excerpt_from_semantic_document(self, document: str) -> str:
        """Extract a display excerpt from a stored semantic document payload.

        Args:
            document: Semantic document text previously built for vector storage.

        Returns:
            Best-effort excerpt extracted from the semantic document body.
        """
        # Split title/path/body using the original double-newline structure and
        # keep the final segment as the body for excerpt construction.
        parts = document.split('\n\n', 2)
        body = parts[-1] if parts else document

        # Use the generic excerpt builder without query terms, matching the old
        # vector-hit fallback behavior.
        return self.build_excerpt(body, [])
