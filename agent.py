from __future__ import annotations

from typing import List, Any, Optional, Dict
from pathlib import Path

from .llm_fetcher import LLMBackendConfig, LLMFetcher, LLMBackendHandler
from .llm_types import Tool, LLMOutput, TokenUsage
from .tool_handler import ToolHandler
from .tool_executor import ToolExecutor
from .context_handlers import ContextHandlerLinear, ContextHandler
from .events import ExecutionEvent, ExecutionHook


class Agent:
    def __init__(
        self,
        llm_fetcher: LLMFetcher,
        *,
        system_prompt: str,
        max_concurrency: int = 3,
        max_context_threshold: int = 262144,
        context_path: Optional[str | Path] = "",
    ):
        self.llm_fetcher = llm_fetcher
        self.system_prompt = system_prompt
        self.max_concurrency = max_concurrency
        self.max_context_threshold = max_context_threshold
        self.context_path = Path(context_path) if context_path else None

        self.tool_handler: ToolHandler = ToolHandler()
        self.tool_executor: ToolExecutor = ToolExecutor(
            max_concurrency=self.max_concurrency,
        )
        self.context_handler: ContextHandler = ContextHandlerLinear(
            compacting_llmfetcher_handler=self.llm_fetcher,
            max_context_threshold=self.max_context_threshold,
        )

        # Cumulative token usage across all rounds of the most recent run.
        self.usage: TokenUsage = TokenUsage()

        # hook system
        self.hooks: list[ExecutionHook] = []

    # -- hooks ----------------------------------------------------------

    def add_hook(self, hook: ExecutionHook) -> None:
        """Register a hook that receives :class:`ExecutionEvent` records."""
        self.hooks.append(hook)

    def _emit(
        self,
        source: str,
        agent_name: str,
        event_type: str,
        message: str = "",
        data: Any = None,
    ) -> None:
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
        return self.tool_handler.add_tool(tool=tool)

    def add_tools(self, tools: List[Tool]) -> bool:
        results: List[bool] = [False for _ in range(len(tools))]
        for idx, tool in enumerate(tools):
            results[idx] = self.add_tool(tool=tool)

        out = True
        for r in results:
            out *= r
        return bool(out)

    # -- internal --------------------------------------------------------

    def _build_prompt(self) -> str:
        return (
            self.system_prompt
            + "\n"
            + self.tool_handler.get_all_tool_description()
        )

    # -- run ------------------------------------------------------------

    def run(
        self,
        message: str,
        max_rounds: int = 30,
        temperature: float = 0.4,
        max_tokens: int = 32768,
        verbose: bool = False,
    ) -> LLMOutput:
        """Run agent call.

        Args:
            message: user input's message.
            max_rounds: maximum rounds for this.
            temperature: temperature for model.
            max_tokens: how much tokens does output generate (per turn).
            verbose: whether to verbose debug info.

        Returns:
            Return the last round of the LLM agent.
        """
        name = getattr(self, "_agent_name_in_graph", "")

        self._emit("agent", name, "agent:start", message)

        prompt: str = self._build_prompt()
        tool_results: Optional[Dict[str, str]] = None
        have_tool_call: bool = False

        load_result: bool = self.context_handler.load(self.context_path)
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

        result: LLMOutput

        for round_idx in range(1, 1 + max_rounds):
            if verbose:
                print("=" * 10 + "  ROUND " + str(round_idx) + "=" * 10)

            result = self.llm_fetcher.fetch(
                msg=message,
                system_prompt=prompt,
                temperature=temperature,
                context_handler=self.context_handler,
                max_tokens=max_tokens,
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
                handlers, arguments = (
                    self.tool_handler.get_handlers_and_arguments(
                        list(result.tool_calls),
                    )
                )
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
                },
            )

            if verbose:
                print("\n", tool_results, "\n")

            self.context_handler.add_assistant_message(
                message=result,
                tool_results=tool_results,
            )

            if not have_tool_call:
                break

        save_result: bool = self.context_handler.save(self.context_path)
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

        return result

    def close(self) -> None:
        """Release sub-interpreter resources held by the tool executor."""
        self.tool_executor.close()
