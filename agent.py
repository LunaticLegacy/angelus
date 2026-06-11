from __future__ import annotations

import asyncio
import json
import re
import time
from types import CoroutineType
from typing import Any, Callable, Dict, List, Optional, Tuple, Set, Literal
from dataclasses import asdict

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
from .tool_call_adapter import (
    parse_xml_tool_calls,
    strip_xml_tool_calls,
)
from .tool import Tool, ToolRegistry
from .tools.builtin_tools import create_builtin_tools

from .llm_types import (
    LLMInfo, MessageDict, Messages,
    ToolArgs, AssistantMessageDict,
    ToolList,
    AgentMessage,
    AgentState,
    AgentStateTurnEvent,
    AgentStateUpdate,
    ToolExecutionRecord,
    LLMOutput,
    LLMToolCall,
    # 报错类型
    AgentExecutionError,
    EmptyModelResponseError,
    NoToolCallError,
    MaxTurnsExceededError, ToolResultRef,
    ToolResultFact,
    # 上下文管理
    ContextView,
    ContextSelectionView,
    ContextBundle
)

from .prompt import CONTEXT_SELECTION_PROMPT_TEMPLATE, AGENT_STATE_MACHINE_SYSTEM_PROMPT

from .streamers import Streamer, ThinkColorStreamer
from .agent_state import AgentStateMachine


