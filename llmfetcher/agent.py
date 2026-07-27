from __future__ import annotations

import threading
import time
from typing import List, Any, Optional, Dict, Protocol
from pathlib import Path

from .llm_fetcher import LLMBackendConfig, LLMFetcher, LLMBackendHandler
from .llm_types import Tool, LLMOutput, TokenUsage
from .tool_handler import ToolHandler
from .tool_executor import ToolExecutor
from .context_handlers import ContextHandlerLinear, ContextHandler
from .events import ExecutionEvent, ExecutionHook


class AgentRunControl(Protocol):
    """Describe cooperative controls read between completed Agent steps.

    Implementations may persist requests in a database or keep them in an
    application-specific queue. Methods are deliberately only called after a
    model response and its tool batch have completed.
    """

    def should_stop(self) -> bool:
        """Return whether the Agent should stop at the current safe boundary."""
        ...

    def drain_steers(self) -> list[str]:
        """Return and consume queued user steering messages in FIFO order."""
        ...


class AgentRunStopped(RuntimeError):
    """Signal a cooperative stop after durable completion of one Agent step.

    Args:
        message: Human-readable reason for ending the current run.
        last_output: Model result from the completed boundary. It is ``None``
            only when no model round completed before the stop was observed.

    The exception is raised only after the latest assistant message has been
    added to the context and that context has been saved. Browser callers use
    ``last_output`` to persist the matching display transcript.
    """

    def __init__(self, message: str, *, last_output: LLMOutput | None = None) -> None:
        super().__init__(message)
        self.last_output = last_output


def _tool_result_text(value: Any) -> str:
    """Return the complete tool-result string for persistence and events.

    Args:
        value: Raw value returned by a tool handler.
    Returns:
        Complete string form of ``value`` without a display or persistence limit.
    """
    return str(value)


