from __future__ import annotations

import asyncio
import json
import re
import time
from types import CoroutineType
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple, Set, Literal
from dataclasses import dataclass, field

from .llm_fetcher import LLMFetcher
from .llm_context import (
    ContextCompressionProfile,
    ContextMode,
    LLMContext,
    LLMContextCompacted,
    LLMContextHandler,
    LLMContextInfo,
    stable_unique_ids,
)
from .tool_call_adapter import ToolCallSource, normalize_tool_calls
from .tool import Tool, ToolRegistry
from .tools.builtin_tools import create_builtin_tools

from .llm_types import (
    LLMInfo, MessageDict, Messages,
    ToolArgs, AssistantMessageDict,
    ToolList,
    AgentMessage,
    AgentState,
    ToolExecutionRecord,
    LLMOutput,
    LLMToolCall,
    # 报错类型
    AgentExecutionError,
    EmptyModelResponseError,
    NoToolCallError,
    MaxTurnsExceededError, ToolResultRef,
    # 上下文管理
    ContextView,
    ContextSelectionView,
    ContextBundle
)

from .streamers import Streamer, ThinkColorStreamer


class Agent:
    def __init__(
        self,
        llm_handler: LLMFetcher,
        system_prompt: str,
        tools: Optional[List[Tool]] = None,
        max_concurrent_tools: int = 1,
        round_compress_threshold: Optional[int] = None,
        round_compress_keep_tail: int = 6,
        context_selection_interval: Optional[int] = 3,
        context_selection_min_active_items: int = 4,
        context_selection_min_active_chars: int = 16384,
        tool_result_summary_threshold_chars: int = 8192,
        compression_profile: Optional[ContextCompressionProfile] = None,
        context_mode: ContextMode = "linear",
    ):
        """
        初始化 Agent，绑定 LLM 处理器、系统提示词和可选工具列表。

        Args:
            llm_handler: 已有的 LLM fetcher 实例。
            system_prompt: 基础的系统提示词。（推荐在这里注入 skill）
            tools: 本 Agent 初始使用的工具。
            max_concurrent_tools: 工具并发最大数量。
            round_compress_threshold: 当有 N 轮未触发压缩上下文时，压缩上下文。
            round_compress_keep_tail: 当压缩上下文时，保留最后 N 轮信息。
            context_selection_interval: 仅当 context_mode = 'graph' 时有效。每 N 轮执行一次上下文选择。
            context_selection_min_active_items: 仅当 context_mode = 'graph' 时有效，决定触发上下文选择的最小项目数。
            context_selection_min_active_chars: 仅当 context_mode = 'graph' 时有效，决定触发上下文选择的最小字符数。
            tool_result_summary_threshold_chars: 仅当 context_mode = 'graph' 时有效，当工具返回结果长度超过此阈值时，将立即归档该工具信息，并总结此轮。
            compression_profile: Default context-compression profile shared by
                                 automatic archiving and explicit compression calls.
            context_mode: `linear` 将使用传统线性上下文机制， `graph` 模式下启用实验性上下文机制。
        """

        # 先初始化所有输入参数。
        self._base_system_prompt: str = system_prompt   # 系统提示词。
        self.llm_handler = llm_handler  # 用于处理 llm api 通信相关的东西。
        self.compression_profile = compression_profile
        self.max_concurrent_tools = max_concurrent_tools    # 本 agent 最大可并发多少工具。
        
        self.round_compress_threshold = round_compress_threshold
        self.round_compress_keep_tail = round_compress_keep_tail
        self.context_selection_interval = context_selection_interval
        self.context_selection_min_active_items = context_selection_min_active_items
        self.context_selection_min_active_chars = context_selection_min_active_chars
        self.tool_result_summary_threshold_chars = tool_result_summary_threshold_chars
        self.context_mode: ContextMode = context_mode if context_mode == "graph" else "linear"

        # 系统默认的 provider 和后端回退机制 - 这俩好像也可以删

        self.tool_registry = ToolRegistry() # 注册工具。
        self.agent_state = AgentState()     # 当前 agent 状态

        # 上下文管理器。
        self.llm_context_handler = LLMContextHandler(
            llm_handler=self.llm_handler,
            enable_memory=True,     # 启用记忆机制
            enable_tagging=self.context_mode == "graph",    # 图式上下文才启用检索标签
            compression_profile=self.compression_profile,
            context_mode=self.context_mode,
        )

        # 工具调用历史
        self.tool_call_history: List[List[LLMToolCall]] = []
        self._round_task_tags: Optional[List[str]] = None

        # 注册内嵌工具，供 LLM 控制上下文信息
        self._register_builtin_tools()

        # 如果有工具，则对本内容注册工具。
        if tools:
            tool: Tool
            for tool in tools:
                self.tool_registry.register(tool)

    def _register_builtin_tools(self) -> None:
        """
        注册 Agent 内嵌的元工具，用于控制对话轮次的生命周期。
        """
        for tool in create_builtin_tools(agent=self):
            self.tool_registry.register(tool)

    @property
    def system_prompt(self) -> str:
        """
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
        修改 Agent 的系统提示词。
        
        Args:
            new_prompt: 系统提示词。
        """
        self._base_system_prompt = new_prompt

    def set_system_prompt(self, new_prompt: str) -> None:
        """
        函数 `Agent.update_system_prompt` 的别名。
        """
        self.update_system_prompt(new_prompt)

    def add_tool(self, tool: Tool) -> None:
        """
        运行时给 Agent 增加一个工具。
        
        Args:
            tool: 一份有效的工具注册 schema。
        """
        self.tool_registry.register(tool)

    def remove_tool(self, tool_name: str) -> None:
        """
        从本 Agent 的工具注册表内，移除一个工具。
    
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

        建议在调试 agent 系统时使用本方法。
        """

        prev_message: Optional[List[LLMInfo]] = await self._build_prev_messages() if use_history else None

        request_tools = self.tool_registry.tools if use_tools else []

        resolved_system_prompt = system_prompt
        if resolved_system_prompt is None:
            resolved_system_prompt = self.system_prompt
        
        # 拉取本轮回复内容。
        output: LLMOutput = await self.llm_handler.fetch(
            msg=msg,
            system_prompt=resolved_system_prompt,
            temperature=temperature,
            prev_messages=prev_message if prev_message else None,
            tools=request_tools if request_tools else None,
        )

        # tool call 是模型无关的东西
        resolved_tool_calls = output.tool_calls

        # 如果需要保存上下文，则保存。（但是工具不执行）
        if save_context:
            tool_call_info = [str(tool_call.to_execution_format()) for tool_call in resolved_tool_calls]
            context = LLMContext(
                role=output.role or "assistant",    # pyright: ignore
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
        TODO: 这一个函数里压进去了太多屎山，需要拆解。

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

        request_tools = self.tool_registry.tools
        final_content: str = ""
        if not self.agent_state.task:
            self.agent_state.task = msg
        
        user_input_context: LLMContext = LLMContext(
            role="user",
            timeline=0,
            content=msg,
            tags=["user_request"]
        )

        self._round_task_tags = await self._cache_round_task_tags(
            user_input_context=user_input_context,
            temperature=temperature,
        )

        await self.context_manager.add_context(
            user_input_context,
            append_to_active=True
        )

        # 规定一个应当停止的东西。
        def _should_stop() -> bool:
            return bool(stop_callback and stop_callback())

        # 在整个 agent 执行轮开始前，加入用户当前输入。
        turn: int = 0
        # 轮次开始。
        while turn < max_turns:
            turn += 1
            if _should_stop():
                break

            # TODO: 这里每一次都会重新 build 一次旧信息。
            # 如果我要采用线性上下文，我只需要增量。
            # 如果我要让 agent 自己控制上下文，我要怎么做？？

            if self.context_mode == "graph":
                active_window_before_bundle = self.llm_context_handler.get_active_ids_window()

                # 在图式上下文模式下，为本次主模型调用构造显式上下文包。
                context_bundle = await self._build_main_context_bundle(
                    user_input_context=user_input_context,
                    turn=turn,
                    temperature=temperature,
                    verbose_info=verbose_info,
                )

                if verbose_info:
                    print(f"[Agent] Active window before graph bundle: {active_window_before_bundle}")
                    print(f"[Agent] Main context bundle ids: {context_bundle.ordered_ids()}")

                prev_messages: Optional[List[LLMInfo]] = await self._build_prev_messages(context_bundle)
            else:
                if verbose_info:
                    print(f"[Agent] Current active linear context IDs before agent round: {self.llm_context_handler.active_ids}")
                prev_messages = await self._build_prev_messages()

            if verbose_info:
                print(f"\n[Agent] ====== Executing Turn: {turn} ======")
                print(f"[Agent] Provider: {self.llm_handler.provider}")
                print(f"[Agent] Tool count: {len(request_tools)}")
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
                tools=request_tools if request_tools else None,  # 传递工具信息
            )

            # 然后查看工具内容，如果有工具的话。
            message: str = response.text    # 本轮文本
            
            # 现在的 tool call 被抽象为了当前包体的中间层（见类型 `LLMToolCall`），已和供应商无关
            tool_calls: List[LLMToolCall] = response.tool_calls

            executing_result: List[str] = await self._handle_tool_calls(tool_calls, verbose_info=verbose_info, max_concurrent_calls=self.max_concurrent_tools)

            # 记录本轮的信息？？
            self._record_assistant_round_in_state(message, tool_calls)

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
            if (self.context_mode == "graph"):
                now_assistant_context = await self.llm_context_handler.tagify_context(now_assistant_context, temperature)
                await self._maybe_archive_long_round_context(   # 检测长轮次上下文，并压缩之。
                    context=now_assistant_context,
                    verbose_info=verbose_info,
                )
            
            # 将信息加入当前上下文。
            await self.llm_context_handler.add_context(now_assistant_context, append_to_active=True)  # 添加到当前上下文中，并加入到当前激活上下文窗口内。

            if verbose_info:
                print(f"[Agent] Current active context IDs after agent round: {self.llm_context_handler.active_ids}")
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
    
    
    # ---------------
    # 上下文管理相关
    # 现在……到底要不要将它做成真正的图式上下文状态机？
    # ---------------

    async def _maybe_run_context_selection(
        self,
        user_input_context: LLMContext,
        turn: int,
        verbose_info: bool = False,
        temperature: float = 0.4,
    ) -> Optional[List[int]]:
        """Ask the model to reseat the active context window for one turn.
        TODO: 该类方法本身的方法论需要权衡，如果要用 llm 作为选择器，可能会太重。

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
        # 如果当前模式不是 graph，或当前的 llm_context_handler 不支持检索，则不返回。
        if self.context_mode != "graph" or not self.llm_context_handler.retrieval_enabled:
            return None

        # 决定：是否执行上下文选择？
        if not self._should_trigger_context_selection(turn):
            return None

        # 寻找满足用户当前输入的备选 id
        candidate_ids = await self._retrieve_context_candidates_for_task(
            user_input_context=user_input_context,
            temperature=temperature,
            recent_tail_len=self.round_compress_keep_tail   # TODO: 这里有争议，先标记上 todo 再说
        )
        if verbose_info:
            print(f"[Agent] Context selection found {len(candidate_ids)} candidates: {candidate_ids}")
        if not candidate_ids:
            if verbose_info:
                print("[Agent] Context selection found no retrieval candidates; keeping current active window.")
            return None

        # 如果找不到目标上下文的 id
        candidate_listing_ids = self._candidate_closure_ids(candidate_ids)
        context_listing = await self.llm_context_handler.get_now_context_as_str(
            candidate_listing_ids,
            preserve_order=True,
        )
        if not context_listing.strip():
            if verbose_info:
                print("[Agent] Candidate context listing is empty; keeping current active window.")
            return None

        # 建立一个 prompt，用于确定上下文窗口。
        # 这块的 prompt 可能吃了上下文注入，以至于这东西直接变成了第二个解题器。
        selection_prompt = f"""
