from __future__ import annotations

import asyncio
import json
import re
import time
from types import CoroutineType
from typing import Any, Callable, Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field

from .llm_fetcher import LLMFetcher
from .llm_context import (
    ContextCompressionProfile,
    LLMContext,
    LLMContextCompacted,
    LLMContextHandler,
    LLMContextInfo,
)
from .tool_call_adapter import ToolCallSource, normalize_tool_calls
from .tool import Tool, ToolRegistry
from .tools.builtin_tools import create_builtin_tools

from .llm_types import (
    LLMInfo, MessageDict, Messages,
    ToolArgs, AssistantMessageDict,
    ToolList,
    AgentMessage,
    ToolExecutionRecord,
    LLMOutput,
    LLMToolCall,
    # 报错类型
    AgentExecutionError,
    EmptyModelResponseError,
    NoToolCallError,
    MaxTurnsExceededError
)

from .streamers import Streamer, ThinkColorStreamer

class Agent:
    def __init__(
        self,
        llm_handler: LLMFetcher,
        system_prompt: str,
        tools: Optional[ToolList] = None,
        max_concurrent_tools: int = 1,
        fallback_order: Optional[List[str]] = None,
        provider: str = "custom_json",
        round_compress_threshold: Optional[int] = None,
        round_compress_keep_tail: int = 6,
        context_selection_interval: Optional[int] = 3,
        context_selection_min_active_items: int = 4,
        context_selection_min_active_chars: int = 16384,
        tool_result_summary_threshold_chars: int = 8192,
        compression_profile: Optional[ContextCompressionProfile] = None,
    ):
        """
        初始化 Agent，绑定 LLM 处理器、系统提示词和可选工具列表。
        TODO: 再这么下去这傻逼东西迟早会成为一个超级类，可能不能再这么下去了。

        Args:
            llm_handler: 已有的LLM fetcher 实例。
            system_prompt: 基础的系统提示词。（如果要注入 skill，请自便）
            tools: 本 Agent 初始使用的工具。
            max_concurrent_tools: Max parallel tool executions
            fallback_order: Backend fallback order.（这个东西可以删掉，和下面的provider一起）
            provider: LLM provider for tool calling. 
                     Options: "openai", "anthropic", "custom_json"
            round_compress_threshold: Auto-compress temporary in-round messages when
                                      their count reaches this value. None or not set will disables it.

            round_compress_keep_tail: Number of latest in-round messages to keep verbatim.
            context_selection_interval: Trigger active-context reselection every N turns.
                                        Set to None or 0 to disable periodic reselection.
            context_selection_min_active_items: Minimum active item count before reselection can trigger.
            context_selection_min_active_chars: Minimum active-context char length before reselection can trigger.
            tool_result_summary_threshold_chars: Archive and summarize one round immediately
                                                 when tool results exceed this many chars.
            compression_profile: Default context-compression profile shared by
                                 automatic archiving and explicit compression calls.
        """
        self._base_system_prompt: str = system_prompt   # 系统提示词。
        self.llm_handler = llm_handler  # 用于处理 llm api 通信相关的东西。
        self.fallback_order = fallback_order
        self.compression_profile = compression_profile

        # 上下文管理器。
        self.llm_context_handler = LLMContextHandler(
            llm_handler=self.llm_handler,
            fallback_order=self.fallback_order,
            enable_memory=True,     # 启用记忆机制
            enable_tagging=True,    # 启用标签机制
            compression_profile=self.compression_profile,
        )
        self.tool_registry = ToolRegistry() # 注册工具。
        self.max_concurrent_tools = max_concurrent_tools    # 本 agent 最大可并发多少工具。
        self.provider = provider  # ← 保存 provider 设置
        self.round_compress_threshold = round_compress_threshold
        self.round_compress_keep_tail = round_compress_keep_tail
        self.context_selection_interval = context_selection_interval
        self.context_selection_min_active_items = context_selection_min_active_items
        self.context_selection_min_active_chars = context_selection_min_active_chars
        self.tool_result_summary_threshold_chars = tool_result_summary_threshold_chars

        # 工具调用历史
        self.tool_call_history: List[List[LLMToolCall]] = []

        # 注册内嵌工具，供 LLM 控制上下文信息
        self._register_builtin_tools()

        # 如果有工具，则对本内容注册工具。
        if tools:
            tool: Tool
            for tool in tools:
                self.tool_registry.register(tool)

    def _register_builtin_tools(self) -> None:
        """注册 Agent 内嵌的元工具，用于控制对话轮次的生命周期。"""
        for tool in create_builtin_tools(agent=self):
            self.tool_registry.register(tool)

    @property
    def system_prompt(self) -> str:
        """
        Dynamic system prompt enriched with tool descriptions.
        该函数会拼装系统提示词，和工具提示词。
        """
        prompt: str = self._base_system_prompt

        hint: Optional[str] = self.tool_registry.get_prompt_hint()  # 获取所有工具提示。
        if hint:
            prompt = f"{prompt}\n{hint}"    # 拼接提示，随后返回数据。
        return prompt
    
    @property
    def context_manager(self):
        """
        直接返回上下文管理器实例。
        """
        return self.llm_context_handler

    def update_system_prompt(self, new_prompt: str) -> None:
        """
        运行时动态修改 Agent 的系统提示词。
        
        Args:
            new_prompt: 系统提示词。
        """
        self._base_system_prompt = new_prompt

    def add_tool(self, tool: "Tool") -> None:
        """
        运行时给 Agent 增加一个工具。
        
        Args:
            tool: 一份有效的工具注册 schema。
        """
        self.tool_registry.register(tool)

    def remove_tool(self, tool_name: str) -> None:
        """
        在运行期间，从本 Agent 的工具注册表内，移除一个命名工具。
    
        Args:
            tool_name: 工具名。
        """
        self.tool_registry.unregister(tool_name)

    # ------------------------------------------------------------------
    # 上下文管理接口
    # DEPRECATED - 以后上下文管理将直接调用上下文管理器。
    # ------------------------------------------------------------------

    async def chat_once(
        self,
        msg: str,
        *,
        system_prompt: Optional[str] = None,
        temperature: float = 0.4,
        use_history: bool = True,
        use_tools: bool = False,
        save_context: bool = True,
        tag_context: bool = True,
    ) -> LLMOutput:
        """
        Execute exactly one LLM chat request.

        Use this for simple chat, debugging, tag/summarizer-style calls, or
        cases where the caller wants to inspect raw `LLMOutput.tool_calls`.
        """
        prev_message: Optional[List[LLMInfo]] = await self._build_prev_messages() if use_history else None
        tool_schemas = self.tool_registry.get_schemas_for_provider(self.provider) if use_tools else []

        resolved_system_prompt = system_prompt
        if resolved_system_prompt is None:
            resolved_system_prompt = self.system_prompt if use_tools else self._base_system_prompt

        output: LLMOutput = await self.llm_handler.fetch(
            msg=msg,
            system_prompt=resolved_system_prompt,
            temperature=temperature,
            prev_messages=prev_message if prev_message else None,
            tools=tool_schemas if tool_schemas else None,
            fallback_order=self.fallback_order,
        )

        resolved_tool_calls = self._resolve_tool_calls(output)

        if save_context:
            tool_call_info = [str(tool_call.to_execution_format()) for tool_call in resolved_tool_calls]
            context = LLMContext(
                role=output.role or "assistant",
                content=output.text,
                tool_call_info=tool_call_info,
            )
            if tag_context:
                context = await self.llm_context_handler.tagify_context(context)
            await self.llm_context_handler.add_context(context)

        return output


    async def run_agent_round(
        self,
        msg: str,
        streamer: Optional[Streamer | Callable[[str], int | None]] = lambda x: print(x, end="", flush=True),
        verbose_info: bool = False,
        max_turns: int = 8,
        max_context_size: int = 131072,
        temperature: float = 0.4,
        max_tokens: int = 4096,
        stop_callback: Optional[Callable[[], bool]] = None,
    ) -> str:
        """
        进行一整个轮次的 Agent 执行轮。

        核心特性：
        - 多轮工具调用循环：LLM 可在一次 agent 轮内连续调用多个工具，
          拿到结果后继续思考，直到决定结束。
        - 保留每轮 content：assistant 的原始回复与工具 JSON 都会保留。
        - round_end：LLM 可通过 JSON tool call 主动结束本轮。
        - 并行执行：当 max_concurrent_tools > 1 时，同一轮内的多个工具调用会并发执行。
        - 支持多种 LLM provider（OpenAI, Anthropic, custom JSON）

        Args:
            msg: 本 agent 的本次输入。
            streamer: 流式输出的处理器，如果无处理器则默认正常颜色输出。
            verbose_info: 为 True 时，打印每轮调用、tool_calls、结果等调试信息。
            max_turns: 最大轮次上限。
            temperature: 采样温度，透传给底层 LLM 请求。
            max_tokens: 最大输出 token 数，透传给底层 LLM 请求。
            stop_callback: 可选，用于确定是否停止运行的回调函数。该函数返回 True 时则停止执行。

        Returns:
            LLM 生成的完整回复文本。
        """
        # TODO: 为防止每一个轮次开始时都重新调度上下文，需要缓存一些东西。

        tool_schemas = self.tool_registry.get_schemas_for_provider(self.provider)   # 拉取工具调用方法
        final_content: str = ""

        # 在整个 agent 执行轮开始前，加入用户当前输入。
        await self.context_manager.add_context(
            LLMContext(
                role="user",
                timeline=0,
                content=msg, 
                tags=["user_request"]), 
            append_to_active=True
        )

        # 规定一个应当停止的东西。
        def _should_stop() -> bool:
            return bool(stop_callback and stop_callback())

        turn: int = 0
        # 轮次开始。
        while turn < max_turns:
            turn += 1
            if _should_stop():
                break

            # TODO: 这里每一次都会重新 build 一次旧信息。
            # 如果我要采用线性上下文，我只需要增量。
            # 如果我要让 agent 自己控制上下文，我要怎么做？？

            # 在每一轮开始时，决定本轮使用的上下文……？
            await self._maybe_run_context_selection(
                task_msg=msg,
                turn=turn,
                verbose_info=verbose_info,
                temperature=temperature
            )

            prev_messages: Optional[List[LLMInfo]] = await self._build_prev_messages()

            if verbose_info:
                print(f"\n[Agent] ====== Executing Turn: {turn} ======")
                print(f"[Agent] Provider: {self.provider}")
                print(f"[Agent] Tool schemas count: {len(tool_schemas)}")
                print(f"[Agent] Current context length: {self.llm_context_handler.context_len()} / {max_context_size}")

            if _should_stop():
                break

            # ---- 调用 LLM - 这里采用异步执行 ----
            response: LLMOutput = await self.llm_handler.fetch(
                msg=msg,
                system_prompt=self.system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                prev_messages=prev_messages if prev_messages else None,  # 这东西又是个 optional，我类型是对的，估计是插件bug
                tools=tool_schemas if tool_schemas else None,  # 传递工具信息
                fallback_order=self.fallback_order,
            )

            # 然后查看工具内容，如果有工具的话。
            message: str = response.text
            tool_calls: List[LLMToolCall] = self._resolve_tool_calls(response)
            executing_tools: List[CoroutineType] = []
            executing_result: List[str] = []
            if verbose_info:            
                print(f"\n[Agent] Message output: \n{message}")
                print(f"[Agent] Parsed tool calls: {len(tool_calls)}")
                if tool_calls:
                    for idx, tool in enumerate(tool_calls, start=1):
                        print(f"[Agent] Tool call {idx}: {tool.to_execution_format()}")

            if len(tool_calls) > 0:
                # 工具可并行。todo: 工具执行最大并发量限制未能使用。（后面再做，现在先改上下文）
                for tool in tool_calls:
                    executing_tools.append(
                        self._execute_single_tool(
                            tool_call=tool.to_execution_format(), 
                            verbose=verbose_info
                        )
                    )
                # 然后等待
                executing_result = await asyncio.gather(*executing_tools)

            if _should_stop():
                final_content = final_content or response.text
                break

            # 将工具执行结果放进来。
            # 这一块东西不会进入上下文，而是被 agent 实例自己记录。
            tool_record_round: List[ToolExecutionRecord] = [
                ToolExecutionRecord(
                    name=tool_info.name,
                    arguments=tool_info.arguments,
                    result=tool_result
                ) for (tool_info, tool_result) in zip(tool_calls, executing_result)
            ]
            self.tool_call_history.append(tool_calls)

            # 拼接上下文。
            # 这里才会包括工具。
            now_assistant_context: LLMContext = LLMContext(
                role="assistant",
                content=message,  # 文本
                tool_call_info=[str(i) for i in tool_record_round],
            )

            # 然后将其加入自身上下文中。注意：加入新的上下文后，激活上下文窗口也需要变。
            # 先打标签，再加进来。
            now_assistant_context = await self.llm_context_handler.tagify_context(now_assistant_context, temperature)
            await self.llm_context_handler.add_context(now_assistant_context, append_to_active=True)  # 添加到当前上下文中，并加入到当前激活上下文窗口内。
            await self._maybe_archive_long_round_context(   # 检测长轮次上下文，并压缩之。
                context=now_assistant_context,
                verbose_info=verbose_info,
            )

            if verbose_info:
                print(f"[Agent] Current active context IDs: {self.llm_context_handler.active_ids}")
                print(f"[Agent] Tag to Context index: {self.llm_context_handler.tag_to_context}")

            # 检测上下文长度，并压缩之。
            if self.llm_context_handler.context_len() > max_context_size:
                print(f"[Agent] Current context length: {self.llm_context_handler.context_len()} / {max_context_size}")
                print(f"[Agent] Context exceeded, compressing history...")
                while self.llm_context_handler.context_len() > max_context_size:
                    compressed = await self._archive_old_active_context(verbose_info=verbose_info)
                    if not compressed:
                        break

            # 判断是否结束？
            # 传统：如果没有 tool call，则立即结束。
            if len(tool_record_round) == 0:
                final_content = message
                break
            if _should_stop():
                final_content = final_content or response.text
                break

        else:
            raise MaxTurnsExceededError(f"Agent round exceeded max_turns={max_turns}.")

        return final_content
    
    
    # ------------------------------------------------------------------
    # 内部辅助方法
    # ------------------------------------------------------------------

    async def _maybe_run_context_selection(
        self,
        task_msg: str,
        turn: int,
        verbose_info: bool = False,
        temperature: float = 0.4,
    ) -> None:
        """Ask the model to reseat the active context window for one turn.

        Notes:
            This hook runs at the beginning of selected turns. It first retrieves
            a smaller candidate pool, then asks the model to choose the minimum
            sufficient subset from that pool only.

        Args:
            task_msg: User-visible task text for the current round.
            turn: One-based turn number inside the current agent round.
            verbose_info: Whether diagnostic messages should be printed.
            temperature: Sampling temperature used by helper model calls.

        Returns:
            The applied active context ids when reselection succeeds, otherwise
            `None` when reselection is skipped or rejected.
        """
        # 决定：是否执行上下文选择？
        if not self._should_trigger_context_selection(turn):
            return None

        # 寻找满足用户当前输入的备选 id
        candidate_ids = await self._retrieve_context_candidates_for_task(
            task_msg=task_msg,
            temperature=temperature,
        )
        print(f"[Agent] Context selection found {len(candidate_ids)} candidates: {candidate_ids}")
        if not candidate_ids:
            if verbose_info:
                print("[Agent] Context selection found no retrieval candidates; keeping current active window.")
            return None

        # 如果找不到目标上下文的 id
        context_listing = await self.llm_context_handler.get_now_context_as_str(candidate_ids)
        if not context_listing.strip():
            if verbose_info:
                print("[Agent] Candidate context listing is empty; keeping current active window.")
            return None

        # 建立一个 prompt，用于确定上下文窗口。
        # 这块的 prompt 可能吃了上下文注入，以至于这东西直接变成了第二个解题器。
        selection_prompt = f"""
You are selecting the best active context window for the current agent round.

Current task:
{task_msg}

Available context entries:
{context_listing}

Return only strict JSON in this format:
{{"ids": [1, 2, 3]}}

Rules:
- Select only the ids needed for the current task.
- The selection SHOULD contain the previous essential data for the current task. Like: codes, logs, etc.
- You may select raw entries, compacted entries, or both.
- Do not explain.
""".strip()

        if verbose_info:
            print(f"[Agent] Triggering periodic context selection at turn {turn}.")
        
        # 在这里直接和 agent 进行聊天，并对话。
        selection_output = await self.chat_once(
            selection_prompt,
            temperature=temperature,
            use_history=False,
            use_tools=False,
            save_context=False,
            tag_context=False,
        )

        # 解析来自 agent 的选择结果。
        selected_ids = self._parse_selection_timelines(selection_output.text)
        if verbose_info:
            print(f"[Agent] Original selection output as: {selection_output.text}")
            print(f"[Agent] Selection output as: {selected_ids}")

        if not selected_ids:
            if verbose_info:
                print("[Agent] Context selection returned no valid ids; keeping current active window.")
            return None

        # 过滤掉所有不在备选 id 范围内的 id
        # # 不过滤了，直接试试看
        # valid_candidate_ids = set(candidate_ids)
        # filtered_ids = [
        #     context_id
        #     for context_id in selected_ids
        #     if context_id in valid_candidate_ids
        # ]
        # if not filtered_ids:
        #     if verbose_info:
        #         print("[Agent] Context selection returned ids outside candidates; keeping current active window.")
        #     return None

        # 然后展开这些 id
        expanded_selected_ids = self.llm_context_handler.expand_active_selection_ids(
            selected_ids,
            expand_compacted_sources=True,
            keep_compacted_entries=True,
        )
        if not expanded_selected_ids:
            if verbose_info:
                print("[Agent] Expanded active selection is empty; keeping current active window.")
            return None

        # Preserve the newest active tail so the agent keeps immediate local
        # continuity even when the selector picks an older history slice.
        recent_tail_ids = self.llm_context_handler.get_active_ids_window()[-2:]
        final_ids = sorted(set(expanded_selected_ids + recent_tail_ids)) 

        # 设置激活的上下文 id
        applied_ids = self.llm_context_handler.set_active_ids(final_ids)

        if verbose_info:
            print(f"[Agent] Active context window updated to: {applied_ids}")

    async def _retrieve_context_candidates_for_task(
        self,
        task_msg: str,
        temperature: float = 0.4,
        recent_tail_len: int = 4,
    ) -> List[int]:
        """Retrieve prompt-selectable context ids for the current task.

        Args:
            task_msg: User-visible task text for the current round.
            temperature: Sampling temperature used by helper tagging calls.
            recent_tail_len: Number of recent active context ids to preserve.

        Returns:
            A sorted candidate id list containing any expanded retrieval hits and
            a recent active tail preserved for local continuity.
        """

        # 选择最后若干轮的上下文表示当前进度
        active_ids: List[int] = self.llm_context_handler.get_active_ids_window()
        recent_tail_ids = active_ids[-recent_tail_len:]

        # 将用户的输入转为上下文，然后标签化
        task_tags: List[str] = []
        if self.llm_context_handler.enable_tagging:
            # 创建用户的上下文，并自动标签化
            # TODO: 这个代码快好像可以直接缓存以避免重新计算……
            probe_context = LLMContext(role="user", content=task_msg)
            probe_context = await self.llm_context_handler.tagify_context(
                probe_context,
                temperature=temperature,
            )
            task_tags = probe_context.tags or []

        # 寻找同时满足输入标签和输入摘要的索引。
        intersected_hits: Optional[List[LLMInfo]] = None
        if task_tags:
            intersected_hits = await self.llm_context_handler.find_context_by_summary_and_tags(
                summary_query=task_msg,
                tags=task_tags,
                blur_summary=True,
                blur_tags=True,
            )
        
        # 然后分别查询标签和摘要。
        # 标签
        tag_hits = None
        if task_tags:
            tag_hits: Optional[List[LLMInfo]] = await self.llm_context_handler.find_context_by_tags(
                tags=task_tags,
                blur=True,
            )
        # 摘要
        summary_hits: Optional[List[LLMInfo]] = await self.llm_context_handler.find_context_by_summary(
            summary_query=task_msg,
            blur=True,
            include_raw=False,
            include_compacted=True,
        )

        # Expand compacted hits back into raw source timeline ids so summary
        # matches can re-open the original detailed context for selection.
        candidate_ids: Set[int] = set()
        if intersected_hits: # 如果找到交集内容
            intersect_id: Optional[List[int]] = self.llm_context_handler.expand_retrieval_hit_ids(intersected_hits)
            if intersect_id:
                candidate_ids.update(intersect_id)

        else:   # 没找到交集内容，则分别找
            if tag_hits:
                tag_hit_id: Optional[List[int]] = self.llm_context_handler.expand_retrieval_hit_ids(tag_hits)
                if tag_hit_id:
                    candidate_ids.update(tag_hit_id)
            if summary_hits:
                summary_hit_id: Optional[List[int]] = self.llm_context_handler.expand_retrieval_hit_ids(summary_hits)
                if summary_hit_id:
                    candidate_ids.update(summary_hit_id)
        
        # 然后添加最近几轮的上下文
        candidate_ids.update(recent_tail_ids)
        return sorted(candidate_ids)


    def _parse_selection_timelines(self, content: str) -> List[int]:
        """
        Extract selected context ids from a strict JSON response.
        
        Args:
            content: 输入的 JSON 内容，该内容会直接来自上下文选择器。
        """
        if not content.strip():
            return []

        candidates: List[str] = [content.strip()]
        candidates.extend(match.group(0) for match in re.finditer(r"\{.*?\}", content, flags=re.DOTALL))

        for candidate in candidates:
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            ids = payload.get("ids")
            if not isinstance(ids, list):
                ids = payload.get("timelines")
            if isinstance(ids, list):
                return [int(item) for item in ids]
        return []

    def _should_trigger_context_selection(self, turn: int) -> bool:
        """
        Determine whether the active context should be reselected this turn.

        Notes:
            1. 当前轮数是否满足间隔条件。
            2. 当前激活上下文数量是否满足最小阈值。
            3. 当前激活上下文字符总长度是否满足最小阈值。
            必须同时满足以上三个条件，才会重新进行选择。

        Args:
            turn: 当前回合轮数。
        
        Returns:
            如果是 True，则表示需要重新选择上下文。
        """

        # 检查当前轮次
        interval = self.context_selection_interval
        if not interval or interval <= 0:   # 无间隔或间隔小于 0
            return False
        if turn % interval != 0:            # 不是间隔的轮次
            return False
        
        # 检查当前激活上下文数量
        active_ids = self.llm_context_handler.get_active_ids_window()
        if len(active_ids) < self.context_selection_min_active_items:   # 如果激活上下文数量小于要求的最小阈值
            return False

        if self.llm_context_handler.context_len() < self.context_selection_min_active_chars:    # 如果激活上下文字符总长度小于最小阈值
            return False

        return True

    async def _maybe_archive_long_round_context(
        self,
        context: LLMContext,
        verbose_info: bool = False,
    ) -> bool:
        """
        对于一些长度较长的东西，将其压缩并摘要。

        Args:
            context: 目标上下文信息。
            verbose_info: 是否打印信息。
        """
        tool_result_chars = sum(len(result) for result in context.tool_call_info or [])
        if tool_result_chars < self.tool_result_summary_threshold_chars:
            return False

        if context.timeline < 0:
            return False

        if verbose_info:
            print(
                "[Agent] Tool result payload exceeded threshold; archiving context ID "
                f"{context.timeline} ({tool_result_chars} chars)."
            )
        return await self.llm_context_handler.compress_context([context.timeline])

    async def _archive_old_active_context(
        self, verbose_info: bool = False
    ) -> bool:
        """
        Archive older active uncompacted entries while keeping a recent verbatim tail.

        The original entries remain addressable by their timeline ids through
        `context_read`, even after they leave the active window.
        """
        active_ids: List[int] = self.llm_context_handler.active_ids

        keep_tail = max(0, self.round_compress_keep_tail)
        
        if len(active_ids) > keep_tail:
            target_ids = active_ids[:-keep_tail] if keep_tail else active_ids
        elif active_ids:
            target_ids = [active_ids[0]]
        else:
            return False

        if not target_ids:
            return False

        if verbose_info:
            print(f"[Agent] Archiving active context ids: {target_ids}")

        return await self.llm_context_handler.compress_context(target_ids)

    async def _build_prev_messages(self) -> Optional[List[LLMInfo]]:
        """
        将历史内容导出，而非序列化，匹配 llmfetcher 的要求。

        Returns:
            上下文内容。如果没有上下文，则返回空白内容。
        """
        if self.llm_context_handler.empty:
            return None
        
        # 这部分已经被 llm_context 实现。
        history_msg_raw: Optional[LLMContextInfo] = await self.llm_context_handler.get_now_active_context()
        if not history_msg_raw:
            history_msg = []
        else:
            history_msg = history_msg_raw.items
        
        return history_msg
    
    # ====================================================================
    # Tool handlers
    # 这些函数会处理工具相关事务。
    # ====================================================================

    async def _execute_single_tool(self, tool_call: Dict[str, Any], verbose: bool) -> str:
        """
        执行一个工具，工具执行结果将异步返回。

        Args:
            tool_call: 一个 tool call 方法。
            verbose: 显示 tool call 信息。
        """
        tool_name: str = str(tool_call["tool"])
        args: ToolArgs = dict(tool_call.get("arguments") or {})

        if verbose:
            print(f"[Agent] Calling tool {tool_name} with param: {json.dumps(args, ensure_ascii=False)}")
        
        # 执行工具
        try:
            result = await self.tool_registry.execute(tool_name, args)
        except Exception as exc:
            result = f"Error: {exc}"

        if verbose:
            print(f"[Agent] Result of tool {tool_name} as: \n{str(result)}")

        return str(result)

    def _coerce_tool_arguments(self, value: Any) -> Dict[str, Any]:
        """
        Coerce tool arguments from dict/string/None into a dict.

        Args:
            value: tool call arguments.
        """
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    def _parse_custom_json_tool_calls(self, content: str) -> List[Dict[str, Any]]:
        """Parse tool calls embedded in a text response."""
        if not content:
            return []

        candidates: List[str] = []
        fenced_blocks = re.findall(r"```(?:json)?\s*(.*?)```", content, flags=re.IGNORECASE | re.DOTALL)
        candidates.extend(block.strip() for block in fenced_blocks if block.strip())

        xml_blocks = re.findall(r"<tool_call>\s*(.*?)\s*</tool_call>", content, flags=re.IGNORECASE | re.DOTALL)
        candidates.extend(block.strip() for block in xml_blocks if block.strip())

        xml_list_blocks = re.findall(r"<tool_calls>\s*(.*?)\s*</tool_calls>", content, flags=re.IGNORECASE | re.DOTALL)
        candidates.extend(block.strip() for block in xml_list_blocks if block.strip())

        stripped = content.strip()
        if stripped:
            candidates.append(stripped)

        parsed_calls: List[Dict[str, Any]] = []
        for candidate in candidates:
            parsed = self._try_parse_tool_payload(candidate)
            if parsed:
                parsed_calls.extend(parsed)

        for match in re.finditer(r"\{.*?\}", content, flags=re.DOTALL):
            parsed = self._try_parse_tool_payload(match.group(0))
            if parsed:
                parsed_calls.extend(parsed)

        deduped: List[Dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for item in parsed_calls:
            tool_name = str(item.get("tool", "")).strip()
            if not tool_name:
                continue
            arguments = item.get("arguments") or {}
            signature = (tool_name, json.dumps(arguments, sort_keys=True, ensure_ascii=False))
            if signature in seen:
                continue
            seen.add(signature)
            deduped.append({"tool": tool_name, "arguments": arguments})

        return deduped

    def _try_parse_tool_payload(self, text: str) -> List[Dict[str, Any]]:
        """Parse a JSON object or array into tool call dicts."""
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return []
        return self._normalize_tool_payload(payload)

    def _normalize_tool_payload(self, payload: Any) -> List[Dict[str, Any]]:
        """Normalize a parsed JSON payload into tool call dicts."""
        if isinstance(payload, dict):
            if "tool_calls" in payload and isinstance(payload["tool_calls"], list):
                normalized: List[Dict[str, Any]] = []
                for entry in payload["tool_calls"]:
                    normalized.extend(self._normalize_tool_payload(entry))
                return normalized

            tool_name = payload.get("tool", payload.get("name"))
            if tool_name:
                raw_arguments = payload.get("arguments", payload.get("input", {}))
                return [
                    {
                        "tool": str(tool_name),
                        "arguments": self._coerce_tool_arguments(raw_arguments),
                    }
                ]
            return []

        if isinstance(payload, list):
            normalized: List[Dict[str, Any]] = []
            for entry in payload:
                normalized.extend(self._normalize_tool_payload(entry))
            return normalized

        return []

    def _resolve_tool_calls(self, response: LLMOutput) -> List[LLMToolCall]:
        """Resolve tool calls from native outputs or custom JSON text."""
        if response.tool_calls:
            return response.tool_calls

        if self.provider not in {"custom_json", "openvino"}:
            return []

        normalized = normalize_tool_calls(
            response,
            source=ToolCallSource.CUSTOM_JSON,
            fallback_parser=self._parse_custom_json_tool_calls,
        )
        return [
            LLMToolCall(
                name=item.tool_name,
                arguments=item.arguments,
                call_id=item.call_id,
                source=item.source.value,
            )
            for item in normalized
        ]
