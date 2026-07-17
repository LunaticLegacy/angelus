"""Dependency-driven execution graph for coordinating multiple agents.

The graph models each :class:`Agent` instance as a vertex and each directed
connection as a dependency edge. An agent becomes runnable as soon as all of
its direct predecessors have completed.

The execution model supports the following common topologies:

- Pass-through: one agent forwards its output to one successor.
- Fan-out: one agent broadcasts its output to multiple successors.
- Fan-in: one agent waits for multiple predecessors and aggregates their
  outputs before execution.

Additional features:

- **Mapper** (node-level): a single callable on any agent that transforms all
  predecessor outputs into the agent's input message (``set_mapper``).
  Without a mapper, a single predecessor's output is passed through directly,
  and multiple predecessors' outputs are joined with source labels.
- **Router**: dynamic successor selection — after an agent completes, a
  router function decides which downstream agents to activate.  Non-LLM
  routing nodes (``add_routing_node``) can be used as lightweight decision
  points without an Agent instance.

Dynamic mutation at runtime
---------------------------
The graph supports **runtime mutation** during :meth:`ExecutionGraph.run`:

- :meth:`dynamic_add_agent` / :meth:`dynamic_remove_agent`
- :meth:`dynamic_add_connection`

These are thread-safe and designed to be called from within an agent's tool
handlers (e.g. a coordinator LLM dynamically spawning workers).

A coordinator agent can build a sub-graph on the fly::

    # Inside a coordinator's tool handler:
    graph.dynamic_add_agent("worker_1", worker_agent)
    graph.dynamic_add_connection("coordinator", "worker_1")

When the coordinator finishes, the scheduler automatically activates its
successors — including agents added dynamically during its execution.

.. important::

   Connections must be added **before** the source agent completes.
   Adding a connection *from an already-finished agent* has no effect
   because the source's successors have already been activated.

Agents whose dependencies are satisfied are scheduled concurrently through a
thread pool. Thread-based execution is appropriate for agents whose primary
work consists of network or other I/O-bound operations.

The graph must be acyclic.
"""

from __future__ import annotations

from collections import deque
from concurrent.futures import (
    FIRST_COMPLETED,
    Future,
    ThreadPoolExecutor,
    wait,
)
import threading
from typing import Any, Callable, Mapping

from ..agent import Agent
from ..events import ExecutionEvent, ExecutionHook


MapperFn = Callable[[Mapping[str, Any]], str]
"""Node-level mapper: receives a ``{predecessor_name: raw_output}`` mapping
and returns the input string for the agent."""

RouterFn = Callable[[str], list[str]]
"""Post-completion router: receives the agent's output text and returns the
list of successor names that should be activated.  Successors not in the
returned list are skipped for this run."""


