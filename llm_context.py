import hashlib
import math
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Mapping, Optional, Sequence, Set, Tuple

from .llm_fetcher import LLMFetcher, LLMOutput
from .prompt import (
    CONTEXT_COMPACT_PROMPT_TEMPLATE,
    MEMORY_CONCLUDE_PROMPT_TEMPLATE, 
    TAGIFY_CONTEXT_PROMPT,
    CONTEXT_SELECTION_PROMPT_TEMPLATE,
    TOOL_RESULT_FACT_PROMPT,
)
from .llm_types import (
    LLMContext, 
    LLMContextCompacted, 
    LLMContextInfo, 
    LLMInfo, 
    ToolExecutionRecord,
    ToolResultFact,
    LLMContextSnapshot,
    ContextMode, 
    STOP_TAGS    
)

from .utils_function import (
    extract_first_json_object,
    normalize_context_mode,
    sanitize_tags,
    stable_unique_ids,
    parse_tags_and_abstracts
)


@dataclass
class ContextCompressionProfile:
    """Describe how one agent should compress stored context.

    Attributes:
        task_type: Human-readable task label inserted into the compaction prompt.
        domain_schema: Domain-specific extraction schema appended to the prompt.
        prompt_template: Prompt template used to render the final compaction request.
    """

    task_type: str = "general"
    domain_schema: str = "No additional domain-specific extraction rules."
    prompt_template: str = CONTEXT_COMPACT_PROMPT_TEMPLATE


class ContextIndex:
    """Maintain inverted indexes for fast context and tag retrieval.

    The handler keeps the full timeline store as the source of truth, while
    this helper stores derived postings lists and compacted-source links so
    lookup methods can avoid scanning the whole timeline on every query.
    """

    def __init__(self) -> None:
        self.clear()

    def clear(self) -> None:
        """Reset every derived index."""
        self.raw_ids: Set[int] = set()
        self.compacted_ids: Set[int] = set()
        self.normalized_text_by_id: Dict[int, str] = {}
        self.text_postings: Dict[str, Set[int]] = {}
        self.tag_exact_postings: Dict[str, Set[int]] = {}
        self.tag_postings: Dict[str, Set[int]] = {}
        self.source_to_compacted: Dict[int, Set[int]] = {}
        self.compacted_to_sources: Dict[int, List[int]] = {}

    @staticmethod
    def _normalize_text(text: str) -> str:
        """
        Normalize text before it is indexed or matched.
        在查询文本之前，先进行标准化。（转为小写，并移除标点符号）
        """
        return " ".join(str(text or "").lower().split())

    @classmethod
    def _tokenize(cls, text: str) -> List[str]:
        """
        Split normalized text into tokens used by the postings index.
        将文本进行分词，并返回分词后的结果。
        """
        normalized = cls._normalize_text(text)
        if not normalized:
            return []
        # 使用 re 正则表达式匹配
        return re.findall(r"[a-z0-9_]+", normalized)

    @classmethod
    def _ngrams(cls, text: str, size: int = 3) -> List[str]:
        """Generate fixed-size character ngrams from normalized text."""
        normalized = cls._normalize_text(text)
        if len(normalized) < size:
            return [normalized] if normalized else []
        return [normalized[index:index + size] for index in range(len(normalized) - size + 1)]

    @classmethod
    def _sampled_ngrams(cls, text: str, size: int = 3, max_terms: int = 12) -> List[str]:
        """
        Sample representative ngrams from a query without generating all of them.
        """
        # 标准化。
        normalized = cls._normalize_text(text)
        if len(normalized) < size:
            return [normalized] if normalized else []

        total = len(normalized) - size + 1
        if total <= max_terms:
            return [normalized[index:index + size] for index in range(total)]

        positions = {
            round(index * (total - 1) / max(1, max_terms - 1))
            for index in range(max_terms)
        }
        return [normalized[position:position + size] for position in sorted(positions)]

    @classmethod
    def _query_terms(cls, text: str, *, max_ngrams: int = 12) -> List[str]:
        """
        Build a compact query term set for postings lookups.
        查询什么？
        """
        normalized = cls._normalize_text(text)
        if not normalized:
            return []

        terms: List[str] = []
        seen: Set[str] = set()

        # 进行索引
        for token in cls._tokenize(normalized):
            if token not in seen:
                seen.add(token)
                terms.append(token)

        for ngram in cls._sampled_ngrams(normalized, max_terms=max_ngrams):
            if ngram not in seen:
                seen.add(ngram)
                terms.append(ngram)

        return terms

    @staticmethod
    def _add_posting(index: Dict[str, Set[int]], term: str, context_id: int) -> None:
        """Add one context id to a postings bucket."""
        bucket = index.setdefault(term, set())
        bucket.add(context_id)

    def _add_terms(self, index: Dict[str, Set[int]], text: str, context_id: int) -> None:
        """Index both word tokens and character ngrams for one text value."""
        normalized = self._normalize_text(text)
        if not normalized:
            return

        terms = set(self._tokenize(normalized))
        terms.update(self._ngrams(normalized))
        for term in terms:
            self._add_posting(index, term, context_id)

    def index_context(
        self,
        context: LLMInfo,
        *,
        tag_to_context: Optional[Dict[str, List[int]]] = None,
    ) -> None:
        """Index one raw or compacted context entry.

        Args:
            context: Raw or compacted context entry to index.
            tag_to_context: Optional compatibility tag map maintained by the
                handler for debug output and legacy callers.
        """
        context_id = context.timeline
        if isinstance(context, LLMContextCompacted):
            self.compacted_ids.add(context_id)
            self.compacted_to_sources[context_id] = list(context.source_timeline)
            for source_id in context.source_timeline:
                self.source_to_compacted.setdefault(source_id, set()).add(context_id)
            searchable_text = context.abstract_msg
        else:
            self.raw_ids.add(context_id)
            searchable_text = context.content

        self.normalized_text_by_id[context_id] = self._normalize_text(searchable_text)
        self._add_terms(self.text_postings, searchable_text, context_id)
        self.index_tags(context, tag_to_context=tag_to_context)

    def index_tags(
        self,
        context: LLMInfo,
        *,
        tag_to_context: Optional[Dict[str, List[int]]] = None,
    ) -> None:
        """Index the tags attached to one context entry."""
        tags = sanitize_tags(context.tags)
        context.tags = tags
        if not tags:
            return

        for tag in tags:
            self._add_posting(self.tag_exact_postings, tag, context.timeline)
            self._add_terms(self.tag_postings, tag, context.timeline)
            if tag_to_context is not None:
                bucket = tag_to_context.setdefault(tag, [])
                if context.timeline not in bucket:
                    bucket.append(context.timeline)

    def _candidate_ids_for_terms(
        self,
        index: Dict[str, Set[int]],
        terms: List[str],
    ) -> Set[int]:
        """
        Return ids that contain every supplied term.
        Args:
            index: Postings index to query.
            terms: List of query terms to match.
        """
        # 我去，这……干啥呢？！
        buckets: List[Set[int]] = []
        
        for term in terms:
            bucket = index.get(term)
            if bucket is None:
                return set()
            buckets.append(bucket)
        if not buckets:
            return set()
        buckets.sort(key=len)

        candidate_ids: Set = set(buckets[0])
        for bucket in buckets[1:]:
            candidate_ids.intersection_update(bucket)
            if not candidate_ids:
                break
        return candidate_ids

    def candidate_text_ids(
        self,
        query: str,
        *,
        include_raw: bool = True,
        include_compacted: bool = True,
    ) -> Set[int]:
        """Return candidate context ids for a summary or body query.

        The method uses postings lists as a coarse filter and leaves exact
        substring or equality validation to the caller.
        """
        normalized_query = self._normalize_text(query)
        if not normalized_query:
            return set()

        query_terms = self._query_terms(normalized_query)
        candidate_ids = self._candidate_ids_for_terms(self.text_postings, query_terms)
        if not candidate_ids:
            return set()

        allowed_ids: Set[int] = set()
        if include_raw:
            allowed_ids.update(self.raw_ids)
        if include_compacted:
            allowed_ids.update(self.compacted_ids)
        return candidate_ids.intersection(allowed_ids)

    def candidate_tag_ids(self, tags: List[str], *, blur: bool = False) -> Set[int]:
        """
        Return candidate ids for a tag query.
        
        Args:
            tags: List of tags to query.
            blur: Whether to use fuzzy matching for tag queries.
        """
        # 先清洗标签。
        normalized_tags = sanitize_tags(tags, max_tags=max(12, len(tags)))
        if not normalized_tags:
            return set()
        
        # 然后匹配 id
        matched_ids: Set[int] = set()
        for query_tag in normalized_tags:
            # 在启用模糊搜索的场合
            if blur:
                query_terms = self._query_terms(query_tag, max_ngrams=6)
                candidate_ids = self._candidate_ids_for_terms(self.tag_postings, query_terms)
                matched_ids.update(candidate_ids)
            else:
                # 否则，精确匹配
                matched_ids.update(self.tag_exact_postings.get(query_tag, set()))
        return matched_ids

    def compacted_ids_for_source_ids(self, source_ids: List[int]) -> Set[int]:
        """Return compacted ids that reference any of the supplied raw ids."""
        if not source_ids:
            return set()

        matched_ids: Set[int] = set()
        for source_id in source_ids:
            matched_ids.update(self.source_to_compacted.get(source_id, set()))
        return matched_ids


