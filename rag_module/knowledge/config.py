"""Configuration objects for the local knowledge-base package."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class KnowledgeConfig:
    """Stores runtime configuration for knowledge-base indexing and retrieval.

    The configuration centralizes constants that were previously scattered on
    the monolithic `KnowledgeBase` class.

    Attributes:
        root: Absolute path to the local Markdown knowledge base.
        embedding_model_name: Sentence-transformers model name or local path.
        local_files_only: Whether model loading must avoid network access.
        result_limit: Default limit for freeform search results.
        context_limit: Default limit for task-context retrieval.
        excerpt_chars: Maximum length of generated text excerpts.
        embedding_max_chars: Maximum Markdown content length embedded per file.
        semantic_candidates: Minimum semantic candidate count before fusion.
        strategy_prefix: Repository-relative prefix used to classify strategies.
        index_filename: Manifest filename written inside the knowledge root.
        chroma_dirname: ChromaDB persistence directory inside the knowledge root.
        collection_name: ChromaDB collection name.
        manifest_version: Manifest schema version.
        semantic_backend: Human-readable vector backend label.
    """

    root: Path
    embedding_model_name: str
    local_files_only: bool
    result_limit: int = 5
    context_limit: int = 3
    excerpt_chars: int = 320
    embedding_max_chars: int = 24000    # 这个值默认为 6000，实际操作时建议直接改。
    chunk_max_chars: int = 1800
    chunk_overlap_chars: int = 240
    semantic_candidates: int = 24
    strategy_prefix: str = 'kb/strategy/'
    index_filename: str = '.vector_index.json'
    chroma_dirname: str = '.chroma'
    collection_name: str = 'knowledge_base'
    manifest_version: int = 3
    semantic_backend: str = 'chromadb+sentence-transformers'

    @classmethod
    def from_environment(cls, root: Path | str | None = None) -> 'KnowledgeConfig':
        """Build configuration from environment variables and defaults.

        This class method preserves the old environment-variable behavior while
        moving configuration construction out of the facade constructor.

        Args:
            root: Optional explicit knowledge root as a `Path` or path string.
                When omitted, a `kb` directory is resolved relative to the
                project root inferred from this package location.

        Returns:
            A fully initialized immutable configuration object.
        """
        # Resolve the default project root to match the old single-file layout
        # when the new `knowledge/` package is placed beside `knowledge_base.py`.
        package_file = Path(__file__).resolve()
        project_root = package_file.parent.parent.parent
        root_value = Path(root).expanduser() if root is not None else project_root / 'kb'
        resolved_root = root_value.resolve()

        # Preserve the original embedding model and local-only environment
        # variable names so deployments do not need immediate configuration edits.
        model_name = os.getenv('POFPCTF_KB_EMBEDDING_MODEL', '').strip()
        local_only_raw = os.getenv('POFPCTF_KB_MODEL_LOCAL_ONLY', '').strip().lower()
        local_only = local_only_raw in {'1', 'true', 'yes', 'on'}

        def read_int_env(name: str, default: int) -> int:
            raw = os.getenv(name, '').strip()
            if not raw:
                return default
            try:
                return max(0, int(raw))
            except ValueError:
                return default

        # Construct the immutable config with all constants in one place so
        # downstream components do not import settings from the facade.
        return cls(
            root=resolved_root,
            embedding_model_name=model_name or 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2',
            local_files_only=local_only,
            chunk_max_chars=read_int_env('POFPCTF_KB_CHUNK_MAX_CHARS', 1800) or 1800,
            chunk_overlap_chars=read_int_env('POFPCTF_KB_CHUNK_OVERLAP_CHARS', 240),
        )

    @property
    def index_path(self) -> Path:
        """Return the manifest path inside the configured knowledge root.

        Returns:
            Absolute path to `.vector_index.json` under `root`.
        """
        # Keep manifest path derivation centralized so the manifest store and
        # status reporting cannot accidentally disagree.
        return self.root / self.index_filename

    @property
    def chroma_path(self) -> Path:
        """Return the Chroma persistence directory path.

        Returns:
            Absolute path to the ChromaDB persistence directory under `root`.
        """
        # Keep vector-store persistence path derivation centralized for rebuild
        # and status operations.
        return self.root / self.chroma_dirname
