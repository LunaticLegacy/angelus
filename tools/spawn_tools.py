"""Tool factory: expose swarm graph mutation as Agent-callable tools.

Usage
-----
These tools are given to a **coordinator** agent so it can dynamically spawn
worker agents, wire them into the execution graph, and inspect topology at
runtime::

    from modules.llmfetcher.tools.spawn_tools import create_swarm_tools

    coordinator.add_tools(
        create_swarm_tools(
            swarm=my_swarm,
            llm_fetcher=llm_fetcher,
            worker_tool_pool=global_tools,
        )
    )
"""

from __future__ import annotations

from typing import Any

from ..agent import Agent
from ..llm_fetcher import LLMFetcher
from ..llm_types import Tool, ToolParameter, ToolSchema
from ..swarm_module.swarm import AgentSwarm


def create_swarm_tools(
    swarm: AgentSwarm,
    llm_fetcher: LLMFetcher,
    worker_tool_pool: list[Tool],
) -> list[Tool]:
    """Create tools that let a coordinator LLM manipulate the swarm at runtime.

    Args:
        swarm:
            The running swarm instance. The coordinator must be registered
            in this swarm so its tool calls can mutate the graph.
        llm_fetcher:
            Shared ``LLMFetcher`` used to create new worker ``Agent``
            instances.
        worker_tool_pool:
            Tools that are registered on every worker created by the
            coordinator.

    Returns:
        A list of ``Tool`` instances the coordinator can call.
    """

    def _dynamic_add_agent(**kwargs: Any) -> str:
        """Create and register a new worker agent in the swarm.

        Each new agent receives the shared *worker_tool_pool* and a
        customized system *prompt*.

        Required parameters: ``name`` (unique agent name), ``system_prompt``.
        """
        name: str = kwargs.get("name", "")
        system_prompt: str = kwargs.get("system_prompt", "")

        if not name or not system_prompt:
            return "Error: both 'name' and 'system_prompt' are required."

        agent = Agent(
            llm_fetcher=llm_fetcher,
            system_prompt=system_prompt,
        )
        agent.add_tools(worker_tool_pool)

        return swarm.dynamic_add_agent(name, agent)

    def _dynamic_add_connection(**kwargs: Any) -> str:
        """Add a directed dependency edge between two agents.

        After this call, *target* waits for *source* to complete before
        it may execute.  The source must not have finished yet.

        Required: ``source``, ``target``.
        """
        source: str = kwargs.get("source", "")
        target: str = kwargs.get("target", "")

        if not source or not target:
            return "Error: both 'source' and 'target' are required."

        return swarm.dynamic_add_connection(source, target)

    def _dynamic_remove_agent(**kwargs: Any) -> str:
        """Remove an agent and every edge connected to it."""
        name: str = kwargs.get("name", "")
        if not name:
            return "Error: 'name' is required."
        return swarm.dynamic_remove_agent(name)

    def _dynamic_get_info(**kwargs: Any) -> str:
        """Return the current graph topology as structured text.

        Useful for inspecting which agents are registered and how they
        are connected before deciding on next steps.
        """
        return swarm.dynamic_get_info()

    return [
        Tool(
            name="dynamic_add_agent",
            description=(
                "Create and register a new worker agent in the execution graph. "
                "The new agent will receive the shared worker tools (web fetch, "
                "KB read/write, clock).  After creation, connect it to the graph "
                "with dynamic_add_connection."
            ),
            schemas=ToolSchema(
                properties=[
                    ToolParameter(
                        name="name",
                        type="string",
                        description="Unique name for the new agent (e.g. 'worker_mexico'). Must not conflict with existing names.",
                    ),
                    ToolParameter(
                        name="system_prompt",
                        type="string",
                        description="Full system prompt for the new worker agent.",
                    ),
                ],
            ),
            handler=_dynamic_add_agent,
        ),
        Tool(
            name="dynamic_add_connection",
            description=(
                "Add a dependency edge from source to target. "
                "The target agent will not execute until the source has completed. "
                "Connect workers to the coordinator AFTER creating them, so they "
                "run when the coordinator finishes."
            ),
            schemas=ToolSchema(
                properties=[
                    ToolParameter(
                        name="source",
                        type="string",
                        description="Name of the predecessor agent (e.g. 'coordinator').",
                    ),
                    ToolParameter(
                        name="target",
                        type="string",
                        description="Name of the successor agent (e.g. 'worker_mexico').",
                    ),
                ],
            ),
            handler=_dynamic_add_connection,
        ),
        Tool(
            name="dynamic_remove_agent",
            description=(
                "Remove an agent and every edge connected to it from the graph. "
                "Useful to clean up failed or misconfigured workers."
            ),
            schemas=ToolSchema(
                properties=[
                    ToolParameter(
                        name="name",
                        type="string",
                        description="Name of the agent to remove.",
                    ),
                ],
            ),
            handler=_dynamic_remove_agent,
        ),
        Tool(
            name="dynamic_get_info",
            description=(
                "Inspect the current execution graph: list registered agents, "
                "their connections, and concurrency limits. Useful before "
                "creating or removing workers."
            ),
            schemas=ToolSchema(properties=[]),
            handler=_dynamic_get_info,
        ),
    ]
