"""
Abstract:

    Agent handler should handle agent's creation, status modify and tool.
    There should be a factory for the Agent.

"""
from typing import Optional, List, Callable
from pathlib import Path

from llmfetcher import Agent, LLMBackendConfig, LLMFetcher, Tool
from llmfetcher.graph_memory import GraphContextHandler
from llmfetcher.context_handlers import ContextHandler

def create_agent(
    configs: List[LLMBackendConfig],
    tools: List[Tool],
    *,
    system_prompt: str,
    max_concurrency: int = 3,
    max_context_threshold: int = 262144,
    compaction_output_max_tokens: int = 8192,
    context_path: Optional[str | Path] = "",
    context_handler: Optional[ContextHandler] = None,
    default_max_rounds: int = 30,
    default_max_tokens: int = 32768,
    enable_stop_turn: bool = False,
    default_stream: bool = True,
    tool_result_transformer: Callable[[str, str, str], str] | None = None,
) -> Agent:
    """Build one configured Agent without assigning it to a session or run.

    Args:
        configs: Ordered backend configurations used to construct its fetcher.
        tools: Tool definitions added to the resulting Agent.

        system_prompt: Instructions supplied to the model.
        max_concurrency: Maximum concurrent tool handlers.
        max_context_threshold: Context size at which compaction starts.
        compaction_output_max_tokens: Maximum generated tokens for one
            compactor summary request.
        context_path: Optional persisted context file path.
        context_handler: Optional custom context implementation, such as
            ``RetrievedContextHandler``.
        default_max_rounds: Default maximum model-and-tool steps for a
            ``run`` call that omits ``max_rounds``. ``0`` means unlimited.
        default_max_tokens: Default maximum generated tokens per model
            step for a ``run`` call that omits ``max_tokens``.
        enable_stop_turn: Whether to register the reserved native
            ``stop_turn`` control tool. Hosts enable it when their user
            workflow needs a model-visible non-text terminal boundary.
        default_stream: Whether calls omitting ``stream`` should emit
            incremental lifecycle events while preserving final results.
        tool_result_transformer: Optional Session-owned transformation that
            persists large tool results before they enter model context.
    
    Returns:
        Fully configured but not yet executing Agent.

    Raises:
        ValueError: If either default execution budget is negative or the
            token budget is not positive.

    Side Effects:
        Creates the parent directory of ``context_path`` when persistence is
        enabled, before the Agent can write its first checkpoint.

    """
    fetcher = LLMFetcher(configs)
    # GraphContextHandler is the standard persistent context implementation.
    # Passing an explicit handler remains supported for specialised hosts.
    if context_handler is None:
        context_handler = GraphContextHandler(
            compacting_fetcher=fetcher,
            max_context_threshold=max_context_threshold,
            compaction_output_max_tokens=compaction_output_max_tokens,
        )
    if context_path:
        Path(context_path).parent.mkdir(parents=True, exist_ok=True)
    agent = Agent(
        fetcher,
        system_prompt=system_prompt,
        max_concurrency=max_concurrency,
        max_context_threshold=max_context_threshold,
        default_max_rounds=default_max_rounds,
        default_max_tokens=default_max_tokens,
        enable_stop_turn=enable_stop_turn,
        default_stream=default_stream,
        context_path=context_path,
        context_handler=context_handler,
        tool_result_transformer=tool_result_transformer,
    )
    # Tool ownership belongs to the Agent factory. Session ownership is
    # established later by SessionHandler.
    agent.add_tools(tools=tools)
    return agent
