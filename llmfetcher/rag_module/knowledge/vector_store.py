"""ChromaDB vector-store adapter for semantic knowledge retrieval."""

from __future__ import annotations

from typing import Any, Sequence

from .config import KnowledgeConfig
from .embedding_model import EmbeddingModelProvider
from .models import VectorHit
from .text_utils import TextTools


class ChromaVectorStore:
    """Wraps ChromaDB collection management and semantic querying.

    This class owns ChromaDB-specific behavior. It does not scan Markdown files,
    compute keyword scores, or construct final hybrid hits.
    """

    def __init__(self, config: KnowledgeConfig, embeddings: EmbeddingModelProvider, text: TextTools) -> None:
        """Initialize the vector store adapter.

        Args:
            config: Knowledge-base configuration containing Chroma paths and
                collection names.
            embeddings: Embedding provider used to encode documents and queries.
            text: Text helper used for excerpt extraction from stored documents.
        """
        # Cache Chroma dependency, client, and collection lazily to preserve the
        # old behavior where keyword fallback works without Chroma installed.
        self.config = config
        self.embeddings = embeddings
        self.text = text
        self._chromadb_module: Any = None
        self._dependency_error = ''
        self._chroma_client: Any = None
        self._chroma_collection: Any = None
        self.runtime_error = ''

    def dependencies_available(self) -> tuple[bool, str]:
        """Check whether ChromaDB can be imported.

        Returns:
            Tuple of `(is_available, error_message)`. The error message is empty
            when ChromaDB is available.
        """
        # Return cached dependency state to avoid repeated import attempts after
        # a dependency failure.
        if self._chromadb_module is not None:
            return True, ''
        if self._dependency_error:
            return False, self._dependency_error

        # Import Chroma lazily because vector features are optional and keyword
        # fallback should remain available.
        try:
            import chromadb  # type: ignore
        except Exception as exc:  # pragma: no cover - depends on environment
            self._dependency_error = self.format_error(exc)
            return False, self._dependency_error

        # Cache the imported module for client construction and status checks.
        self._chromadb_module = chromadb
        self._dependency_error = ''
        return True, ''

    def rebuild(
        self,
        *,
        ids: Sequence[str],
        documents: Sequence[str],
        metadatas: Sequence[dict[str, str]],
    ) -> bool:
        """Rebuild the Chroma collection with supplied documents.

        Args:
            ids: Stable vector-store document identifiers.
            documents: Semantic document texts to store and retrieve.
            metadatas: Metadata dictionaries aligned with `ids` and `documents`.

        Returns:
            `True` when the collection exists after rebuild, otherwise `False`.

        Raises:
            RuntimeError: Propagates dependency, model, or Chroma errors to the
                caller so the index manager can record them in the manifest.
        """
        # Encode all documents before replacing the collection so embedding
        # failures do not delete the old collection prematurely.
        embeddings = self.embeddings.encode_documents(documents) if ids else []
        collection = self.get_collection(recreate=True)

        # Upsert only when there is content. An empty knowledge base can still
        # create a collection and be marked backend-ready.
        if collection is not None and ids:
            collection.upsert(
                ids=list(ids),
                documents=list(documents),
                metadatas=list(metadatas),
                embeddings=embeddings,
            )
        return collection is not None

    def query(self, query_text: str, *, limit: int) -> dict[str, VectorHit]:
        """Query the Chroma collection for semantic candidates.

        Args:
            query_text: Freeform query text to encode and search.
            limit: Maximum number of vector candidates to request.

        Returns:
            Dictionary keyed by stable chunk identifier. Missing or unavailable
            vector backends return an empty dictionary.
        """
        # Reject empty semantic queries and non-positive limits before touching
        # optional vector dependencies.
        if not query_text.strip() or limit <= 0:
            return {}

        # Treat Chroma or embedding failures as recoverable runtime errors so the
        # hybrid retriever can continue with keyword-only scoring.
        try:
            collection = self.get_collection()
            if collection is None:
                return {}
            query_embedding = self.embeddings.encode_query(query_text)
            payload = collection.query(
                query_embeddings=[query_embedding],
                n_results=limit,
                include=['documents', 'metadatas', 'distances'],
            )
        except Exception as exc:  # pragma: no cover - depends on environment
            self.runtime_error = self.format_error(exc)
            return {}

        # Normalize Chroma's nested response lists into simple aligned sequences
        # for deterministic metadata extraction.
        raw_metadatas = payload.get('metadatas') or [[]]
        raw_documents = payload.get('documents') or [[]]
        raw_distances = payload.get('distances') or [[]]
        metadatas = raw_metadatas[0] if raw_metadatas else []
        documents = raw_documents[0] if raw_documents else []
        distances = raw_distances[0] if raw_distances else []

        # Convert each valid Chroma row into a chunk-keyed vector hit, dropping
        # malformed rows without failing the full query.
        semantic_hits: dict[str, VectorHit] = {}
        for index, metadata in enumerate(metadatas):
            if not isinstance(metadata, dict):
                continue
            source_path = str(metadata.get('source_path', metadata.get('path', ''))).strip()
            if not source_path:
                continue
            document = str(documents[index] if index < len(documents) else '')
            distance = distances[index] if index < len(distances) else None
            chunk_key = str(metadata.get('chunk_key', metadata.get('document_id', ''))).strip() or source_path
            semantic_hits[chunk_key] = VectorHit(
                path=source_path,
                chunk_key=chunk_key,
                chunk_index=int(metadata.get('chunk_index', index) or 0),
                chunk_title=str(metadata.get('chunk_title', '')).strip(),
                heading_path=str(metadata.get('heading_path', '')).strip(),
                start_line=int(metadata.get('start_line', 0) or 0),
                end_line=int(metadata.get('end_line', 0) or 0),
                score=self.distance_to_similarity(distance),
                excerpt=self.text.excerpt_from_semantic_document(document),
            )
        return semantic_hits

    def get_client(self) -> Any:
        """Return the persistent ChromaDB client.

        Returns:
            ChromaDB persistent client object.

        Raises:
            RuntimeError: If ChromaDB is not installed or cannot be imported.
        """
        # Validate the optional dependency and raise a clear error if semantic
        # retrieval cannot be used in this environment.
        dependency_ok, dependency_error = self.dependencies_available()
        if not dependency_ok:
            raise RuntimeError(dependency_error or '语义检索依赖未安装')

        # Lazily create the persistent client and its backing directory to avoid
        # filesystem side effects at package import time.
        if self._chroma_client is None:
            self.config.chroma_path.mkdir(parents=True, exist_ok=True)
            self._chroma_client = self._chromadb_module.PersistentClient(path=str(self.config.chroma_path))
        return self._chroma_client

    def get_collection(self, *, recreate: bool = False) -> Any | None:
        """Return the configured Chroma collection.

        Args:
            recreate: Whether to delete and recreate the collection before
                returning it.

        Returns:
            Chroma collection object, or `None` when an existing collection is
            absent and recreation was not requested.
        """
        # Resolve the client first because both read and recreate paths require a
        # live ChromaDB connection.
        client = self.get_client()

        # When rebuilding, clear the cached collection and best-effort delete the
        # persisted collection. Deletion failure is safe when it did not exist.
        if recreate:
            self._chroma_collection = None
            try:
                client.delete_collection(name=self.config.collection_name)
            except Exception:
                pass

        # Reuse a cached collection unless the caller explicitly requested a
        # recreate path above.
        if self._chroma_collection is not None:
            return self._chroma_collection

        # Recreate mode always creates a fresh collection with compatible HNSW
        # metadata.
        if recreate:
            self._chroma_collection = self.create_collection(client)
            return self._chroma_collection

        # Read mode returns None if the collection has not been created yet,
        # preserving the old semantic-query fallback behavior.
        try:
            self._chroma_collection = client.get_collection(name=self.config.collection_name)
        except Exception:
            return None
        return self._chroma_collection

    def create_collection(self, client: Any) -> Any:
        """Create or fetch the configured Chroma collection.

        Args:
            client: ChromaDB persistent client.

        Returns:
            Chroma collection object configured for cosine distance.
        """
        # Build metadata once so new and compatibility creation paths record the
        # same collection identity.
        metadata = {
            'scope': 'knowledge-base',
            'root': self.config.root.name,
            'embedding_model': self.config.embedding_model_name,
        }

        # Prefer the newer Chroma collection configuration API and fall back to
        # legacy metadata when the installed version does not support it.
        try:
            return client.get_or_create_collection(
                name=self.config.collection_name,
                metadata=metadata,
                configuration={'hnsw': {'space': 'cosine'}},
            )
        except TypeError:
            compatibility_metadata = dict(metadata)
            compatibility_metadata['hnsw:space'] = 'cosine'
            return client.get_or_create_collection(
                name=self.config.collection_name,
                metadata=compatibility_metadata,
            )

    def distance_to_similarity(self, distance: Any) -> float:
        """Convert Chroma cosine distance to bounded similarity.

        Args:
            distance: Raw distance value returned by ChromaDB.

        Returns:
            Similarity score clamped to `[0.0, 1.0]`.
        """
        # Treat non-numeric distances as zero similarity rather than failing the
        # entire hybrid retrieval path.
        try:
            numeric_distance = float(distance)
        except (TypeError, ValueError):
            return 0.0

        # The collection uses cosine space, so the old implementation used
        # `1 - distance` as an approximate similarity.
        similarity = 1.0 - numeric_distance
        return max(0.0, min(similarity, 1.0))

    def format_error(self, exc: Exception) -> str:
        """Format an exception into a compact diagnostic string.

        Args:
            exc: Exception captured during Chroma import, rebuild, or query.

        Returns:
            String in `TypeName: message` format.
        """
        # Keep error formatting compatible with the previous vector status output.
        return f'{type(exc).__name__}: {exc}'