class ExecutionGraph:
    """Directed acyclic graph that schedules dependent agents concurrently.

    Each registered agent is identified by a unique string name. Directed
    connections express execution dependencies: a target agent cannot run
    until every source agent connected to it has completed.

    Root agents receive the initial message passed to :meth:`run`. Non-root
    agents receive input built from their direct predecessor outputs. For a
    single predecessor, the predecessor output is forwarded directly as text.
    For multiple predecessors, outputs are combined with source labels unless
    a custom :class:`MapperFn` has been registered via :meth:`set_mapper`.

    Args:
        max_concurrency_agents:
            Maximum number of agents that may execute concurrently.

    Raises:
        ValueError:
            If ``max_concurrency_agents`` is not greater than zero.

    Note:
        A registered :class:`Agent` instance is expected to participate in at
        most one active execution of this graph at a time unless the agent
        implementation is explicitly thread-safe.
    """

    def __init__(
        self,
        max_concurrency_agents: int = 8,
    ) -> None:
        if max_concurrency_agents <= 0:
            raise ValueError("max_concurrency_agents must be greater than zero")

        self.max_concurrency_agents = max_concurrency_agents

        self.agent_dict: dict[str, Agent] = {}

        # source -> direct successors
        self._successors: dict[str, set[str]] = {}

        # target -> direct predecessors
        self._predecessors: dict[str, set[str]] = {}

        # agent_name -> node-level mapper (predecessor outputs → input string)
        self._mappers: dict[str, MapperFn] = {}

        # agent_name -> post-completion router
        self._routers: dict[str, RouterFn] = {}

        # names of non-LLM routing-only nodes (no Agent instance)
        self._routing_nodes: set[str] = set()

        # thread-safety lock for dynamic mutation during run()
        self._lock = threading.Lock()

        # hook system
        self.hooks: list[ExecutionHook] = []
        self._shutdown_requested = False

    # -- hook registration -------------------------------------------------

    def add_hook(self, hook: ExecutionHook) -> None:
        """Register a hook that receives every :class:`ExecutionEvent`."""
        self.hooks.append(hook)

    def _emit(
        self,
        source: str,
        agent_name: str,
        event_type: str,
        message: str = "",
        data: Any = None,
    ) -> None:
        """Fire an event to all registered hooks.

        A single failed hook does not crash the execution.
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
                pass  # hook must not crash the swarm

    # ------------------------------------------------------------------
    # Graph construction  —  agents
    # ------------------------------------------------------------------

    def add_agent(
        self,
        agent_name: str,
        agent_instance: Agent,
    ) -> bool:
        """Register an agent as a graph vertex.

        Args:
            agent_name:
                Unique name used to reference the agent in graph operations.
            agent_instance:
                Agent instance executed when this vertex becomes ready.

        Returns:
            ``True`` if the agent was registered. ``False`` if another agent
            already uses ``agent_name``.
        """
        if agent_name in self.agent_dict:
            return False

        self.agent_dict[agent_name] = agent_instance
        self._successors[agent_name] = set()
        self._predecessors[agent_name] = set()
        # Tag the agent so its own hook events carry its graph name.
        agent_instance._agent_name_in_graph = agent_name
        return True

    def add_routing_node(
        self,
        name: str,
        router: RouterFn,
    ) -> bool:
        """Register a lightweight non-LLM routing node.

        A routing node has no ``Agent`` instance — it simply evaluates
        *router* on its input and activates the successors it returns.
        This is useful for conditional branching without an LLM round-trip.

        Args:
            name:
                Unique node name.
            router:
                Function that receives the input text and returns the
                list of successor names to activate.

        Returns:
            ``True`` if the node was registered. ``False`` if *name* is
            already taken by an agent or another routing node.
        """
        if name in self.agent_dict:
            return False

        self.agent_dict[name] = None  # sentinel — no Agent
        self._successors[name] = set()
        self._predecessors[name] = set()
        self._routing_nodes.add(name)
        self._routers[name] = router
        return True

    def remove_agent(self, agent_name: str) -> bool:
        """Remove an agent and every edge connected to it.

        Any mapper or router registered for the agent is also removed.

        Args:
            agent_name:
                Name of the registered agent to remove.

        Returns:
            ``True`` if the agent existed and was removed. ``False`` if no
            registered agent uses ``agent_name``.
        """
        if agent_name not in self.agent_dict:
            return False

        for predecessor in self._predecessors[agent_name]:
            self._successors[predecessor].discard(agent_name)

        for successor in self._successors[agent_name]:
            self._predecessors[successor].discard(agent_name)

        del self.agent_dict[agent_name]
        del self._successors[agent_name]
        del self._predecessors[agent_name]
        self._mappers.pop(agent_name, None)
        self._routers.pop(agent_name, None)
        self._routing_nodes.discard(agent_name)

        return True

    # ------------------------------------------------------------------
    # Graph construction  —  edges
    # ------------------------------------------------------------------

    def add_connection(
        self,
        source: str,
        target: str,
    ) -> bool:
        """Add a directed dependency edge from one agent to another.

        After the edge is added, ``target`` waits for ``source`` to complete
        before it may execute.

        Args:
            source:
                Name of the predecessor agent.
            target:
                Name of the successor agent.

        Returns:
            ``True`` if the edge was added. ``False`` if the same edge already
            exists.

        Raises:
            KeyError:
                If either agent name is not registered.
            ValueError:
                If ``source`` and ``target`` refer to the same agent.

        Note:
            This method does not immediately detect longer cycles. Cycles are
            detected when :meth:`run` is called.
        """
        self._require_agent(source)
        self._require_agent(target)

        if source == target:
            raise ValueError("An agent cannot connect to itself")

        if target in self._successors[source]:
            return False

        self._successors[source].add(target)
        self._predecessors[target].add(source)

        return True

    def add_split(
        self,
        source: str,
        targets: list[str],
    ) -> None:
        """Broadcast one agent's output to multiple successor agents.

        This operation adds one ordinary dependency edge from ``source`` to
        each target. Every target receives the same source output unless a
        custom mapper on the target changes the aggregation.

        Args:
            source:
                Name of the agent whose output is broadcast.
            targets:
                Names of agents that depend on ``source``.

        Raises:
            KeyError:
                If ``source`` or any target name is not registered.
            ValueError:
                If a target is identical to ``source``.
        """
        for target in targets:
            self.add_connection(source, target)

    def add_gather(
        self,
        sources: list[str],
        target: str,
        mapper: MapperFn | None = None,
    ) -> None:
        """Make one agent depend on and aggregate multiple source agents.

        The target becomes runnable only after every source has completed.
        If *mapper* is provided, it is registered on the target — it
        receives a ``{source_name: raw_output}`` mapping and must return
        the input string for the target agent.

        This is sugar for ``add_connection`` calls followed by
        ``set_mapper(target, mapper)``.

        Args:
            sources:
                Names of predecessor agents whose outputs are gathered.
            target:
                Name of the agent that consumes the gathered outputs.
            mapper:
                Optional node-level mapper for the target agent.

        Raises:
            KeyError:
                If any source or the target is not registered.
            ValueError:
                If a source is identical to ``target``.
        """
        for source in sources:
            self.add_connection(source, target)

        if mapper is not None:
            self._mappers[target] = mapper

    # ------------------------------------------------------------------
    # Graph construction  —  mappers (node-level)
    # ------------------------------------------------------------------

    def set_mapper(
        self,
        agent_name: str,
        mapper: MapperFn,
    ) -> None:
        """Set a node-level mapper on *agent_name*.

        The mapper receives a ``{predecessor_name: raw_output}`` mapping
        and must return the string that the agent receives as input.

        This replaces the default aggregation behaviour (single-predecessor
        passthrough, multi-predecessor label-join).

        Args:
            agent_name:
                Name of a registered agent.
            mapper:
                Callable that converts predecessor outputs into a string.

        Raises:
            KeyError:
                If *agent_name* is not registered.
        """
        self._require_agent(agent_name)
        self._mappers[agent_name] = mapper

    # ------------------------------------------------------------------
    # Graph construction  —  routers (dynamic successor selection)
    # ------------------------------------------------------------------

    def set_router(
        self,
        agent_name: str,
        router: RouterFn,
    ) -> None:
        """Attach a post-completion router to an existing agent.

        After the agent finishes, *router* is called with its output text
        and must return the list of successor names to activate.  Any
        successor *not* in the returned list is skipped — its dependency
        count is never decremented and it will never run (unless another
        path satisfies its dependencies).

        Args:
            agent_name:
                Name of a registered agent (not a routing node).
            router:
                Function that receives the agent's output text and
                returns successor names to activate.

        Raises:
            KeyError:
                If *agent_name* is not registered or is a routing node.
        """
        self._require_agent(agent_name)
        if agent_name in self._routing_nodes:
            raise KeyError(
                f"{agent_name!r} is a routing-only node — use "
                "``add_routing_node`` to set the router at creation time"
            )
        self._routers[agent_name] = router

    def remove_router(self, agent_name: str) -> bool:
        """Remove a post-completion router from an agent.

        After removal, all registered successors are activated normally.

        Returns:
            ``True`` if a router existed and was removed.
        """
        if agent_name not in self._routers:
            return False
        del self._routers[agent_name]
        return True

    # ------------------------------------------------------------------
    # Dynamic mutation  —  thread-safe, usable during run()
    # ------------------------------------------------------------------

    def dynamic_add_agent(
        self,
        agent_name: str,
        agent_instance: Agent,
    ) -> str:
        with self._lock:
            if agent_name in self.agent_dict:
                return f"Error: agent '{agent_name}' already exists"

            self.agent_dict[agent_name] = agent_instance
            self._successors[agent_name] = set()
            self._predecessors[agent_name] = set()

        self._emit("graph", agent_name, "dynamic:add_agent",
                    f"Agent '{agent_name}' created")
        return f"Agent '{agent_name}' created"

    def dynamic_remove_agent(self, agent_name: str) -> str:
        """Dynamically remove an agent and its edges during execution.

        Returns a status message for the calling LLM.
        """
        with self._lock:
            if agent_name not in self.agent_dict:
                return f"Error: agent '{agent_name}' does not exist"

            for predecessor in self._predecessors[agent_name]:
                self._successors[predecessor].discard(agent_name)
            for successor in self._successors[agent_name]:
                self._predecessors[successor].discard(agent_name)

            del self.agent_dict[agent_name]
            del self._successors[agent_name]
            del self._predecessors[agent_name]
            self._mappers.pop(agent_name, None)
            self._routers.pop(agent_name, None)
            self._routing_nodes.discard(agent_name)

            return f"Agent '{agent_name}' removed"

    def dynamic_add_connection(self, source: str, target: str) -> str:
        """Dynamically add a dependency edge during execution.

        The edge is only effective if *source* has not yet completed
        (i.e. the source agent is still running when this method is called).
        After the source finishes, the scheduler automatically activates all
        successors — including those added dynamically.

        Returns a status message for the calling LLM.
        """
        with self._lock:
            if source not in self.agent_dict:
                return f"Error: source agent '{source}' does not exist"
            if target not in self.agent_dict:
                return f"Error: target agent '{target}' does not exist"
            if source == target:
                return "Error: an agent cannot connect to itself"
            if target in self._successors[source]:
                return f"Connection already exists: {source} -> {target}"

            self._successors[source].add(target)
            self._predecessors[target].add(source)

        self._emit(
            "graph", source, "dynamic:connect",
            f"{source} -> {target}",
            data={"source": source, "target": target},
        )
        return f"Connected: {source} -> {target}"

    def dynamic_get_info(self) -> str:
        """Return the current graph state as a structured string.

        Useful for LLM agents that need to inspect the graph topology
        before deciding which agents to create or connect.
        """
        with self._lock:
            lines = ["Current agents:"]
            for name in sorted(self.agent_dict):
                agent = self.agent_dict[name]
                if agent is None:
                    lines.append(f"  {name} (routing node)")
                else:
                    lines.append(f"  {name} (Agent)")
            lines.append("")
            lines.append("Current connections:")
            for source in sorted(self._successors):
                targets = sorted(self._successors[source])
                if not targets:
                    lines.append(f"  {source} -> (none)")
                else:
                    for target in targets:
                        lines.append(f"  {source} -> {target}")
            lines.append("")
            lines.append(f"Concurrency limit: {self.max_concurrency_agents}")
            return "\n".join(lines)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def run(self, message: str) -> dict[str, Any]:
        """Execute the graph using dependency-driven concurrent scheduling.

        Root agents receive ``message`` directly. Whenever an agent finishes,
        each successor's unresolved dependency count is decremented. A
        successor is submitted immediately once all of its predecessors have
        completed; execution does not wait for an entire topological level.

        If the completed agent has a post-completion :class:`RouterFn`
        attached, only the successors returned by the router are activated.
        Non-LLM routing nodes (added via :meth:`add_routing_node`) are
        evaluated synchronously — they produce no output themselves.

        Args:
            message:
                Initial input message supplied independently to every root
                agent.

        Returns:
            Mapping from every executed agent name to its raw output.
            Routing-only nodes are **not** included in the returned dict.

        Raises:
            ValueError:
                If the graph contains a cycle or a deadlock.
            RuntimeError:
                If an agent raises an exception. The original exception is
                available as the raised exception's cause.

        Note:
            Cancelling a :class:`Future` only stops work that has not started.
            Already-running sibling agents may continue until the thread-pool
            executor shuts down.
        """
        if not self.agent_dict:
            return {}

        self._shutdown_requested = False

        self._emit("graph", "", "graph:start", message)

        with self._lock:
            remaining_dependencies = {
                name: len(self._predecessors[name])
                for name in self.agent_dict
            }

            ready = deque(
                name
                for name, dependency_count in remaining_dependencies.items()
                if dependency_count == 0
            )

            if not ready:
                raise ValueError("Execution graph contains a cycle")

        outputs: dict[str, Any] = {}
        running: dict[Future[Any], str] = {}
        routed_out: set[str] = set()

        with ThreadPoolExecutor(
            max_workers=self.max_concurrency_agents
        ) as executor:
            while (
                (ready or running)
                and not self._shutdown_requested
            ):
                # --- submit ready agents up to the concurrency limit ----
                while (
                    ready
                    and len(running) < self.max_concurrency_agents
                    and not self._shutdown_requested
                ):
                    agent_name = ready.popleft()

                    # Non-LLM routing node: evaluate synchronously
                    if agent_name in self._routing_nodes:
                        with self._lock:
                            input_message = self._build_input(
                                agent_name=agent_name,
                                initial_message=message,
                                outputs=outputs,
                            )
                        outputs[agent_name] = input_message
                        selected = self._routers[agent_name](input_message)
                        selected_set = set(selected)
                        with self._lock:
                            for s in self._successors[agent_name]:
                                if s not in selected_set:
                                    routed_out.add(s)
                            self._activate(
                                agent_name, selected,
                                remaining_dependencies, ready,
                            )
                        continue

                    with self._lock:
                        input_message = self._build_input(
                            agent_name=agent_name,
                            initial_message=message,
                            outputs=outputs,
                        )

                    self._emit(
                        "graph", agent_name, "agent:submitted",
                        message,
                    )

                    future = executor.submit(
                        self.agent_dict[agent_name].run,
                        input_message,
                    )
                    running[future] = agent_name

                if not running or self._shutdown_requested:
                    break

                # --- poll with timeout for Ctrl+C responsiveness -------
                completed_futures, _ = wait(
                    running,
                    timeout=0.5,
                    return_when=FIRST_COMPLETED,
                )

                if not completed_futures:
                    # timeout — continue loop (allows shutdown check)
                    continue

                for future in completed_futures:
                    agent_name = running.pop(future)

                    try:
                        outputs[agent_name] = future.result()
                        self._emit(
                            "graph", agent_name, "agent:completed",
                            f"Agent completed",
                            data={"output_len": len(str(outputs[agent_name]))},
                        )
                    except Exception as exc:
                        self._emit(
                            "graph", agent_name, "agent:failed",
                            str(exc),
                            data={"error": exc},
                        )
                        for pending_future in running:
                            pending_future.cancel()
                        raise RuntimeError(
                            f"Agent {agent_name!r} failed"
                        ) from exc

                    # Post-completion router or activate all successors
                    with self._lock:
                        if agent_name in self._routers:
                            output_text = self._output_to_text(
                                outputs[agent_name]
                            )
                            selected = self._routers[agent_name](output_text)
                            selected_set = set(selected)
                            for s in self._successors[agent_name]:
                                if s not in selected_set:
                                    routed_out.add(s)
                            self._activate(
                                agent_name, selected,
                                remaining_dependencies, ready,
                            )
                        else:
                            self._activate(
                                agent_name, self._successors[agent_name],
                                remaining_dependencies, ready,
                            )

        # --- final validation: detect deadlocks -------------------------
        with self._lock:
            never_ran = [
                n for n in self.agent_dict
                if n not in outputs
                and n not in self._routing_nodes
                and n not in routed_out
            ]
        if never_ran:
            unresolved = {
                n: remaining_dependencies.get(n, -1)
                for n in never_ran
                if remaining_dependencies.get(n, 0) > 0
            }
            if unresolved:
                raise ValueError(
                    "Execution graph contains a cycle or unresolved "
                    f"dependencies: {unresolved}"
                )

        self._emit(
            "graph", "", "graph:complete",
            f"Swarm finished, {len(outputs)} agent(s) executed",
            data={"agent_count": len(outputs), "agents": list(outputs.keys())},
        )

        return outputs

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _activate(
        self,
        completed_agent: str,
        successors: list[str] | set[str],
        remaining_dependencies: dict[str, int],
        ready: deque[str],
    ) -> None:
        """Decrement dependency counts and enqueue ready successors.

        Handles both statically-registered and dynamically-added agents.
        For dynamically-added agents (not yet in *remaining_dependencies*),
        computes the full dependency count from :attr:`_predecessors`.
        """
        for successor in successors:
            if successor in remaining_dependencies:
                remaining_dependencies[successor] -= 1
                if remaining_dependencies[successor] == 0:
                    ready.append(successor)
            elif successor in self.agent_dict:
                # Dynamically-added agent — compute full dep count from
                # current predecessors (one of which just completed).
                deps = len(self._predecessors[successor])
                remaining_dependencies[successor] = deps - 1
                if remaining_dependencies[successor] == 0:
                    ready.append(successor)

    def _build_input(
        self,
        agent_name: str,
        initial_message: str,
        outputs: Mapping[str, Any],
    ) -> str:
        """Build the input message for one ready agent.

        If the agent has a node-level mapper (set via :meth:`set_mapper`),
        it receives all predecessor outputs and returns the input string.
        Otherwise, the default strategy is:

        - Single predecessor: pass through the output directly.
        - Multiple predecessors: join with ``[Output from <name>]`` labels.
        """
        predecessors = sorted(self._predecessors[agent_name])

        if not predecessors:
            return initial_message

        # Collect predecessor outputs
        predecessor_outputs = {
            predecessor: outputs[predecessor]
            for predecessor in predecessors
        }

        # Node-level mapper replaces the default aggregation entirely
        mapper = self._mappers.get(agent_name)
        if mapper is not None:
            return mapper(predecessor_outputs)

        # Single predecessor — pass through directly
        if len(predecessor_outputs) == 1:
            output = next(iter(predecessor_outputs.values()))
            return self._output_to_text(output)

        # Multiple predecessors — join with labels
        parts = [
            f"[Output from {predecessor}]\n"
            f"{self._output_to_text(output)}"
            for predecessor, output in predecessor_outputs.items()
        ]

        return "\n\n---\n\n".join(parts)

    @staticmethod
    def _output_to_text(output: Any) -> str:
        """Convert an arbitrary agent output into message text.

        If the output exposes a non-``None`` ``content`` attribute, that value
        is preferred. Otherwise, ``str(output)`` is used.
        """
        content = getattr(output, "content", None)

        if content is not None:
            return str(content)

        return str(output)

    def _require_agent(self, agent_name: str) -> None:
        """Ensure that an agent name is registered.

        Args:
            agent_name:
                Name to validate.

        Raises:
            KeyError:
                If the name does not identify a registered agent.
        """
        if agent_name not in self.agent_dict:
            raise KeyError(f"Unknown agent: {agent_name!r}")