ORT_TOOL_CALL_CONTRACT = """
Tool calling contract:
- If the user explicitly asks you to use a tool, or the answer depends on current/local system information, call an available tool before answering.
- To call a tool, output exactly one tool call and no explanatory prose:
<tool_call>
{"name": "<tool_name>", "arguments": {<arguments_json>}}
</tool_call>
- After tool results are provided, use them to answer the user.
"""


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
        semantic_embedding_model: Optional[str] = None,
    ):
        """
        初始化 Agent，绑定 LLM 处理器、系统提示词和可选工具列表。

        Args:
            llm_handler: 已有的 LLM fetcher 实例。
            system_prompt: 基础的系统提示词。（推荐在这里注入 skill）
            tools: 本 Agent 初始使用的工具。
            max_concurrent_tools: 工具并发最大数量。
            round_compress_threshold: 当有 N 轮未触发压缩上下文时，压缩上下文。
            round_compress_keep_tail: 当压缩上下文时，保留最后 N 轮信息。在触发上下文选择的场合，也会保留最后 N 轮信息，作为近期信息。（TODO: 考虑将第二个职责分离到另一个 `Agent.__init__` 的参数里）
            context_selection_interval: 仅当 context_mode = 'graph' 时有效。每 N 轮执行一次上下文选择。
            context_selection_min_active_items: 仅当 context_mode = 'graph' 时有效，决定触发上下文选择的最小项目数。
            context_selection_min_active_chars: 仅当 context_mode = 'graph' 时有效，决定触发上下文选择的最小字符数。
            tool_result_summary_threshold_chars: 仅当 context_mode = 'graph' 时有效，当工具返回结果长度超过此阈值时，将立即归档该工具信息，并总结此轮。
            compression_profile: 决定在特定应用场景（或工作领域）内的上下文压缩配置，将被用于自动归档信息，以及显式上下文
            context_mode: `linear` 将使用传统线性上下文机制，`graph` 模式下启用实验性上下文机制。
            semantic_embedding_model: Optional sentence-transformers model name
                or local path used by the in-memory semantic context index.
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
        self.state_machine = AgentStateMachine(self.llm_handler)

        # 上下文管理器。
        self.llm_context_handler = LLMContextHandler(
            llm_handler=self.llm_handler,
            enable_memory=True,     # 启用记忆机制
            enable_tagging=self.context_mode == "graph",    # 图式上下文才启用检索标签
            compression_profile=self.compression_profile,
            context_mode=self.context_mode,
            semantic_embedding_model=semantic_embedding_model,
        )

        # 工具调用历史
        self.tool_call_history: List[List[LLMToolCall]] = []
        self.tool_call_result_history: List[List[str]] = []
        self._round_task_tags: Optional[List[str]] = None

        # 注册内嵌工具，供 LLM 控制上下文信息
        self._register_builtin_tools()

        # 如果有工具，则对本内容注册工具。
        if tools:
            tool: Tool
            for tool in tools:
                self.tool_registry.register(tool)

    @property
    def agent_state(self) -> AgentState:
        """Compatibility view of the state-machine snapshot."""
        return self.state_machine.state

    @agent_state.setter
    def agent_state(self, state: AgentState) -> None:
        """Replace the state-machine snapshot during restore/migration."""
        self.state_machine.state = state if isinstance(state, AgentState) else AgentState()

    def _register_builtin_tools(self) -> None:
        """
        注册 Agent 内嵌的元工具，用于控制对话轮次的生命周期。
        """
        for tool in create_builtin_tools(agent=self):
            self.tool_registry.register(tool)

    @staticmethod
    def _split_reasoning_from_stream_text(text: str) -> tuple[str, str]:
        """Split streamed think blocks from visible assistant content."""
        reasoning_parts: list[str] = []
        content_parts: list[str] = []
        cursor = 0
        pattern = re.compile(r"<think>\s*(.*?)\s*</think>", flags=re.DOTALL | re.IGNORECASE)
        for match in pattern.finditer(text or ""):
            content_parts.append(text[cursor:match.start()])
            reasoning = match.group(1).strip()
            if reasoning:
                reasoning_parts.append(reasoning)
            cursor = match.end()
        content_parts.append(text[cursor:])
        content = "".join(content_parts).strip()
        reasoning = "\n".join(reasoning_parts).strip()
        return reasoning, content

    @property
    def system_prompt(self) -> str:
        """
        该函数会拼装系统提示词。工具 schema 仍交给 llm fetcher 处理；
        本地 ORT/Qwen 额外需要一个轻量契约来稳定触发工具调用。
        """
        prompt: str = self._base_system_prompt
        provider = getattr(self.llm_handler, "provider", "")
        if provider in {"onnxruntime", "ort"} and self.tool_registry.tools:
            prompt = prompt.rstrip() + "\n\n" + ORT_TOOL_CALL_CONTRACT.strip()
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
        max_tokens: int = 4096,
        use_history: bool = True,
        use_tools: bool = False,
        save_context: bool = True,
        tag_context: bool = True,
        streamer: Optional[Streamer | Callable[[str], int | None]] = None,
    ) -> LLMOutput:
        """
        Execute exactly one LLM chat request.

        Use this for simple chat, debugging, tag/summarizer-style calls, or
        cases where the caller wants to inspect raw `LLMOutput.tool_calls`.

        建议在调试 agent 系统时使用本方法。

        Args:
            msg: 用户输入。
            system_prompt: 可选的系统提示词覆盖。
            temperature: 采样温度。
            max_tokens: 最大输出 token 数。
            use_history: 是否使用历史上下文。
            use_tools: 是否注入工具定义。
            save_context: 是否将本轮对话保存到上下文。
            tag_context: 是否对保存的上下文执行标签化。
            streamer: 可选的流式输出处理器。提供时启用流式生成。
        """

        prev_message: Optional[List[LLMInfo]] = await self._build_prev_messages() if use_history else None

        request_tools = self.tool_registry.tools if use_tools else []

        resolved_system_prompt = system_prompt or self.system_prompt
        
        # 拉取本轮回复内容。
        if streamer:
            collected: list[str] = []
            async for chunk in self.llm_handler.fetch_stream(
                msg=msg,
                system_prompt=resolved_system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                prev_messages=prev_message if prev_message else None,
                tools=request_tools if request_tools else None,
            ):
                if chunk:
                    collected.append(chunk)
                    streamer(chunk)
            response_text = "".join(collected)
            streamed_tool_calls = [
                LLMToolCall(
                    name=tool_call.tool_name,
                    arguments=tool_call.arguments,
                    call_id=tool_call.call_id,
                    source=tool_call.source.value,
                )
                for tool_call in parse_xml_tool_calls(response_text)
            ]
            output = LLMOutput(
                content=strip_xml_tool_calls(response_text) if streamed_tool_calls else response_text,
                provider=self.llm_handler.provider,
                backend_name=self.llm_handler.default_backend_config.name,
                model=self.llm_handler.default_backend_config.model,
                tool_calls=streamed_tool_calls,
            )
        else:
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
                tool_call_ids=[tool_call.call_id or "" for tool_call in resolved_tool_calls] or None,
            )

            await self.llm_context_handler.add_context(context)

        return output


    async def run_agent_round(
        self,
        msg: str,
        verbose_info: bool = False,
        max_turns: int = 8,
        max_context_size: int = 131072,
        temperature: float = 0.4,
        max_tokens: int = 4096,
        stop_callback: Optional[Callable[[], bool]] = None,
        streamer: Optional[Streamer | Callable[[str], int | None]] = None,
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
            streamer: 可选的流式输出处理器。提供时启用流式生成。
            verbose_info: 为 True 时，打印每轮调用、tool_calls、结果等调试信息。
            max_turns: 最大轮次上限。
            temperature: 采样温度，透传给底层 LLM 请求。
            max_tokens: 最大输出 token 数，透传给底层 LLM 请求。
            stop_callback: 可选，用于确定是否停止运行的回调函数。该函数返回 True 时则停止执行。
            streamer: 一个用于对外输出流式内容的函数。本函数将使用其 __call__ 方法进行输出。

        Returns:
            LLM 生成的完整回复文本。
        """

        request_tools = self.tool_registry.tools
        final_content: str = ""
        if not self.agent_state.task:
            self.agent_state.task = msg
        
        # 保存输入。
        user_input_context: LLMContext = LLMContext(
            role="user",
            timeline=0,
            content=msg,
            tags=["user_request"]
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

            # 预处理工作流
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

                if self.llm_context_handler.context_len() > max_context_size:
                    await self.llm_context_handler.compress_context()

            if verbose_info:
                print(f"\n[Agent] ====== Executing Turn: {turn} ======")
                print(f"[Agent] Provider: {self.llm_handler.provider}")
                print(f"[Agent] Tool count: {len(request_tools)}")
                print(f"[Agent] Current context length: {self.llm_context_handler.context_len()} / {max_context_size}")

            if _should_stop():
                break

            # ---- 主工作流内容 ----
            if streamer:
                collected: list[str] = []
                async for chunk in self.llm_handler.fetch_stream(
                    msg=msg,
                    system_prompt=self.system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    prev_messages=prev_messages if prev_messages else None,
                    tools=request_tools if request_tools else None,
                    output_reasoning=True
                ):
                    if chunk:
                        collected.append(chunk)
                        streamer(chunk)
                else:
                    print() # 在循环结束的场合，换行
                response_text = "".join(collected)
                response_reasoning, response_text = self._split_reasoning_from_stream_text(response_text)
                streamed_tool_calls = [
                    LLMToolCall(
                        name=tool_call.tool_name,
                        arguments=tool_call.arguments,
                        call_id=tool_call.call_id,
                        source=tool_call.source.value,
                    )
                    for tool_call in parse_xml_tool_calls(response_text)
                ]
                response = LLMOutput(
                    content=strip_xml_tool_calls(response_text) if streamed_tool_calls else response_text,
                    provider=self.llm_handler.provider,
                    backend_name=self.llm_handler.default_backend_config.name,
                    model=self.llm_handler.default_backend_config.model,
                    reasoning_content=response_reasoning,
                    tool_calls=streamed_tool_calls,
                )
            else:
                response: LLMOutput = await self.llm_handler.fetch(
                    msg=msg,
                    system_prompt=self.system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    prev_messages=prev_messages if prev_messages else None,
                    tools=request_tools if request_tools else None,
                )

            # 然后查看工具内容，如果有工具的话。
            message: str = response.text    # 本轮文本
            if verbose_info and not streamer:
                print(f"[Agent] LLM response: \n -----------\n{message}\n -----------")

            # 现在的 tool call 被抽象为了当前包体的中间层（见类型 `LLMToolCall`），已和供应商无关
            tool_calls: List[LLMToolCall] = response.tool_calls

            # 处理工具调用
            executing_result: List[str] = await self._handle_tool_calls(tool_calls, verbose_info=verbose_info, max_concurrent_calls=self.max_concurrent_tools)

            tool_record_round: List[ToolExecutionRecord] = [
                ToolExecutionRecord(
                    name=tool_info.name,
                    arguments=tool_info.arguments,
                    result=tool_result
                ) for (tool_info, tool_result) in zip(tool_calls, executing_result)
            ]

            # 压缩工具信息。
            tool_result_facts: List[ToolResultFact] = []

            tool_result_facts = await self.llm_context_handler.compress_tool_result_records(
                tool_record_round,
                tool_call_ids=[tool_call.call_id for tool_call in tool_calls],
                temperature=temperature,
            )

            # 更新状态消息。
            await self.state_machine.update_from_turn(
                AgentStateTurnEvent(
                    user_goal=msg,
                    turn=turn,
                    assistant_message=message,
                    tool_records=tool_record_round,
                    tool_result_facts=tool_result_facts,
                    stop_requested=_should_stop(),
                ),
                temperature=temperature,
            )

            if _should_stop():
                final_content = final_content or response.text
                break

            self.tool_call_history.append(tool_calls)
            self.tool_call_result_history.append(executing_result)

            # 拼接上下文。
            # 这里才会包括工具。
            now_assistant_context: LLMContext = LLMContext(
                role="assistant",
                content=message,  # 文本
                content_reasoning=response.reasoning_content or None,
                tool_call_info=[str(tool_info.to_execution_format()) for tool_info in tool_calls],
                tool_call_ids=[tool_call.call_id or "" for tool_call in tool_calls] or None,
                tool_result_facts=[fact.to_context_text() for fact in tool_result_facts] or None,
            )

            # 然后将其加入自身上下文中。注意：加入新的上下文后，激活上下文窗口也需要变。
            # 这个函数疑似性能瓶颈，注意。
            await self._maybe_archive_long_round_context(   # 检测长度过长的上下文，并压缩之。
                context=now_assistant_context,
                verbose_info=verbose_info,
            )
            
            # 将信息加入当前上下文。
            await self.llm_context_handler.add_context(now_assistant_context, append_to_active=True)  # 添加到当前上下文中，并加入到当前激活上下文窗口内。

            # 将工具结果回放为独立的 tool 消息，供下一轮模型读取。
            for tool_info, tool_result in zip(tool_calls, executing_result):
                fact = tool_result_facts.pop(0) if tool_result_facts else None
                tool_context = LLMContext(
                    role="tool",
                    content=fact.to_context_text() if fact is not None else "",
                    tool_call_info=[str(tool_info.to_execution_format())],
                    tool_call_ids=[tool_info.call_id or ""],
                    tool_result_facts=[fact.to_context_text()] if fact is not None else None,
                )
                await self.llm_context_handler.add_context(tool_context, append_to_active=True)

            if verbose_info:
                print(f"[Agent] Current active context IDs after agent round: {self.llm_context_handler.active_ids}")
                print(f"[Agent] Tag to Context index: {self.llm_context_handler.tag_to_context}")

            # 检测上下文长度，并压缩之 — 仅在 graph 模式下启用。
            if self.context_mode == "graph" and self.llm_context_handler.context_len() > max_context_size:
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
        agent_state_text: Optional[str] = None,
    ) -> Optional[List[int]]:
        """Reselect the graph-mode active context window for one agent turn.

        This method is state-aware: it passes the current agent state-machine
        snapshot both into candidate retrieval and into the final selector
        prompt. The selector still cannot choose arbitrary history; it can only
        select ids from the retrieved candidate closure.

        Args:
            user_input_context: User-visible task context for the current round.
            turn: One-based turn number inside the current agent round.
            verbose_info: Whether diagnostic messages should be printed.
            temperature: Sampling temperature used by helper model calls.
            agent_state_text: Rendered state-machine snapshot. When omitted,
                the method renders `self.agent_state` at call time.

        Returns:
            The applied active context ids when reselection succeeds, otherwise
            `None` when reselection is skipped or rejected.
        """
        # Skip selector work unless graph retrieval is enabled for this agent.
        if self.context_mode != "graph" or not self.llm_context_handler.retrieval_enabled:
            return None

        # Respect interval and size thresholds before spending model calls.
        if not self._should_trigger_context_selection(turn):
            return None

        # Render state once so retrieval and selector judgment share the same snapshot.
        resolved_agent_state_text = agent_state_text if agent_state_text is not None else str(self.agent_state)
        current_task_text = getattr(user_input_context, "content", str(user_input_context))

        # Retrieve a state-aware candidate pool before asking the selector to rank it.
        candidate_ids = await self._retrieve_context_candidates_for_task(
            user_input_context=user_input_context,
            temperature=temperature,
            agent_state_text=resolved_agent_state_text,
        )
        if verbose_info:
            print(f"[Agent] Context selection found {len(candidate_ids)} candidates: {candidate_ids}")

        # Keep the existing active window when retrieval cannot produce a useful pool.
        if not candidate_ids:
            if verbose_info:
                print("[Agent] Context selection found no retrieval candidates; keeping current active window.")
            return None
        
        # Expand compacted candidates into their selectable descendants while preserving stable order.
        candidate_listing_ids = self._candidate_closure_ids(candidate_ids)
        
        # Render only the candidate closure, because the selector must not see unrestricted history.
        context_listing = await self.llm_context_handler.get_now_abstract_as_str(
            candidate_listing_ids,
            preserve_order=True,
        )

        # Abort selection if every candidate serializes to an empty listing.
        if not context_listing.strip():
            if verbose_info:
                print("[Agent] Candidate context listing is empty; keeping current active window.")
            return None

        # Build a state-aware prompt that lets the selector align context with phase and next actions.
        selection_prompt = CONTEXT_SELECTION_PROMPT_TEMPLATE.format(
            agent_state_text=resolved_agent_state_text,
            current_task=current_task_text,
            context_listing=context_listing,
        )

        if verbose_info:
            print(f"[Agent] Triggering periodic context selection at turn {turn}.")
        
        # Call the selector as a plain LLM helper with no tools or chat history.
        #
        selection_output = await self.llm_handler.fetch(
            msg=selection_prompt,
            temperature=temperature,
        )

        # Parse the selector's JSON response into typed id/view choices.
        selected_views = self._parse_selection_views(selection_output.text)
        selected_ids = [item.id for item in selected_views]
        if verbose_info:
            print(f"[Agent] Original selection output as: {selection_output.text}")
            print(f"[Agent] Selection output as: {selected_views}")

        # Treat empty selector output as a no-op rather than clearing context.
        if not selected_ids:
            if verbose_info:
                print("[Agent] Context selection returned no valid ids; keeping current active window.")
            return None

        # Enforce that the model can only choose ids from the candidate closure.
        allowed_ids = set(candidate_listing_ids)
        filtered_ids = [
            context_id
            for context_id in selected_ids
            if context_id in allowed_ids
        ]

        # Reject hallucinated ids instead of silently activating unrelated history.
        if not filtered_ids:
            if verbose_info:
                print("[Agent] Context selection returned ids outside candidates; keeping current active window.")
            return None

        # Normalize ids while keeping compacted entries compact unless raw descendants were selected.
        normalized_selected_ids = self.llm_context_handler.expand_active_selection_ids(
            filtered_ids,
            expand_compacted_sources=False,
            keep_compacted_entries=True,
        )

        # Guard against normalization eliminating every selected id.
        if not normalized_selected_ids:
            if verbose_info:
                print("[Agent] Normalized active selection is empty; keeping current active window.")
            return None

        # Mirror the accepted selection into the context manager's active cache.
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
        """Build the explicit prompt context bundle for one main LLM turn.
        
        Args:
            user_input_context: User-visible task context for the current round.
            turn: One-based turn number inside the current agent round.
            temperature: Sampling temperature passed into helper model calls.
            verbose_info: Whether diagnostic messages should be printed.

        Returns:
            A `ContextBundle` that pins the rendered agent state, includes any
            state-aware selector output, and preserves a recent active tail.
        """
        # Snapshot the rendered state once so selector and main prompt share the same state.
        agent_state_text = str(self.agent_state)

        # Preserve a recent active tail independently from selector output for local continuity.
        active_ids: List[int] = self.llm_context_handler.get_active_ids_window()
        recent_tail_ids: List[int] = stable_unique_ids(active_ids[-self.round_compress_keep_tail:])

        # Start empty; selector output is optional and should not imply clearing active context.
        selected_ids: List[int] = []

        # Let the state-aware selector reseat long-range context when thresholds allow it.
        maybe_selected_ids = await self._maybe_run_context_selection(
            user_input_context=user_input_context,
            turn=turn,
            verbose_info=verbose_info,
            temperature=temperature,
            agent_state_text=agent_state_text,
        )

        # Deduplicate accepted selector ids while preserving model-chosen order.
        if maybe_selected_ids:
            selected_ids = stable_unique_ids(maybe_selected_ids)
        
        # Return the prompt bundle consumed by `_build_prev_messages`.
        return ContextBundle(
            state_text=agent_state_text,
            selected_ids=selected_ids,
            recent_ids=recent_tail_ids,
        )

    def _candidate_closure_ids(self, candidate_ids: List[int]) -> List[int]:
        """
        Return candidates plus descendants of compacted candidates in stable order.
        """
        closure_ids: List[int] = []
        for context_id in candidate_ids:
            # 如果不在时间线里
            if context_id not in self.llm_context_handler.context_timeline_dict:
                continue

            # 加入条目，如果是压缩后上下文，则将被压缩后的东西全部加入到这里……？
            closure_ids.append(context_id)

            # 寻找所有被压缩后上下文的子条目。
            entry = self.llm_context_handler.context_timeline_dict[context_id]
            if isinstance(entry, LLMContextCompacted):
                closure_ids.extend(sorted(self.llm_context_handler.get_descendant_ids(context_id)))
        
        # 去重并返回。
        return stable_unique_ids(closure_ids)

    async def _retrieve_context_candidates_for_task(
        self,
        user_input_context: LLMContext,
        temperature: float = 0.4,
        agent_state_text: Optional[str] = None,
    ) -> List[int]:
        """Retrieve prompt-selectable context ids for the current task and state.

        Args:
            user_input_context: User-visible task context for the current round.
            temperature: Sampling temperature used by helper tagging calls.
            agent_state_text: Rendered state-machine snapshot used to broaden
                summary retrieval toward current phase, facts, failed actions,
                do-not-repeat constraints, and next actions.

        Returns:
            A stable candidate id list expanded from retrieval hits. The caller
            is responsible for adding recent-tail continuity separately.
        """

        # Retrieval candidates only exist in graph mode with indexes enabled.
        if self.context_mode != "graph" or not self.llm_context_handler.retrieval_enabled:
            return []

        # Normalize the task text because older internal tests may pass a raw string.
        current_task_text = getattr(user_input_context, "content", str(user_input_context))

        # Build a state-aware summary query without mutating the original user context.
        retrieval_query_parts = [current_task_text]
        if agent_state_text:
            retrieval_query_parts.append(agent_state_text)
        retrieval_query = "\n\n".join(part for part in retrieval_query_parts if part)

        # Convert the current user input into cached task tags for tag-index retrieval.
        task_tags: List[str] = await self._get_round_task_tags(user_input_context, temperature=temperature)

        # Prefer candidates that satisfy both task tags and state-aware summary text.
        intersected_hits: Optional[List[LLMInfo]] = None

        # Only run the AND query when task tags exist.
        if task_tags:
            intersected_hits = await self.llm_context_handler.find_context_by_summary_and_tags(
                summary_query=retrieval_query,
                tags=task_tags,
                blur_summary=True,
                blur_tags=True,
            )
        
        # Retrieve tag-only hits as a fallback path when the intersection is empty.
        tag_hits = None
        if task_tags:
            tag_hits: Optional[List[LLMInfo]] = await self.llm_context_handler.find_context_by_tags(
                tags=task_tags,
                blur=True,
            )

        # Retrieve summary hits from compacted context using both task and state text.
        summary_hits: Optional[List[LLMInfo]] = await self.llm_context_handler.find_context_by_summary(
            summary_query=retrieval_query,
            blur=True,
            include_raw=False,
            include_compacted=True,
        )

        # Prefer expanded ids from the tag-summary intersection when available.
        candidate_ids: List[int] = []
        if intersected_hits:
            intersect_id: Optional[List[int]] = self.llm_context_handler.expand_retrieval_hit_ids(intersected_hits)
            if intersect_id:
                candidate_ids.extend(intersect_id)

        # Fall back to the union of tag hits and summary hits when no intersection exists.
        else:
            if tag_hits:
                tag_hit_id: Optional[List[int]] = self.llm_context_handler.expand_retrieval_hit_ids(tag_hits)
                if tag_hit_id:
                    candidate_ids.extend(tag_hit_id)
            if summary_hits:
                summary_hit_id: Optional[List[int]] = self.llm_context_handler.expand_retrieval_hit_ids(summary_hits)
                if summary_hit_id:
                    candidate_ids.extend(summary_hit_id)
        
        # Return stable ids so repeated selector calls see deterministic candidate order.
        return stable_unique_ids(candidate_ids)

    async def _cache_round_task_tags(
        self,
        user_input_context: LLMContext,
        temperature: float = 0.4,
    ) -> List[str]:
        """
        保存标签。

        Args:
            user_input_context: 用户输入上下文。
            temperature: 模型采样温度，用于进行标签/摘要的生成。
        """

        # 如果不使用图式上下文，或不允许上标签，则不执行本函数。
        if self.context_mode != "graph" or not self.llm_context_handler.enable_tagging:
            return []
        
        # 上标签。
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
        返回任务标签。
        如果没有当前任务的标签，则进行 llm call 以获取之。

        Args:
            user_input_context: 用户输入上下文。
            temperature: 模型采样温度，用于进行标签/摘要的生成。
        """
        if self._round_task_tags is None:
            self._round_task_tags = await self._cache_round_task_tags(
                user_input_context=user_input_context,
                temperature=temperature,
            )
        return self._round_task_tags
    def _parse_selection_views(self, content: str) -> List[ContextSelectionView]:
        """
        Extract selector choices from JSON for context selection views.
        
        Args:
            content: 输入的 JSON 内容，该内容会直接来自上下文选择器。
        """
        # 如果没东西
        if not content.strip():
            return []

        candidates: List[str] = [content.strip()]
        candidates.extend(match.group(0) for match in re.finditer(r"\{.*?\}", content, flags=re.DOTALL))    # 从原始内容里……我日 你在读取什么？？

        # 对于每一个条目
        for candidate in candidates:
            # 如果无法转为 json 则跳过
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError:
                continue

            # 条目，可能是 dict
            items = payload.get("items")
            # 如果 items 的类型是列表
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

            # Schema 3: single item {"id": X, "view": Y, "reason": Z}
            # This matches the format the LLM selector actually outputs in practice.
            try:
                context_id = int(payload.get("id"))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
            view_value = payload.get("view", "raw")
            view: ContextView = "compacted" if view_value == "compacted" else "raw"
            reason = payload.get("reason")
            return [
                ContextSelectionView(
                    id=context_id,
                    view=view,
                    reason=str(reason) if reason is not None else None,
                )
            ]
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
            return []
            
        # 如果有 bundle 内容
        if bundle is not None:
            history_msg: List[LLMInfo] = []

            # 在有当前状态文本的场合，加入当前状态
            if bundle.state_text.strip():
                history_msg.append(
                    LLMContext(
                        role="user",
                        timeline=0,
                        content=bundle.state_text,
                        tags=["agent_state"],
                    )
                )
            # 获取各个状态的 id
            ordered_ids = bundle.ordered_ids()
            if ordered_ids:
                # 获取上下文信息，保留顺序
                context_info: Optional[LLMContextInfo] = await self.llm_context_handler.get_now_context(
                    ordered_ids,
                    preserve_order=True,
                )
                if context_info:
                    history_msg.extend(context_info.items)

            return history_msg or []
        
        # 这部分已经被 llm_context 实现。
        else:
            history_msg_raw: Optional[LLMContextInfo] = await self.llm_context_handler.get_now_active_context()
            if not history_msg_raw:
                history_msg = []
            else:
                history_msg = history_msg_raw.items
            
            return history_msg


    def _render_agent_state(self):
        """Compatibility renderer for the current state-machine snapshot."""
        return self.state_machine.render()
    
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
            print(f"[Agent] Parsed tool call numbers: {len(tool_calls)}")
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