You are selecting the best active context window for the current agent round.

Current task:
{user_input_context.content}

Available context entries:
{context_listing}

Return only strict JSON in this format:
{{"items": [
  {{"id": 12, "view": "raw", "reason": "need exact tool result"}},
  {{"id": 18, "view": "compacted", "reason": "summary is enough"}}
]}}

Rules:
- Select only the ids needed for the current task.
- Prefer compacted entries when the summary is sufficient.
- Select raw entries only when you need the original details that are not fully preserved in a compacted summary.
- You may choose descendants of listed compacted entries when exact original details are needed.
- You may select raw entries, compacted entries, or both, but avoid selecting both unless you truly need both representations.
- Backward-compatible {{"ids": [1, 2, 3]}} is accepted, but prefer the items format.
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
        selected_views = self._parse_selection_views(selection_output.text)
        selected_ids = [item.id for item in selected_views]
        if verbose_info:
            print(f"[Agent] Original selection output as: {selection_output.text}")
            print(f"[Agent] Selection output as: {selected_views}")

        if not selected_ids:
            if verbose_info:
                print("[Agent] Context selection returned no valid ids; keeping current active window.")
            return None

        allowed_ids = set(candidate_listing_ids)
        filtered_ids = [
            context_id
            for context_id in selected_ids
            if context_id in allowed_ids
        ]
        if not filtered_ids:
            if verbose_info:
                print("[Agent] Context selection returned ids outside candidates; keeping current active window.")
            return None

        # 归一化这些 id，但默认保留压缩条目本身，不强制展开成原文。
        normalized_selected_ids = self.llm_context_handler.expand_active_selection_ids(
            filtered_ids,
            expand_compacted_sources=False,
            keep_compacted_entries=True,
        )
        if not normalized_selected_ids:
            if verbose_info:
                print("[Agent] Normalized active selection is empty; keeping current active window.")
            return None

        applied_ids = self.llm_context_handler.set_active_ids(normalized_selected_ids)

        if verbose_info:
            print(f"[Agent] Active context cache updated to selected ids: {applied_ids}")

        return applied_ids

    async def _build_main_context_bundle(
        self,
        user_input_context: LLMContext,
        turn: int,
        temperature: float,
        verbose_info: bool = False,
    ) -> ContextBundle:
        """
        Build the explicit context bundle for one main LLM turn.
        
        Args:
            task_msg: 任务。（一般来自用户输入）
            turn: 当前轮数。
            temperature: 模型温度。
            verbose_info: 是否输出详细推理信息。
        """
        active_ids = self.llm_context_handler.get_active_ids_window()
        recent_tail_ids = stable_unique_ids(active_ids[-2:])
        selected_ids: List[int] = []

        # 选择 id
        maybe_selected_ids = await self._maybe_run_context_selection(
            user_input_context=user_input_context,
            turn=turn,
            verbose_info=verbose_info,
            temperature=temperature,
        )
        if maybe_selected_ids:
            selected_ids = stable_unique_ids(maybe_selected_ids)
        
        # 返回上下文包体。
        return ContextBundle(
            state_text=str(self.agent_state),   # 重载 str 方法实现
            selected_ids=selected_ids,
            recent_ids=recent_tail_ids,
        )

    def _candidate_closure_ids(self, candidate_ids: List[int]) -> List[int]:
        """
        Return candidates plus descendants of compacted candidates in stable order.
        """
        closure_ids: List[int] = []
        for context_id in candidate_ids:
            if context_id not in self.llm_context_handler.context_timeline_dict:
                continue
            closure_ids.append(context_id)
            entry = self.llm_context_handler.context_timeline_dict[context_id]
            if isinstance(entry, LLMContextCompacted):
                closure_ids.extend(sorted(self.llm_context_handler.get_descendant_ids(context_id)))
        return stable_unique_ids(closure_ids)

    async def _retrieve_context_candidates_for_task(
        self,
        user_input_context: LLMContext,
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

        if self.context_mode != "graph" or not self.llm_context_handler.retrieval_enabled:
            return []

        # 选择最后若干轮的上下文表示当前进度
        active_ids: List[int] = self.llm_context_handler.get_active_ids_window()
        recent_tail_ids = active_ids[-recent_tail_len:]

        # 将用户输入转为上下文标签；优先使用 round 开始时缓存好的结果。
        task_tags = await self._get_round_task_tags(user_input_context, temperature=temperature)

        # 寻找同时满足输入标签和输入摘要的索引。
        intersected_hits: Optional[List[LLMInfo]] = None
        if task_tags:
            intersected_hits = await self.llm_context_handler.find_context_by_summary_and_tags(
                summary_query=user_input_context.content,
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
            summary_query=user_input_context.content,
            blur=True,
            include_raw=False,
            include_compacted=True,
        )

        # Keep compacted hits compact by default; if the selector later needs
        # raw provenance, it can explicitly choose those raw ids.
        candidate_ids: List[int] = []
        if intersected_hits: # 如果找到交集内容
            intersect_id: Optional[List[int]] = self.llm_context_handler.expand_retrieval_hit_ids(intersected_hits)
            if intersect_id:
                candidate_ids.extend(intersect_id)

        else:   # 没找到交集内容，则分别找
            if tag_hits:
                tag_hit_id: Optional[List[int]] = self.llm_context_handler.expand_retrieval_hit_ids(tag_hits)
                if tag_hit_id:
                    candidate_ids.extend(tag_hit_id)
            if summary_hits:
                summary_hit_id: Optional[List[int]] = self.llm_context_handler.expand_retrieval_hit_ids(summary_hits)
                if summary_hit_id:
                    candidate_ids.extend(summary_hit_id)
        
        # 然后添加最近几轮的上下文
        candidate_ids.extend(recent_tail_ids)
        return stable_unique_ids(candidate_ids)

    async def _cache_round_task_tags(
        self,
        user_input_context: LLMContext,
        temperature: float = 0.4,
    ) -> List[str]:
        """Cache the current round's task tags before context selection begins."""
        if self.context_mode != "graph" or not self.llm_context_handler.enable_tagging:
            return []

        probe_context = await self.llm_context_handler.tagify_context(
            user_input_context,
            temperature=temperature,
        )
        return probe_context.tags or []

    async def _get_round_task_tags(
        self,
        user_input_context: LLMContext,
        temperature: float = 0.4,
    ) -> List[str]:
        """
        Return the cached task tags for the current round, computing them on demand if needed.
        TODO: 这个好像真可以用。
        """
        if self._round_task_tags is None:
            self._round_task_tags = await self._cache_round_task_tags(
                user_input_context=user_input_context,
                temperature=temperature,
            )
        return self._round_task_tags


    def _parse_selection_timelines(self, content: str) -> List[int]:
        """
        Extract selected context ids from a strict JSON response.
        
        Args:
            content: 输入的 JSON 内容，该内容会直接来自上下文选择器。
        """
        return [item.id for item in self._parse_selection_views(content)]

    def _parse_selection_views(self, content: str) -> List[ContextSelectionView]:
        """Extract selector choices from new `items` or legacy `ids` JSON."""
        if not content.strip():
            return []

        candidates: List[str] = [content.strip()]
        candidates.extend(match.group(0) for match in re.finditer(r"\{.*?\}", content, flags=re.DOTALL))

        for candidate in candidates:
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError:
                continue

            items = payload.get("items")
            if isinstance(items, list):
                parsed_items: List[ContextSelectionView] = []
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    try:
                        context_id = int(item.get("id"))
                    except (TypeError, ValueError):
                        continue
                    view_value = item.get("view", "raw")
                    view: ContextView = "compacted" if view_value == "compacted" else "raw"
                    reason = item.get("reason")
                    parsed_items.append(
                        ContextSelectionView(
                            id=context_id,
                            view=view,
                            reason=str(reason) if reason is not None else None,
                        )
                    )
                return parsed_items

            ids = payload.get("ids")
            if not isinstance(ids, list):
                ids = payload.get("timelines")
            if isinstance(ids, list):
                parsed_ids: List[ContextSelectionView] = []
                for item in ids:
                    try:
                        context_id = int(item)
                    except (TypeError, ValueError):
                        continue
                    entry = self.llm_context_handler.context_timeline_dict.get(context_id)
                    view: ContextView = "compacted" if isinstance(entry, LLMContextCompacted) else "raw"
                    parsed_ids.append(ContextSelectionView(id=context_id, view=view))
                return parsed_ids
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
        检查上下文信息，对于长度超标的上下文信息，进行压缩。

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

    async def _build_prev_messages(
        self,
        bundle: Optional[ContextBundle] = None,
    ) -> Optional[List[LLMInfo]]:
        """
        将历史内容导出，而非序列化，匹配 llmfetcher 的要求。

        Returns:
            上下文内容。如果没有上下文，则返回空白内容。
        """
        if self.llm_context_handler.empty and not (bundle and bundle.state_text.strip()):
            return None

        if bundle is not None:
            history_msg: List[LLMInfo] = []
            if bundle.state_text.strip():
                history_msg.append(
                    LLMContext(
                        role="user",
                        timeline=0,
                        content=bundle.state_text,
                        tags=["agent_state"],
                    )
                )

            ordered_ids = bundle.ordered_ids()
            if ordered_ids:
                context_info = await self.llm_context_handler.get_now_context(
                    ordered_ids,
                    preserve_order=True,
                )
                if context_info:
                    history_msg.extend(context_info.items)

            return history_msg or None
        
        # 这部分已经被 llm_context 实现。
        history_msg_raw: Optional[LLMContextInfo] = await self.llm_context_handler.get_now_active_context()
        if not history_msg_raw:
            history_msg = []
        else:
            history_msg = history_msg_raw.items
        
        return history_msg


    # ---------------------------
    # 状态机相关
    # 本段函数开始，将是 agent 状态机相关的处理器。
    # ---------------------------

    def _record_tool_round_in_state(
        self,
        tool_calls: List[LLMToolCall],
        executing_result: List[str],
    ) -> None:
        """Add concise tool execution facts to the persistent agent state."""
        if not tool_calls:
            return

        self.agent_state.phase = "tool_execution"
        for tool_call, result in zip(tool_calls, executing_result):
            result_text = str(result or "").replace("\n", " ").strip()
            if len(result_text) > 240:
                result_text = f"{result_text[:237]}..."
            fact = f"Executed {tool_call.name}: {result_text or '(empty result)'}"
            self._append_agent_state_item("facts", fact, limit=24)

            if result_text.lower().startswith("error:"):
                failed_action = f"{tool_call.name}({json.dumps(tool_call.arguments, ensure_ascii=False)})"
                self._append_agent_state_item("failed_actions", failed_action, limit=12)
                self._append_agent_state_item("do_not_repeat", failed_action, limit=12)

    def _record_assistant_round_in_state(
        self,
        message: str,
        tool_calls: List[LLMToolCall],
    ) -> None:
        """
        Record structured assistant state updates into the persistent Agent state.

        This method intentionally avoids natural-language chunking. It only
        consumes a structured JSON payload when the assistant emits one, then
        merges the payload into the existing AgentState schema.
        """
        text = str(message or "").strip()
        parsed_update = self._parse_agent_state_update(text) if text else None
        if parsed_update:
            self._apply_agent_state_update(parsed_update)

        if tool_calls:
            planned_tools = ", ".join(tool.name for tool in tool_calls)
            self._append_agent_state_item("next_actions", f"Call tools: {planned_tools}", limit=12)
            if not parsed_update or "phase" not in parsed_update:
                self.agent_state.phase = "reasoning"
        elif text:
            if not parsed_update or "phase" not in parsed_update:
                self.agent_state.phase = "answering"
        elif not parsed_update:
            # No structured update and no assistant text: keep the phase as-is.
            return

    def _parse_agent_state_update(self, text: str) -> Optional[Dict[str, Any]]:
        """Parse a structured AgentState update from assistant output."""
        if not text.strip():
            return None

        payload = self._load_json_object(text)
        if payload is None:
            return None

        if not isinstance(payload, dict):
            return None

        update = payload.get("state_updates")
        if isinstance(update, dict):
            payload = update

        normalized: Dict[str, Any] = {}
        for key in (
            "task",
            "phase",
            "facts",
            "key_facts",
            "hypotheses",
            "artifacts",
            "credentials",
            "known_routes",
            "failed_actions",
            "failed_attempts",
            "do_not_repeat",
            "next_actions",
        ):
            if key in payload:
                normalized[key] = payload[key]

        return normalized or None

    def _load_json_object(self, text: str) -> Optional[object]:
        """Load a JSON object from raw text or fenced JSON content."""
        candidate_texts = [text.strip()]
        fenced_blocks = re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
        candidate_texts.extend(block.strip() for block in fenced_blocks if block.strip())

        for candidate in candidate_texts:
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
        return None

    def _apply_agent_state_update(self, update: Mapping[str, Any]) -> None:
        """Merge a structured state update into the persistent AgentState."""
        task = update.get("task")
        if isinstance(task, str) and task.strip():
            self.agent_state.task = task.strip()

        phase = update.get("phase")
        if isinstance(phase, str) and phase.strip():
            self.agent_state.phase = phase.strip()

        list_field_map: Dict[str, str] = {
            "facts": "facts",
            "key_facts": "facts",
            "hypotheses": "hypotheses",
            "failed_actions": "failed_actions",
            "do_not_repeat": "do_not_repeat",
            "next_actions": "next_actions",
        }
        for source_field, target_field in list_field_map.items():
            values = update.get(source_field)
            if isinstance(values, list):
                for value in values:
                    if isinstance(value, str):
                        self._append_agent_state_item(target_field, value, limit=24 if target_field == "facts" else 12)
                    elif isinstance(value, dict):
                        self._append_agent_state_item(
                            target_field,
                            json.dumps(value, ensure_ascii=False, sort_keys=True),
                            limit=24 if target_field == "facts" else 12,
                        )

        failed_attempts = update.get("failed_attempts")
        if isinstance(failed_attempts, list):
            for item in failed_attempts:
                if not isinstance(item, dict):
                    continue
                action = str(item.get("action", "")).strip()
                reason = str(item.get("reason", "")).strip()
                evidence = str(item.get("evidence", "")).strip()
                summary_parts = [part for part in (action, reason, evidence) if part]
                if summary_parts:
                    failed_action = " | ".join(summary_parts)
                    self._append_agent_state_item("failed_actions", failed_action, limit=12)
                    self._append_agent_state_item("do_not_repeat", failed_action, limit=12)

        artifacts = update.get("artifacts")
        if isinstance(artifacts, dict):
            for key, value in artifacts.items():
                if not isinstance(key, str):
                    continue
                self.agent_state.artifacts[key] = str(value)
        elif isinstance(artifacts, list):
            for index, item in enumerate(artifacts, start=1):
                if not isinstance(item, dict):
                    continue
                artifact_key = str(item.get("path") or item.get("name") or item.get("id") or f"artifact_{index}")
                self.agent_state.artifacts[artifact_key] = json.dumps(item, ensure_ascii=False, sort_keys=True)

        credentials = update.get("credentials")
        if isinstance(credentials, list):
            for item in credentials:
                if isinstance(item, dict):
                    normalized = {str(key): str(value) for key, value in item.items()}
                    if normalized not in self.agent_state.credentials:
                        self.agent_state.credentials.append(normalized)

        known_routes = update.get("known_routes")
        if isinstance(known_routes, dict):
            for key, value in known_routes.items():
                if isinstance(key, str):
                    self.agent_state.known_routes[key] = str(value)

    def _append_agent_state_item(
        self, 
        field_name: str, 
        value: str, 
        *, 
        limit: int
    ) -> None:
        """
        Append a unique non-empty string to an AgentState list field.

        来了来了，codex 又开始霍霍 agent 状态了。
        TODO: 现在需要紧急明确 agent state schema 的内容，包括从提示词方面。
        TODO for TODO: 删掉所有这个函数。
        """
        normalized = " ".join(str(value or "").split())
        if not normalized:
            return
        target = getattr(self.agent_state, field_name)
        if normalized in target:
            return
        target.append(normalized)
        setattr(self.agent_state, field_name, target[-limit:])

    def _render_agent_state(self):
        """对一个旧接口的兼容：将 agent_state 转换成字符串。"""
        return str(self.agent_state)
    
    # ====================================================================
    # Tool handlers
    # 这些函数会处理工具相关事务。
    # ====================================================================

    async def _handle_tool_calls(
        self,
        tool_calls: List[LLMToolCall],
        verbose_info: bool = False,
        max_concurrent_calls: int = 1,
    ) -> List[str]:
        """
        同时执行多个工具，并返回工具调用结果。

        Args:
            tool_calls: 工具调用列表。
            verbose_info: 是否打印信息。
            max_concurrent_calls: 最大并发调用数。TODO: 未来补充本参数的用途。

        Returns:
            如果没有工具调用，则返回一个空列表。
        """
        executing_tools: List[CoroutineType] = []
        executing_result: List[str] = []
        if verbose_info:            
            print(f"[Agent] Parsed tool calls: {len(tool_calls)}")
            if tool_calls:
                for idx, tool in enumerate(tool_calls, start=1):
                    print(f"[Agent] Tool call {idx}: {tool.to_execution_format()}")

        if len(tool_calls) > 0:
            # 工具可并行。TODO: 工具执行最大并发量限制未能生效。（后面再做，现在先改上下文）
            for tool in tool_calls:
                executing_tools.append(
                    self._execute_single_tool(
                        tool_call=tool,
                        verbose=verbose_info
                    )
                )
            # 然后等待
            executing_result = await asyncio.gather(*executing_tools)
            self._record_tool_round_in_state(tool_calls, executing_result)
        return executing_result


    async def _execute_single_tool(
        self, 
        tool_call: LLMToolCall, 
        verbose: bool
    ) -> str:
        """
        执行一个工具，工具执行结果将异步返回。

        Args:
            tool_call: 一个 tool call 方法。
            verbose: 显示 tool call 信息。
        """

        # 解包工具调用信息
        tool_name: str = tool_call.name
        args: ToolArgs = tool_call.arguments or {}

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
