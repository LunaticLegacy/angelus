"""Vector-index lifecycle management for the local knowledge base."""

from __future__ import annotations

from typing import Any

from ...llm_types import JsonObject

from .config import KnowledgeConfig
from .markdown_loader import MarkdownKnowledgeLoader
from .manifest_store import KnowledgeManifestStore
from .models import KnowledgeChunk, KnowledgeIndexEntry
from .text_utils import TextTools
from .vector_store import ChromaVectorStore
from .embedding_model import EmbeddingModelProvider


class VectorIndexManager:
    """Coordinates manifest freshness checks and vector-index rebuilds.

    This class contains the side-effectful indexing path that was previously
    mixed into normal search methods on the old `KnowledgeBase` class.
    """

    def __init__(
        self,
        *,
        config: KnowledgeConfig,
        loader: MarkdownKnowledgeLoader,
        manifest: KnowledgeManifestStore,
        vector_store: ChromaVectorStore,
        embeddings: EmbeddingModelProvider,
        text: TextTools,
    ) -> None:
        """Initialize the index manager with its collaborators.

        Args:
            config: Knowledge-base runtime configuration.
            loader: Markdown loader used to scan and parse source documents.
            manifest: Manifest store used for load, save, and freshness checks.
            vector_store: Chroma adapter used to rebuild semantic indexes.
            embeddings: Embedding provider used for dependency status reporting.
            text: Text helper used to build excerpts and semantic documents.
        """
        # Store the collaborators explicitly so the manager owns indexing workflow
        # but not low-level parsing, embedding, or persistence implementation.
        self.config = config
        self.loader = loader
        self.manifest = manifest
        self.vector_store = vector_store
        self.embeddings = embeddings
        self.text = text
        self.runtime_error = ''

    def ensure_vector_index(self, *, force: bool = False) -> dict[str, KnowledgeIndexEntry]:
        """Ensure the vector manifest exists and matches current documents.

        This method intentionally preserves the old behavior where search paths
        may trigger freshness checks and rebuilds.

        Args:
            force: Whether to rebuild even when the manifest appears fresh.

        Returns:
            Manifest entries keyed by repository-relative path.
        """
        # Handle missing knowledge roots without trying to read or create index
        # files, matching the old unavailable behavior.
        if not self.loader.available():
            self.manifest.meta = self.manifest.build_meta(entry_count=0, chunk_count=0, backend_ready=False, last_error='')
            return {}

        # Load current documents once so freshness checks and potential rebuilds
        # compare against the same filesystem snapshot.
        documents = self.loader.load_documents()
        if not force and self.config.index_path.exists():
            loaded = self.manifest.load(self.config.index_path)
            if (
                loaded is not None
                and self.manifest.meta.version == self.config.manifest_version
                and self.manifest.is_fresh(loaded, documents)
                and self.manifest.meta.chunk_count > 0
            ):
                return loaded
        return self.rebuild_vector_index(documents=documents)

    def rebuild_vector_index(self, *, documents: list | None = None) -> dict[str, KnowledgeIndexEntry]:
        """Rebuild vector index entries and the Chroma collection.

        Args:
            documents: Optional preloaded documents. When omitted, the manager
                scans the knowledge root itself.

        Returns:
            Manifest entries keyed by repository-relative path.
        """
        # Keep unavailable roots as a no-op that still resets manifest metadata to
        # a known disabled state.
        if not self.loader.available():
            self.manifest.meta = self.manifest.build_meta(entry_count=0, chunk_count=0, backend_ready=False, last_error='')
            return {}

        # Reuse caller-provided documents when available so ensure/rebuild does
        # not scan the filesystem twice.
        source_documents = documents if documents is not None else self.loader.load_documents()
        entries: dict[str, KnowledgeIndexEntry] = {}
        ids: list[str] = []
        semantic_documents: list[str] = []
        metadatas: list[dict[str, str]] = []
        chunk_count = 0

        # Convert parsed Markdown documents into manifest entries and vector-store
        # payloads while preserving document freshness and adding chunk-level
        # semantic payloads for retrieval.
        for document in source_documents:
            relative_path = document.repository_relative_path
            fingerprint = self.manifest.fingerprint_document(document)
            excerpt = self.text.build_excerpt(
                document.content,
                self.text.extract_terms([document.title, relative_path, document.content]),
            )
            document_id = self.manifest.document_id(relative_path)
            entries[relative_path] = KnowledgeIndexEntry(
                path=relative_path,
                title=document.title,
                fingerprint=fingerprint,
                excerpt=excerpt,
                document_id=document_id,
            )
            document_chunks: list[KnowledgeChunk] = self.text.chunk_document(document)
            for chunk in document_chunks:
                ids.append(chunk.chunk_key)
                semantic_documents.append(self.text.build_chunk_semantic_document(chunk))
                metadatas.append(
                    {
                        'path': relative_path,
                        'source_path': chunk.source_path,
                        'source_title': chunk.source_title,
                        'chunk_key': chunk.chunk_key,
                        'chunk_index': str(chunk.chunk_index),
                        'chunk_title': chunk.chunk_title,
                        'heading_path': chunk.heading_path,
                        'start_line': str(chunk.start_line),
                        'end_line': str(chunk.end_line),
                        'fingerprint': fingerprint,
                    }
                )
            chunk_count += len(document_chunks)

        # Rebuild the vector backend as a best-effort operation; failures are
        # recorded in the manifest while keyword fallback remains usable.
        backend_ready = False
        last_error = ''
        try:
            backend_ready = self.vector_store.rebuild(ids=ids, documents=semantic_documents, metadatas=metadatas)
        except Exception as exc:  # pragma: no cover - depends on environment
            last_error = self.format_error(exc)
            self.runtime_error = last_error

        # Save the manifest regardless of backend success so keyword search can
        # still use cached metadata and report useful status.
        self.manifest.save(entries, chunk_count=chunk_count, backend_ready=backend_ready, last_error=last_error)
        return entries

    def vector_status(self) -> JsonObject:
        """Return the current vector-index status payload.

        Returns:
            Dictionary compatible with the old `KnowledgeBase.vector_status()`
            response shape.
        """
        # Ensure the manifest is loaded or rebuilt before status fields are read,
        # preserving the old method's side-effectful status behavior.
        entries = self.ensure_vector_index()
        chroma_ok, chroma_error = self.vector_store.dependencies_available()
        embed_ok, embed_error = self.embeddings.dependencies_available()

        # Merge dependency errors because the semantic backend requires both
        # ChromaDB and sentence-transformers to be usable.
        dependency_ok = chroma_ok and embed_ok
        dependency_error = chroma_error or embed_error
        last_error = self.manifest.meta.last_error.strip() or self.runtime_error or self.vector_store.runtime_error

        # Return the same public keys as the original status method so UI/API code
        # can consume the refactored package without changes.
        return {
            'knowledge_base_root': str(self.config.root),
            'index_path': str(self.config.index_path),
            'chroma_path': str(self.config.chroma_path),
            'collection_name': self.config.collection_name,
            'enabled': self.loader.available(),
            'backend': self.config.semantic_backend,
            'embedding_model': self.config.embedding_model_name,
            'entry_count': len(entries),
            'chunk_count': int(self.manifest.meta.chunk_count),
            'backend_ready': bool(self.manifest.meta.backend_ready),
            'query_mode': 'hybrid' if self.manifest.meta.backend_ready else 'keyword_fallback',
            'dependencies_installed': dependency_ok,
            'dependency_error': dependency_error,
            'last_error': last_error,
        }

    def semantic_candidate_limit(self, limit: int, chunk_count: int) -> int:
        """Calculate the number of vector candidates to request.

        Args:
            limit: Final requested hit count.
            chunk_count: Number of indexed semantic chunks available in the manifest.

        Returns:
            Bounded semantic candidate count.
        """
        # Preserve the old candidate policy: at least configured semantic
        # candidates, at least 8x requested hits, and never more than entry count.
        if chunk_count <= 0:
            return 0
        return max(1, min(chunk_count, max(int(limit) * 8, self.config.semantic_candidates)))

    def format_error(self, exc: Exception) -> str:
        """Format an exception into a compact diagnostic string.

        Args:
            exc: Exception captured during index rebuild.

        Returns:
            String in `TypeName: message` format.
        """
        # Keep error formatting compatible with previous status and manifest
        # error strings.
        return f'{type(exc).__name__}: {exc}'
