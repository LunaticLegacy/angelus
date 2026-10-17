"""
Abstract:

    Agent handler should handle agent's creation, status modify and tool.
    There should be a factory for the Agent.

"""
from typing import Optional, List, Callable, Any, Mapping, Sequence
from pathlib import Path

from llmfetcher import Agent, LLMBackendConfig, LLMFetcher, Tool
from llmfetcher.context_handlers import (
    DEFAULT_CONTEXT_HANDLER,
    ContextHandler,
    ContextProvider,
    create_context_handler,
)
from llmfetcher.context_handlers.sage import SageContext, create_sage_tools
from llmfetcher.graph_memory import GraphContextHandler, create_graph_tools

def create_agent(
    configs: List[LLMBackendConfig],
    tools: List[Tool],
    *,
    system_prompt: str,
    max_concurrency: int = 3,
    max_context_threshold: int = 262144,
    compaction_output_max_tokens: int = 8192,
    keep_recent: int = 0,
    context_path: Optional[str | Path] = "",
    context_handler_name: str = DEFAULT_CONTEXT_HANDLER,
    context_handler: Optional[ContextHandler] = None,
    context_settings: Mapping[str, Any] | None = None,
    context_providers: Sequence[ContextProvider] = (),
    default_max_rounds: int = 30,
    default_max_tokens: int = 32768,
    enable_stop_turn: bool = False,
    default_stream: bool = True,
    output_reasoning: bool = True,
    thinking_mode: str = "auto",
    reasoning_effort: str = "auto",
    tool_result_transformer: Callable[[str, str, str], str] | None = None,
    image_resolver: Callable[[dict[str, Any]], dict[str, str]] | None = None,
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
        keep_recent: Number of newest active entries compaction keeps verbatim
            instead of summarising. ``0`` summarises the whole active
            transcript.
        context_path: Optional persisted context file path.
        context_handler_name: Registered handler id to build when
            ``context_handler`` is omitted. The selectable ids come from
            :func:`llmfetcher.context_handlers.available_context_handlers`.
        context_handler: Optional custom context implementation, such as
            ``RetrievedContextHandler``. Takes precedence over
            ``context_handler_name``.
        context_providers: Optional plugin providers registered on the
            Agent's ``ContextComposer`` before the first request.
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
        image_resolver: Session-owned image lookup used only for model I/O.
    
    Returns:
        Fully configured but not yet executing Agent.

    Raises:
        ValueError: If either default execution budget is negative or the
            token budget is not positive, or if ``context_handler_name`` is
            not a registered context handler.

    Side Effects:
        Creates the parent directory of ``context_path`` when persistence is
        enabled, before the Agent can write its first checkpoint.

    """
    fetcher = LLMFetcher(configs)
    fetcher.image_resolver = image_resolver
    # The llmfetcher registry owns both the selectable list and the default;
    # an explicitly injected handler still wins for specialised hosts.
    if context_handler is None:
        context_handler = create_context_handler(
            context_handler_name,
            fetcher=fetcher,
            max_context_threshold=max_context_threshold,
            compaction_output_max_tokens=compaction_output_max_tokens,
            keep_recent=keep_recent,
            settings=(context_settings or {}).get(context_handler_name, {}),
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
        output_reasoning=output_reasoning,
        thinking_mode=thinking_mode,
        reasoning_effort=reasoning_effort,
        context_path=context_path,
        context_handler=context_handler,
        tool_result_transformer=tool_result_transformer,
        context_providers=tuple(context_providers),
    )
    # Tool ownership belongs to the Agent factory. Session ownership is
    # established later by SessionHandler.
    agent.add_tools(tools=tools)
    # Sage coordination tools are bound to this Agent's handler instance.
    # They enqueue branch mutations and are applied by Agent at the round
    # boundary, so separate Sage Agents never share worktree state.
    if isinstance(context_handler, SageContext):
        agent.add_tools(tools=create_sage_tools(context_handler))
    if isinstance(context_handler, GraphContextHandler):
        agent.add_tools(tools=create_graph_tools(context_handler))
    return agent
