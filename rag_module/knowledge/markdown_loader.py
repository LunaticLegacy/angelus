"""Markdown filesystem loader for the local knowledge base."""

from __future__ import annotations

from fnmatch import fnmatchcase
from pathlib import Path
from collections.abc import Iterable

from .models import KnowledgeDocument


class MarkdownKnowledgeLoader:
    """Loads Markdown knowledge documents from a configured root directory.

    The loader owns filesystem scanning and document title extraction. It does
    not perform retrieval, vector indexing, or prompt construction.
    """

    def __init__(self, root: Path) -> None:
        """Initialize the loader with a knowledge root.

        Args:
            root: Absolute or relative path to the local Markdown knowledge-base
                directory.
        """
        # Store a resolved root so all relative-path calculations remain stable
        # even when callers pass `.` or symlinked paths.
        self.root = root.resolve()

    def available(self) -> bool:
        """Return whether the configured knowledge root exists.

        Returns:
            `True` when the root exists and is a directory, otherwise `False`.
        """
        # Keep availability as a cheap filesystem check that callers can use
        # before attempting scans, reads, or index rebuilds.
        return self.root.exists() and self.root.is_dir()

    def iter_entry_files(self) -> Iterable[Path]:
        """Yield Markdown files that should be treated as knowledge entries.

        The method preserves the old exclusion rules for `index.md`, root
        `README.md`, files under `templates/`, and any path matched by the
        knowledge-root `.kbignore` file.

        Yields:
            Absolute paths to Markdown entry files in deterministic sorted order.
        """
        ignore_patterns = self._load_ignore_patterns()

        # Iterate through sorted Markdown paths so manifests and search results
        # remain deterministic across platforms.
        for candidate in sorted(self.root.rglob('*.md')):
            relative = candidate.relative_to(self.root)
            parts = relative.parts

            # Preserve original skip rules for generated indexes, templates, and
            # the top-level README that describes the knowledge base itself.
            if not parts:
                continue
            if candidate.name == 'index.md':
                continue
            if parts[0] == 'templates':
                continue
            if candidate.name == 'README.md' and len(parts) == 1:
                continue
            if self._is_ignored_path(relative.as_posix(), ignore_patterns):
                continue
            yield candidate

    def read_document(self, path: Path) -> KnowledgeDocument:
        """Read and parse a single Markdown knowledge document.

        Args:
            path: Absolute path to a Markdown document under the configured root.

        Returns:
            A `KnowledgeDocument` containing path metadata, title, and content.
        """
        # Decode with replacement errors to preserve the old behavior of keeping
        # searchable text even when a file contains invalid UTF-8 bytes.
        content = path.read_text(encoding='utf-8', errors='replace')
        title = self.extract_title(path, content)

        # Build both root-relative and repository-relative paths because the old
        # code used both forms in scoring and returned hit metadata.
        root_relative_path = str(path.relative_to(self.root))
        repository_relative_path = str(path.relative_to(self.root.parent))

        # Return a structured document so downstream components do not need to
        # repeatedly re-read and re-parse the same path information.
        return KnowledgeDocument(
            absolute_path=path,
            root_relative_path=root_relative_path,
            repository_relative_path=repository_relative_path,
            title=title,
            content=content,
        )

    def load_documents(self) -> list[KnowledgeDocument]:
        """Load every knowledge entry document under the root.

        Returns:
            A list of parsed `KnowledgeDocument` objects in sorted path order.
        """
        # Materialize the generator because rebuild, freshness checks, and hybrid
        # retrieval all need stable repeatable document lists.
        return [self.read_document(path) for path in self.iter_entry_files()]

    def extract_title(self, path: Path, content: str) -> str:
        """Extract a document title from Markdown content.

        The first Markdown heading is used when present; otherwise the filename
        stem is converted to a space-separated title.

        Args:
            path: Source Markdown file path used for fallback title generation.
            content: Raw Markdown content.

        Returns:
            A non-empty title string.
        """
        # Start with the filename fallback so empty or heading-less files still
        # have a stable display title.
        title = path.stem.replace('-', ' ')

        # Walk the file linearly and use the first Markdown heading, preserving
        # the old implementation's simple heading detection behavior.
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith('#'):
                title = stripped.lstrip('#').strip() or title
                break

        # Return the heading-derived or fallback title without further semantic
        # normalization to preserve old display behavior.
        return title

    def _load_ignore_patterns(self) -> list[str]:
        """Load repository-level `.kbignore` patterns.

        Returns:
            Ordered ignore patterns, or an empty list when the file does not
            exist or cannot be read.
        """
        ignore_file = self.root / '.kbignore'
        try:
            raw_lines = ignore_file.read_text(encoding='utf-8').splitlines()
        except OSError:
            return []

        patterns: list[str] = []
        for line in raw_lines:
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue
            patterns.append(stripped.replace('\\', '/'))
        return patterns

    def _is_ignored_path(self, root_relative: str, patterns: list[str]) -> bool:
        """Return whether a path matches any configured `.kbignore` pattern."""
        for pattern in patterns:
            if self._match_ignore_pattern(root_relative, pattern):
                return True
        return False

    def _match_ignore_pattern(self, path: str, pattern: str) -> bool:
        """Match one path against a `.kbignore` pattern.

        Directory patterns ending in `/` match the directory itself and any
        descendant path. Other patterns use glob matching.
        """
        normalized_path = path.replace('\\', '/')
        normalized_pattern = pattern.replace('\\', '/')

        if normalized_pattern.endswith('/'):
            directory = normalized_pattern.rstrip('/')
            return normalized_path == directory or normalized_path.startswith(directory + '/')

        if fnmatchcase(normalized_path, normalized_pattern):
            return True

        # Allow directory-style matches without a trailing slash so a pattern
        # like `kb/case-studies/drafts` still ignores the subtree.
        return normalized_path == normalized_pattern or normalized_path.startswith(normalized_pattern + '/')
