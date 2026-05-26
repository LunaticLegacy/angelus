"""平台无关的 LLM 调度器。

本模块只负责后端注册、fallback 顺序、重试、限流与统一输出调度。
具体 provider 的请求构造、响应归一化和流式解析都委托给 `handlers/` 里的后端类。

"""

from __future__ import annotations

import asyncio
from typing import (
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
    LLMInfo, LLMToolCall, LLMOutput,
    LLMError,
    LLMTimeoutError, LLMBackendError
)

from .handlers import (
    ToolSchema,
    LLMBackendHandler,
)

class LLMFetcher:
    """Route chat requests across one or more configured LLM backends."""

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

        # 如果有设置后端
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
    ) -> List[Dict[str, str]]:
        """构造发给后端的统一消息列表。"""
        messages: List[Dict[str, str]] = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        if msg:
            messages.append({"role": "user", "content": msg})

        if prev_messages:
            # 解析过去的信息时，这个过去信息会分为如下：
            # List[LLMInfo]，包含两种实例：LLMContext et LLMContextCompacted
            for item in prev_messages:
                role: Optional[str] = None
                content: Optional[str] = None
                
                if isinstance(item, LLMContext):
                    context: LLMContext = item
                    role = context.role
                    content = str(context)

                if isinstance(item, LLMContextCompacted):
                    context_compacted: LLMContextCompacted = item
                    role = "user"
                    # 我要怎么解析这个该死的上下文信息？
                    content = str(context_compacted)

                if not role:
                    continue
                messages.append({"role": role, "content": content})

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
        fallback_order: Optional[Sequence[str]] = None,
        tools: Optional[List[ToolSchema]] = None,
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
            tools: 可选的 OpenAI tools schema 列表。

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
        for backend in self._resolve_backends(backend_name, fallback_order):
            handler = self._handler_for_backend(backend)
            # 重试次数：
            retries_left = self._timeout_retry_count(backend)

            while True:
                try:
                    # 原始信息
                    raw_response = handler.create_completion(
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stream=False,
                        tools=tools,
                    )
                    # 使用 handler 的处理方式
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
        fallback_order: Optional[Sequence[str]] = None,
        tools: Optional[List[ToolSchema]] = None,
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
            fallback_order: 额外指定的回退后端顺序。
            tools: 可选的 OpenAI tools schema 列表。

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

        for backend in self._resolve_backends(backend_name, fallback_order):
            handler = self._handler_for_backend(backend)
            retries_left = self._timeout_retry_count(backend)

            while True:
                yielded_any = False
                try:
                    response = handler.create_completion(
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stream=True,
                        tools=tools,
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
