from __future__ import annotations

import asyncio
import json
import re
from types import CoroutineType
from typing import Any, Callable, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from .llm_fetcher import LLMFetcher, LLMOutput, LLMToolCall
from .llm_context import LLMContext, LLMContextCompacted, LLMContextHandler, LLMContextInfo
from .prompt import TAGIFY_CONTEXT_PROMPT
from .tool_call_adapter import ToolCallSource, normalize_tool_calls
from .tool import Tool, ToolRegistry
from .tools.builtin_tools import create_builtin_tools

from .llm_types import (
    OptionalToolList,
    MessageDict, Messages,
    ToolArgs, AssistantMessageDict,
    ToolList,
    OptionalToolList,
    AgentMessage,
    ToolExecutionRecord,
    LLMOutput,
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
        tools: OptionalToolList = None,
        max_concurrent_tools: int = 1,
        fallback_order: Optional[List[str]] = None,
        provider: str = "custom_json",
        round_compress_threshold: Optional[int] = None,
        round_compress_keep_tail: int = 6,
    ):
        """
        初始化Agent，绑定LLM处理器、系统提示词和可选工具列表。
        TODO: 再这么下去这傻逼东西迟早会成为一个超级类，可能不能再这么下去了。

        Args:
            llm_handler: LLM fetcher instance
            system_prompt: Base system prompt
            tools: Initial tools to register
            max_concurrent_tools: Max parallel tool executions
                                  TODO: 设置为-1，以无限制并行工具。
            fallback_order: Backend fallback order
            provider: LLM provider for tool calling. 
                     Options: "openai", "anthropic", "custom_json"
            round_compress_threshold: Auto-compress temporary in-round messages when
                                      their count reaches this value. None or not set will disables it.

            round_compress_keep_tail: Number of latest in-round messages to keep verbatim.
        """
        self._base_system_prompt: str = system_prompt   # 系统提示词。
        self.llm_handler = llm_handler  # 用于处理 llm api 通信相关的东西。
        self.llm_context_handler = LLMContextHandler(llm_handler=self.llm_handler)  # 上下文管理器。
        self.tool_registry = ToolRegistry() # 注册工具。
        self.max_concurrent_tools = max_concurrent_tools    # 本 agent 最大可并发多少工具。
        self.fallback_order = fallback_order
        self.provider = provider  # ← 保存 provider 设置
        self.round_compress_threshold = round_compress_threshold
        self.round_compress_keep_tail = round_compress_keep_tail

        # 记忆
        self.memory_list: List[str] = []

        # 工具调用历史
        self.tool_call_history: List[List[LLMToolCall]] = []
        self.tool_call_result_history: List[List[str]] = []


        # 注册内嵌工具（round_end 等），供 LLM 控制轮次生命周期
        self._register_builtin_tools()  # 现在这里只有一个 turn end……我可能需要将结束回合的东西单独从工具里摘出来。

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
        """运行时动态修改 Agent 的系统提示词。"""
        self._base_system_prompt = new_prompt

    def add_tool(self, tool: "Tool") -> None:
        """运行时给 Agent 增加一个工具。"""
        self.tool_registry.register(tool)

    def remove_tool(self, tool_name: str) -> None:
        """在运行期间，从本 Agent 的工具注册表内，移除一个命名工具。"""
        self.tool_registry.unregister(tool_name)

    # ------------------------------------------------------------------
    # 上下文管理接口
    # ------------------------------------------------------------------

    async def add_context(self, msg: LLMContext) -> None:
        """
        增加上下文内容。
        """
        await self.llm_context_handler.add_context(msg)

    async def get_conversation_history(self, id_list: Optional[List[int]] = None) -> Optional[LLMContextInfo]:
        """
        获取完整的对话历史。
        异步，等待当前上下文内容。

        Args:
            id_list: 选择的ID。如果不选择ID，则压缩全部未被压缩过的对话。
        
        Returns:
            List of message dicts with 'role' and 'content' keys.
        """
        return await self.llm_context_handler.get_now_context(id_list)

    async def get_conversation_summary(self, id_list: Optional[List[int]] = None) -> Optional[str]:
        """
        获取格式化的对话摘要。

        Args:
            id_list: 选择的ID。如果不选择ID，则压缩全部未被压缩过的对话。
        
        Returns:
            将所有上下文放在了同一个 str 里。
        """
        return await self.llm_context_handler.get_content_as_single_str(id_list)

    async def compress_history(self, id_list: Optional[List[int]] = None) -> bool:
        """
        压缩对话历史以节省 token。
        
        Args:
            id_list: 选择的ID。如果不选择ID，则压缩全部未被压缩过的对话。
            
        Returns:
            True if compression succeeded, False if no history to compress.
        """
        return await self.llm_context_handler.compress_context(id_list)

    async def create_memory(self, context_ids: List[int]) -> Optional[str]:
        """
        从特定对话中提取关键信息作为永久记忆。
        本函数会调用上下文管理器实例，创建新的记忆。
        
        Args:
            context_ids: List of context IDs to summarize into memory.
            
        Returns:
            Memory summary string, or None if extraction failed.
        """
        memory = await self.llm_context_handler.generate_memory(context_ids)
        if memory:
            self.memory_list.append(memory)
        return memory

    def copy_memories(self) -> List[str]:
        """
        获取所有已存储的记忆，该操作会拷贝一份。
        注意：“记忆”层级不等于“上下文”——记忆不会被再次压缩。

        Returns:
            List of memory summary strings.
        """
        return self.memory_list.copy()

    def get_memories(self) -> List[str]:
        """
        获取所有已存储的记忆，该操作不会拷贝，而是会返回其引用。
        建议在获取后立即改为 tuple 类型以只读。

        Returns:
            List of memory summary strings.
        """
        return self.memory_list

    def clear_memories(self) -> None:
        """
        清除所有记忆。
        """
        self.memory_list.clear()

    def get_context_count(self) -> int:
        """
        获取存储的上下文条目数量。
        
        Returns:
            Number of conversation rounds stored.
        """
        return len(self.llm_context_handler.context_dict)

    async def get_context_by_ids(self, ids: List[int]) -> Optional[LLMContextInfo]:
        """
        Retrieve specific context entries by their IDs.
        根据ID检索特定的上下文条目。
        
        Args:
            ids: List of context IDs to retrieve.
            
        Returns:
            LLMContextInfo containing compacted and uncompacted entries, or None.
        """
        return await self.llm_context_handler.get_now_context(ids)


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

        This helper is intentionally not an agent loop:
        - it does not execute tool calls
        - it does not call the model again with tool results
        - it only saves the assistant response when requested

        Use this for simple chat, debugging, tag/summarizer-style calls, or
        cases where the caller wants to inspect raw `LLMOutput.tool_calls`.
        """
        prev_message: Optional[LLMContext] = await self._build_prev_messages() if use_history else None
        tool_schemas = self.tool_registry.get_schemas_for_provider(self.provider) if use_tools else []

        resolved_system_prompt = system_prompt
        if resolved_system_prompt is None:
            resolved_system_prompt = self.system_prompt if use_tools else self._base_system_prompt

        output: LLMOutput = await self.llm_handler.fetch(
            msg=msg,
            system_prompt=resolved_system_prompt,
            temperature=temperature,
            prev_messages=[prev_message] if prev_message else None,
            tools=tool_schemas if tool_schemas else None,
            fallback_order=self.fallback_order,
        )

        resolved_tool_calls = self._resolve_tool_calls(output)

        if save_context:
            tool_call_info = [str(tool_call.to_execution_format()) for tool_call in resolved_tool_calls]
            tool_call_result = [
                "Tool call was returned by chat_once but not executed."
                for _ in resolved_tool_calls
            ]
            context = LLMContext(
                role=output.role or "assistant",
                content=output.text,
                tool_call_info=tool_call_info,
                tool_call_result=tool_call_result,
            )
            if tag_context:
                context = await self._tagify_context(context)
            await self.add_context(context)

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
            prev_messages: Optional[LLMContext] = await self._build_prev_messages()

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
                prev_messages=[prev_messages] if prev_messages else None,  # 这东西又是个 optional，我类型是对的，估计是插件bug
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
                # 工具可并行
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
            tool_record_round: List[ToolExecutionRecord] = [
                ToolExecutionRecord(
                    name=tool_info.name,
                    arguments=tool_info.arguments,
                    result=tool_result
                ) for (tool_info, tool_result) in zip(tool_calls, executing_result)
            ]
            self.tool_call_history.append(tool_calls)
            self.tool_call_result_history.append(executing_result)

            # 拼接上下文
            now_context: LLMContext = LLMContext(
                role="assistant",
                content=message,  # 文本
                tool_call_info=[str(i) for i in tool_record_round],
                tool_call_result=[i for i in executing_result]
            )
            # 然后将其加入自身上下文中
            await self.add_context(await self._tagify_context(now_context, temperature))
            # 如果 stdout 太大，需要将工具怎么办？而且这样做的话，工具是否要重构？

            # 上下文压缩。
            if self.llm_context_handler.context_len() > max_context_size:
                print(f"[Agent] Current context length: {self.llm_context_handler.context_len()} / {max_context_size}")
                print(f"[Agent] Context exceeded, compressing history...")
                await self.llm_context_handler.compress_context()

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

    async def _tagify_context(self, context: LLMContext, temperature: float = 1.0) -> LLMContext:
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
        if context.tool_call_result:
            tag_source_parts.extend(context.tool_call_result)

        tag_source = "\n".join(part for part in tag_source_parts if part.strip())
        if not tag_source.strip():
            context.tags = []
            return context

        prompt: str = """
        You should generate machine-readable tags for one Agent context entry.
        Return only 3 to 5 lowercase snake_case tags separated by commas.
        Do not explain. Do not ask for more input. Do not use Markdown or backticks.
        Example: context_lookup, tool_call, empty_history
        """

        tags: LLMOutput = await self.llm_handler.fetch(msg=tag_source, system_prompt=prompt, temperature=temperature)
        parsed_tags = [
            tag
            for tag in re.findall(r"[a-zA-Z][a-zA-Z0-9_]{1,40}", tags.content.lower())
            if tag not in {"tag_1", "tag_2", "tag_3", "tag_4", "tag_5"}
        ]
        context.tags = parsed_tags[:5]
        return context

    async def _build_prev_messages(self) -> Optional[LLMContext]:
        """
        将历史内容序列化。
        规定：传入一个 agent 时，需要的 schema：
        - 上下文内容
            - 压缩后上下文内容（已实现）
            - 未压缩的上下文内容（已实现）
        - 工具历史（已在上下文内容里）
        
        Returns:
            上下文内容。如果没有上下文，则返回空白内容。
        """
        if self.llm_context_handler.empty:
            return None

        history_msg: Optional[str] = await self.get_conversation_summary()
        if not history_msg:
            history_msg = ""

        history_context: LLMContext = LLMContext(
            role="user",
            content=f"[History]\n{history_msg}\n[End of History]"
        )

        return history_context
    
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

        if tool_name == "round_end":
            result: str = "Round ended."
        else:
            try:
                result = await self.tool_registry.execute(tool_name, args)
            except Exception as exc:
                result = f"Error: {exc}"

        if verbose:
            print(f"[Agent] Result of tool {tool_name} as: \n{str(result)}")

        return str(result)

    def _coerce_tool_arguments(self, value: Any) -> Dict[str, Any]:
        """Coerce tool arguments from dict/string/None into a dict."""
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
