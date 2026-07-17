"""
AgentSwarm — multi-agent orchestration via dependency-driven execution graph.

Wraps :class:`ExecutionGraph` with a simplified API. See the graph module
for full details on scheduling semantics.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from ..agent import Agent
from ..events import ExecutionHook
from .execution_graph import (
    ExecutionGraph,
    MapperFn,
    RouterFn,
)


class AgentSwarm:
    """Orchestrate multiple agents through an execution graph.

    Typical usage — sequential pipeline::

        swarm = AgentSwarm(max_concurrency_agents=2)
        swarm.add_agent("researcher", researcher_agent)
        swarm.add_agent("writer", writer_agent)
        swarm.add_connection("researcher", "writer")
        outputs = swarm.run("Explore and report on topic X")

    Fan-out + fan-in::

        swarm = AgentSwarm(max_concurrency_agents=4)
        swarm.add_agent("root", root_agent)
        swarm.add_agent("a", agent_a)
        swarm.add_agent("b", agent_b)
        swarm.add_agent("merge", merge_agent)
        swarm.add_split("root", ["a", "b"])
        swarm.add_gather(["a", "b"], "merge")
        outputs = swarm.run("Analyze from two perspectives")
    """

    def __init__(self, max_concurrency_agents: int = 8) -> None:
        """Create a public facade around an execution graph.

        Args:
            max_concurrency_agents: Maximum concurrent Agent executions.

        Returns:
            None.
        """
        self._graph = ExecutionGraph(
            max_concurrency_agents=max_concurrency_agents,
        )

    # ------------------------------------------------------------------
    # Graph construction  —  agents
    # ------------------------------------------------------------------

    def add_agent(self, agent_name: str, agent_instance: Agent) -> bool:
        """Register an ``Agent`` instance as a graph vertex."""
        return self._graph.add_agent(agent_name, agent_instance)

    def add_routing_node(self, name: str, router: RouterFn) -> bool:
        """Register a lightweight non-LLM routing node."""
        return self._graph.add_routing_node(name, router)

    def remove_agent(self, agent_name: str) -> bool:
        """Remove a registered agent and every edge connected to it."""
        return self._graph.remove_agent(agent_name)

    # ------------------------------------------------------------------
    # Graph construction  —  edges
    # ------------------------------------------------------------------

    def add_connection(self, source: str, target: str) -> bool:
        """Add a directed dependency edge from *source* to *target*."""
        return self._graph.add_connection(source, target)

    def add_split(self, source: str, targets: list[str]) -> None:
        """Broadcast one agent's output to multiple successors."""
        self._graph.add_split(source, targets)

    def add_gather(
        self,
        sources: list[str],
        target: str,
        mapper: MapperFn | None = None,
    ) -> None:
        """Make *target* depend on and aggregate outputs from *sources*."""
        self._graph.add_gather(sources, target, mapper)

    # ------------------------------------------------------------------
    # Graph construction  —  mappers (node-level)
    # ------------------------------------------------------------------

    def set_mapper(self, agent_name: str, mapper: MapperFn) -> None:
        """Set a node-level mapper that converts predecessor outputs into
        the agent's input message."""
        self._graph.set_mapper(agent_name, mapper)

    # ------------------------------------------------------------------
    # Graph construction  —  routers (dynamic successor selection)
    # ------------------------------------------------------------------

    def set_router(self, agent_name: str, router: RouterFn) -> None:
        """Attach a post-completion router to an existing agent."""
        self._graph.set_router(agent_name, router)

    def remove_router(self, agent_name: str) -> bool:
        """Remove a post-completion router from an agent."""
        return self._graph.remove_router(agent_name)

    # ------------------------------------------------------------------
    # Dynamic mutation  —  thread-safe, usable during run()
    # ------------------------------------------------------------------

    def dynamic_add_agent(
        self, agent_name: str, agent_instance: Agent,
    ) -> str:
        """Dynamically register an ``Agent`` instance during execution."""
        return self._graph.dynamic_add_agent(agent_name, agent_instance)

    def dynamic_remove_agent(self, agent_name: str) -> str:
        """Dynamically remove an agent and its edges during execution."""
        return self._graph.dynamic_remove_agent(agent_name)

    def dynamic_add_connection(self, source: str, target: str) -> str:
        """Dynamically add a dependency edge during execution."""
        return self._graph.dynamic_add_connection(source, target)

    def dynamic_remove_connection(self, source: str, target: str) -> str:
        """Dynamically remove a dependency edge during execution."""
        return self._graph.dynamic_remove_connection(source, target)

    def dynamic_set_mapper(self, agent_name: str, mode: str) -> str:
        """Dynamically set a declarative predecessor-output mapper."""
        return self._graph.dynamic_set_mapper(agent_name, mode)

    def dynamic_set_router(self, agent_name: str, targets: list[str]) -> str:
        """Dynamically set a fixed successor router."""
        return self._graph.dynamic_set_router(agent_name, targets)

    def dynamic_get_info(self) -> str:
        """Return current graph state as a structured string."""
        return self._graph.dynamic_get_info()

    # ------------------------------------------------------------------
    # Hooks
    # ------------------------------------------------------------------

    def add_hook(self, hook: ExecutionHook) -> None:
        """Register a hook that receives every :class:`ExecutionEvent`.

        The hook is forwarded to the underlying :class:`ExecutionGraph`.
        """
        self._graph.add_hook(hook)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def run(self, message: str) -> dict[str, Any]:
        """Execute the graph and return a mapping of agent name → output."""
        return self._graph.run(message)