class ContextSemanticIndex:
    """Maintain an in-memory vector-like index for semantic context retrieval.

    The index prefers an ephemeral Chroma collection when available, but it can
    fall back to a deterministic pure-Python embedding path when the optional
    vector dependencies or model weights are unavailable. That keeps semantic
    retrieval usable in offline test environments while still allowing richer
    embeddings in production.
    """

    def __init__(
        self,
        *,
        embedding_model_name: Optional[str] = None,
        collection_name: str = "llmfetcher_context",
    ) -> None:
        """Initialize the semantic index.

        Args:
            embedding_model_name: Optional sentence-transformers model name or
                local path. When omitted, the index falls back to a hashed
                embedding representation instead of loading a heavy model.
            collection_name: Name used for the ephemeral Chroma collection.
        """
        self.embedding_model_name = (embedding_model_name or os.getenv("LLMFETCHER_CONTEXT_EMBEDDING_MODEL", "")).strip() or None
        self.collection_name = collection_name
        self.clear()
        self._sentence_transformer_class: Optional[Any] = None
        self._embedding_model: Any = None
        self._embedding_model_error = ""
        self._chromadb_module: Any = None
        self._chroma_client: Any = None
        self._chroma_collection: Any = None

    def clear(self) -> None:
        """Reset all derived semantic vectors and transient collection state."""
        self.raw_ids: Set[int] = set()
        self.compacted_ids: Set[int] = set()
        self.text_by_id: Dict[int, str] = {}
        self.kind_by_id: Dict[int, str] = {}
        self.vector_by_id: Dict[int, List[float]] = {}
        self._chroma_client = None
        self._chroma_collection = None

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize text before encoding or similarity matching."""
        return " ".join(str(text or "").lower().split())

    @staticmethod
    def _build_context_text(context: LLMInfo) -> str:
        """Build a semantic document for one context entry."""
        parts: List[str] = []
        if isinstance(context, LLMContextCompacted):
            parts.append(f"summary: {context.abstract_msg}")
            if context.tags:
                parts.append(f"tags: {' '.join(context.tags)}")
            if context.source_timeline:
                parts.append(f"source_timeline: {' '.join(str(item) for item in context.source_timeline)}")
            return "\n".join(part for part in parts if part.strip())

        if context.role:
            parts.append(f"role: {context.role}")
        if context.content:
            parts.append(f"content: {context.content}")
        if context.content_reasoning:
            parts.append(f"reasoning: {context.content_reasoning}")
        if context.abstract_msg:
            parts.append(f"abstract: {context.abstract_msg}")
        if context.tool_call_info:
            parts.append("tool_call_info: " + "\n".join(context.tool_call_info))
        if context.tool_result_facts:
            parts.append("tool_result_facts: " + "\n".join(context.tool_result_facts))
        if context.tags:
            parts.append(f"tags: {' '.join(context.tags)}")
        return "\n".join(part for part in parts if part.strip())

    def _load_sentence_transformer(self) -> Optional[Any]:
        """Lazily load a sentence-transformers model when configured."""
        if self._embedding_model is not None:
            return self._embedding_model
        if self._embedding_model_error:
            return None
        if not self.embedding_model_name:
            return None

        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except Exception as exc:  # pragma: no cover - depends on environment
            self._embedding_model_error = f"{type(exc).__name__}: {exc}"
            return None

        try:
            model_source = self._resolve_model_source(self.embedding_model_name)
            self._sentence_transformer_class = SentenceTransformer
            self._embedding_model = SentenceTransformer(model_source, local_files_only=True)
        except Exception as exc:  # pragma: no cover - depends on environment
            self._embedding_model_error = f"{type(exc).__name__}: {exc}"
            self._embedding_model = None
        return self._embedding_model

    @staticmethod
    def _resolve_model_source(model_name: str) -> str:
        """Resolve a configured model name to a local path when possible."""
        normalized = model_name.strip()
        if not normalized:
            return "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

        candidate_path = os.path.expanduser(normalized)
        if os.path.exists(candidate_path):
            return os.path.abspath(candidate_path)
        return normalized

    @staticmethod
    def _hash_token_vector(text: str, dimension: int = 384) -> List[float]:
        """Build a deterministic fallback embedding from token and n-gram hashes."""
        normalized = ContextSemanticIndex._normalize_text(text)
        if not normalized:
            return [0.0] * dimension

        vector = [0.0] * dimension
        tokens = re.findall(r"[a-z0-9_]+", normalized) or [normalized]
        features: List[str] = list(tokens)
        features.extend(
            normalized[index:index + 3]
            for index in range(max(0, len(normalized) - 2))
        )

        for feature in features:
            digest = hashlib.sha256(feature.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "big") % dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign

        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    def _encode_texts(self, texts: Sequence[str]) -> List[List[float]]:
        """Encode texts into normalized vectors using the configured backend."""
        normalized_texts = [self._normalize_text(text) for text in texts]
        if not normalized_texts:
            return []

        model = self._load_sentence_transformer()
        if model is not None:
            vectors = model.encode(
                list(normalized_texts),
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            if hasattr(vectors, "tolist"):
                return vectors.tolist()
            return [list(vector) for vector in vectors]

        return [self._hash_token_vector(text) for text in normalized_texts]

    def _ensure_chroma_collection(self) -> Optional[Any]:
        """Create the ephemeral Chroma collection on first use."""
        if self._chroma_collection is not None:
            return self._chroma_collection

        try:
            if self._chromadb_module is None:
                import chromadb  # type: ignore

                self._chromadb_module = chromadb
        except Exception:  # pragma: no cover - optional dependency
            self._chromadb_module = None
            return None

        try:
            client_factory = getattr(self._chromadb_module, "EphemeralClient", None)
            if callable(client_factory):
                self._chroma_client = client_factory()
            else:  # pragma: no cover - fallback path for older Chroma versions
                self._chroma_client = self._chromadb_module.Client()

            self._chroma_collection = self._chroma_client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        except Exception:  # pragma: no cover - optional dependency
            self._chroma_client = None
            self._chroma_collection = None
        return self._chroma_collection

    def index_context(self, context: LLMInfo) -> None:
        """Index one raw or compacted context entry for semantic retrieval."""
        context_id = context.timeline
        semantic_text = self._build_context_text(context)
        if not semantic_text.strip():
            return

        if isinstance(context, LLMContextCompacted):
            self.compacted_ids.add(context_id)
            kind = "compacted"
        else:
            self.raw_ids.add(context_id)
            kind = "raw"

        self.text_by_id[context_id] = semantic_text
        self.kind_by_id[context_id] = kind

        vector = self._encode_texts([semantic_text])[0]
        self.vector_by_id[context_id] = vector

        collection = self._ensure_chroma_collection()
        if collection is not None:
            try:
                collection.upsert(
                    ids=[str(context_id)],
                    embeddings=[vector],
                    documents=[semantic_text],
                    metadatas=[{"kind": kind}],
                )
            except Exception:  # pragma: no cover - optional dependency
                self._chroma_collection = None

    def _search_with_chroma(
        self,
        query_vector: List[float],
        *,
        top_k: int,
        include_raw: bool,
        include_compacted: bool,
        allowed_ids: Optional[Set[int]] = None,
    ) -> List[int]:
        """Query the Chroma-backed index and normalize its response."""
        collection = self._ensure_chroma_collection()
        if collection is None:
            return []

        candidate_count = max(top_k, min(len(self.vector_by_id), top_k * 4))
        try:
            response = collection.query(
                query_embeddings=[query_vector],
                n_results=candidate_count,
                include=["metadatas", "documents", "distances"],
            )
        except Exception:  # pragma: no cover - optional dependency
            return []

        ids = (response.get("ids") or [[]])[0]
        metadatas = (response.get("metadatas") or [[]])[0]
        distances = (response.get("distances") or [[]])[0]

        ranked: List[Tuple[int, float]] = []
        for raw_id, metadata, distance in zip(ids, metadatas, distances):
            try:
                context_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            kind = str(metadata.get("kind", "raw")) if isinstance(metadata, dict) else "raw"
            if kind == "raw" and not include_raw:
                continue
            if kind == "compacted" and not include_compacted:
                continue
            if allowed_ids is not None and context_id not in allowed_ids:
                continue
            score = 1.0 / (1.0 + float(distance or 0.0))
            ranked.append((context_id, score))

        ranked.sort(key=lambda item: (-item[1], item[0]))
        return [context_id for context_id, _ in ranked[:top_k]]

    def _search_locally(
        self,
        query_vector: List[float],
        *,
        top_k: int,
        include_raw: bool,
        include_compacted: bool,
        allowed_ids: Optional[Set[int]] = None,
    ) -> List[int]:
        """Query the in-memory vector cache without Chroma."""
        ranked: List[Tuple[int, float]] = []
        query_norm = math.sqrt(sum(value * value for value in query_vector)) or 1.0
        for context_id, vector in self.vector_by_id.items():
            kind = self.kind_by_id.get(context_id, "raw")
            if kind == "raw" and not include_raw:
                continue
            if kind == "compacted" and not include_compacted:
                continue
            if allowed_ids is not None and context_id not in allowed_ids:
                continue

            numerator = sum(left * right for left, right in zip(query_vector, vector))
            vector_norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            score = numerator / (query_norm * vector_norm)
            if score > 0:
                ranked.append((context_id, score))

        ranked.sort(key=lambda item: (-item[1], item[0]))
        return [context_id for context_id, _ in ranked[:top_k]]

    def search(
        self,
        query: str,
        *,
        top_k: int = 8,
        include_raw: bool = True,
        include_compacted: bool = True,
        allowed_ids: Optional[Set[int]] = None,
    ) -> List[int]:
        """Return semantic nearest-neighbour ids for one query."""
        normalized_query = self._normalize_text(query)
        if not normalized_query:
            return []

        query_vector = self._encode_texts([normalized_query])[0]
        if self._chroma_collection is not None:
            chroma_ids = self._search_with_chroma(
                query_vector,
                top_k=top_k,
                include_raw=include_raw,
                include_compacted=include_compacted,
                allowed_ids=allowed_ids,
            )
            if chroma_ids:
                return chroma_ids
        return self._search_locally(
            query_vector,
            top_k=top_k,
            include_raw=include_raw,
            include_compacted=include_compacted,
            allowed_ids=allowed_ids,
        )


class LLMContextHandler:
    """Manage stored conversation context, summaries, and lightweight retrieval.

    Notes:
        Each agent owns exactly one handler instance. The handler keeps a full
        timeline store, a smaller active window used for prompt assembly, and
        optional memory/tag indexes for retrieval.
    """

    def __init__(
        self,
        llm_handler: LLMFetcher,
        enable_memory: bool = True,
        enable_tagging: bool = False,
        compression_profile: Optional[ContextCompressionProfile] = None,
        context_mode: ContextMode = "graph",
        semantic_embedding_model: Optional[str] = None,
    ):
        """Initialize the context handler.

        Args:
            llm_handler: Fetcher used for compression, tagging, and memory
                generation requests.
            enable_memory: Whether persistent memory summaries should be stored.
            enable_tagging: Whether tag-based retrieval indexes should be built.
            compression_profile: Default prompt profile used whenever context
                compression is requested without an explicit override.
            context_mode: `linear` disables retrieval/tagging and keeps a
                chronological active context with summarization; `graph`
                enables the experimental retrieval/selection helpers.
            semantic_embedding_model: Optional sentence-transformers model name
                or local path used for in-memory semantic retrieval. When
                omitted, the handler uses a deterministic fallback embedding.
        """
        self.llm_handler = llm_handler        
        self.compression_profile = compression_profile or ContextCompressionProfile()
        self.context_mode: ContextMode = normalize_context_mode(context_mode)
        self.retrieval_enabled = self.context_mode == "graph"

        # 在储存变量结束后加入回退索引
        self.fallback_order = self.llm_handler.fallback_order

        # ========== 基础索引 ==========
        # 索引：时间线 id -> 上下文对象。
        self.context_timeline_dict: Dict[int, LLMInfo] = {}

        # 当前激活的上下文时间线 id 列表。
        self.active_ids: List[int] = []

        # 本 agent 的时间线游标。
        self.now_context_id: int = 1

        # Derive fast lookup structures from the full timeline store.
        self.context_index = ContextIndex()
        self.semantic_index = ContextSemanticIndex(
            embedding_model_name=semantic_embedding_model,
        )

        # ========= 记忆机制 =========
        # 记忆不会被压缩。
        self.enable_memory = enable_memory
        self.memory_list: Optional[List[str]] = None
        if self.enable_memory:
            self.memory_list = []

        # 工具结果事实不会被压缩为普通上下文，而是保留为更短的
        # 可检索、可喂给状态机的事实层记录。
        self.tool_result_facts: List[ToolResultFact] = []


        # ========= 标签索引和查询机制 ==========
        # k: tag: str 当前标签, v: List[int] 具有当前标签的信息
        # 标签具有不确定性
        self.enable_tagging = bool(enable_tagging)    # 启用标签功能
        self.tag_to_context: Optional[Dict[str, List[int]]] = None  # 反查：tag -> 时间线 id
        if self.enable_tagging:
            self.tag_to_context = {}

    def configure_context_mode(
        self,
        context_mode: ContextMode,
        *,
        enable_tagging: Optional[bool] = None,
    ) -> None:
        """Apply an immutable task context mode to this handler.

        This exists for durable task reloads where the Agent is reconstructed
        from disk and then refreshed with the persisted task configuration.
        Switching to linear clears retrieval-only indexes while keeping the
        timeline store and active ids intact.
        TODO: 包括该函数在内的其他所有函数，删掉 enable_tagging 参数。当使用图式上下文时自动要求匹配。

        Args:
            context_mode: literal for 'linear' and 'graph'.
            enable_tagging:
        """
        next_mode = normalize_context_mode(context_mode)
        requested_tagging = self.enable_tagging if enable_tagging is None else enable_tagging
        self.context_mode = next_mode
        self.retrieval_enabled = next_mode == "graph"
        self.enable_tagging = bool(requested_tagging and self.retrieval_enabled)
        self._rebuild_indexes()

    def _rebuild_indexes(self) -> None:
        """Rebuild the derived text, semantic, and tag indexes from scratch."""
        self.context_index.clear()
        self.semantic_index.clear()
        self.tag_to_context = {} if self.enable_tagging else None
        if not self.retrieval_enabled:
            return

        for context_id in sorted(self.context_timeline_dict):
            entry = self.context_timeline_dict[context_id]
            self.context_index.index_context(
                entry,
                tag_to_context=self.tag_to_context if self.enable_tagging else None,
            )
            self.semantic_index.index_context(entry)

    # ====================================================================
    # Basic System
    # 这里是上下文管理器的基础，当前实现仍可兼容线性上下文。
    # ====================================================================

    @property
    def empty(self) -> bool:
        """
        检查：当前上下文内容是否为空。
        """
        return not self.context_timeline_dict

    def clear(self) -> None:
        """
        清除所有上下文内容，并重置时间线索引。
        如果需要清楚记忆，请手动清理记忆。
        """
        self.context_timeline_dict.clear()
        self.active_ids.clear()
        self.now_context_id = 1
        self.context_index.clear()
        self.semantic_index.clear()

        if self.enable_tagging and self.tag_to_context is not None:
            self.tag_to_context.clear() # pyright: ignore
        self.tool_result_facts.clear()

    def set_active_ids(self, context_ids: Optional[List[int]] = None) -> List[int]:
        """
        设置当前激活的上下文窗口。

        Args:
            context_ids: 需要激活的时间线 id 列表。传入 `None` 时激活全部已知条目。
        
        Returns:
            返回当前激活的 id 列表。
        """

        if context_ids is None:
            normalized_ids = sorted(self.context_timeline_dict.keys())
        else:
            # 检查：id 有效，这里已经检查过了
            normalized_ids = [
                context_id
                for context_id in context_ids
                if context_id in self.context_timeline_dict
            ]
        
        # 去重但保留调用者提供的顺序。
        self.active_ids = stable_unique_ids(normalized_ids)
        return list(self.active_ids)

    def append_active_ids(self, context: LLMInfo) -> None:
        """
        在当前活跃上下文列表末尾添加一个上下文 id。

        Args:
            context: 上下文信息，需要携带 timeline。
        """
        # 检查：如果本上下文信息不在活跃列表中
        if context.timeline not in self.active_ids:
            self.active_ids.append(context.timeline)

    def get_active_ids_window(self) -> List[int]:
        """
        返回当前活跃上下文列表。
        """
        return list(self.active_ids)

    def context_len(self) -> int:
        """
        返回当前活跃上下文序列化后的总字符长度。
        """
        total = 0
        for context_id in self.active_ids:
            entry = self.context_timeline_dict.get(context_id)
            if entry is not None:
                total += len(str(entry))
        return total

    async def add_context(
        self,
        context: LLMContext,
        append_to_active: bool = True,
        temperature: float = 0.4
    ) -> None:
        """
        加入一条新的上下文内容。

        Args:
            context: 每次调度的信息。
            append_to_active: 是否加入当前活跃上下文窗口。
            temperature: 给上下文打标签时，该 agent handler 的温度。
        """
        # 如果支持标签化，则先打标签，然后加入反查表。
        if self.enable_tagging:
            context = await self.tagify_context(context, temperature)
        
        context.tags = sanitize_tags(context.tags)
        context.timeline = self.now_context_id
        self.context_timeline_dict[self.now_context_id] = context
        self.now_context_id += 1

        # Index the new entry so later retrieval can use postings lists instead
        # of rescanning the whole timeline.
        if self.retrieval_enabled:
            self.context_index.index_context(
                context,
                tag_to_context=self.tag_to_context if self.enable_tagging else None,
            )
            self.semantic_index.index_context(context)

        # 加入当前活跃上下文窗口
        if append_to_active:
            self.append_active_ids(context)
        

    async def get_now_context(
        self,
        timeline_id_list: Optional[List[int]] = None,
        *,
        preserve_order: bool = False,
    ) -> Optional[LLMContextInfo]:
        """
        获取上下文，以消息字典列表格式。
        TODO: 需要按时间线走。

        Args:
            timeline_id_list: 可选返回的上下文内容的时间线 id 列表。
            preserve_order: 是否保持时间线顺序。

        Notes:
            如果未指定，则返回当前被激活的上下文内容。
        """
        if self.empty:
            return None

        if timeline_id_list is None:
            # 如果未指定，获取当前被激活的上下文。
            selected_ids = self.get_active_ids_window()
        else:
            # 获取指定时间线的内容，保证存在。
            selected_ids = [
                timeline_id
                for timeline_id in timeline_id_list
                if timeline_id in self.context_timeline_dict
            ]
        
        # 是否保持时间线顺序
        if preserve_order:
            ordered_ids = stable_unique_ids(selected_ids)
        else:
            # 兼容旧行为：默认按时间线有序，从小到大。
            ordered_ids = sorted(set(selected_ids))
        
        # 然后压入信息。
        info: List[LLMInfo] = []

        for context_id in ordered_ids:
            entry = self.context_timeline_dict[context_id]
            info.append(entry)
        
        return LLMContextInfo(items=info)

    async def get_now_active_context(self) -> Optional[LLMContextInfo]:
        """
        Alias:
            get_now_context()
        """
        return await self.get_now_context()
    
    async def transcribe_context_to_str(
        self,
        contexts: LLMContextInfo
    ) -> str:
        """
        将上下文信息转为字符串。

        Args:
            contexts: 上下文信息。
        
        Return:
            str: 转换后的字符串。
        """
        lines: List[str] = []
        for context in contexts.items:
            lines.append(str(context))

        return "\n".join(lines)
    
    async def transcribe_context_abstarct_to_str(
        self,
        contexts: LLMContextInfo
    ) -> str:
        """
        将上下文的摘要信息转为字符串。

        Args:
            contexts: 上下文信息。
        
        Return:
            str: 被抽象后的上下文信息。
        """
        lines: List[str] = []
        for context in contexts.items:
            lines.append(context.abstract_msg)
        
        return "\n".join(lines)

    async def get_now_context_as_str(
        self,
        timeline_id_list: Optional[List[int]] = None,
        *,
        preserve_order: bool = False,
    ) -> str:
        """
        获取当前上下文全部格式，以字符串格式。

        Args:
            timeline_id_list: 可选返回的上下文内容的时间线 id 列表。

        Returns:
            返回当前上下文，以单个字符串格式。如果为空则返回空字符串。
        """
        info = await self.get_now_context(timeline_id_list, preserve_order=preserve_order)
        if info is None:
            return ""

        return await self.transcribe_context_to_str(info)
    
    async def get_now_abstract_as_str(
        self,
        timeline_id_list: Optional[List[int]] = None,
        *,
        preserve_order: bool = False,
    ) -> str:
        """
        获取当前上下文全部格式，以字符串格式。

        Args:
            timeline_id_list: 可选返回的上下文内容的时间线 id 列表。

        Returns:
            返回当前上下文，以单个字符串格式。如果为空则返回空字符串。
        """
        info = await self.get_now_context(timeline_id_list, preserve_order=preserve_order)
        if info is None:
            return ""
        return await self.transcribe_context_abstarct_to_str(info)

    async def compress_context(
        self,   
        timeline_id_list: Optional[List[int]] = None,
        temperature: float = 0.3,
        compression_profile: Optional[ContextCompressionProfile] = None,
    ) -> bool:
        """
        压缩当前全部未压缩上下文，或压缩给定时间线 id 对应的条目。
        todo: 思考：压缩上下文为什么要用 llm？这不会太长了吧。

        Args:
            timeline_id_list: 可选返回的上下文内容的时间线 id 列表。
            temperature: 模型温度。
            compression_profile: 可选的压缩配置，允许调用方按任务类型
                切换压缩模板、task_type 与领域 schema。

        Returns:
            返回是否成功压缩。
        """
        # 获取目标 id
        target_ids = self.get_active_ids_window() if timeline_id_list is None \
            else [
                timeline_id
                for timeline_id in timeline_id_list
                if timeline_id in self.context_timeline_dict
            ]
        
        if not target_ids:
            return False
        
        # 获取当前上下文信息
        target_ids = stable_unique_ids(target_ids)
        info: Optional[LLMContextInfo] = await self.get_now_context(target_ids, preserve_order=True)
        if info is None:
            return False

        lines = await self.transcribe_context_to_str(info)
        if not lines:
            return False

        # 解析本次压缩应使用的 profile，使任务层可以按场景调度压缩策略，
        # 而不是把领域知识硬编码在上下文管理器内部。
        resolved_profile = compression_profile or self.compression_profile

        # 根据 profile 渲染压缩提示词，并将当前选中的上下文内容交给 LLM
        # 生成可用于后续检索和恢复的摘要条目。
        prompt = resolved_profile.prompt_template.format(
            task_type=resolved_profile.task_type,
            domain_schema=resolved_profile.domain_schema,
            lines=lines,
        )
        response: LLMOutput = await self.llm_handler.fetch(
            msg=prompt,
            temperature=temperature
        )
        # 压缩
        compacted_text = response.content.strip()
        if not compacted_text:
            return False
        
        # 创建压缩信息
        info_by_timeline: Dict[int, LLMInfo] = {
            item.timeline: item
            for item in info.items
        }
        source_items: List[LLMInfo] = [
            info_by_timeline[context_id]
            for context_id in target_ids
        ]

        # 合并标签，并整理时间线
        merged_tags: List[str] = []
        flattened_timeline: List[int] = []
        for item in source_items:
            if item.tags:
                merged_tags.extend(item.tags)
            if isinstance(item, LLMContextCompacted):
                flattened_timeline.extend(item.source_timeline)
            else:
                flattened_timeline.append(item.timeline)
        
        # 使用新的 id，并加入时间线
        compacted_id: int = self.now_context_id
        compacted_info = LLMContextCompacted(
            timeline=self.now_context_id,
            abstract_msg=compacted_text,
            source=source_items,
            source_timeline=stable_unique_ids(flattened_timeline),
            tags=sanitize_tags(merged_tags),
        )

        self.context_timeline_dict[compacted_id] = compacted_info
        self.now_context_id += 1

        # Update the derived indexes so source-to-summary lookups stay O(1)
        # on the common path even when summaries are nested.
        if self.retrieval_enabled:
            self.context_index.index_context(
                compacted_info,
                tag_to_context=self.tag_to_context if self.enable_tagging else None,
            )
            self.semantic_index.index_context(compacted_info)
        
        # 然后更改激活上下文
        selected_id_set = set(target_ids)
        self.active_ids = [
            context_id
            for context_id in self.active_ids       # 在已有的被激活上下文里
            if context_id not in selected_id_set    # 剔除已选择的上下文
        ]
        self.active_ids.append(compacted_id)
        self.active_ids = stable_unique_ids(self.active_ids)

        return True

    async def search_context_by_keyword(
        self, 
        keywords: str
    ) -> Optional[LLMContextInfo]:
        """
        基于关键词和语义索引查询上下文信息。

        Args:
            keywords: 关键字信息表达式，使用搜索引擎同款。
        """
        if not self.retrieval_enabled:
            return None

        normalized_query = self.context_index._normalize_text(keywords)
        if not normalized_query:
            return None

        semantic_ids = self.semantic_index.search(
            normalized_query,
            top_k=8,
            include_raw=True,
            include_compacted=True,
        )
        if not semantic_ids:
            semantic_ids = sorted(self.context_index.candidate_text_ids(
                normalized_query,
                include_raw=True,
                include_compacted=True,
            ))

        if not semantic_ids:
            return None

        info = await self.get_now_context(semantic_ids, preserve_order=True)
        return info

    # ====================================================================
    # Memory System
    # 记忆是不会改变的。
    # “记忆”层级不等于“上下文”——记忆不会被压缩。
    # ====================================================================
    
    async def create_memory(self, id_list: Optional[List[int]]) -> Optional[str]:
        """
        将特定的上下文内容提取为短条内容。
        - 这是作为“记忆”的重要部分，记忆不会被格式化。
        - 如果未规定记忆则提取全部。

        Args:
            id_list: 目标上下文内容 id。
        
        Returns:
            返回生成的记忆。如果为空则返回 None。
        """
        if not self.context_timeline_dict:
            return None

        lines = await self.get_now_context_as_str(id_list)
        if not lines:
            return None

        prompt = MEMORY_CONCLUDE_PROMPT_TEMPLATE.format(lines=lines)
        response = await self.llm_handler.fetch(
            msg=prompt
        )
        memory = response.content or None
        if memory and self.enable_memory and self.memory_list is not None:
            self.memory_list.append(memory)
        return memory

    def copy_memories(self) -> Optional[List[str]]:
        """
        获取所有已存储的记忆，该操作会拷贝一份。
        
        Notes:
            仅当记忆开启时会返回内容，记忆不开启时将返回 None。

        Returns:
            记忆内容，拷贝一份。
        """
        if self.enable_memory:
            # 此时 self.memory_list 的类型是 List[str]
            return self.memory_list.copy()  # pyright: ignore
        return None

    def get_memories(self) -> Optional[Tuple[str]]:
        """
        获取所有已存储的记忆，该操作将返回只读引用。

        Notes:
            建议在获取后立即改为 tuple 类型以只读。
            仅当记忆开启时会返回内容，记忆不开启时将返回 None。

        Returns:
            记忆内容。
        """
        if self.enable_memory:
            return tuple(self.memory_list)  # pyright: ignore
        return None

    def clear_memories(self) -> None:
        """
        清除记忆。
        """
        if self.enable_memory:
            # 同上
            self.memory_list.clear()    # pyright: ignore

    def copy_tool_result_facts(self) -> List[ToolResultFact]:
        """Return a shallow copy of the compressed tool-result facts."""
        return list(self.tool_result_facts)

    def get_tool_result_facts(self) -> Tuple[ToolResultFact, ...]:
        """Return the compressed tool-result facts as an immutable tuple."""
        return tuple(self.tool_result_facts)

    def clear_tool_result_facts(self) -> None:
        """Remove every stored tool-result fact from the handler."""
        self.tool_result_facts.clear()

    @staticmethod
    def _serialize_tool_result_fact(fact: ToolResultFact) -> Dict[str, Any]:
        """Serialize one tool-result fact bundle into JSON-friendly data."""
        return fact.to_dict()

    @staticmethod
    def _deserialize_tool_result_fact(payload: Mapping[str, Any]) -> ToolResultFact:
        """Rebuild a tool-result fact bundle from exported JSON data."""
        return ToolResultFact(
            tool_name=str(payload.get("tool_name", "")).strip(),
            summary=str(payload.get("summary", "")),
            facts=[
                str(item).strip()
                for item in payload.get("facts", [])
                if str(item).strip()
            ],
            evidence=str(payload.get("evidence", "")),
            status=str(payload.get("status", "unknown")) or "unknown",
            tool_call_id=(
                str(payload.get("tool_call_id")).strip()
                if payload.get("tool_call_id") is not None and str(payload.get("tool_call_id")).strip()
                else None
            ),
            tags=[
                str(item).strip()
                for item in payload.get("tags", [])
                if str(item).strip()
            ],
        )

    @staticmethod
    def _serialize_context_entry(context: LLMInfo) -> Dict[str, Any]:
        """Serialize one timeline entry into a JSON-friendly record."""
        if isinstance(context, LLMContextCompacted):
            source_ids = [
                source.timeline
                for source in context.source
                if getattr(source, "timeline", -1) >= 0
            ]
            return {
                "context_id": context.timeline,
                "kind": "compacted",
                "abstract_msg": context.abstract_msg,
                "source_ids": source_ids,
                "source_timeline": list(context.source_timeline),
                "tags": list(context.tags),
            }

        return {
            "context_id": context.timeline,
            "kind": "raw",
            "role": context.role,
            "content": context.content,
            "timeline": context.timeline,
            "abstract_msg": context.abstract_msg,
            "content_reasoning": context.content_reasoning,
            "tool_call_info": list(context.tool_call_info or []),
            "tool_call_ids": list(context.tool_call_ids or []),
            "tool_result_facts": list(context.tool_result_facts or []),
            "tags": list(context.tags or []),
        }

    def export_context(self) -> LLMContextSnapshot:
        """Export the handler state into a JSON-friendly snapshot.

        Returns:
            A snapshot object that contains timeline entries, active ids,
            memories, compressed tool-result facts, and handler metadata.
        """
        contexts = [
            self._serialize_context_entry(self.context_timeline_dict[context_id])
            for context_id in sorted(self.context_timeline_dict)
        ]
        memories = list(self.memory_list or []) if self.enable_memory else []
        return LLMContextSnapshot(
            schema_version=1,
            context_mode=self.context_mode,
            now_context_id=self.now_context_id,
            active_ids=list(self.active_ids),
            contexts=contexts,
            memories=memories,
            tool_result_facts=[
                self._serialize_tool_result_fact(fact)
                for fact in self.tool_result_facts
            ],
            enable_memory=self.enable_memory,
            enable_tagging=self.enable_tagging,
        )

    def _apply_snapshot_contexts(self, contexts: Sequence[Mapping[str, Any]]) -> None:
        """Insert serialized context records before rebuilding derived indexes."""
        compacted_source_map: Dict[int, List[int]] = {}
        for item in contexts:
            try:
                context_id = int(item.get("context_id", item.get("timeline", -1)))
            except (TypeError, ValueError):
                continue
            if context_id < 0:
                continue

            kind = str(item.get("kind", "raw")).strip().lower()
            if kind == "compacted":
                source_timeline: List[int] = []
                for source_id in item.get("source_timeline", []):
                    try:
                        source_timeline.append(int(source_id))
                    except (TypeError, ValueError):
                        continue
                source_ids: List[int] = []
                for source_id in item.get("source_ids", []):
                    try:
                        source_ids.append(int(source_id))
                    except (TypeError, ValueError):
                        continue
                compacted = LLMContextCompacted(
                    abstract_msg=str(item.get("abstract_msg", "")),
                    source=[],
                    source_timeline=source_timeline,
                    tags=[
                        str(tag).strip()
                        for tag in item.get("tags", [])
                        if tag is not None and str(tag).strip()
                    ],
                    timeline=context_id,
                )
                self.context_timeline_dict[context_id] = compacted
                compacted_source_map[context_id] = source_ids
                continue

            context = LLMContext(
                role=str(item.get("role", "")),
                content=str(item.get("content", "")),
                timeline=context_id,
                abstract_msg=str(item.get("abstract_msg", "")),
                content_reasoning=(
                    str(item.get("content_reasoning")).strip()
                    if item.get("content_reasoning") is not None and str(item.get("content_reasoning")).strip()
                    else None
                ),
                tool_call_info=[
                    str(value)
                    for value in item.get("tool_call_info", [])
                    if value is not None and str(value).strip()
                ] or None,
                tool_call_ids=[
                    str(value)
                    for value in item.get("tool_call_ids", [])
                    if value is not None and str(value).strip()
                ] or None,
                tool_result_facts=[
                    str(value)
                    for value in item.get("tool_result_facts", [])
                    if value is not None and str(value).strip()
                ] or None,
                tags=[
                    str(tag).strip()
                    for tag in item.get("tags", [])
                    if tag is not None and str(tag).strip()
                ],
            )
            self.context_timeline_dict[context_id] = context

        for compacted_id, source_ids in compacted_source_map.items():
            entry = self.context_timeline_dict.get(compacted_id)
            if not isinstance(entry, LLMContextCompacted):
                continue
            entry.source = [
                self.context_timeline_dict[source_id]
                for source_id in source_ids
                if source_id in self.context_timeline_dict
            ]

    @staticmethod
    def _normalize_legacy_snapshot_payload(payload: Mapping[str, Any]) -> Dict[str, Any]:
        """Convert older session-store payloads into the current snapshot shape."""
        contexts: List[Dict[str, Any]] = []
        for item in payload.get("contexts", []):
            if not isinstance(item, dict):
                continue
            contexts.append(
                {
                    "context_id": item.get("context_id", item.get("timeline", -1)),
                    "kind": "raw",
                    "role": item.get("role", ""),
                    "content": item.get("content", ""),
                    "timeline": item.get("context_id", item.get("timeline", -1)),
                    "abstract_msg": item.get("abstract_msg", item.get("abstract", "")),
                    "content_reasoning": item.get("content_reasoning", item.get("reasoning_content", "")),
                    "tool_call_info": list(item.get("tool_call_info", [])),
                    "tool_call_ids": list(item.get("tool_call_ids", [])),
                    "tool_result_facts": list(item.get("tool_result_facts", [])),
                    "tags": list(item.get("tags", [])),
                }
            )

        for item in payload.get("compacted_contexts", []):
            if not isinstance(item, dict):
                continue
            contexts.append(
                {
                    "context_id": item.get("context_id", item.get("timeline", -1)),
                    "kind": "compacted",
                    "abstract_msg": item.get("abstract_msg", ""),
                    "source_ids": list(item.get("source_ids", item.get("source_timeline", []))),
                    "source_timeline": list(item.get("source_timeline", item.get("source_ids", []))),
                    "tags": list(item.get("tags", [])),
                }
            )

        return {
            "schema_version": payload.get("version", payload.get("schema_version", 1)),
            "context_mode": payload.get("context_mode", payload.get("mode", "graph")),
            "now_context_id": payload.get("next_context_id", payload.get("now_context_id", 1)),
            "active_ids": list(payload.get("active_ids", [])),
            "contexts": contexts,
            "memories": list(payload.get("memories", [])),
            "tool_result_facts": list(payload.get("tool_result_facts", [])),
            "enable_memory": bool(payload.get("enable_memory", True)),
            "enable_tagging": bool(payload.get("enable_tagging", False)),
        }

    def import_context(
        self,
        payload: LLMContextSnapshot | Mapping[str, Any],
        *,
        replace: bool = True,
    ) -> LLMContextSnapshot:
        """Restore handler state from an exported snapshot or mapping.

        Args:
            payload: Exported snapshot object or JSON-friendly mapping.
            replace: Whether to discard the current in-memory timeline before
                loading the supplied snapshot.

        Returns:
            The normalized snapshot that was applied to the handler.
        """
        if isinstance(payload, LLMContextSnapshot):
            snapshot = payload
        else:
            raw_payload = dict(payload)
            if "compacted_contexts" in raw_payload:
                raw_payload = self._normalize_legacy_snapshot_payload(raw_payload)
            snapshot = LLMContextSnapshot.from_dict(raw_payload)

        if replace:
            self.context_timeline_dict.clear()
            self.active_ids.clear()
            self.now_context_id = 1
            self.context_index.clear()
            self.semantic_index.clear()
            if self.enable_tagging and self.tag_to_context is not None:
                self.tag_to_context.clear()
            self.tool_result_facts.clear()

        self.context_mode = normalize_context_mode(snapshot.context_mode)
        self.retrieval_enabled = self.context_mode == "graph"
        self.enable_memory = snapshot.enable_memory
        self.enable_tagging = bool(snapshot.enable_tagging and self.retrieval_enabled)
        self.tag_to_context = {} if self.enable_tagging else None
        self.memory_list = list(snapshot.memories) if self.enable_memory else None
        self.tool_result_facts = [
            self._deserialize_tool_result_fact(item)
            for item in snapshot.tool_result_facts
            if isinstance(item, dict)
        ]

        self._apply_snapshot_contexts(snapshot.contexts)
        self.active_ids = stable_unique_ids(
            [
                context_id
                for context_id in snapshot.active_ids
                if context_id in self.context_timeline_dict
            ]
        )

        if self.context_timeline_dict:
            self.now_context_id = max(
                max(self.context_timeline_dict.keys()) + 1,
                snapshot.now_context_id,
            )
        else:
            self.now_context_id = max(1, snapshot.now_context_id)

        self._rebuild_indexes()
        return snapshot

    async def compress_tool_result(
        self,
        record: ToolExecutionRecord,
        *,
        tool_call_id: Optional[str] = None,
        temperature: float = 0.0,
    ) -> Optional[ToolResultFact]:
        """Compress one tool execution result into durable facts.

        Args:
            record: Tool execution record containing the tool name, arguments,
                and raw string result to compress.
            temperature: Sampling temperature used for the summarizer call.

        Returns:
            A compressed tool-result fact bundle, or ``None`` when the tool
            name is missing.
        """
        tool_name = str(record.name or "").strip()
        raw_result = str(record.result or "").strip()
        if not tool_name:
            return None

        if not raw_result:
            fact = ToolResultFact(
                tool_name=tool_name,
                summary="(empty result)",
                facts=["(empty result)"],
                evidence="",
                status="unknown",
                tool_call_id=tool_call_id,
                tags=sanitize_tags([tool_name]),
            )
            self.tool_result_facts.append(fact)
            return fact

        prompt = TOOL_RESULT_FACT_PROMPT.format(
            tool_name=tool_name,
            tool_call_id=tool_call_id or "",
            tool_result=raw_result,
        )
        response = await self.llm_handler.fetch(
            msg="",
            system_prompt=prompt,
            temperature=temperature,
        )
        payload = extract_first_json_object(response.content)

        status = "error" if raw_result.lower().startswith("error:") else "unknown"
        summary = ""
        facts: List[str] = []
        tags: List[str] = []

        if isinstance(payload, dict):
            raw_summary = payload.get("summary", "")
            if isinstance(raw_summary, str):
                summary = " ".join(raw_summary.split())[:200]

            raw_facts = payload.get("facts", [])
            if isinstance(raw_facts, list):
                for item in raw_facts:
                    if isinstance(item, str):
                        normalized = " ".join(item.split())
                        if normalized:
                            facts.append(normalized)

            raw_tags = payload.get("tags", [])
            if isinstance(raw_tags, list):
                tags = sanitize_tags([str(tag) for tag in raw_tags])

            raw_status = payload.get("status", status)
            if isinstance(raw_status, str):
                normalized_status = raw_status.strip().lower()
                if normalized_status in {"success", "error", "unknown"}:
                    status = normalized_status

        if not summary:
            summary = raw_result[:200]
            if len(raw_result) > 200:
                summary = summary[:197].rstrip() + "..."

        if not facts and summary:
            facts = [summary]

        if not tags:
            tags = sanitize_tags([tool_name])

        fact = ToolResultFact(
            tool_name=tool_name,
            summary=summary,
            facts=facts,
            evidence=raw_result,
            status=status,
            tool_call_id=tool_call_id,
            tags=tags,
        )
        self.tool_result_facts.append(fact)
        return fact

    async def compress_tool_result_records(
        self,
        records: List[ToolExecutionRecord],
        *,
        tool_call_ids: Optional[List[Optional[str]]] = None,
        temperature: float = 0.0,
    ) -> List[ToolResultFact]:
        """Compress a batch of tool execution results into facts.

        Args:
            records: Tool execution records to compress, in execution order.
            tool_call_ids: Optional provider tool-call ids aligned with
                ``records``; missing ids are stored as ``None``.
            temperature: Sampling temperature used for each compression call.

        Returns:
            A list of compressed fact bundles in the same order as ``records``.
        """
        compressed: List[ToolResultFact] = []
        ids = list(tool_call_ids or [])
        for index, record in enumerate(records):
            fact = await self.compress_tool_result(
                record,
                tool_call_id=ids[index] if index < len(ids) else None,
                temperature=temperature,
            )
            if fact is not None:
                compressed.append(fact)
        return compressed

    # ====================================================================
    # Tag System
    # 从这里，将开始标签化查询系统的构建。
    # 需要的东西：
    # - 标签化系统
    # - 标签查询系统（包括模糊匹配）
    # - 摘要索引系统
    # ====================================================================
    
    async def tagify_context(
        self, 
        context: LLMContext, 
        temperature: float = 0.0
    ) -> LLMContext:
        """
        为一个上下文历史加入标签（和摘要）。
        
        Notes:
            必须在允许标签化时才可使用。

        Args:
            context: 等待加标签的上下文。
        
        Returns:
            加好标签的上下文内容。
        """

        if not self.enable_tagging:
            return context

        tag_source_parts: List[str] = []
        if context.content.strip():
            tag_source_parts.append(context.content.strip())
        if context.content_reasoning:
            tag_source_parts.append(context.content_reasoning.strip())
        if context.tool_call_info:
            tag_source_parts.extend(context.tool_call_info)
        if context.tool_result_facts:
            tag_source_parts.extend(context.tool_result_facts)

        tag_source = "\n".join(part for part in tag_source_parts if part.strip())
        if not tag_source.strip():
            context.tags = []
            return context
        
        # 标签
        tags_and_abstracts: LLMOutput = await self.llm_handler.fetch(
            msg=tag_source, 
            system_prompt=TAGIFY_CONTEXT_PROMPT, 
            temperature=temperature
        )

        # 解析
        parsed_tags, abstract_msg = parse_tags_and_abstracts(
            tags_and_abstracts.content
        )

        context.tags = parsed_tags
        context.abstract_msg = abstract_msg
        

        return context
    
    async def find_context_by_tags(
        self,
        tags: List[str],
        blur: bool = False
    ) -> Optional[List[LLMInfo]]:
        """
        根据特定的标签，找到所有具有该标签的上下文信息。支持模糊查询。

        Args:
            tags: 待查标签
            bool: 是否使用模糊查询

        Returns:
            所有符合要求的上下文，包括原始内容和被压缩后内容。
        """
        if not self.retrieval_enabled:
            return None
        if not self.enable_tagging and not self.context_index.tag_exact_postings:
            return None

        matched_ids = self.context_index.candidate_tag_ids(tags, blur=blur)
        if not matched_ids:
            return None

        ordered_ids = sorted(
            context_id
            for context_id in matched_ids
            if context_id in self.context_timeline_dict
        )

        return [
            self.context_timeline_dict[context_id]
            for context_id in ordered_ids
        ]

    async def find_context_by_semantic(
        self,
        semantic_query: str,
        *,
        top_k: int = 8,
        include_raw: bool = True,
        include_compacted: bool = True,
    ) -> Optional[List[LLMInfo]]:
        """Find context entries by semantic vector similarity."""
        if not self.retrieval_enabled:
            return None

        matched_ids = self.semantic_index.search(
            semantic_query,
            top_k=top_k,
            include_raw=include_raw,
            include_compacted=include_compacted,
        )
        if not matched_ids:
            return None

        matched_items = [
            self.context_timeline_dict[context_id]
            for context_id in matched_ids
            if context_id in self.context_timeline_dict
        ]
        return matched_items or None

    async def find_context_by_summary(
        self,
        summary_query: str,
        blur: bool = True,
        include_raw: bool = False,
        include_compacted: bool = True,
    ) -> Optional[List[LLMInfo]]:
        """
        根据摘要文本、正文内容或语义相似度检索上下文。

        Args:
            summary_query: 待搜索的摘要关键词。
            blur: 是否模糊搜索。
            include_raw: 是否允许在原始上下文正文中检索。
            include_compacted: 是否允许在压缩摘要中检索。

        Returns:
            所有命中的上下文内容。
        """
        if not self.retrieval_enabled:
            return None
        normalized_query = self.context_index._normalize_text(summary_query)
        if blur:
            semantic_hits = await self.find_context_by_semantic(
                normalized_query,
                top_k=8,
                include_raw=include_raw,
                include_compacted=include_compacted,
            )
            if semantic_hits:
                return semantic_hits

        candidate_ids = self.context_index.candidate_text_ids(
            summary_query,
            include_raw=include_raw,
            include_compacted=include_compacted,
        )
        if not candidate_ids:
            return None

        matched_items: List[LLMInfo] = []
        for context_id in sorted(candidate_ids):
            entry = self.context_timeline_dict.get(context_id)
            if entry is None:
                continue

            target_text = self.context_index.normalized_text_by_id.get(context_id, "")
            if not target_text:
                continue

            is_match = (normalized_query in target_text) if blur else (normalized_query == target_text)
            if is_match:
                matched_items.append(entry)

        if not matched_items:
            return None

        return matched_items
    
    async def find_context_by_summary_and_tags(
        self,
        summary_query: str,
        tags: List[str],
        blur_summary: bool = True,
        blur_tags: bool = False,
    ) -> Optional[List[LLMInfo]]:
        """
        根据标签和摘要，从上下文内容里查询同时满足两种信号的条目。

        Notes:
            - 如果要多次搜索的话，时间复杂度可能高达 O(nn) - 检查是否已被修复。
            - 这是最小实现，且该实现表达的关系为 "AND"。

        Args:
            summary_query: 待搜索的摘要
            tags: 待搜索的标签
            blur_summary: 是否模糊搜索摘要
            blur_tags: 是否模糊搜索标签
        """
        # 如果不允许通过标签反查，通常是上下文模式选择为 graph
        if not self.retrieval_enabled:
            return None
        
        # 获取标签
        tag_ids = self.context_index.candidate_tag_ids(tags, blur=blur_tags)
        if not tag_ids:
            return None
        
        # 查询摘要
        used_semantic_summary = False
        if blur_summary:
            summary_ids = set(
                self.semantic_index.search(
                    summary_query,
                    top_k=max(8, len(tag_ids)),
                    include_raw=False,
                    include_compacted=True,
                    allowed_ids=tag_ids,
                )
            )
            used_semantic_summary = bool(summary_ids)
        else:
            summary_ids = self.context_index.candidate_text_ids(
                summary_query,
                include_raw=False,
                include_compacted=True,
            )
        if not summary_ids:
            summary_ids = set()
        if not summary_ids:
            return None

        intersected_ids = sorted(tag_ids & set(summary_ids))

        # 没东西
        if not intersected_ids:
            return None

        normalized_query = self.context_index._normalize_text(summary_query)
        matched_items: List[LLMInfo] = []
        for context_id in intersected_ids:
            entry = self.context_timeline_dict.get(context_id)
            if entry is None:
                continue
            if used_semantic_summary:
                matched_items.append(entry)
                continue

            target_text = self.context_index.normalized_text_by_id.get(context_id, "")
            if not target_text:
                continue
            if (normalized_query in target_text) if blur_summary else (normalized_query == target_text):
                matched_items.append(entry)

        if not matched_items:
            return None

        return matched_items

    def expand_retrieval_hit_ids(
        self,
        items: Optional[List[LLMInfo]],
        *,
        expand_compacted: bool = True,
        include_hit_id_for_compacted: bool = True,
    ) -> Optional[List[int]]:
        """Expand retrieval hits into prompt-selectable context timeline ids.
        本函数直接被 agent._retrieve_context_candidates_for_task 调用，用于从压缩后的内容中获取原始内容。

        Args:
            items: 在查询环节中被命中的条目。
            expand_compacted: 决定：从被摘要的内容里抽取 ID。
            include_hit_id_for_compacted: 压缩后的内容被选择时，是否保留压缩后的 id。

        Returns:
            在当前时间线内储存的、排序并去重后的目标 id 列表。
        """

        if not self.retrieval_enabled:
            return None

        # 如果没东西，返回 None
        if not items:
            return None
        
        # 获取 id
        expanded_ids: List[int] = []
        for item in items:    # 对于每一项内容
            # 如果是压缩后内容
            if isinstance(item, LLMContextCompacted):
                if include_hit_id_for_compacted and item.timeline in self.context_timeline_dict:    # 压缩后的内容被选择时，保留压缩后的 id
                    expanded_ids.append(item.timeline)
                
                # 如果允许扩展，此时：
                if expand_compacted:
                    # 对于每个源
                    for source_timeline in item.source_timeline:
                        # 如果源存在则加入
                        if source_timeline in self.context_timeline_dict:
                            expanded_ids.append(source_timeline)
                continue

            # 如果是原始内容，保证其真实存在即可
            if item.timeline in self.context_timeline_dict:
                expanded_ids.append(item.timeline)

        return stable_unique_ids(expanded_ids)

    def expand_active_selection_ids(
        self,
        context_ids: Optional[List[int]],
        *,
        expand_compacted_sources: bool = False,
        keep_compacted_entries: bool = True,
    ) -> List[int]:
        """Expand selected ids into an active-window-friendly id list.

        Args:
            context_ids: Context timeline ids chosen by the selector model.
            expand_compacted_sources: Whether selected compacted entries should
                also contribute their raw `source_timeline` ids. The default is
                `False` so the caller can keep compacted entries as-is when the
                summary is sufficient.
            keep_compacted_entries: Whether selected compacted entries should
                remain in the active window. When `False`, a selected compacted
                entry only contributes raw sources if expansion is enabled.

        Returns:
            A sorted de-duplicated list of valid timeline ids ready to be stored
            as the next active context window.
        """
        # Treat missing selections as an empty expansion so callers can reuse
        # the helper in fallback paths without extra branching.
        if not context_ids:
            return []

        expanded_ids: List[int] = []
        for context_id in context_ids:
            entry = self.context_timeline_dict.get(context_id)
            if entry is None:
                continue

            # Keep the selected compacted entry itself when requested so the
            # active window can preserve the concise summary representation.
            # This is the default path now; callers only opt into expansion
            # when they explicitly need the underlying raw provenance.
            if isinstance(entry, LLMContextCompacted):
                if keep_compacted_entries:
                    expanded_ids.append(entry.timeline)

                # Pull the compacted entry's flattened raw provenance back into
                # the active window only when the caller explicitly asks for it.
                if expand_compacted_sources:
                    for source_timeline in entry.source_timeline:
                        if source_timeline in self.context_timeline_dict:
                            expanded_ids.append(source_timeline)
                continue

            # Preserve raw selections directly because they already point at the
            # detailed context entries the model explicitly asked for.
            expanded_ids.append(entry.timeline)

        return stable_unique_ids(expanded_ids)

    def get_descendant_ids(self, context_id: int) -> Set[int]:
        """
        从目标（被压缩后的）上下文条目里，寻找所有原始信息条目。

        Args:
            context_id: 目标条目 ID。
        
        Returns:
            所有原始信息条目的 ID，但不包含输入的条目 ID。
        """
        # 确认当前需选择的条目是等待压缩的东西。
        entry = self.context_timeline_dict.get(context_id)
        if not isinstance(entry, LLMContextCompacted):
            return set()
        
        # 手动栈，迭代。
        descendants: Set[int] = set()
        stack: List[LLMInfo] = list(entry.source)

        # 先将本压缩后条目的所有后续条目入栈。
        for source_id in entry.source_timeline:
            if source_id in self.context_timeline_dict:
                descendants.add(source_id)
        
        # 然后开始。
        while stack:
            item = stack.pop()
            # 如果在
            if item.timeline in self.context_timeline_dict:
                descendants.add(item.timeline)
            # 如果要继续向下走，深度优先便利。
            if isinstance(item, LLMContextCompacted):
                for source_id in item.source_timeline:
                    if source_id in self.context_timeline_dict:
                        descendants.add(source_id)
                stack.extend(item.source)
        
        # 原始 ID 将不被包含。
        descendants.discard(context_id)
        return descendants

    def find_compacted_entries_by_source_ids(self, source_ids: List[int]) -> Optional[List[int]]:
        """Find compacted timeline ids that reference any supplied raw ids.
        这个函数的存在是何意味？？codex 到底为啥会整这个烂活？

        Args:
            source_ids: Raw timeline ids that may be represented by compacted
                summary entries elsewhere in the timeline store.

        Returns:
            A sorted list of compacted timeline ids whose `source_timeline`
            contains at least one of the supplied raw ids.
        """

        if not self.retrieval_enabled:
            return None

        matched_ids = self.context_index.compacted_ids_for_source_ids(source_ids)
        if not matched_ids:
            return None
        return sorted(matched_ids)

    
    
