from typing import Dict, List, Optional, Set
from uuid import UUID

from .llm_fetcher import LLMFetcher, LLMOutput
from .prompt import CONTEXT_COMPACT_PROMPT_TEMPLATE, MEMORY_CONCLUDE_PROMPT_TEMPLATE
from .llm_types import (
    LLMInfo, LLMContext, LLMContextCompacted,
    LLMCompactedContextInfoItem,
    LLMUncompactedContextInfoItem,
    LLMContextInfo,
)


class LLMContextHandler:
    """
    用于处理 LLM 上下文内容的管理器，对每一个 agent 都要有一个实例。

    Notes:
        该类会在创建类 Agent 时自动为其创建，作为类实例。
    """

    def __init__(
        self,
        llm_handler: LLMFetcher,
        fallback_order: Optional[List[str]] = None,
    ):
        """
        初始化。

        Args:
            llm_handler: 传入的 LLM 实例内容。
            fallback_order: 可选的回退后端顺序列表。
        """
        self.llm_handler = llm_handler
        self.fallback_order = fallback_order

        # 时间线 id 到上下文对象。
        self.context_raw_dict: Dict[int, LLMInfo] = {}
        # UUID 索引，供 active_context 和外部引用使用。
        self.context_uuid_dict: Dict[UUID, LLMInfo] = {}
        self.context_uuid_to_timeline: Dict[UUID, int] = {}

        self.context_dict: Dict[int, LLMContext] = {}
        self.context_dict_uncompacted: Dict[int, LLMContext] = {}
        self.context_dict_compacted: Dict[int, LLMContextCompacted] = {}

        # 当前轮默认可取用的上下文窗口。
        self.active_context: List[UUID] = []

        # 根据标签反查上下文 timeline id。
        self.reverse_tag_dict: Dict[str, Set[int]] = {}

        # 全局时间线游标。
        self.now_context_id: int = 0

    @property
    def empty(self) -> bool:
        return not (
            self.context_raw_dict
            or self.context_uuid_dict
            or self.context_dict
            or self.context_dict_uncompacted
            or self.context_dict_compacted
        )

    def clear_memories(self) -> None:
        """清除所有上下文内容。"""
        self.context_raw_dict.clear()
        self.context_uuid_dict.clear()
        self.context_uuid_to_timeline.clear()
        self.context_dict.clear()
        self.context_dict_uncompacted.clear()
        self.context_dict_compacted.clear()
        self.active_context.clear()
        self.reverse_tag_dict.clear()
        self.now_context_id = 0

    def _ordered_active_uuids(self) -> List[UUID]:
        """Return active context UUIDs ordered by timeline."""
        return sorted(
            [context_uuid for context_uuid in self.active_context if context_uuid in self.context_uuid_to_timeline],
            key=lambda context_uuid: self.context_uuid_to_timeline[context_uuid],
        )

    def _ordered_active_ids(self) -> List[int]:
        """Return active context timeline ids ordered by timeline."""
        return [
            self.context_uuid_to_timeline[context_uuid]
            for context_uuid in self._ordered_active_uuids()
        ]

    def get_active_context(self) -> List[UUID]:
        """Return the UUID list for the current active context window."""
        return list(self._ordered_active_uuids())

    def get_active_context_ids(self) -> List[int]:
        """Return the timeline ids for the current active context window."""
        return list(self._ordered_active_ids())

    def set_active_context(self, context_uuids: Optional[List[UUID]] = None) -> None:
        """
        Replace the active context window.

        Args:
            context_uuids: UUIDs to activate. `None` means activate every known context
                           entry still present in the manager.
        """
        if context_uuids is None:
            context_uuids = list(self.context_uuid_to_timeline.keys())

        seen: Set[UUID] = set()
        normalized: List[UUID] = []
        for context_uuid in context_uuids:
            if context_uuid in seen or context_uuid not in self.context_uuid_to_timeline:
                continue
            seen.add(context_uuid)
            normalized.append(context_uuid)

        self.active_context = sorted(
            normalized,
            key=lambda context_uuid: self.context_uuid_to_timeline[context_uuid],
        )

    def set_active_context_by_ids(self, context_ids: Optional[List[int]] = None) -> List[int]:
        """
        Replace the active context window using timeline ids.

        Args:
            context_ids: Timeline ids to activate. `None` means activate every known
                         context entry still present in the manager.

        Returns:
            The normalized active timeline ids after selection.
        """
        if context_ids is None:
            selected_ids = sorted(self.context_raw_dict.keys())
        else:
            selected_ids = sorted(
                {
                    int(context_id)
                    for context_id in context_ids
                    if int(context_id) in self.context_raw_dict
                }
            )

        selected_uuids = [
            self.context_raw_dict[context_id].uuid
            for context_id in selected_ids
        ]
        self.set_active_context(selected_uuids)
        return self._ordered_active_ids()

    def context_len(self) -> int:
        """
        返回上下文总字符长度。

        只统计当前活跃上下文：
        - 未压缩上下文的 role/content/tool 信息/tags
        - 压缩上下文的摘要/source_uuid/source_timeline/tags

        不递归统计压缩摘要的 source 原文，否则压缩后长度不会下降。
        """

        def list_len(values: Optional[List[str]]) -> int:
            if not values:
                return 0
            return sum(len(str(value)) for value in values)

        total = 0
        active_uuid_set = set(self.active_context)

        for context in self.context_dict_uncompacted.values():
            if context.uuid not in active_uuid_set:
                continue
            total += len(context.role)
            total += len(context.content)
            total += list_len(context.tool_call_info)
            total += list_len(context.tool_call_result)
            total += list_len(context.tags)

        for context_comp in self.context_dict_compacted.values():
            if context_comp.uuid not in active_uuid_set:
                continue
            total += len(context_comp.abstract_msg)
            total += list_len([str(value) for value in context_comp.source_uuid])
            total += list_len([str(value) for value in context_comp.source_timeline])
            total += list_len(context_comp.tags)

        return total

    async def add_context(self, context: LLMContext) -> None:
        """
        加入上下文内容。

        Args:
            context: 每次调度的信息。
        """
        context.order = self.now_context_id

        self.context_raw_dict[self.now_context_id] = context
        self.context_uuid_dict[context.uuid] = context
        self.context_uuid_to_timeline[context.uuid] = self.now_context_id
        self.context_dict[self.now_context_id] = context
        self.context_dict_uncompacted[self.now_context_id] = context
        self.active_context.append(context.uuid)

        self.now_context_id += 1

        if context.tags:
            for tag in context.tags:
                self.reverse_tag_dict.setdefault(tag, set()).add(context.order)

    async def get_now_context(
        self,
        id_list: Optional[List[int]] = None,
    ) -> Optional[LLMContextInfo]:
        """
        获取当前上下文，以消息字典列表格式。

        Args:
            id_list: 可选返回的上下文内容，如果不填则默认返回全部上下文。
        """
        if not self.context_raw_dict:
            return None

        compacted_info: List[LLMCompactedContextInfoItem] = []
        uncompacted_info: List[LLMUncompactedContextInfoItem] = []
        added_info: Set[int] = set()
        id_list_set: Optional[Set[int]] = set(id_list) if id_list is not None else None

        for entry_compacted in self.context_dict_compacted.values():
            context_id = self.context_uuid_to_timeline[entry_compacted.uuid]
            if id_list_set is None or context_id in id_list_set:
                compacted_info.append(
                    LLMCompactedContextInfoItem(
                        context_id=context_id,
                        info=entry_compacted,
                    )
                )
            added_info.add(context_id)

        for entry in self.context_dict_uncompacted.values():
            context_id = self.context_uuid_to_timeline[entry.uuid]
            if id_list_set is None or context_id in id_list_set:
                uncompacted_info.append(
                    LLMUncompactedContextInfoItem(
                        context_id=context_id,
                        info=entry,
                    )
                )
            added_info.add(context_id)

        if id_list_set is not None:
            lefting_ids: Set[int] = set(id_list_set) - added_info
            for entry_all in self.context_dict.values():
                context_id = self.context_uuid_to_timeline[entry_all.uuid]
                if context_id in lefting_ids:
                    uncompacted_info.append(
                        LLMUncompactedContextInfoItem(
                            context_id=context_id,
                            info=entry_all,
                        )
                    )

        compacted_info.sort(key=lambda item: item.context_id)
        uncompacted_info.sort(key=lambda item: item.context_id)

        return LLMContextInfo(
            compacted_info=compacted_info,
            uncompacted_info=uncompacted_info,
        )

    async def get_active_context_info(self) -> Optional[LLMContextInfo]:
        """Return only the context entries currently marked active."""
        active_ids = self._ordered_active_ids()
        if not active_ids:
            return None
        return await self.get_now_context(active_ids)

    async def get_content_as_single_str(
        self,
        id_list: Optional[List[int]] = None,
    ) -> Optional[str]:
        """
        获取当前上下文，以单个字符串格式。每行一条内容。

        Args:
            id_list: 可选返回的上下文内容，如果不填则默认返回全部上下文。
        """
        messages = await self.get_now_context(id_list)
        if messages is None:
            return None

        lines: List[str] = []

        for c_info in messages.compacted_info:
            msg_str = f"""
            [Context (Compacted)]:
            ID: {c_info.context_id}
            UUID: {c_info.info.uuid}
            Abstract info: {c_info.info.abstract_msg}
            Tag: {c_info.info.tags}
            This abstract is originally from messages with uuid: {c_info.info.source_uuid}.
            This abstract is originally from messages with timeline id: {c_info.info.source_timeline}.
            """
            lines.append(msg_str)

        for u_info in messages.uncompacted_info:
            msg_str = f"""
            [Context (Uncompacted)]:
            ID: {u_info.context_id}
            UUID: {u_info.info.uuid}
            Role: {u_info.info.role}
            Tag: {u_info.info.tags}
            Content: {u_info.info.content}
            """

            if not u_info.info.tool_call_info:
                msg_str += """
                This round does not contains any of tool call.
                """
            else:
                msg_str += f"""
                Called tools: {u_info.info.tool_call_info},
                Results: {u_info.info.tool_call_result}
                """

            lines.append(msg_str)

        return "\n".join(lines)

    async def get_active_content_as_single_str(self) -> Optional[str]:
        """Serialize only the active context window."""
        active_ids = self._ordered_active_ids()
        if not active_ids:
            return None
        return await self.get_content_as_single_str(active_ids)

    async def compress_context(self, id_list: Optional[List[int]] = None) -> bool:
        """
        压缩当前全部未压缩上下文，或给定压缩索引并将其压缩。

        Args:
            id_list: 可选压缩的上下文内容，如果不填则默认压缩未被压缩的上下文。
        """
        if not self.context_dict_uncompacted:
            return False

        if id_list is None:
            target_ids = sorted(self.context_dict_uncompacted.keys())
        else:
            target_ids = [
                context_id
                for context_id in id_list
                if context_id in self.context_dict_uncompacted
            ]

        if not target_ids:
            return False

        lines = await self.get_content_as_single_str(target_ids)
        if lines is None:
            return False

        prompt = CONTEXT_COMPACT_PROMPT_TEMPLATE.format(lines=lines)
        response: LLMOutput = await self.llm_handler.fetch(
            msg=prompt,
            fallback_order=self.fallback_order,
        )
        compacted_text = response.content.strip()

        if not compacted_text:
            return False

        source_items: List[LLMContext] = [
            self.context_dict_uncompacted[context_id]
            for context_id in target_ids
        ]

        merged_tags: Set[str] = set()
        for item in source_items:
            if item.tags:
                merged_tags.update(item.tags)

        compacted_info = LLMContextCompacted(
            abstract_msg=compacted_text,
            source=source_items,       # pyright: ignore[reportArgumentType]
            source_uuid=[item.uuid for item in source_items],
            source_timeline=list(target_ids),
            tags=sorted(merged_tags),
        )

        compacted_id = self.now_context_id
        self.now_context_id += 1

        self.context_raw_dict[compacted_id] = compacted_info
        self.context_uuid_dict[compacted_info.uuid] = compacted_info
        self.context_uuid_to_timeline[compacted_info.uuid] = compacted_id
        self.context_dict_compacted[compacted_id] = compacted_info

        source_uuid_set = {item.uuid for item in source_items}
        self.active_context = [
            context_uuid
            for context_uuid in self.active_context
            if context_uuid not in source_uuid_set
        ]

        for context_id in target_ids:
            self.context_dict_uncompacted.pop(context_id, None)

        self.active_context.append(compacted_info.uuid)

        for tag in compacted_info.tags or []:
            self.reverse_tag_dict.setdefault(tag, set()).add(compacted_id)

        return True

    async def generate_memory(self, id_list: List[int]) -> Optional[str]:
        """
        将特定的上下文内容提取为短条内容。
        - 这是作为“记忆“的重要部分，记忆不会被格式化。

        Args:
            id_list: 目标上下文内容 id。
        """
        if not self.context_raw_dict:
            return None

        lines = await self.get_content_as_single_str(id_list)
        prompt = MEMORY_CONCLUDE_PROMPT_TEMPLATE.format(lines=lines)
        response = await self.llm_handler.fetch(msg=prompt, fallback_order=self.fallback_order)
        return response.content or None