class Agent:
    def __init__(
        self,
        llm_fetcher: LLMFetcher,
        *,
        system_prompt: str,
        max_concurrency: int = 3,
        max_context_threshold: int = 262144,
        context_path: Optional[str | Path] = "",
        context_handler: Optional[ContextHandler] = None,
        default_max_rounds: int = 30,
        default_max_tokens: int = 32768,
    ):
        """Initialize one tool-using Agent.

        Args:
            llm_fetcher: Backend dispatcher used for model rounds.
            system_prompt: Instructions supplied to the model.
            max_concurrency: Maximum concurrent tool handlers.
            max_context_threshold: Context size at which compaction starts.
            context_path: Optional persisted context file path.
            context_handler: Optional custom context implementation, such as
                ``RetrievedContextHandler``.
            default_max_rounds: Default maximum model-and-tool steps for a
                ``run`` call that omits ``max_rounds``. ``0`` means unlimited.
            default_max_tokens: Default maximum generated tokens per model
                step for a ``run`` call that omits ``max_tokens``.

        Returns:
            None.

        Raises:
            ValueError: If either default execution budget is negative or the
                token budget is not positive.
        """
        if default_max_rounds < 0:
            raise ValueError("default_max_rounds must be zero or greater")
        if default_max_tokens <= 0:
            raise ValueError("default_max_tokens must be greater than zero")
        self.llm_fetcher = llm_fetcher
        self.system_prompt = system_prompt
        self.max_concurrency = max_concurrency
        self.max_context_threshold = max_context_threshold
        self.context_path = Path(context_path) if context_path else None
        self.default_max_rounds = default_max_rounds
        self.default_max_tokens = default_max_tokens

        self.tool_handler: ToolHandler = ToolHandler()
        self.tool_executor: ToolExecutor = ToolExecutor(
            max_concurrency=self.max_concurrency,
        )
        self.context_handler: ContextHandler = context_handler or ContextHandlerLinear(
            compacting_llmfetcher_handler=self.llm_fetcher,
            max_context_threshold=self.max_context_threshold,
        )

        # This attribute will be assigned by ExecutionGraph so Agent-level events retain their node.
        self._agent_name_in_graph: str = ""

        # Cumulative token usage across all rounds of the most recent run.
        self.usage: TokenUsage = TokenUsage()

        # hook system
        self.hooks: list[ExecutionHook] = []

        # Terminal workflow tools request this event after persisting their
        # result. ``run`` observes it only at a complete step boundary.
        self._completion_requested = threading.Event()

    # -- hooks ----------------------------------------------------------

    def add_hook(self, hook: ExecutionHook) -> None:
        """Register an execution-event receiver.

        Args:
            hook: Callback invoked synchronously for each agent event.

        Returns:
            None.
        """
        self.hooks.append(hook)

    def remove_hook(self, hook: ExecutionHook) -> bool:
        """Unregister one execution-event receiver.

        Args:
            hook: Previously registered callback.

        Returns:
            ``True`` when the callback was removed, otherwise ``False``.
        """
        try:
            self.hooks.remove(hook)
        except ValueError:
            return False
        return True

    def request_completion(self) -> None:
        """Request completion after the active model-and-tool step finishes.

        Terminal workflow tools, such as a dispatched worker's
        ``report_task``, call this method after writing their durable result.
        The request never interrupts model inference or a parallel tool batch;
        ``run`` observes it only after that complete step is stored.

        Returns:
            None.
        """
        self._completion_requested.set()

    def _emit(
        self,
        source: str,
        agent_name: str,
        event_type: str,
        message: str = "",
        data: Any = None,
    ) -> None:
        """Send one event to each registered hook, isolating hook failures.

        Args:
            source: Event source identifier.
            agent_name: Stable graph name of the emitting Agent.
            event_type: Machine-readable lifecycle event name.
            message: Human-readable event description.
            data: Optional structured event payload.

        Returns:
            None.
        """
        event = ExecutionEvent(
            source=source,
            agent_name=agent_name,
            event_type=event_type,
            message=message,
            data=data,
        )
        for hook in self.hooks:
            try:
                hook(event)
            except Exception:
                pass

    # -- tool registration ----------------------------------------------

    def add_tool(self, tool: Tool) -> bool:
        """Register one callable tool on this Agent.

        Args:
            tool: Tool schema and handler exposed to the model.

        Returns:
            ``True`` when registration succeeds, otherwise ``False``.
        """
        return self.tool_handler.add_tool(tool=tool)

    def add_tools(self, tools: List[Tool]) -> bool:
        """Register a batch of tools in the supplied order.

        Args:
            tools: Tool definitions to register.

        Returns:
            ``True`` only when every registration succeeds.
        """
        results: List[bool] = [False for _ in range(len(tools))]
        for idx, tool in enumerate(tools):
            results[idx] = self.add_tool(tool=tool)

        out = True
        for r in results:
            out *= r
        return bool(out)

    # -- internal --------------------------------------------------------

    def _build_prompt(self) -> str:
        """Combine the system prompt and current tool descriptions.

        Returns:
            Complete model-facing system prompt text.
        """
        return (
            self.system_prompt
            + "\n"
            + self.tool_handler.get_all_tool_description()
        )

    def _save_context(self) -> bool:
        """Persist the current context when this Agent has a storage path.

        Returns:
            ``True`` when a configured context was saved successfully;
            ``False`` when persistence is disabled or the handler reports a
            write failure.

        This helper is called for both ordinary completion and cooperative
        stops so a completed model-and-tool boundary is never lost merely
        because execution will not enter another round.
        """
        if self.context_path is None:
            return False
        return self.context_handler.save(self.context_path)

    # -- run ------------------------------------------------------------

    def run(
        self,
        message: str,
        max_rounds: int | None = None,
        temperature: float = 0.4,
        max_tokens: int | None = None,
        verbose: bool = False,
        control: AgentRunControl | None = None,
    ) -> LLMOutput:
        """Run the Agent until it responds, reaches a budget, or completes.

        Args:
            message: User request or explicit task package for this run.
            max_rounds: Maximum model-and-tool steps. ``None`` uses the
                Agent's ``default_max_rounds``; ``0`` means unlimited.
            temperature: Model sampling temperature.
            max_tokens: Maximum generated tokens per model step. ``None``
                uses the Agent's ``default_max_tokens``.
            verbose: Whether to print per-round diagnostic output.
            control: Optional cooperative stop and steering source. It is read
                after each completed model-and-tool step, never mid-step.

        Returns:
            Last model output produced by the Agent.

        Raises:
            ValueError: If a resolved execution budget is negative or the
                token budget is not positive.
            AgentRunStopped: If ``control`` requests a stop after a completed
                model-and-tool boundary. That boundary is persisted before
                the exception is raised.
            RuntimeError: If execution completes without a model response.
        """
        resolved_max_rounds = self.default_max_rounds if max_rounds is None else max_rounds
        resolved_max_tokens = (
            self.default_max_tokens if max_tokens is None else max_tokens
        )
        if resolved_max_rounds < 0:
            raise ValueError("max_rounds must be zero or greater")
        if resolved_max_tokens <= 0:
            raise ValueError("max_tokens must be greater than zero")
        self._completion_requested.clear()
        name = self._agent_name_in_graph

        backend = self.llm_fetcher.default_backend_config
        self._emit(
            "agent",
            name,
            "agent:start",
            message,
            data={
                "backend": {
                    "name": backend.name,
                    "provider": backend.provider,
                    "model": backend.model,
                },
                "tools": [
                    {"name": tool.name, "description": tool.description}
                    for tool in self.tool_handler.get_all_tools()
                ],
            },
        )

        prompt: str = self._build_prompt()
        tool_results: Optional[Dict[str, str]] = None
        have_tool_call: bool = False

        load_result = (
            self.context_handler.load(self.context_path)
            if self.context_path is not None
            else False
        )
        if verbose:
            if not load_result:
                print(
                    "Context not loaded, check for whether file not exist "
                    "or else issues."
                )
            else:
                print("Context loaded: ", self.context_path)

        self.context_handler.add_user_message(message=message)
        self.usage = TokenUsage()

        result: LLMOutput | None = None
        round_idx = 0

        while resolved_max_rounds == 0 or round_idx < resolved_max_rounds:
            round_idx += 1
            if verbose:
                print("=" * 10 + "  ROUND " + str(round_idx) + "=" * 10)

            round_started_at = time.perf_counter()
            result = self.llm_fetcher.fetch(
                msg=message,
                system_prompt=prompt,
                temperature=temperature,
                context_handler=self.context_handler,
                max_tokens=resolved_max_tokens,
                tools=self.tool_handler.get_all_tools(),
            )

            # Accumulate token usage across rounds.
            if result.usage:
                u = result.usage
                self.usage.input_tokens += u.input_tokens
                self.usage.output_tokens += u.output_tokens
                self.usage.total_tokens += u.total_tokens
                self.usage.cached_tokens += u.cached_tokens
                self.usage.reasoning_tokens += u.reasoning_tokens

            if verbose:
                print(str(result))
                print("")
                print("Tool calls: ", result.tool_calls)
                print("Tool calls nums: ", len(result.tool_calls))

            # parse for tool call. batch execution.
            if result.tool_calls:
                requested_calls = [
                    {
                        "call_id": tool_call.call_id or f"call_{index}",
                        "name": tool_call.name,
                        "args": tool_call.arguments,
                    }
                    for index, tool_call in enumerate(result.tool_calls)
                ]
                self._emit(
                    "agent",
                    name,
                    "agent:tools_requested",
                    f"Requested {len(requested_calls)} tool call(s)",
                    data={"round": round_idx, "tool_calls": requested_calls},
                )

                handlers, arguments = (
                    self.tool_handler.get_handlers_and_arguments(
                        list(result.tool_calls),
                    )
                )
                tool_started_at = time.perf_counter()
                results_list: List[Any] = self.tool_executor.execute_batch(
                    handlers, arguments,
                )
                tool_results = dict([
                    (tc.call_id or f"call_{i}", str(r))
                    for i, (tc, r) in enumerate(
                        zip(result.tool_calls, results_list),
                    )
                ])
                have_tool_call = True

                # Publish complete outcomes so persistence and export never lose tool evidence.
                completed_calls = []
                for call, raw_result in zip(requested_calls, results_list):
                    result_ok = not isinstance(raw_result, Exception)
                    if isinstance(raw_result, dict) and raw_result.get("ok") is False:
                        result_ok = False
                    completed_calls.append({
                        **call,
                        "ok": result_ok,
                        "result": _tool_result_text(raw_result),
                    })
                self._emit(
                    "agent",
                    name,
                    "agent:tools_completed",
                    f"Completed {len(completed_calls)} tool call(s)",
                    data={
                        "round": round_idx,
                        "duration_ms": round((time.perf_counter() - tool_started_at) * 1000),
                        "tool_calls": completed_calls,
                    },
                )
            else:
                tool_results = None
                have_tool_call = False

            self._emit(
                "agent", name, "agent:round",
                f"Round {round_idx}, {len(result.tool_calls)} tool call(s)",
                data={
                    "round": round_idx,
                    "tool_call_count": len(result.tool_calls),
                    "tool_calls": [
                        {"name": tc.name, "args": tc.arguments}
                        for tc in result.tool_calls
                    ],
                    "usage": {
                        "input": self.usage.input_tokens,
                        "output": self.usage.output_tokens,
                        "total": self.usage.total_tokens,
                    },
                    "round_usage": {
                        "input": result.usage.input_tokens if result.usage else 0,
                        "output": result.usage.output_tokens if result.usage else 0,
                        "total": result.usage.total_tokens if result.usage else 0,
                        "cached": result.usage.cached_tokens if result.usage else 0,
                        "reasoning": result.usage.reasoning_tokens if result.usage else 0,
                    },
                    "duration_ms": round((time.perf_counter() - round_started_at) * 1000),
                    "assistant_content": result.content,
                    "reasoning_content": result.reasoning_content,
                },
            )

            if verbose:
                print("\n", tool_results, "\n")

            self.context_handler.add_assistant_message(
                message=result,
                tool_results=tool_results,
            )

            if self._completion_requested.is_set():
                self._emit(
                    "agent", name, "agent:completion_requested",
                    f"Completed after terminal tool in round {round_idx}",
                    data={"round": round_idx},
                )
                break

            # Persist before checking controls because stops are observed only
            # after a completed response and its complete tool batch.
            if control is not None and control.should_stop():
                self._save_context()
                self._emit(
                    "agent", name, "agent:stopped",
                    f"Stopped after round {round_idx}",
                    data={"round": round_idx},
                )
                raise AgentRunStopped(
                    "Agent stopped after the current step",
                    last_output=result,
                )

            # Safe controls are intentionally observed after response
            # persistence and the complete tool batch, preserving one step.
            steers = control.drain_steers() if control is not None else []
            if steers:
                for steer in steers:
                    self.context_handler.add_user_message(message=steer)
                message = steers[-1]
                self._emit(
                    "agent", name, "agent:steer_applied",
                    f"Applied {len(steers)} steering message(s)",
                    data={"round": round_idx, "messages": steers},
                )

            if not have_tool_call and not steers:
                break

        save_result = self._save_context()
        if verbose:
            if not save_result:
                print("Context saving failed.")
            else:
                print("Context saved at: ", self.context_path)

        self._emit(
            "agent", name, "agent:complete",
            f"Completed in {round_idx} round(s), "
            f"{self.usage.total_tokens} total tokens",
            data={
                "rounds": round_idx,
                "usage": {
                    "input": self.usage.input_tokens,
                    "output": self.usage.output_tokens,
                    "total": self.usage.total_tokens,
                },
                "output_len": len(result.content) if result else 0,
            },
        )

        if result is None:
            raise RuntimeError("Agent completed without a model response")
        return result

    def close(self) -> None:
        """Release sub-interpreter resources held by the tool executor."""
        self.tool_executor.close()

    def clear_context(self) -> None:
        """
        Clear context.
        """
        self.context_handler.clear_context()
