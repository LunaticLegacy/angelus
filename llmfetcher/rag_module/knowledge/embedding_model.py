"""Sentence-transformers embedding model wrapper."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

from .config import KnowledgeConfig


class EmbeddingModelProvider:
    """Loads and uses the configured sentence-transformers embedding model.

    The provider isolates optional heavy dependency loading from the facade and
    vector store, making dependency failures explicit and recoverable.

    依赖项：sentence-transformers - 用于执行语义嵌入。
    """

    def __init__(self, config: KnowledgeConfig) -> None:
        """Initialize the embedding provider.

        Args:
            config: Knowledge-base configuration containing model name and
                local-only model-loading policy.
        """
        # Cache dependency objects and model instances lazily so importing the
        # package does not immediately import heavy ML libraries.
        self.config = config
        self._sentence_transformer_class: Optional["SentenceTransformer"] = None
        self._dependency_error = ''
        self._embedding_model: Any = None
        self._embedding_model_error = ''
        self.embedding_model_source = ''

    def dependencies_available(self) -> tuple[bool, str]:
        """Check whether sentence-transformers can be imported.

        Returns:
            Tuple of `(is_available, error_message)`. The error message is empty
            when the dependency is available.
        """
        # Return cached success or failure so repeated status calls do not keep
        # importing or raising the same dependency error.
        if self._sentence_transformer_class is not None:
            return True, ''
        if self._dependency_error:
            return False, self._dependency_error

        # Import lazily because keyword-only operation should work without the
        # semantic embedding dependency installed.
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except Exception as exc:  # pragma: no cover - depends on environment
            self._dependency_error = self.format_error(exc)
            return False, self._dependency_error

        # Cache the class object after a successful import so model construction
        # can happen later only when semantic indexing or query requires it.
        self._sentence_transformer_class = SentenceTransformer
        self._dependency_error = ''
        return True, ''

    def get_model(self) -> Any:
        """Load and return the configured embedding model.

        Returns:
            Loaded sentence-transformers model object.

        Raises:
            RuntimeError: If dependencies are missing or model loading fails.
        """
        # Validate dependencies first so missing packages produce a clear runtime
        # error instead of an AttributeError later.
        dependency_ok, dependency_error = self.dependencies_available()
        if not dependency_ok:
            raise RuntimeError(dependency_error or '语义嵌入依赖未安装')
        if self._embedding_model_error:
            raise RuntimeError(self._embedding_model_error)

        # Lazily construct the model and honor local-only behavior when the model
        # is resolved from an existing local path or explicit local-only flag.
        if self._embedding_model is None:
            kwargs: dict[str, Any] = {}
            model_source = self.resolve_model_source()
            if self.config.local_files_only or model_source != self.config.embedding_model_name:
                kwargs['local_files_only'] = True
            try:
                self._embedding_model = self._sentence_transformer_class(model_source, **kwargs)
                self.embedding_model_source = model_source
            except Exception as exc:  # pragma: no cover - depends on environment
                self._embedding_model_error = self.format_error(exc)
                raise RuntimeError(self._embedding_model_error) from exc
        return self._embedding_model

    def resolve_model_source(self) -> str:
        """Resolve the configured model name to a local path when possible.

        Returns:
            Either a local filesystem path or the original Hugging Face model
            identifier.
        """
        # Normalize once so blank configuration falls back to the package default
        # rather than propagating an empty model identifier.
        normalized = self.config.embedding_model_name.strip()
        if not normalized:
            return 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'

        # Prefer an explicitly configured filesystem path when it exists.
        direct_path = Path(normalized).expanduser()
        if direct_path.exists():
            return str(direct_path.resolve())

        # Search the Hugging Face hub cache using the same path convention as the
        # previous implementation.
        cache_root = Path.home() / '.cache' / 'huggingface' / 'hub'
        cache_key = normalized.replace('/', '--')
        repo_dir = cache_root / f'models--{cache_key}'
        snapshots_dir = repo_dir / 'snapshots'
        if snapshots_dir.exists():
            snapshots = sorted(path for path in snapshots_dir.iterdir() if path.is_dir())
            if snapshots:
                return str(snapshots[-1].resolve())

        # Preserve legacy sentence-transformers cache support for older local
        # development environments.
        legacy_root = Path.home() / '.cache' / 'torch' / 'sentence_transformers'
        legacy_dir = legacy_root / normalized.replace('/', '_')
        if legacy_dir.exists():
            return str(legacy_dir.resolve())
        return normalized

    def encode_documents(self, documents: Sequence[str]) -> list[list[float]]:
        """Encode document texts into normalized embedding vectors.

        Args:
            documents: Sequence of semantic document strings to embed.

        Returns:
            List of vectors, each represented as a list of floats.
        """
        # Preserve the old empty-input fast path to avoid loading the model when
        # there are no documents to encode.
        if not documents:
            return []
        model = self.get_model()

        # Support newer embedding models that expose query/document-specific
        # encode methods while preserving compatibility with standard models.
        if hasattr(model, 'encode_document'):
            vectors = model.encode_document(
                list(documents),
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        else:
            vectors = model.encode(
                list(documents),
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )

        # Convert numpy arrays or tensor-like objects into JSON-compatible nested
        # lists accepted by ChromaDB upsert.
        if hasattr(vectors, 'tolist'):
            return vectors.tolist()
        return [list(item) for item in vectors]

    def encode_query(self, query_text: str) -> list[float]:
        """Encode a query string into one normalized embedding vector.

        Args:
            query_text: Query text used for semantic retrieval.

        Returns:
            A single embedding vector represented as a list of floats.
        """
        # Load the model lazily at query time, matching the original runtime
        # behavior where semantic queries trigger model initialization.
        model = self.get_model()

        # Prefer query-specific encoders when available because some embedding
        # models use asymmetric query/document prompts internally.
        if hasattr(model, 'encode_query'):
            vector = model.encode_query(
                query_text,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        else:
            vector = model.encode(
                query_text,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )

        # Convert model output into a plain Python list for ChromaDB query calls.
        if hasattr(vector, 'tolist'):
            return vector.tolist()
        return list(vector)

    def format_error(self, exc: Exception) -> str:
        """Format an exception into a compact diagnostic string.

        Args:
            exc: Exception captured during dependency import or model loading.

        Returns:
            String in `TypeName: message` format.
        """
        # Keep error formatting consistent with the original public status output.
        return f'{type(exc).__name__}: {exc}'
