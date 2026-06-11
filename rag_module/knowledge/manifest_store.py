"""Manifest persistence and freshness checks for vector indexes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .config import KnowledgeConfig
from .models import KnowledgeDocument, KnowledgeIndexEntry, ManifestMeta


class KnowledgeManifestStore:
    """Reads, writes, and validates the `.vector_index.json` manifest.

    This class isolates manifest schema handling from retrieval and vector-store
    code. It intentionally preserves the old manifest shape.
    """

    def __init__(self, config: KnowledgeConfig) -> None:
        """Initialize the store with manifest configuration.

        Args:
            config: Knowledge-base configuration containing index path, backend,
                model name, and manifest version.
        """
        # Store configuration and initialize metadata to an empty-but-valid state
        # so status calls have deterministic fields before the manifest is read.
        self.config = config
        self.meta = self.build_meta(entry_count=0, chunk_count=0, backend_ready=False, last_error='')

    def load(self, path: Path | None = None) -> dict[str, KnowledgeIndexEntry] | None:
        """Load index entries from the manifest file.

        Args:
            path: Optional explicit manifest path. When omitted, the configured
                `index_path` is used.

        Returns:
            A dictionary keyed by repository-relative path, or `None` if the file
            cannot be read or does not match the expected structure.
        """
        # Resolve the target path once so compatibility callers can pass an old
        # manifest location while normal code uses the configured default.
        manifest_path = path or self.config.index_path
        try:
            payload = json.loads(manifest_path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            return None

        # Validate the root entry container before mutating store metadata. This
        # avoids accepting malformed manifests as fresh indexes.
        raw_entries = payload.get('entries', {})
        if not isinstance(raw_entries, dict):
            return None

        # Load manifest-level metadata with the same defaults as the old class
        # used when fields were absent.
        self.meta = ManifestMeta(
            version=int(payload.get('version', 1) or 1),
            backend=str(payload.get('backend', self.config.semantic_backend)).strip() or self.config.semantic_backend,
            embedding_model=str(payload.get('embedding_model', self.config.embedding_model_name)).strip()
            or self.config.embedding_model_name,
            backend_ready=bool(payload.get('backend_ready')),
            entry_count=int(payload.get('entry_count', 0) or 0),
            chunk_count=int(payload.get('chunk_count', 0) or 0),
            last_error=str(payload.get('last_error', '')).strip(),
        )

        # Convert raw entry dictionaries into strongly typed manifest entries,
        # preserving the old fallback document ID derivation.
        loaded: dict[str, KnowledgeIndexEntry] = {}
        for key, value in raw_entries.items():
            if not isinstance(value, dict):
                continue
            relative_path = str(value.get('path', key)).strip()
            if not relative_path:
                continue
            loaded[relative_path] = KnowledgeIndexEntry(
                path=relative_path,
                title=str(value.get('title', '')).strip(),
                fingerprint=str(value.get('fingerprint', '')).strip(),
                excerpt=str(value.get('excerpt', '')).strip(),
                document_id=str(value.get('document_id', '')).strip() or self.document_id(relative_path),
            )
        return loaded

    def save(
        self,
        entries: dict[str, KnowledgeIndexEntry],
        *,
        chunk_count: int,
        backend_ready: bool,
        last_error: str,
    ) -> None:
        """Write the vector-index manifest to disk.

        Args:
            entries: Manifest entries keyed by repository-relative path.
            backend_ready: Whether the vector backend was rebuilt successfully.
            last_error: Last rebuild error string, or an empty string.

        Returns:
            None. The manifest file is written as a filesystem side effect.
        """
        # Rebuild metadata immediately before writing so entry count and backend
        # state always match the payload being serialized.
        self.meta = self.build_meta(
            entry_count=len(entries),
            chunk_count=chunk_count,
            backend_ready=backend_ready,
            last_error=last_error,
        )

        # Preserve the old manifest shape by merging header fields with an
        # `entries` object at the root of the JSON document.
        payload = {
            **self.meta.to_dict(),
            'entries': {key: value.to_dict() for key, value in entries.items()},
        }

        # Write UTF-8 JSON with non-ASCII characters preserved for easier manual
        # inspection of Chinese titles and paths.
        self.config.index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

    def build_meta(self, *, entry_count: int, chunk_count: int, backend_ready: bool, last_error: str) -> ManifestMeta:
        """Build manifest metadata using configured constants.

        Args:
            entry_count: Number of indexed entries.
            chunk_count: Number of chunk-level semantic entries.
            backend_ready: Whether the semantic backend is considered usable.
            last_error: Last backend or rebuild error string.

        Returns:
            A `ManifestMeta` value ready for serialization or status reporting.
        """
        # Centralize manifest header construction so save paths and unavailable
        # paths produce the same schema.
        return ManifestMeta(
            version=self.config.manifest_version,
            backend=self.config.semantic_backend,
            embedding_model=self.config.embedding_model_name,
            backend_ready=backend_ready,
            entry_count=entry_count,
            chunk_count=chunk_count,
            last_error=last_error.strip(),
        )

    def is_fresh(
        self,
        loaded: dict[str, KnowledgeIndexEntry],
        documents: list[KnowledgeDocument],
    ) -> bool:
        """Return whether a loaded manifest matches the current documents.

        Args:
            loaded: Manifest entries keyed by repository-relative path.
            documents: Current parsed Markdown documents from the loader.

        Returns:
            `True` when every current document exists in the manifest with the
            same fingerprint and no extra entry count mismatch is present.
        """
        # Require exact count equality so deleted documents invalidate the old
        # manifest rather than leaving stale vector entries behind.
        if len(loaded) != len(documents):
            return False

        # Compare every document fingerprint against the manifest, preserving the
        # old freshness semantics based on title plus raw content.
        for document in documents:
            entry = loaded.get(document.repository_relative_path)
            if entry is None:
                return False
            if entry.fingerprint != self.fingerprint_document(document):
                return False
        return True

    def fingerprint_document(self, document: KnowledgeDocument) -> str:
        """Calculate the manifest fingerprint for a parsed document.

        Args:
            document: Parsed Markdown document whose title and content identify
                the indexable text.

        Returns:
            MD5 hex digest matching the old implementation.
        """
        # Preserve the exact old fingerprint input shape so existing manifests
        # remain comparable after refactoring.
        return self.fingerprint_text(document.title, document.content)

    def fingerprint_text(self, title: str, content: str) -> str:
        """Calculate a stable fingerprint from title and content.

        Args:
            title: Parsed document title.
            content: Raw Markdown content.

        Returns:
            MD5 hex digest of `title + newline + content`.
        """
        # Keep MD5 for compatibility with the previous manifest and avoid a
        # breaking rebuild caused solely by changing hash algorithms.
        normalized = f'{title}\n{content}'
        return hashlib.md5(normalized.encode('utf-8')).hexdigest()

    def document_id(self, relative_path: str) -> str:
        """Build the stable vector-store document ID for a path.

        Args:
            relative_path: Repository-relative path of the Markdown document.

        Returns:
            Stable Chroma document identifier with the `kb-` prefix.
        """
        # Preserve the old deterministic ID scheme because Chroma metadata and
        # manifest entries may already refer to it.
        return f'kb-{hashlib.md5(relative_path.encode("utf-8")).hexdigest()}'
