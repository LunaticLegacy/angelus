"""
Facade class for local knowledge-base indexing and retrieval.
"""

from __future__ import annotations

from pathlib import Path

from ...llm_types import JsonObject

from .config import KnowledgeConfig
from .context_builder import TaskContextBuilder
from .embedding_model import EmbeddingModelProvider
from .hybrid_retriever import HybridRetriever
from .index_manager import VectorIndexManager
from .keyword_retriever import KeywordRetriever
from .manifest_store import KnowledgeManifestStore
from .markdown_loader import MarkdownKnowledgeLoader
from .models import KnowledgeChunk, KnowledgeHit, KnowledgeIndexEntry, RetrievalQuery
from .task_policy import TaskRetrievalPolicy
from .text_utils import TextTools
from .vector_store import ChromaVectorStore


class KnowledgeBase:
    """Facade for local Markdown knowledge-base retrieval and indexing.

    The facade preserves the old public API while delegating parsing, indexing,
    vector storage, scoring, task policy, and context formatting to specialized
    classes.
    """

    DEFAULT_RESULT_LIMIT = 5
    DEFAULT_RESULT_MAX_LIMIT = 1000
    DEFAULT_CONTEXT_LIMIT = 3
    DEFAULT_EXCERPT_CHARS = 320
    DEFAULT_EMBEDDING_MAX_CHARS = 6000
    DEFAULT_SEMANTIC_CANDIDATES = 24
    STRATEGY_PREFIX = 'kb/strategy/'
    INDEX_FILENAME = '.vector_index.json'
    CHROMA_DIRNAME = '.chroma'
    COLLECTION_NAME = 'knowledge_base'
    MANIFEST_VERSION = 3
    SEMANTIC_BACKEND = 'chromadb+sentence-transformers'
    DEFAULT_EMBEDDING_MODEL = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'

    def __init__(self, root: Path | None = None) -> None:
        """Initialize the facade and all collaborating components.

        Args:
            root: Optional explicit knowledge-base root. When omitted, the
                package resolves a `kb` directory relative to the inferred project
                root, matching the original default layout.
        """
        # Build immutable configuration first so every component receives the
        # same root path, model name, manifest constants, and size limits.
        self.config = KnowledgeConfig.from_environment(root)    # 初始化配置
        self.root = self.config.root    # 初始化根目录

        # 从设置中导出工具。
        self.embedding_model_name: str = self.config.embedding_model_name    # 从设置项，初始化嵌入模型名称
        self.local_files_only: bool = self.config.local_files_only    # 从设置项，初始化本地文件模式：允许从本地文件系统加载嵌入模型

        # Create pure helpers and filesystem services before retrieval services so
        # each downstream component can depend on a narrow collaborator.
        self.text_tool = TextTools(
            excerpt_chars=self.config.excerpt_chars,
            embedding_max_chars=self.config.embedding_max_chars,    # 6000？
            chunk_max_chars=self.config.chunk_max_chars,
        )
        self.loader = MarkdownKnowledgeLoader(self.config.root)
        self.manifest = KnowledgeManifestStore(self.config)

        # Initialize optional semantic backend wrappers lazily; construction here
        # does not import ChromaDB or sentence-transformers.
        self.embeddings = EmbeddingModelProvider(self.config)
        self.vector_store = ChromaVectorStore(self.config, self.embeddings, self.text_tool)

        # Initialize retrieval policy and retrievers after shared helpers exist so
        # task search and freeform search use the same normalization rules.
        self.keyword = KeywordRetriever(self.text_tool)  # 关键词获取
        self.policy = TaskRetrievalPolicy(self.keyword, self.config.root)
        self.index_manager = VectorIndexManager(
            config=self.config,
            loader=self.loader,
            manifest=self.manifest,
            vector_store=self.vector_store,
            embeddings=self.embeddings,
            text=self.text_tool,
        )
        self.hybrid = HybridRetriever(
            config=self.config,
            loader=self.loader,
            keyword=self.keyword,
            vector_store=self.vector_store,
            index_manager=self.index_manager,
            policy=self.policy,
            text=self.text_tool,
        )
        self.context_builder = TaskContextBuilder(strategy_prefix=self.config.strategy_prefix)

    def available(self) -> bool:
        """Return whether the knowledge-base directory exists.

        Returns:
            `True` when the configured root exists and is a directory, otherwise
            `False`.
        """
        # Delegate filesystem availability checks to the Markdown loader because
        # it owns the knowledge root.
        return self.loader.available()

    def search(self, query: str, *, limit: int = DEFAULT_RESULT_LIMIT) -> list[KnowledgeHit]:
        """Search the knowledge base by freeform query text.

        Args:
            query: User query text used for keyword and semantic retrieval.
            limit: Maximum number of final results. Values are clamped to the old
                public range of 1 to 1000.

        Returns:
            Ranked list of `KnowledgeHit` objects. Returns an empty list when the
            knowledge root is unavailable or no query terms can be extracted.
        """
        # Preserve the old unavailable-root fast path before constructing a
        # retrieval query.
        if not self.available():
            return []

        # Let task policy normalize limits and terms so freeform search and
        # task-aware search share one internal query representation.
        retrieval_query: RetrievalQuery | None = self.policy.build_freeform_query(query, limit=limit, max_limit=self.DEFAULT_RESULT_MAX_LIMIT)
        if retrieval_query is None:
            return []
        return self.hybrid.search(retrieval_query)

    def search_for_task(
        self,
        *,
        task_name: str,
        task_type: str,
        target: str,
        file_descriptions: str,
        limit: int = DEFAULT_CONTEXT_LIMIT,
    ) -> list[KnowledgeHit]:
        """Prefetch knowledge entries relevant to a task.

        Args:
            task_name: Human-readable task name.
            task_type: CTF task type such as `RE`, `PWN`, or `WEB`.
                TODO: task type should be edited to "specified domain", not only for CTF.
            target: Challenge target, URL, filename, or equivalent task target.
            file_descriptions: Description of task files supplied to the agent.
            limit: Maximum number of context hits. Values are clamped to the old
                public task range of 1 to 6.

        Returns:
            Ranked task-relevant hits, or fallback strategy hits when policy-based
            retrieval produces no results.
        """
        # Preserve the old unavailable-root fast path so callers can use this API
        # safely even when no local knowledge base has been installed.
        if not self.available():
            return []

        # Build a task-aware retrieval query; when policy cannot extract terms,
        # preserve the old behavior by returning an empty result list.
        retrieval_query = self.policy.build_task_query(
            task_name=task_name,
            task_type=task_type,
            target=target,
            file_descriptions=file_descriptions,
            limit=limit,
        )
        if retrieval_query is None:
            return []

        # Run hybrid retrieval first and only fall back to static strategy cards
        # when no hybrid hit is produced.
        hits = self.hybrid.search(retrieval_query)
        if hits:
            return hits[: max(1, min(int(limit), 6))]
        return self.hybrid.fallback_hits_for_task_type(task_type, limit=limit)

    def build_task_context(
        self,
        *,
        task_name: str,
        task_type: str,
        target: str,
        file_descriptions: str,
        limit: int = DEFAULT_CONTEXT_LIMIT,
    ) -> str:
        """Build prompt-ready knowledge context for a task.

        Args:
            task_name: Human-readable task name.
            task_type: CTF task type used by retrieval policy.
            target: Challenge target or related task identifier.
            file_descriptions: Description of attached task files.
            limit: Maximum number of retrieved hits to include.

        Returns:
            Prompt-context string preserving the old strategy-first layout.
        """
        # Reuse the public task-search API so context formatting always reflects
        # the same retrieval behavior exposed to other callers.
        hits = self.search_for_task(
            task_name=task_name,
            task_type=task_type,
            target=target,
            file_descriptions=file_descriptions,
            limit=limit,
        )
        return self.context_builder.build(hits)

    def ensure_vector_index(self, *, force: bool = False) -> dict[str, KnowledgeIndexEntry]:
        """Ensure the vector index manifest exists and is fresh.

        Args:
            force: Whether to force a rebuild even if the manifest appears fresh.

        Returns:
            Manifest entries keyed by repository-relative path.
        """
        # Delegate the side-effectful index lifecycle to the index manager while
        # preserving the old facade method name.
        return self.index_manager.ensure_vector_index(force=force)

    def rebuild_vector_index(self) -> dict[str, KnowledgeIndexEntry]:
        """Rebuild the vector index and manifest from source documents.

        Returns:
            Manifest entries keyed by repository-relative path. If semantic
            backend rebuild fails, entries are still returned and the manifest
            records the error for keyword fallback mode.
        """
        # Keep explicit rebuild as a public facade operation so callers can move
        # indexing out of request paths later without changing lower components.
        return self.index_manager.rebuild_vector_index()

    def vector_status(self) -> JsonObject:
        """Return semantic index and dependency status.

        Returns:
            Dictionary compatible with the original `vector_status()` response.
        """
        # Delegate status construction to the index manager because it owns both
        # manifest state and vector-backend readiness checks.
        return self.index_manager.vector_status()

    def get_full_text(self, path: str) -> str | None:
        """Retrieve full text content of a knowledge document by its path.

        Args:
            path: Repository-relative path of the knowledge document (e.g., 
                'reversing/README.md' or 'kb/reversing/README.md').

        Returns:
            Full Markdown content of the document, or None if the document
            cannot be found or loaded.
        """
        if not self.available():
            return None
        
        # Normalize path: remove 'kb/' prefix if present since root is already kb/
        # 去除前缀 kb/，如果路径存在本内容。
        normalized_path = path
        if normalized_path.startswith('kb/'):
            normalized_path = normalized_path[3:]
        
        # 建立 path
        doc_path: Path = self.root / normalized_path
        
        # Check if file exists
        if not doc_path.exists() or not doc_path.is_file():
            return None
        
        try:
            # 获取全文
            document = self.loader.read_document(doc_path)
            return document.content
        except Exception:
            return None

    def get_documents_by_paths(self, paths: list[str]) -> dict[str, str]:
        """Retrieve full text content for multiple documents by their paths.

        Args:
            paths: List of repository-relative paths of knowledge documents.

        Returns:
            Dictionary mapping each path to its full content. Paths that cannot
            be loaded are omitted from the result.
        """
        results = {}
        for path in paths:
            content = self.get_full_text(path)
            if content is not None:
                results[path] = content
        return results

    def get_chunk(
        self,
        path: str,
        *,
        chunk_key: str = '',
        chunk_index: int | None = None,
    ) -> KnowledgeChunk | None:
        """Retrieve one chunk from a knowledge document.

        Args:
            path: Repository-relative path of the source Markdown document.
            chunk_key: Optional stable chunk identifier returned by search.
            chunk_index: Optional zero-based chunk ordinal within the document.

        Returns:
            The matching `KnowledgeChunk`, or `None` when the document or chunk
            cannot be found.
        """
        if not self.available():
            return None

        # Reuse the same path normalisation rules as full-text lookup so chunk
        # retrieval stays consistent with the existing public document API.
        normalized_path = path
        if normalized_path.startswith('kb/'):
            normalized_path = normalized_path[3:]
        doc_path: Path = self.root / normalized_path
        if not doc_path.exists() or not doc_path.is_file():
            return None

        try:
            document = self.loader.read_document(doc_path)
        except Exception:
            return None

        # Chunk the live document and then resolve by chunk key first because it
        # is stable across ranking and tool calls. Fallback to chunk index when
        # the caller only knows ordinal position.
        chunks = self.text_tool.chunk_document(document)
        if chunk_key:
            for chunk in chunks:
                if chunk.chunk_key == chunk_key:
                    return chunk

        if chunk_index is not None and 0 <= chunk_index < len(chunks):
            return chunks[chunk_index]

        # For single-chunk documents, returning the only chunk is convenient and
        # matches the intuitive "give me the content" behavior.
        if not chunk_key and chunk_index is None and len(chunks) == 1:
            return chunks[0]
        return None

    def get_chunk_text(
        self,
        path: str,
        *,
        chunk_key: str = '',
        chunk_index: int | None = None,
    ) -> str | None:
        """Retrieve the raw Markdown content for one chunk.

        Args:
            path: Repository-relative path of the source Markdown document.
            chunk_key: Optional stable chunk identifier returned by search.
            chunk_index: Optional zero-based chunk ordinal within the document.

        Returns:
            The raw chunk content string, or `None` if the chunk is missing.
        """
        chunk = self.get_chunk(path, chunk_key=chunk_key, chunk_index=chunk_index)
        return None if chunk is None else chunk.content

    def get_chunk_text_from_hit(self, hit: KnowledgeHit) -> str | None:
        """Retrieve chunk text for one ranked retrieval hit.

        Args:
            hit: Ranked chunk hit returned by `search()` or `search_for_task()`.

        Returns:
            Raw chunk content, or `None` if the source document cannot be read.
        """
        return self.get_chunk_text(
            hit.path,
            chunk_key=hit.chunk_key,
            chunk_index=hit.chunk_index,
        )
