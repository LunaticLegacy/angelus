import asyncio
from dataclasses import dataclass, field
from re import NOFLAG
from typing import List, Dict, Optional, Tuple, Union, Set

from .llm_fetcher import LLMFetcher, LLMOutput
from .prompt import CONTEXT_COMPACT_PROMPT_TEMPLATE, MEMORY_CONCLUDE_PROMPT_TEMPLATE
from .llm_types import (
    LLMInfo, LLMContext, LLMContextCompacted,
    LLMContextValue, LLMContextCompactedValue,
    LLMCompactedContextInfoItem,
    LLMUncompactedContextInfoItem,
    LLMContextInfo
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
        fallback_order: Optional[List[str]] = None
    ):
        """
        初始化。

        Args:
            llm_handler: 传入的 LLM 实例内容。
            fallback_order: 可选的回退后端顺序列表。
        """
        self.llm_handler = llm_handler
        self.fallback_order = fallback_order

        # 用于保存以调度为单位的内容 - 分流一个压缩后的信息和一个压缩前的信息。
        self.context_raw_dict: Dict[int, LLMInfo] = {}  # 正查信息池
        self.context_raw_dict_reversed: Dict[int, int] = {}  # 反查信息池，根据对象 id 反查上下文 id
        # 理论上，不应该出现两份完全相同的 LLM 信息

        self.context_dict: Dict[int, LLMContext] = {}   # 全部的原始 llm 信息
        self.context_dict_uncompacted: Dict[int, LLMContext] = {}   # 尚未被压缩的信息
        self.context_dict_compacted: Dict[int, LLMContextCompacted] = {}   # 压缩结果


        # 保存一个特定的逆字典 - 根据特定的标签内容，对上下文 id 进行反查。
        self.reverse_tag_dict: Dict[str, Set[int]] = {}

        # ID - 上述信息用于保存内容时，公用同一个ID
        self.now_context_id: int = 0
    
    @property
    def empty(self) -> bool:
        if len(self.context_raw_dict.keys()) == 0 \
            and len(self.context_raw_dict_reversed.keys()) == 0 \
            and len(self.context_dict.keys()) == 0 \
            and len(self.context_dict_uncompacted.keys()) == 0 \
            and len(self.context_dict_compacted.keys()) == 0:
            return True
        return False

    
    def context_len(self) -> int:
        """
        返回上下文总字符长度。

        只统计当前活跃上下文：
        - 未压缩上下文的 role/content/tool 信息/tags
        - 压缩上下文的摘要/source_ids/tags

        不递归统计压缩摘要的 source 原文，否则压缩后长度不会下降。
        """

        def list_len(values: Optional[List[str]]) -> int:
            if not values:
                return 0
            return sum(len(str(value)) for value in values)

        total = 0

        for context in self.context_dict_uncompacted.values():
            total += len(context.role)
            total += len(context.content)
            total += list_len(context.tool_call_info)
            total += list_len(context.tool_call_result)
            total += list_len(context.tags)

        for context in self.context_dict_compacted.values():
            total += len(context.abstract_msg)
            total += list_len(context.source_ids)
            total += list_len(context.tags)

        return total

    async def add_context(
        self,
        context: LLMContext,
    ) -> None:
        """
        加入上下文内容，二选一。
        对于一个 Agent 而言，需要保存的信息里可不包含系统提示词。
    
        Args:
            context: 每次调度的信息。
        """
        # 维护一个正查和一个反查表。
        self.context_raw_dict[self.now_context_id] = context
        self.context_raw_dict_reversed[id(context)] = self.now_context_id
        

        self.context_dict[self.now_context_id] = context
        self.context_dict_uncompacted[self.now_context_id] = context    # 同时维护一个未压缩的东西

        # 时间线记录，并自增。
        self.now_context_id += 1

        # 如果具有标签，则将标签信息加入索引中
        if context.tags:
            for tag in context.tags:
                # 如果在键里没找到该键，则创建一个
                if tag not in self.reverse_tag_dict.keys():
                    self.reverse_tag_dict[tag] = set()
                # 反查id，并加入
                self.reverse_tag_dict[tag].add(self.context_raw_dict_reversed[id(context)])

    async def get_now_context(
        self, 
        id_list: Optional[List[int]] = None
    ) -> Optional[LLMContextInfo]:
        """
        获取当前上下文，以消息字典列表格式。
        TODO: 如果索引到被压缩后的上下文，这个会直接报keyerror - 加入对被压缩后的上下文的索引。
        
        Args:
            id_list: 可选返回的上下文内容，如果不填则默认返回全部上下文。

        Returns:
            按顺序排列的消息字典列表。对每一个元素，有如下：
                k: id, v: llminfo
            如果没有上下文内容，返回 None。
        """
        if not self.context_dict:   # 如果上下文字典是空白的
            return None

        compacted_info: List[LLMCompactedContextInfoItem] = []
        uncompacted_info: List[LLMUncompactedContextInfoItem] = []

        # 如果有索引值则保存一个信息
        added_info: Set[int] = set()

        if id_list is not None:
            id_list_set: Set[int] = set(id_list)    # 统一容器类型为 set

        # 先将压缩后的内容压进来，注意我需要压入的东西
        for entry_compacted in self.context_dict_compacted.values():
            context_id: int = self.context_raw_dict_reversed[id(entry_compacted)]
            # 如果满足id
            if id_list is not None:
                if context_id in id_list_set:
                    compacted_info.append(
                        LLMCompactedContextInfoItem(
                            context_id=context_id,
                            info=entry_compacted
                        )
                    )
            else:
                compacted_info.append(
                    LLMCompactedContextInfoItem(
                        context_id=context_id,
                        info=entry_compacted
                    )
                )

            added_info.add(context_id)


        # 再将没压缩的东西压进来
        for entry in self.context_dict_uncompacted.values():
            context_id: int = self.context_raw_dict_reversed[id(entry)]
            # 如果满足id
            if id_list is not None:
                if context_id in id_list_set:
                    uncompacted_info.append(
                        LLMUncompactedContextInfoItem(
                            context_id=context_id,
                            info=entry
                        )
                    )

            else:
                uncompacted_info.append(
                    LLMUncompactedContextInfoItem(
                        context_id=context_id,
                        info=entry
                    )
                )

            added_info.add(context_id)
        

        # 检查：如果当前列表不在全局信息池内，从储存原始信息的池里查找原始信息。
        if id_list is not None:
            lefting_ids: Set[int] = set(id_list) - set(added_info)
            for entry_all in self.context_dict.values():
                # 还剩多少个
                context_id: int = self.context_raw_dict_reversed[id(entry_all)]
                if context_id in lefting_ids:
                    uncompacted_info.append(
                        LLMUncompactedContextInfoItem(
                            context_id=context_id,
                            info=entry_all
                        )
                    )
                
        # 根据键进行排序，从小到大进行
        compacted_info.sort(key=lambda x: x.context_id)
        uncompacted_info.sort(key=lambda x: x.context_id)
        
        return LLMContextInfo(
            compacted_info=compacted_info,
            uncompacted_info=uncompacted_info
        )
    
    async def get_content_as_single_str(
        self, 
        id_list: Optional[List[int]] = None
    ) -> Optional[str]:
        """
        获取当前上下文，以单个字符串格式。每行一条内容。

        Args:
            id_list: 可选返回的上下文内容，如果不填则默认返回全部上下文。
        """
        messages: Optional[LLMContextInfo] = await self.get_now_context(id_list)
        if messages == None:
            return None

        compacted_info: List[LLMCompactedContextInfoItem] = messages.compacted_info
        uncompacted_info: List[LLMUncompactedContextInfoItem] = messages.uncompacted_info

        # 接下来需要将这个东西全部序列化了。
        # 已保证过，压缩和未压缩的代码部分，返回的东西都严格保证 schema。
        lines: List[str] = []
        for c_info in compacted_info:
            msg_str: str = f"""
            [Context (Compacted)]:
            Abstract info: {c_info.info.abstract_msg}
            Tag: {c_info.info.tags}
            This abstract is originally from messages with id: {c_info.context_id}.
            """
            lines.append(msg_str)


        for u_info in uncompacted_info:
            msg_str: str = f"""
            [Context (Uncompacted)]:
            Role: {u_info.info.role}
            Tag: {u_info.info.tags}
            Content: {u_info.info.content}
            """
            if not u_info.info.tool_call_info:
                msg_str_additional_tool: str = f"""
                This round does not contains any of tool call.
                """
            else:
                msg_str_additional_tool: str = f"""
                Called tools: {u_info.info.tool_call_info},
                Results: {u_info.info.tool_call_result}
                """
            msg_str += msg_str_additional_tool

            lines.append(msg_str)

        return "\n".join(lines)
    
    async def compress_context(self, id_list: Optional[List[int]] = None) -> bool:
        """
        压缩当前全部未压缩上下文，或给定压缩索引，将其压缩。

        Args:
            id_list: 可选压缩的上下文内容，如果不填则默认压缩未被压缩的上下文。
        """
        if not self.context_dict_uncompacted:
            return False

        # 1. 确定要压缩哪些 id
        if id_list is None:
            # 不指定的场合，要求所有内容都压缩
            target_ids = sorted(self.context_dict_uncompacted.keys())
        else:
            target_ids = [
                context_id
                for context_id in id_list
                if context_id in self.context_dict_uncompacted
            ]

        if not target_ids:
            return False

        # 2. 序列化目标上下文
        lines = await self.get_content_as_single_str(target_ids)
        if lines is None:
            return False

        prompt = CONTEXT_COMPACT_PROMPT_TEMPLATE.format(lines=lines)

        # 3. 请求 LLM 压缩
        response: LLMOutput = await self.llm_handler.fetch(
            msg=prompt,
            fallback_order=self.fallback_order,
        )
        compacted_text = response.content.strip()

        if not compacted_text:
            return False

        # 4. 收集源对象与 tags
        source_items: List[LLMContext] = [
            self.context_dict_uncompacted[context_id]
            for context_id in target_ids
        ]

        merged_tags: Set[str] = set()
        for item in source_items:
            if item.tags:
                merged_tags.update(item.tags)

        # 5. 创建压缩对象
        compacted_info = LLMContextCompacted(
            abstract_msg=compacted_text,
            source=source_items,       # pyright: ignore[reportArgumentType]
            source_ids=target_ids,
            tags=sorted(merged_tags),
        )

        # 6. 分配新 id
        compacted_id = self.now_context_id
        self.now_context_id += 1

        # 7. 注册到总池和压缩池
        self.context_raw_dict[compacted_id] = compacted_info
        self.context_raw_dict_reversed[id(compacted_info)] = compacted_id
        self.context_dict_compacted[compacted_id] = compacted_info

        # 8. 从未压缩 active 信息里移除源 id
        for context_id in target_ids:
            self.context_dict_uncompacted.pop(context_id, None)

        # 9. 给压缩摘要建立 tag 倒排索引
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
        if not self.context_dict:
            return None

        lines = await self.get_content_as_single_str(id_list)

        prompt = MEMORY_CONCLUDE_PROMPT_TEMPLATE.format(lines=lines)

        response = await self.llm_handler.fetch(msg=prompt, fallback_order=self.fallback_order)
        return response.content or None
