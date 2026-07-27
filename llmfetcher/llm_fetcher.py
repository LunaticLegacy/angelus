"""Platform-agnostic LLM dispatcher.

Responsible for backend registration, fallback ordering, retries,
and unified call dispatching. All provider details are delegated to
`fetcher_handlers/` — message adaptation, tool schema conversion, tool call
parsing, streaming event parsing, and response normalisation should not
be reimplemented here.

Message construction from conversation history is handled by
``ContextHandler`` subclasses; ``LLMFetcher`` accepts pre-built message
lists via the ``context`` parameter.
"""

from __future__ import annotations

import asyncio
import time
from typing import (
    Any,
    AsyncGenerator,
    Generator,
    Dict,
    List,
    Optional,
    Sequence,
)

from .llm_types import (
    LLMBackendConfig,
    LLMOutput,
    LLMError,
    LLMTimeoutError,
    LLMBackendError,
)

from .fetcher_handlers import (
    ToolDefinition,
    LLMBackendHandler,
)

from .context_handlers import ContextHandler


class LLMFetcher:
    """Route chat requests across one or more configured LLM backends.

    Each backend is backed by an ``LLMBackendHandler`` subclass that adapts
    provider-specific wire formats.  Backends are tried in registration order
    unless a ``default_backend`` is given (which is promoted to the front).

    Example::

        fetcher = LLMFetcher(
            backends=[
                LLMBackendConfig(name="primary", provider="openai", ...),
                LLMBackendConfig(name="fallback", provider="anthropic", ...),
            ],
            default_backend="primary",
        )
        output = await fetcher.fetch("Hello")
    """

    @staticmethod
    def list_available_backend_providers() -> tuple[str, ...]:
        """Return all provider names supported by registered handlers, sorted.

        Returns:
            A tuple of unique provider name strings, alphabetically sorted.
            Each name corresponds to a value accepted by
            ``LLMBackendConfig.provider``.
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
        """Initialise the multi-backend dispatcher.

        Args:
            backends:
                One or more backend configurations.  Backends are registered
                in the order they appear and tried in that same order during
                fallback.
            default_backend:
                Name of the backend to use when no explicit ``backend_name``
                is passed to ``fetch`` / ``fetch_stream``.  If given, this
                backend is also moved to the front of the fallback chain.
                When ``None``, the first entry in ``backends`` is used as the
                default.

        Raises:
            ValueError:
                If ``backends`` is empty or ``None``, or if
                ``default_backend`` names a backend that does not exist in
                ``backends``.
        """
        if not backends:
            raise ValueError(
                "At least one LLMBackendConfig is required."
            )

        self.backends: Dict[str, LLMBackendConfig] = {}
        self.backend_order: List[str] = []
        self.handlers: Dict[str, LLMBackendHandler] = {}

        for backend in backends:
            self._register_backend(backend)

        if default_backend is not None:
            if default_backend not in self.backends:
                raise ValueError(f"Unknown default backend: {default_backend}")
            self.backend_order.remove(default_backend)
            self.backend_order.insert(0, default_backend)

        self.default_backend: str = self.backend_order[0]

    # -- read-only property accessors -------------------------------------------

    @property
    def backend_configs(self) -> Dict[str, LLMBackendConfig]:
        """Return a copy of all registered backend configurations.

        Returns:
            A mapping from backend name to its ``LLMBackendConfig``.
            Mutating the returned dict does not affect the fetcher.
        """
        return dict(self.backends)

    @property
    def fallback_order(self) -> List[str]:
        """Return the current fallback order (shallow copy).

        Returns:
            Backend names in the order they will be tried, with the
            default backend first.
        """
        return list(self.backend_order)

    @property
    def default_backend_config(self) -> LLMBackendConfig:
        """Return the configuration of the default backend.

        Returns:
            The ``LLMBackendConfig`` of the backend designated as default.
        """
        return self.backends[self.default_backend]

    # -- internal backend management --------------------------------------------

    def _register_backend(self, backend: LLMBackendConfig) -> None:
        """Register a single backend and pre-create its handler.

        Args:
            backend: The backend configuration to register.

        Raises:
            ValueError: If a backend with the same name already exists.
        """
        if backend.name in self.backends:
            raise ValueError(
                f"Duplicate backend name: {backend.name}. "
                f"Already registered: {self.backends[backend.name]}"
            )
        self.backends[backend.name] = backend
        self.backend_order.append(backend.name)
        self.handlers[backend.name] = LLMBackendHandler.create_for_backend(
            self, backend
        )

    def _resolve_backends(
        self,
        backend_name: Optional[str],
        fallback_order: Optional[Sequence[str]],
    ) -> List[LLMBackendConfig]:
        """Resolve the ordered backend list for a single request.

        The resolution logic:
        1. If ``backend_name`` is given, use only that backend.
        2. Otherwise start with the default backend.
        3. Append any names from ``fallback_order`` not yet in the list.
        4. Append remaining registered backends not yet in the list.

        Args:
            backend_name:
                Explicit backend name for this request, or ``None`` to use
                the default.
            fallback_order:
                Additional backend names to try after the primary, before
                the remaining registered backends.

        Returns:
            Backend configurations in attempt order.

        Raises:
            ValueError: If ``backend_name`` is not a registered backend.
        """
        if backend_name:
            if backend_name not in self.backends:
                raise ValueError(f"Unknown backend: {backend_name}")
            names = [backend_name]
        else:
            names = [self.default_backend]
            if fallback_order:
                names.extend(fallback_order)
            names.extend(
                name for name in self.backend_order if name not in names
            )
        return [self.backends[name] for name in names]

    def _handler_for_backend(
        self, backend: LLMBackendConfig
    ) -> LLMBackendHandler:
        """Return the handler instance for a given backend configuration.

        Args:
            backend: The backend configuration whose handler is needed.

        Returns:
            The ``LLMBackendHandler`` instance registered for *backend*.
        """
        return self.handlers[backend.name]

    # -- request execution helpers ----------------------------------------------

    @staticmethod
    def _normalize_exception(
        backend: LLMBackendConfig, exc: Exception
    ) -> LLMError:
        """Normalise any exception into an ``LLMError`` subclass.

        ``TimeoutError`` and ``asyncio.TimeoutError`` become
        ``LLMTimeoutError``.  Exceptions whose message contains "timeout"
        (case-insensitive) are also classified as timeouts.  All other
        exceptions become a plain ``LLMError``.

        Args:
            backend: The backend that raised the exception (used for the
                     error message).
            exc: The original exception.

        Returns:
            An ``LLMError`` (or subclass) instance with a descriptive
            message.
        """
        message = (
            f"Backend '{backend.name}' ({backend.provider}) failed: {exc}"
        )
        if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
            return LLMTimeoutError(message)
        if "timeout" in str(exc).lower():
            return LLMTimeoutError(message)
        return LLMError(message)

    @staticmethod
    async def _sleep_before_retry() -> None:
        """Short fixed-duration sleep before retrying a timed-out request."""
        await time.sleep(1)

    # -- public API -------------------------------------------------------------

    def fetch(
        self,
        msg: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.4,
        max_tokens: int = 4096,
        context_handler: Optional[ContextHandler] = None,
        backend_name: Optional[str] = None,
        tools: Optional[Sequence[ToolDefinition]] = None,
    ) -> LLMOutput:
        """Execute a non-streaming completion with backend fallback and retry.

        Backends are tried in fallback order.  On timeout, the same
        backend is retried up to ``max_retries + 1`` times.  Non-timeout
        errors skip to the next backend immediately.

        When a *context* handler is provided, the message list is built
        by ``context.build_messages(msg, system_prompt)``.  Otherwise a
        minimal one-shot message list is constructed from *msg* and
        *system_prompt* alone.

        Args:
            msg:
                The current user message text.
            system_prompt:
                Optional system-level instruction.
            temperature:
                Sampling temperature, passed to the backend handler.
                Defaults to 0.4.
            max_tokens:
                Maximum number of tokens in the generated response.
                Defaults to 4096.
            context_handler:
                A ``ContextHandler`` instance holding conversation history. 
                When provided, its ``build_messages`` method is used to
                construct the full message list including history.  Pass
                ``None`` for stateless single-turn calls.
            backend_name:
                Explicit backend to use for this request.  When ``None``,
                the default backend is used (with the registered fallback
                order).
            tools:
                Optional tool definitions to make available to the model.
                Accepts ``Tool`` instances or raw provider-specific schema
                dicts.  Conversion to provider format is handled by the
                backend handler.

        Returns:
            A normalised ``LLMOutput`` with content, reasoning, tool calls,
            and usage information.

        Raises:
            LLMBackendError:
                All candidate backends have been exhausted without
                producing a successful response.
        """
        messages = self._build_messages(msg, system_prompt, context_handler)
        backend_errors: List[str] = []

        for backend in self._resolve_backends(backend_name, self.fallback_order):
            handler = self._handler_for_backend(backend)

            for _ in range(self._max_attempts(backend)):
                try:
                    provider_tools = handler.prepare_tools(tools)
                    raw = handler.create_completion(
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stream=False,
                        tools=provider_tools,
                    )
                    return handler.normalize_completion_response(raw)
                except Exception as exc:
                    error = self._normalize_exception(backend, exc)
                    if isinstance(error, LLMTimeoutError):
                        self._sleep_before_retry()
                        continue
                    backend_errors.append(str(error))
                    break

        raise LLMBackendError("; ".join(backend_errors))

    def fetch_stream(
        self,
        msg: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.4,
        max_tokens: int = 4096,
        output_reasoning: bool = False,
        context_handler: Optional[ContextHandler] = None,
        backend_name: Optional[str] = None,
        tools: Optional[Sequence[ToolDefinition]] = None,
    ) -> Generator[str, None]:
        """Execute a streaming completion with backend fallback and retry.

        Behaviour is identical to ``fetch`` except that response text is
        yielded incrementally as an async generator.  If a timeout occurs
        before any text has been yielded, the backend is retried.  Once
        text has been yielded, an error on the same backend is propagated
        immediately.

        Args:
            msg:
                The current user message text.
            system_prompt:
                Optional system-level instruction.
            temperature:
                Sampling temperature.  Defaults to 0.4.
            max_tokens:
                Maximum tokens in the generated response.  Defaults to 4096.
            output_reasoning:
                When ``True``, include the model's reasoning content in the
                yielded text stream.  The exact format depends on the
                backend handler.
            context_handler:
                A ``ContextHandler`` instance holding conversation history. 
                When provided, its ``build_messages`` method is used to
                construct the full message list including history.  Pass
                ``None`` for stateless single-turn calls.
            backend_name:
                Explicit backend to use.  ``None`` means the default.
            tools:
                Optional tool definitions.  See ``fetch`` for details.

        Yields:
            Normalised text chunks from the LLM response.  Chunks are
            strings that should be concatenated to form the full response.

        Raises:
            LLMBackendError:
                All candidate backends have been exhausted without yielding
                any output.
            LLMError:
                A backend fails after partial output has already been
                yielded.  The stream cannot continue.
        """
        messages = self._build_messages(msg, system_prompt, context_handler)
        backend_errors: List[str] = []

        for backend in self._resolve_backends(backend_name, self.fallback_order):
            handler = self._handler_for_backend(backend)
            yielded_any = False

            for _ in range(self._max_attempts(backend)):
                try:
                    provider_tools = handler.prepare_tools(tools)
                    raw = handler.create_completion(
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stream=True,
                        tools=provider_tools,
                    )
                    for text in handler.iter_stream_text(
                        raw, output_reasoning=output_reasoning,
                    ):
                        yielded_any = True
                        yield text
                    return
                except Exception as exc:
                    error = self._normalize_exception(backend, exc)
                    if (
                        isinstance(error, LLMTimeoutError)
                        and not yielded_any
                    ):
                        self._sleep_before_retry()
                        continue
                    if yielded_any:
                        raise error
                    backend_errors.append(str(error))
                    break

        raise LLMBackendError("; ".join(backend_errors))

    # -- helpers ----------------------------------------------------------------

    @staticmethod
    def _max_attempts(backend: LLMBackendConfig) -> int:
        """Return the number of times to attempt a request for a backend.

        At least one attempt is always made, even when ``max_retries``
        is set to 0.

        Args:
            backend: The backend configuration to read ``max_retries`` from.

        Returns:
            The total number of attempts (1 + retries).
        """
        return max(1, int(backend.max_retries))

    @staticmethod
    def _build_messages(
        msg: str,
        system_prompt: Optional[str],
        context: Optional[ContextHandler],
    ) -> List[Dict[str, Any]]:
        """Build the message list, delegating to a context handler when available.

        When *context* is provided, its ``build_messages()`` is called
        to retrieve the stored conversation history.  The system prompt
        and current user message are always appended by this method so
        that the context handler stays focused purely on history.

        Args:
            msg: The current user message text.
            system_prompt: Optional system-level instruction.
            context: An optional ``ContextHandler`` with conversation history.

        Returns:
            A list of message dicts ready for the backend handler.
        """
        messages: List[Dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if context is not None:
            messages.extend(context.build_messages())
        if msg:
            messages.append({"role": "user", "content": msg})
        
        return messages
