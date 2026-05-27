import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from .llm_fetcher import LLMFetcher, LLMOutput
from .prompt import (
    CONTEXT_COMPACT_PROMPT_TEMPLATE,
    MEMORY_CONCLUDE_PROMPT_TEMPLATE, 
    TAGIFY_CONTEXT_PROMPT
)
from .llm_types import LLMContext, LLMContextCompacted, LLMContextInfo, LLMInfo


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
        fallback_order: Optional[List[str]] = None,
        enable_memory: bool = True,
        enable_tagging: bool = False,
        compression_profile: Optional[ContextCompressionProfile] = None,
    ):
        """Initialize the context handler.

        Args:
            llm_handler: Fetcher used for compression, tagging, and memory
                generation requests.
            fallback_order: Optional backend preference order forwarded to the
                fetcher during helper LLM calls.
            enable_memory: Whether persistent memory summaries should be stored.
            enable_tagging: Whether tag-based retrieval indexes should be built.
            compression_profile: Default prompt profile used whenever context
                compression is requested without an explicit override.
        """
        self.llm_handler = llm_handler
        self.fallback_order = fallback_order
        self.compression_profile = compression_profile or ContextCompressionProfile()

        # ========== 基础索引 ==========
        # 索引：时间线 id -> 上下文对象。
        self.context_timeline_dict: Dict[int, LLMInfo] = {}

        # 当前激活的上下文时间线 id 列表。
        self.active_ids: List[int] = []

        # 本 agent 的时间线游标。
        self.now_context_id: int = 1

        # ========= 记忆机制 =========
        # 记忆不会被压缩。
        self.enable_memory = enable_memory
        self.memory_list: Optional[List[str]] = None
        if self.enable_memory:
            self.memory_list = []


        # ========= 标签索引和查询机制 ==========
        # k: tag: str 当前标签, v: List[int] 具有当前标签的信息
        # 标签具有不确定性
        self.enable_tagging = enable_tagging    # 启用标签功能
        self.tag_to_context: Optional[Dict[str, List[int]]] = None
        if self.enable_tagging:
            self.tag_to_context = {}

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

        if self.enable_tagging:
            self.tag_to_context.clear() # pyright: ignore

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
        
        # 去重
        self.active_ids = list(set(normalized_ids))
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
        
        context.timeline = self.now_context_id
        self.context_timeline_dict[self.now_context_id] = context
        self.now_context_id += 1

        if self.enable_tagging:
            await self.add_tag_index(context)

        # 加入当前活跃上下文窗口
        if append_to_active:
            self.append_active_ids(context)
        

    async def get_now_context(
        self,
        timeline_id_list: Optional[List[int]] = None,
    ) -> Optional[LLMContextInfo]:
        """
        获取上下文，以消息字典列表格式。
        TODO: 需要按时间线走。

        Args:
            timeline_id_list: 可选返回的上下文内容的时间线 id 列表。

        Notes:
            如果未指定，则返回当前被激活的上下文内容。
        """
        if self.empty:
            return None

        if timeline_id_list is None:
            # 获取当前被激活的上下文。
            selected_ids = self.get_active_ids_window()
        else:
            # 获取指定时间线的内容，保证存在。
            selected_ids = [
                timeline_id
                for timeline_id in timeline_id_list
                if timeline_id in self.context_timeline_dict
            ]

        # 保持时间线有序，从小到大。
        sorted_ids = sorted(selected_ids)

        info: List[LLMInfo] = []

        for context_id in sorted_ids:
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

    async def get_now_context_as_str(
        self,
        timeline_id_list: Optional[List[int]] = None,
    ) -> str:
        """
        获取当前上下文，以字符串格式。

        Args:
            timeline_id_list: 可选返回的上下文内容的时间线 id 列表。

        Returns:
            返回当前上下文，以单个字符串格式。如果为空则返回空字符串。
        """
        info = await self.get_now_context(timeline_id_list)
        if info is None:
            return ""

        return await self.transcribe_context_to_str(info)

    async def get_now_active_context_as_str(self) -> str:
        """
        Alias: 
            get_content_as_single_str()
        """
        return await self.get_now_context_as_str()
    

    async def compress_context(
        self,
        timeline_id_list: Optional[List[int]] = None,
        temperature: float = 0.3,
        compression_profile: Optional[ContextCompressionProfile] = None,
    ) -> bool:
        """
        压缩当前全部未压缩上下文，或压缩给定时间线 id 对应的条目。

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
        info: Optional[LLMContextInfo] = await self.get_now_context(target_ids)
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
            fallback_order=self.fallback_order,
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
        merged_tags: Set[str] = set()
        flattened_timeline: List[int] = []
        for item in source_items:
            if item.tags:
                merged_tags.update(item.tags)
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
            source_timeline=flattened_timeline,
            tags=sorted(merged_tags),
        )

        self.context_timeline_dict[compacted_id] = compacted_info
        self.now_context_id += 1

        if self.enable_tagging:
            await self.add_tag_index(compacted_info)
        
        # 然后更改激活上下文
        selected_id_set = set(target_ids)
        self.active_ids = [
            context_id
            for context_id in self.active_ids       # 在已有的被激活上下文里
            if context_id not in selected_id_set    # 剔除已选择的上下文
        ]
        self.active_ids.append(compacted_id)

        # 如果有压缩上下文
        if self.enable_tagging:
            await self.add_tag_index(compacted_info)

        return True

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
            msg=prompt,
            fallback_order=self.fallback_order,
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
        为一个上下文历史加入标签。

        Args:
            context: 等待加标签的上下文。
        
        Returns:
            加好标签的上下文内容。
        """

        tag_source_parts: List[str] = []
        if context.content.strip():
            tag_source_parts.append(context.content.strip())
        if context.tool_call_info:
            tag_source_parts.extend(context.tool_call_info)

        tag_source = "\n".join(part for part in tag_source_parts if part.strip())
        if not tag_source.strip():
            context.tags = []
            return context
        
        # 标签
        tags: LLMOutput = await self.llm_handler.fetch(
            msg=tag_source, 
            system_prompt=TAGIFY_CONTEXT_PROMPT, 
            temperature=temperature
        )
        parsed_tags = [
            tag
            for tag in re.findall(r"[a-zA-Z][a-zA-Z0-9_]{1,40}", tags.content.lower())
            if tag not in {"tag_1", "tag_2", "tag_3", "tag_4", "tag_5"}
        ]
        # 不要强制限定标签数。
        context.tags = parsed_tags
        return context
    
    async def add_tag_index(
        self,
        context: LLMInfo
    ) -> None:
        """
        将特定上下文的东西加入到标签反查表内。
        
        Args:
            context: 加入到标签反查表的上下文索引。
        """
        if not self.enable_tagging or self.tag_to_context == None:
            return

        tags: List[str] = context.tags or []
        for tag in tags:
            bucket = self.tag_to_context.setdefault(tag, [])
            if context.timeline not in bucket:
                bucket.append(context.timeline)

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
        if not self.enable_tagging or not self.tag_to_context:
            return None

        normalized_tags: List[str] = [
            tag.strip().lower()
            for tag in tags
            if isinstance(tag, str) and tag.strip()
        ]
        if not normalized_tags:
            return None
        
        # 寻找查找到的内容
        matched_ids: Set[int] = set()
        for query_tag in normalized_tags:
            # 支持模糊查询的场合
            if blur:
                for indexed_tag, context_ids in self.tag_to_context.items():
                    if query_tag in indexed_tag or indexed_tag in query_tag:
                        matched_ids.update(context_ids)
            else:
                matched_ids.update(self.tag_to_context.get(query_tag, []))
        
        # 如果没东西
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

        # Scan the timeline store in order and collect entries whose chosen text field matches the query.
        matched_items: List[LLMInfo] = []
        # 对全部上下文进行查找
        for context_id in sorted(self.context_timeline_dict.keys()):

            # Pick the searchable text from either the compacted abstract or the raw content payload.
            # 从上下文字典里抓一个东西
            entry: LLMInfo = self.context_timeline_dict[context_id]
            target_text: str = ""

            # 是否为压缩后的？
            if isinstance(entry, LLMContextCompacted):
                # 门控：在压缩后内容里检索
                if not include_compacted:
                    continue
                # 从压缩后的内容里检索摘要
                target_text = entry.abstract_msg
            else:
                # 门控：在原始内容里检索
                if not include_raw:
                    continue
                # 从原始内容里检索
                target_text = entry.content

            # Skip empty targets and then apply either substring matching or exact matching.
            if not target_text.strip():
                continue

            # 是否匹配？
            is_match = (summary_query in target_text) if blur else (summary_query == target_text)

            # 匹配的场合，直接加进去。
            if is_match:
                matched_items.append(entry)

        # Return None instead of an empty list so callers can treat "no hit" as a simple falsey branch.
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
            - 如果要多次搜索的话，时间复杂度可能高达 O(nn)
            - 这是最小实现，且该实现表达的关系为 "AND"。

        Args:
            summary_query: 待搜索的摘要
            tags: 待搜索的标签
            blur_summary: 是否模糊搜索摘要
            blur_tags: 是否模糊搜索标签
        """
        # Resolve the tag-side candidate set first so empty tag matches can short-circuit early.
        # 寻找：标签候选项
        tag_hits = await self.find_context_by_tags(tags=tags, blur=blur_tags)
        if not tag_hits:
            return None
        
        # 从摘要里寻找候选内容。
        summary_hits = await self.find_context_by_summary(
            summary_query=summary_query,
            blur=blur_summary,
            include_raw=False,
            include_compacted=True,
        )
        if not summary_hits:
            return None

        # 获取候选内容的 id，并进行交集运算
        tag_hit_ids: Set[int] = {item.timeline for item in tag_hits}
        summary_hit_ids: Set[int] = {item.timeline for item in summary_hits}
        intersected_ids = sorted(tag_hit_ids & summary_hit_ids)

        # 没东西
        if not intersected_ids:
            return None
        
        # 抓出这些内容
        return [
            self.context_timeline_dict[context_id]
            for context_id in intersected_ids
            if context_id in self.context_timeline_dict
        ]

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
            expand_compacted: 决定：压缩后的内容是否可被选择。
            include_hit_id_for_compacted: 压缩后的内容被选择时，是否保留压缩后的 id。

        Returns:
            在当前时间线内储存的、排序并去重后的目标 id 列表。
        """

        # 如果没东西，返回 None
        if not items:
            return None
        
        # 获取 id
        expanded_ids: Set[int] = set()
        for item in items:    # 对于每一项内容
            # 如果是压缩后内容
            if isinstance(item, LLMContextCompacted):
                if include_hit_id_for_compacted and item.timeline in self.context_timeline_dict:    # 压缩后的内容被选择时，保留压缩后的 id
                    expanded_ids.add(item.timeline)
                
                # 如果允许扩展，此时：
                if expand_compacted:
                    # 对于每个源
                    for source_timeline in item.source_timeline:
                        # 如果源存在则加入
                        if source_timeline in self.context_timeline_dict:
                            expanded_ids.add(source_timeline)
                continue

            # 如果是原始内容，保证其真实存在即可
            if item.timeline in self.context_timeline_dict:
                expanded_ids.add(item.timeline)

        return sorted(expanded_ids)

    def expand_active_selection_ids(
        self,
        context_ids: Optional[List[int]],
        *,
        expand_compacted_sources: bool = True,
        keep_compacted_entries: bool = True,
    ) -> List[int]:
        """Expand selected ids into an active-window-friendly id list.

        Args:
            context_ids: Context timeline ids chosen by the selector model.
            expand_compacted_sources: Whether selected compacted entries should
                also contribute their raw `source_timeline` ids.
            keep_compacted_entries: Whether selected compacted entries should
                remain in the active window together with their raw sources.

        Returns:
            A sorted de-duplicated list of valid timeline ids ready to be stored
            as the next active context window.
        """
        # Treat missing selections as an empty expansion so callers can reuse
        # the helper in fallback paths without extra branching.
        if not context_ids:
            return []

        expanded_ids: Set[int] = set()
        for context_id in context_ids:
            entry = self.context_timeline_dict.get(context_id)
            if entry is None:
                continue

            # Keep the selected compacted entry itself when requested so the
            # active window preserves the concise summary representation.
            if isinstance(entry, LLMContextCompacted):
                if keep_compacted_entries:
                    expanded_ids.add(entry.timeline)

                # Pull the compacted entry's flattened raw provenance back into
                # the active window so reverse indexing restores detailed text.
                if expand_compacted_sources:
                    for source_timeline in entry.source_timeline:
                        if source_timeline in self.context_timeline_dict:
                            expanded_ids.add(source_timeline)
                continue

            # Preserve raw selections directly because they already point at the
            # detailed context entries the model explicitly asked for.
            expanded_ids.add(entry.timeline)

        return sorted(expanded_ids)

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

        # 如果没东西，返回 None
        if not source_ids:
            return None
        
        # 创建一个 id 集合
        source_id_set = set(source_ids)
        matched_ids: List[int] = []

        # 在当前时间线内搜索压缩后的内容，然后组装时间线。
        for context_id, entry in self.context_timeline_dict.items():
            if not isinstance(entry, LLMContextCompacted):
                continue
            if source_id_set.intersection(entry.source_timeline):
                matched_ids.append(context_id)

        return sorted(matched_ids)

    
    
