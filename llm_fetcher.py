"""平台无关的 LLM 调度器。

本模块只负责后端注册、fallback 顺序、重试和统一调用调度。
所有 provider 细节都下沉到 `handlers/`：
消息适配、tool schema 转换、tool call 解析、流式事件解析和响应归一化
都不应在这里再实现一次。
"""

from __future__ import annotations

import ast
import json
import asyncio
from typing import (
    Any,
    AsyncGenerator,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)

from .prompt import DEBUG_STREAM_SYSTEM_PROMPT
from .llm_types import (
    LLMBackendConfig,
    LLMContext,
    LLMContextCompacted,
    LLMInfo,
    LLMOutput,
    TokenUsage,
    LLMError,
    LLMTimeoutError,
    LLMBackendError,
)

from .handlers import (
    ToolDefinition,
    LLMBackendHandler,
)

class LLMFetcher:
    """
    Route chat requests across one or more configured LLM backends.
    """

    @staticmethod
    def list_available_backend_providers() -> Tuple[str, ...]:
        """
        列举当前 handler 系统支持的全部 provider 名称。

        返回值按字母序排序，便于 CLI/调试输出稳定。
        """
        provider_names: set[str] = set()
        for handler_cls in LLMBackendHandler._iter_descendants():
            provider_names.update(handler_cls.provider_names)
        return tuple(sorted(provider_names))

    def __init__(
        self,
        backends: Optional[Sequence[LLMBackendConfig]] = None,
        default_backend: Optional[str] = None,
    ) -> None:
        """
        初始化 LLM 管理器。

        Notes:
            构造要求：传入多个 `LLMBackendConfig`，构造带路由与回退能力的多后端管理器。

        Args:
            backends: 多后端模式下的后端配置列表，可以是 list 或 tuple
            default_backend: 多后端模式下的默认后端名称。

        Raises:
            ValueError: 当没有提供有效的构造参数，或默认后端名称不存在时抛出。
        """
        self.backends: Dict[str, LLMBackendConfig] = {}     # 后端 handler 配置索引
        self.backend_order: List[str] = []  # 按次序调用后端内容。
        self.handlers: Dict[str, LLMBackendHandler] = {}    # 后端 handler 索引

        # 如果有设置后端，则对每个后端进行注册。
        if backends and len(backends) > 0:
            for backend in backends:
                self._register_backend(backend)
        # 否则直接报错：
        else:
            raise ValueError("You should set at least ONE backend with class LLMBackendConfig.")

        # 设置默认后端。
        if default_backend is not None:
            if default_backend not in self.backends:
                raise ValueError(f"Unknown default backend: {default_backend}")
            # 将 default backend 提到列表最前。
            self.backend_order.remove(default_backend)
            self.backend_order.insert(0, default_backend)

        self.default_backend = self.backend_order[0]
    
    @property
    def backend_configs(self) -> Dict[str, LLMBackendConfig]:
        """
        获得当前全部后端配置。
        """
        return dict(self.backends)
    
    @property
    def fallback_order(self) -> List[str]:
        """
        获得当前回退顺序。
        """
        return list(self.backend_order)

    @property
    def default_backend_config(self) -> LLMBackendConfig:
        """
        返回默认后端配置。
        """
        return self.backends[self.default_backend]

    @property
    def provider(self) -> str:
        """
        返回当前默认后端的供应商。
        TODO: 考虑是否保留该 property
        """
        return self.default_backend_config.provider

    @property
    def backend_providers(self) -> Dict[str, str]:
        """Return backend-name to provider-name mapping for routing inspection."""
        return {name: backend.provider for name, backend in self.backends.items()}

    def _register_backend(
        self, 
        backend: LLMBackendConfig
    ) -> None:
        """
        注册单个后端，并预创建客户端。时刻准备好输出。

        Args:
            backend: 要注册的后端配置。

        Raises:
            ValueError: 当后端名称重复时抛出。
        """
        # 强制要求后端不得重名。
        if backend.name in self.backends:
            raise ValueError(f"Duplicate backend name: {backend.name}. You already registered a backend as: {self.backends[backend.name]}")
        self.backends[backend.name] = backend
        self.backend_order.append(backend.name)
        # 创建后端 handler 实例。
        self.handlers[backend.name] = LLMBackendHandler.create_for_backend(self, backend)

    def _resolve_backends(
        self,
        backend_name: Optional[str],
        fallback_order: Optional[Sequence[str]],
    ) -> List[LLMBackendConfig]:
        """
        解析一次请求应使用的后端顺序。

        Args:
            backend_name: 显式指定的单个后端名称。
            fallback_order: 额外指定的回退后端顺序。

        Returns:
            按请求顺序排列的后端配置列表。

        Raises:
            ValueError: 当显式指定的后端名称不存在时抛出。
        """
        if backend_name:
            if backend_name not in self.backends:
                raise ValueError(f"Unknown backend: {backend_name}")
            names = [backend_name]
        else:
            names = [self.default_backend]
            if fallback_order:
                names.extend(fallback_order)
            names.extend(name for name in self.backend_order if name not in names)
        return [self.backends[name] for name in names]

    def _handler_for_backend(self, backend: LLMBackendConfig) -> LLMBackendHandler:
        return self.handlers[backend.name]

    def _build_messages(
        self,
        msg: str,
        prev_messages: Optional[List[LLMInfo]] = None,
        system_prompt: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """构造发给后端的统一消息列表。"""
        messages: List[Dict[str, Any]] = []

        def _parse_tool_call_info(raw: str) -> Optional[dict[str, Any]]:
            try:
                parsed = ast.literal_eval(raw)
            except (ValueError, SyntaxError):
                return None
            if not isinstance(parsed, dict):
                return None
            return parsed

        def _tool_call_id_for(item: LLMContext, index: int) -> str:
            if item.tool_call_ids and index < len(item.tool_call_ids):
                value = str(item.tool_call_ids[index]).strip()
                if value:
                    return value
            return f"legacy_tool_call_{item.timeline}_{index}"

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        if prev_messages:
            # 历史上下文已经被上层整理成统一的可渲染对象。
            # 这里不做 provider 侧的结构理解，只负责把上下文转成消息序列。
            pending_tool_call_ids: set[str] = set()
            for item in prev_messages:
                role: Optional[str] = None
                content: Optional[str] = None

                if isinstance(item, LLMContext):
                    role = item.role
                    content = item.content
                    if item.content_reasoning:
                        reasoning = item.content_reasoning.strip()
                        if reasoning:
                            reasoning_block = f"<think>\n{reasoning}\n</think>"
                            content = f"{reasoning_block}\n{content}" if content else reasoning_block
                    if role == "assistant" and item.tool_call_info:
                        tool_calls: list[dict[str, Any]] = []
                        for index, raw_tool_call in enumerate(item.tool_call_info):
                            parsed = _parse_tool_call_info(raw_tool_call)
                            if not parsed:
                                continue
                            tool_name = str(parsed.get("tool") or parsed.get("name") or "").strip()
                            if not tool_name:
                                continue
                            arguments = parsed.get("arguments", {})
                            if not isinstance(arguments, dict):
                                arguments = {}
                            tool_calls.append(
                                {
                                    "id": _tool_call_id_for(item, index),
                                    "type": "function",
                                    "function": {
                                        "name": tool_name,
                                        "arguments": json.dumps(arguments, ensure_ascii=False),
                                    },
                                }
                            )
                        if tool_calls:
                            pending_tool_call_ids = {
                                str(tool_call.get("id") or "").strip()
                                for tool_call in tool_calls
                                if str(tool_call.get("id") or "").strip()
                            }
                            messages.append({
                                "role": "assistant",
                                "content": content or None,
                                "tool_calls": tool_calls,
                            })
                            continue
                        pending_tool_call_ids.clear()
                    if role == "tool":
                        if not content and item.tool_result_facts:
                            content = "\n".join(item.tool_result_facts)
                        tool_call_id = ""
                        if item.tool_call_ids:
                            tool_call_id = str(item.tool_call_ids[0]).strip()
                        if not tool_call_id:
                            tool_call_id = f"legacy_tool_call_{item.timeline}_0"
                        if tool_call_id not in pending_tool_call_ids:
                            continue
                        pending_tool_call_ids.discard(tool_call_id)
                        messages.append({
                            "role": "tool",
                            "content": content,
                            "tool_call_id": tool_call_id,
                        })
                        continue
                    pending_tool_call_ids.clear()
                elif isinstance(item, LLMContextCompacted):
                    role = "user"
                    content = str(item)
                    pending_tool_call_ids.clear()

                if role:
                    messages.append({"role": role, "content": content or ""})

        if msg:
            messages.append({"role": "user", "content": msg})

        return messages

    def _normalize_exception(self, backend: LLMBackendConfig, exc: Exception) -> LLMError:
        message = f"Backend '{backend.name}' ({backend.provider}) failed: {exc}"
        if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
            return LLMTimeoutError(message)
        if "timeout" in str(exc).lower():
            return LLMTimeoutError(message)
        return LLMError(message)

    def _timeout_retry_count(self, backend: LLMBackendConfig) -> int:
        """将 max_retries 解释为额外重试次数，但至少执行一次请求。"""
        return max(1, int(backend.max_retries))

    async def _sleep_before_retry(
        self,
        backend: LLMBackendConfig,
        retries_left: int,
    ) -> None:
        total_retries = self._timeout_retry_count(backend)
        attempt_index = total_retries - retries_left
        await asyncio.sleep(min(1.5, 0.25 * attempt_index))

    async def fetch(
        self,
        msg: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.4,
        max_tokens: int = 4096,
        prev_messages: Optional[List[LLMInfo]] = None,
        backend_name: Optional[str] = None,
        tools: Optional[Sequence[ToolDefinition]] = None,
    ) -> LLMOutput:
        """执行一次非流式请求，并按顺序尝试后端回退。

        Args:
            msg: 当前轮用户输入。
            system_prompt: 当前请求使用的系统提示词。
            temperature: 采样温度。
            max_tokens: 最大输出 token 数。
            prev_messages: 历史上下文。（在未来，这个东西有可能会是被精选后的上下文了）
            backend_name: 显式指定的后端名称。
            fallback_order: 额外指定的回退后端顺序。
            tools: 可选工具列表。可以传入可执行 `Tool` 对象，或兼容旧调用的
                provider/tool schema 字典。具体转换由 handler 负责。

        Returns:
            抽象后的 LLM 输出，只暴露正文、推理内容、工具调用、用量等统一字段。

        Raises:
            LLMBackendError: 当所有候选后端均调用失败时抛出。
        """
        messages = self._build_messages(
            msg,
            prev_messages=prev_messages,
            system_prompt=system_prompt,
        )

        backend_errors: List[str] = []

        # 解析后端
        for backend in self._resolve_backends(backend_name, self.fallback_order):
            handler = self._handler_for_backend(backend)
            # 重试次数：
            retries_left = self._timeout_retry_count(backend)

            while True:
                try:
                    # 这些东西将全部由 provider 返回。
                    provider_tools = handler.prepare_tools(tools)
                    raw_response = handler.create_completion(
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stream=False,
                        tools=provider_tools,
                    )
                    return handler.normalize_completion_response(raw_response)
                except Exception as exc:
                    normalized_error = self._normalize_exception(backend, exc)
                    if isinstance(normalized_error, LLMTimeoutError) and retries_left > 0:
                        retries_left -= 1
                        await self._sleep_before_retry(backend, retries_left)
                        continue

                    backend_errors.append(str(normalized_error))
                    break

        raise LLMBackendError("; ".join(backend_errors))

    async def fetch_stream(
        self,
        msg: str,
        prev_messages: Optional[List[LLMInfo]] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.4,
        max_tokens: int = 4096,
        output_reasoning: bool = False,
        backend_name: Optional[str] = None,
        tools: Optional[Sequence[ToolDefinition]] = None,
    ) -> AsyncGenerator[str, None]:
        """执行一次流式请求，并按顺序尝试后端回退。
        TODO: 让这个函数可正式返回一个函数包体。

        Args:
            msg: 当前轮用户输入。
            prev_messages: 历史上下文。
            system_prompt: 当前请求使用的系统提示词。
            temperature: 采样温度。
            max_tokens: 最大输出 token 数。
            output_reasoning: 是否输出推理内容。
            backend_name: 显式指定的后端名称。
            tools: 可选工具列表。可以传入可执行 `Tool` 对象，或兼容旧调用的
                provider/tool schema 字典。具体转换由 handler 负责。

        Yields:
            标准化后的流式文本片段。

        Raises:
            LLMBackendError: 当所有候选后端均调用失败时抛出。
            LLMError: 当流已经部分输出后，当前后端又发生异常时抛出。
        """
        messages = self._build_messages(
            msg,
            prev_messages=prev_messages,
            system_prompt=system_prompt,
        )
        backend_errors: List[str] = []

        for backend in self._resolve_backends(backend_name, self.fallback_order):
            handler = self._handler_for_backend(backend)
            retries_left = self._timeout_retry_count(backend)

            while True:
                yielded_any = False
                try:
                    provider_tools = handler.prepare_tools(tools)
                    response = handler.create_completion(
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stream=True,
                        tools=provider_tools,
                    )

                    for text in handler.iter_stream_text(
                        response,
                        output_reasoning=output_reasoning,
                    ):
                        yielded_any = True
                        yield text
                    return
                except Exception as exc:
                    normalized_error = self._normalize_exception(backend, exc)

                    if (
                        isinstance(normalized_error, LLMTimeoutError)
                        and not yielded_any
                        and retries_left > 0
                    ):
                        retries_left -= 1
                        await self._sleep_before_retry(backend, retries_left)
                        continue

                    if yielded_any:
                        raise normalized_error

                    backend_errors.append(str(normalized_error))
                    break

        raise LLMBackendError("; ".join(backend_errors))

async def chat_test() -> None:
    """执行本地后端接线的手工冒烟测试。"""
    llm = LLMFetcher(
        backends=[
            LLMBackendConfig(
                name="deepseek-primary",
                provider="openai",
                api_url="https://api.deepseek.com",
                api_key="sk-replace-me",
                model="deepseek-reasoner",
                timeout=60.0,
            )
        ]
    )

    async for chunk in llm.fetch_stream(
        msg="给我一段用于调试流式输出的样例文本。",
        system_prompt=DEBUG_STREAM_SYSTEM_PROMPT,
        temperature=0.7,
        max_tokens=512,
        output_reasoning=True,
    ):
        print(chunk, end="", flush=True)


if __name__ == "__main__":
    try:
        asyncio.run(chat_test())
    except KeyboardInterrupt:
        print("== exit ==")
