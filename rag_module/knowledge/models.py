"""Shared data models for the local knowledge-base package."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

from ...llm_types import JsonObject


@dataclass(frozen=True)
class KnowledgeHit:
    """Represents one final knowledge-base retrieval result.

    This model is returned by public retrieval APIs after chunk-level keyword
    scores, vector scores, and task-specific boosts have been merged.

    Attributes:
        path: Repository-relative path of the source Markdown document.
        title: Human-readable title extracted from the source document.
        chunk_key: Stable chunk identifier used by the vector index.
        chunk_index: Zero-based chunk ordinal within the source document.
        chunk_title: Short title or heading label for the chunk.
        heading_path: Hierarchical Markdown heading path for the chunk.
        start_line: First source line covered by the chunk.
        end_line: Last source line covered by the chunk.
        score: Final fused score used for result ranking.
        excerpt: Short text excerpt suitable for prompt injection or display.
        keyword_score: Contribution from deterministic keyword matching.
        vector_score: Contribution from semantic vector retrieval.
    """

    path: str
    title: str
    score: float
    excerpt: str
    chunk_key: str = ''
    chunk_index: int = 0
    chunk_title: str = ''
    heading_path: str = ''
    start_line: int = 0
    end_line: int = 0
    keyword_score: float = 0.0
    vector_score: float = 0.0


@dataclass(frozen=True)
class KnowledgeIndexEntry:
    """Represents one document entry stored in the vector-index manifest.

    This model mirrors the previous `.vector_index.json` entry schema, so the
    refactored package can read and write the same manifest shape.

    Attributes:
        path: Repository-relative Markdown path used as manifest key.
        title: Document title used for display and semantic indexing.
        fingerprint: Stable content fingerprint used for freshness checks.
        excerpt: Cached fallback excerpt used when live excerpt construction fails.
        document_id: Stable vector-store identifier derived from the path.
    """

    path: str
    title: str
    fingerprint: str
    excerpt: str
    document_id: str

    def to_dict(self) -> JsonObject:
        """Convert the index entry to a JSON-serializable dictionary.

        This method preserves the original manifest entry layout by returning
        dataclass fields without renaming them.

        Returns:
            A dictionary containing only JSON-compatible primitive values.
        """
        # Serialize the dataclass with the standard library helper so future
        # field additions remain automatically reflected in the manifest.
        return cast(JsonObject, asdict(self))


@dataclass(frozen=True)
class KnowledgeDocument:
    """Represents one parsed Markdown document from the knowledge root.

    This model is the structured replacement for repeatedly passing raw
    `(path, title, content)` tuples through the old monolithic class.

    Attributes:
        absolute_path: Absolute filesystem path to the source Markdown file.
        root_relative_path: Path relative to the configured knowledge root.
        repository_relative_path: Path relative to the knowledge root parent.
        title: First Markdown heading or filename-derived fallback title.
        content: Raw Markdown content decoded as UTF-8 with replacement errors.
    """

    absolute_path: Path
    root_relative_path: str
    repository_relative_path: str
    title: str
    content: str


@dataclass(frozen=True)
class KnowledgeChunk:
    """Represents one chunk produced from a source Markdown document.

    The chunk is the retrieval unit stored in the semantic vector backend. The
    source document remains the unit of freshness checking and file retrieval.

    Attributes:
        source_path: Repository-relative path of the source Markdown document.
        source_title: Title extracted from the source Markdown document.
        chunk_key: Stable chunk identifier derived from the source path and span.
        chunk_index: Zero-based chunk ordinal within the source document.
        chunk_title: Short title or heading label for the chunk.
        heading_path: Hierarchical Markdown heading path for the chunk.
        start_line: First source line covered by the chunk.
        end_line: Last source line covered by the chunk.
        content: Raw Markdown text belonging to the chunk.
    """

    source_path: str
    source_title: str
    chunk_key: str
    chunk_index: int
    chunk_title: str
    heading_path: str
    start_line: int
    end_line: int
    content: str


@dataclass(frozen=True)
class MarkdownBlock:
    """Represent one logical block extracted from Markdown content.

    Attributes:
        kind: Block category such as `heading`, `text`, `code`, or `table`.
        text: Normalized Markdown text for the block.
        start_line: First source line covered by the block, using 1-based line
            numbers from the original document.
        end_line: Last source line covered by the block, using 1-based line
            numbers from the original document.
        level: Optional heading level for `heading` blocks.
        info: Optional fenced-code info string or parser metadata.
    """

    kind: str
    text: str
    start_line: int
    end_line: int
    level: int | None = None
    info: str | None = None


@dataclass(frozen=True)
class VectorHit:
    """Represents one semantic retrieval result from the vector backend.

    This model intentionally contains only vector-layer data. The hybrid
    retriever is responsible for merging it with keyword scores and documents.

    Attributes:
        path: Repository-relative path of the source Markdown document.
        chunk_key: Stable chunk identifier returned from vector metadata.
        chunk_index: Zero-based chunk ordinal within the source document.
        chunk_title: Short title or heading label for the chunk.
        heading_path: Hierarchical Markdown heading path for the chunk.
        start_line: First source line covered by the chunk.
        end_line: Last source line covered by the chunk.
        score: Similarity score normalized into the range `[0.0, 1.0]`.
        excerpt: Best-effort excerpt derived from the stored semantic document.
    """

    path: str
    chunk_key: str
    chunk_index: int
    chunk_title: str
    heading_path: str
    start_line: int
    end_line: int
    score: float
    excerpt: str


@dataclass(frozen=True)
class RetrievalQuery:
    """Represents a normalized retrieval request.

    This model keeps freeform search and task-aware search on the same internal
    pathway while still recording task-specific semantics for policy boosts.

    Attributes:
        query_text: Text sent to semantic retrieval backends.
        terms: Normalized keyword terms used by deterministic scoring.
        limit: Maximum number of final hits requested by the caller.
        task_type: Optional CTF task type used for policy-specific boosts.
            TODO: this task type should be edited to "specified domain", not only for CTF.
        semantic_multiplier: Weight applied to vector scores during fusion.
    """

    query_text: str
    terms: list[str]
    limit: int
    task_type: str = ''
    semantic_multiplier: float = 20.0


@dataclass(frozen=True)
class ManifestMeta:
    """Represents manifest-level metadata stored beside vector entries.

    This model separates the manifest header from individual entries, making it
    easier to inspect backend readiness and failure information.

    Attributes:
        version: Manifest schema version written to `.vector_index.json`.
        backend: Human-readable semantic backend name.
        embedding_model: Embedding model name or local path used by the index.
        backend_ready: Whether the vector backend was successfully built.
        entry_count: Number of indexed Markdown documents.
        chunk_count: Number of indexed semantic chunks.
        last_error: Last rebuild or dependency error, if one was recorded.
    """

    version: int
    backend: str
    embedding_model: str
    backend_ready: bool
    entry_count: int
    chunk_count: int
    last_error: str

    def to_dict(self) -> dict[str, Any]:
        """Convert manifest metadata into a JSON-compatible dictionary.

        Returns:
            Dictionary representation suitable for merging into the manifest
            payload root.
        """
        # Use dataclass serialization so the manifest header remains aligned
        # with the strongly typed metadata model.
        return asdict(self)
