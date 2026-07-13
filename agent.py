from typing import List, Any, Optional

from .llm_fetcher import LLMBackendConfig, LLMFetcher, LLMBackendHandler
from .llm_types import Tool, LLMOutput
from .tool_handler import ToolHandler
from .context_handlers import ContextHandlerLinear, ContextHandler


class Agent:
    def __init__(
        self,
        llm_fetcher: LLMFetcher,
        *,
        system_prompt: str,
        max_concurrency: int = 8,
        max_context_threshold: int = 65536
    ):
        self.llm_fetcher = llm_fetcher
        self.system_prompt = system_prompt
        self.max_concurrency = max_concurrency
        self.max_context_threshold = max_context_threshold
        
        self.tool_handler: ToolHandler = ToolHandler(
            max_concurrency=self.max_concurrency
        )
        self.context_handler: ContextHandler = ContextHandlerLinear(
            max_context_threshold=self.max_context_threshold
        )

        self.instance_elapsed_rounds: int = 0

    def add_tool(
        self,
        tool: Tool,
    ) -> bool:
        return self.tool_handler.add_tool(tool=tool)
    
    def add_tools(
        self,
        tools: List[Tool],
    ) -> bool:
        results: List[bool] = [False for _ in range(len(tools))]
        for idx, tool in enumerate(tools):
            results[idx] = self.add_tool(tool=tool)
        
        out = True
        for r in results:
            out *= r
        
        return out

    def _build_prompt(self) -> str:
        return self.system_prompt + "\n" \
            + self.tool_handler.get_all_tool_description()

    def run(
        self,
        message: str,
        max_rounds: int = 30,
        temperature: float = 0.4,
        max_tokens: int = 32768,
        verbose: bool = False
    ):

        prompt: str = self._build_prompt()
        tool_results: Optional[List[Any]] = None
        have_tool_call: bool = False

        for round in range(1, 1 + max_rounds):
           
            # prepare for round
            self.instance_elapsed_rounds += 1

            if verbose:
                print("=" * 10 + "  ROUND " + str(round) + "=" * 10)

            # fetch
            result: LLMOutput = self.llm_fetcher.fetch(
                msg=message,
                system_prompt=prompt,
                temperature=temperature,
                context=self.context_handler,
                max_tokens=max_tokens,
                tools=self.tool_handler.get_all_tools(),
            )

            if verbose:
                print(str(result))
                print("")
                print("Tool calls: ", result.tool_calls)
                print("Tool calls nums: ", len(result.tool_calls))

            # parse for tool call. batch execution.

            if result.tool_calls:  # List[LLMToolCall]
                results: List[Any] = self.tool_handler.execute_batch(
                    list(result.tool_calls)
                )
                tool_results = dict([
                    (tc.call_id or f"call_{i}", str(r))
                    for i, (tc, r) in enumerate(zip(result.tool_calls, results))
                ])
                have_tool_call = True
            else:
                tool_results = None
                have_tool_call = False
            
            if verbose:
                print("\n", tool_results, "\n")

            # and add this into
            self.context_handler.add_assistant_message(
                message=result,
                timeline=self.instance_elapsed_rounds,
                tool_results=tool_results,
            )

            if not have_tool_call:
                break

            

