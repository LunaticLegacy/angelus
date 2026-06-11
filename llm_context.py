import re
from dataclasses import dataclass
from typing import Dict, List, Literal, Optional, Set, Tuple

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
        self.context_index.clear()
        self.tag_to_context = {} if self.enable_tagging else None
        if self.retrieval_enabled:
            for context_id in sorted(self.context_timeline_dict):
                self.context_index.index_context(
                    self.context_timeline_dict[context_id],
                    tag_to_context=self.tag_to_context if self.enable_tagging else None,
                )

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
        基于关键词结合标签，查询上下文信息。

        Args:
            keywords: 关键字信息表达式，使用搜索引擎同款。
            mode: 
        """
        pass

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

    async def find_context_by_summary(
        self,
        summary_query: str,
        blur: bool = True,
        include_raw: bool = False,
        include_compacted: bool = True,
    ) -> Optional[List[LLMInfo]]:
        """
        根据摘要文本或正文内容检索上下文。

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
        candidate_ids = self.context_index.candidate_text_ids(
            summary_query,
            include_raw=include_raw,
            include_compacted=include_compacted,
        )
        if not candidate_ids:
            return None

        normalized_query = self.context_index._normalize_text(summary_query)
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
        根据标签和摘要，从被压缩后的上下文内容里，查询原始上下文。

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
        summary_ids = self.context_index.candidate_text_ids(
            summary_query,
            include_raw=False,
            include_compacted=True,
        )
        if not summary_ids:
            return None

        intersected_ids = sorted(tag_ids & summary_ids)

        # 没东西
        if not intersected_ids:
            return None

        normalized_query = self.context_index._normalize_text(summary_query)
        matched_items: List[LLMInfo] = []
        for context_id in intersected_ids:
            entry = self.context_timeline_dict.get(context_id)
            if entry is None:
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

    
    
