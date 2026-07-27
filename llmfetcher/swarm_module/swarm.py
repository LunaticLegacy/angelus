"""
AgentSwarm — multi-agent orchestration via dependency-driven execution graph.

Wraps :class:`ExecutionGraph` with a simplified API. See the graph module
for full details on scheduling semantics.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from ..agent import Agent, AgentRunControl
from ..events import ExecutionHook
from .execution_graph import (
    ExecutionGraph,
    MapperFn,
    RouterFn,
)
from .task_bus import TaskAssignment, TaskReport


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

    def dispatch_task(
        self,
        *,
        agent_name: str,
        agent_instance: Agent,
        objective: str,
        handoff: str,
        reply_to: str,
        expected_artifacts: Iterable[str] = (),
        task_id: str = "",
    ) -> TaskAssignment:
        """Create and immediately schedule a task-addressed subagent.

        Args:
            agent_name: Unique graph name for the worker.
            agent_instance: Worker configured with task-report tools.
            objective: Concrete task delivered to the worker inbox.
            handoff: Bounded coordinator state relevant to the task.
            reply_to: Coordinator Agent that receives the final report.
            expected_artifacts: Optional detailed-output references expected.
            task_id: Optional stable task identifier.

        Returns:
            Immutable task assignment accepted by the graph task bus.
        """
        return self._graph.dispatch_task(
            agent_name=agent_name,
            agent_instance=agent_instance,
            objective=objective,
            handoff=handoff,
            reply_to=reply_to,
            expected_artifacts=expected_artifacts,
            task_id=task_id,
        )

    def report_task(
        self,
        *,
        task_id: str,
        reporter: str,
        status: str,
        summary: str,
        findings: Iterable[str] = (),
        evidence: Iterable[str] = (),
        artifacts: Iterable[str] = (),
        open_questions: Iterable[str] = (),
        recommended_next_action: str = "",
    ) -> TaskReport:
        """Submit one structured worker report to the assigned coordinator.

        Args:
            task_id: Correlation identifier from the assignment.
            reporter: Reporting worker name.
            status: Terminal task status.
            summary: Bounded conclusion.
            findings: Key claims or observations.
            evidence: Source or evidence references.
            artifacts: Persisted detailed-output references.
            open_questions: Remaining uncertainties.
            recommended_next_action: Suggested follow-up.

        Returns:
            Accepted immutable report.
        """
        return self._graph.report_task(
            task_id=task_id,
            reporter=reporter,
            status=status,
            summary=summary,
            findings=findings,
            evidence=evidence,
            artifacts=artifacts,
            open_questions=open_questions,
            recommended_next_action=recommended_next_action,
        )

    def wait_for_reports(
        self,
        task_ids: Iterable[str],
        timeout_seconds: float,
    ) -> list[TaskReport]:
        """Wait for reports from explicitly dispatched subagent tasks.

        Args:
            task_ids: Task identifiers expected by a coordinator.
            timeout_seconds: Maximum wait duration in seconds.

        Returns:
            Available reports in requested task order.
        """
        return self._graph.wait_for_reports(task_ids, timeout_seconds)

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

    def view_snapshot(self) -> dict[str, Any]:
        """Return a safe, UI-oriented snapshot of the active graph topology.

        Returns:
            JSON-compatible node, edge, assignment, and task-state data from
            the underlying :class:`ExecutionGraph`.
        """
        return self._graph.view_snapshot()

    def finalize_tasks(self) -> dict[str, str]:
        """Close unfinished dynamic tasks after any terminal run outcome.

        Returns:
            Mapping of changed task identifiers to ``interrupted`` or
            ``cancelled``.

        Side Effects:
            Emits terminal task lifecycle events through registered hooks.
        """
        return self._graph.finalize_tasks()

    def request_shutdown(self) -> None:
        """Stop scheduling further runnable Agents in the active graph.

        Already-running Agents finish their current work according to their
        own cooperative controls.

        Returns:
            None.
        """
        self._graph.request_shutdown()

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def run(
        self,
        message: str,
        max_rounds: int | None = None,
        control: AgentRunControl | None = None,
    ) -> dict[str, Any]:
        """Execute the graph with an optional cooperative Agent control.

        Args:
            message: Initial input supplied to every root Agent.
            max_rounds: Maximum rounds passed to every Agent; ``0`` means
                unlimited and ``None`` uses each Agent's default.
            control: Optional stop and steering source shared by graph Agents.

        Returns:
            Mapping of agent name to its raw output.

        Side Effects:
            Finalizes every unfinished dynamic assignment before returning or
            propagating a scheduler exception.
        """
        try:
            return self._graph.run(message, max_rounds=max_rounds, control=control)
        finally:
            self._graph.finalize_tasks()
