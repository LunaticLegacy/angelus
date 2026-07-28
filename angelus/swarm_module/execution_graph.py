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
from dataclasses import asdict
import json
from pathlib import Path
import threading
import time
from queue import Empty, SimpleQueue
from typing import Any, Callable, Iterable, Mapping

from ..agent import Agent, AgentRunControl, AgentRunStopped
from llmfetcher.context_handlers import ContextHandlerLinear
from llmfetcher.events import ExecutionEvent, ExecutionHook
from llmfetcher.llm_fetcher import LLMFetcher
from llmfetcher.llm_types import LLMBackendConfig
from .task_bus import TaskAssignment, TaskBus, TaskReport


MapperFn = Callable[[Mapping[str, Any]], str]
"""Node-level mapper: receives a ``{predecessor_name: raw_output}`` mapping
and returns the input string for the agent."""

RouterFn = Callable[[str], list[str]]
"""Post-completion router: receives the agent's output text and returns the
list of successor names that should be activated.  Successors not in the
returned list are skipped for this run."""

AgentSerializer = Callable[[str, Agent], dict[str, Any]]
AgentResolver = Callable[[str, Mapping[str, Any]], Agent]
CallbackSerializer = Callable[[str, str, Callable[..., Any]], str]
CallbackResolver = Callable[[str, str, str], Callable[..., Any]]


class GraphPersistenceError(ValueError):
    """Raised when an ExecutionGraph cannot be safely saved or restored."""


_SNAPSHOT_VERSION = 1


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
        """Initialize an empty dependency graph.

        Args:
            max_concurrency_agents: Maximum number of concurrently running
                Agent nodes.

        Raises:
            ValueError: If the concurrency limit is not positive.
        """
        if max_concurrency_agents <= 0:
            raise ValueError("max_concurrency_agents must be greater than zero")

        self.max_concurrency_agents = max_concurrency_agents

        self.agent_dict: dict[str, Agent | None] = {}

        # source -> direct successors
        self._successors: dict[str, set[str]] = {}

        # target -> direct predecessors
        self._predecessors: dict[str, set[str]] = {}

        # agent_name -> node-level mapper (predecessor outputs → input string)
        self._mappers: dict[str, MapperFn] = {}

        # agent_name -> post-completion router
        self._routers: dict[str, RouterFn] = {}

        # Router selection applies to successors present when the router was
        # configured; later dynamic children remain eligible by default.
        self._router_scopes: dict[str, set[str]] = {}

        # names of non-LLM routing-only nodes (no Agent instance)
        self._routing_nodes: set[str] = set()

        # Explicit assignments replace implicit predecessor-output delivery
        # for dynamically dispatched subagents.
        self.task_bus = TaskBus()
        self._task_by_agent: dict[str, str] = {}
        self._task_by_id: dict[str, str] = {}
        self._node_states: dict[str, dict[str, Any]] = {}
        self._dynamic_ready: SimpleQueue[str] = SimpleQueue()

        # Topology mutations are short and independent from Agent execution.
        self._topology_lock = threading.RLock()

        # Hooks are snapshotted before invocation so user callbacks never hold
        # graph topology or hook-registration locks.
        self._hooks_lock = threading.Lock()
        self.hooks: list[ExecutionHook] = []

        # Shutdown is observed by the scheduler without sharing topology state.
        self._shutdown_requested = threading.Event()

    def __str__(self) -> str:
        """Render a thread-safe human-readable snapshot of graph topology.

        The output includes registered nodes, directed connections, and the
        concurrency limit. It deliberately delegates to
        :meth:`dynamic_get_info` so diagnostic printing and the graph-inspect
        tool always expose the same current state during dynamic mutation.

        Returns:
            Multi-line summary suitable for ``print(graph)``.
        """
        return self.dynamic_get_info()

    @staticmethod
    def _default_agent_serializer(agent_name: str, agent: Agent) -> dict[str, Any]:
        """Serialize a standard tool-free Agent into JSON-compatible config.

        Args:
            agent_name: Graph-local name used in validation errors.
            agent: Agent whose LLM, context-path, and execution settings are saved.

        Returns:
            Versioned Agent specification that :meth:`_default_agent_resolver` restores.

        Raises:
            GraphPersistenceError: If tools or a custom context handler need an
                application-supplied serializer.
        """
        if not isinstance(agent.context_handler, ContextHandlerLinear):
            raise GraphPersistenceError(f"Agent {agent_name!r} uses custom context; provide agent_serializer")
        if agent.tool_handler.get_all_tools():
            raise GraphPersistenceError(f"Agent {agent_name!r} has tools; provide agent_serializer")
        try:
            result = {
                "kind": "llmfetcher.agent.v1",
                "backends": [asdict(item) for item in agent.llm_fetcher.backend_configs.values()],
                "default_backend": agent.llm_fetcher.default_backend,
                "system_prompt": agent.system_prompt,
                "max_concurrency": agent.max_concurrency,
                "max_context_threshold": agent.max_context_threshold,
                "context_path": str(agent.context_path) if agent.context_path else None,
                "default_max_rounds": agent.default_max_rounds,
                "default_max_tokens": agent.default_max_tokens,
            }
            json.dumps(result)
            return result
        except (AttributeError, TypeError, ValueError) as exc:
            raise GraphPersistenceError(f"Cannot serialize Agent {agent_name!r}: {exc}") from exc

    @staticmethod
    def _default_agent_resolver(agent_name: str, spec: Mapping[str, Any]) -> Agent:
        """Recreate a standard tool-free Agent from a persisted specification.

        Args:
            agent_name: Graph-local name used in validation errors.
            spec: JSON-decoded standard Agent configuration.

        Returns:
            Reconstructed Agent without application tools.

        Raises:
            GraphPersistenceError: If ``spec`` is unsupported or malformed.
        """
        if spec.get("kind") != "llmfetcher.agent.v1":
            raise GraphPersistenceError(f"Agent {agent_name!r} requires a custom agent_resolver")
        try:
            backends = [LLMBackendConfig(**dict(item)) for item in spec["backends"]]
            return Agent(
                llm_fetcher=LLMFetcher(backends, default_backend=spec.get("default_backend")),
                system_prompt=str(spec["system_prompt"]), max_concurrency=int(spec["max_concurrency"]),
                max_context_threshold=int(spec["max_context_threshold"]), context_path=spec.get("context_path"),
                default_max_rounds=int(spec["default_max_rounds"]), default_max_tokens=int(spec["default_max_tokens"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise GraphPersistenceError(f"Invalid Agent spec for {agent_name!r}: {exc}") from exc

    def to_snapshot(self, *, agent_serializer: AgentSerializer | None = None,
                    callback_serializer: CallbackSerializer | None = None) -> dict[str, Any]:
        """Create a JSON-compatible snapshot of a quiescent graph.

        Args:
            agent_serializer: Optional safe Agent-to-spec adapter. Required for tools/custom contexts.
            callback_serializer: Required callback-to-stable-ID adapter when mappers or routers exist.

        Returns:
            Versioned topology, Agent specs, callback IDs, and TaskBus state.

        Raises:
            GraphPersistenceError: If executable application objects lack adapters.
        """
        serializer = agent_serializer or self._default_agent_serializer
        with self._topology_lock:
            nodes = []
            for name in sorted(self.agent_dict):
                if name in self._routing_nodes:
                    nodes.append({"name": name, "kind": "routing"})
                else:
                    agent = self.agent_dict[name]
                    if agent is None:
                        raise GraphPersistenceError(f"Missing Agent instance for {name!r}")
                    nodes.append({"name": name, "kind": "agent", "spec": serializer(name, agent)})
            if (self._mappers or self._routers) and callback_serializer is None:
                raise GraphPersistenceError("Graph callbacks require callback_serializer")
            callbacks = {
                "mappers": {name: callback_serializer(name, "mapper", fn) for name, fn in self._mappers.items()} if callback_serializer else {},
                "routers": {name: callback_serializer(name, "router", fn) for name, fn in self._routers.items()} if callback_serializer else {},
            }
            snapshot = {
                "version": _SNAPSHOT_VERSION, "max_concurrency_agents": self.max_concurrency_agents,
                "nodes": nodes,
                "edges": [{"source": source, "target": target} for source in sorted(self._successors) for target in sorted(self._successors[source])],
                "callbacks": callbacks,
                "router_scopes": {name: sorted(scope) for name, scope in self._router_scopes.items()},
                "task_bus": self.task_bus.to_snapshot(), "task_by_agent": dict(self._task_by_agent), "task_by_id": dict(self._task_by_id),
            }
        try:
            json.dumps(snapshot)
        except (TypeError, ValueError) as exc:
            raise GraphPersistenceError(f"Snapshot is not JSON-compatible: {exc}") from exc
        return snapshot

    def save(self, path: str | Path, *, agent_serializer: AgentSerializer | None = None,
             callback_serializer: CallbackSerializer | None = None) -> Path:
        """Atomically save a quiescent graph snapshot to ``path``.

        Args:
            path: Destination JSON file; parent directories are created.
            agent_serializer: Optional Agent-to-spec adapter.
            callback_serializer: Optional callback-to-ID adapter.

        Returns:
            Destination path after replacement.
        """
        destination = Path(path)
        snapshot = self.to_snapshot(agent_serializer=agent_serializer, callback_serializer=callback_serializer)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(destination)
        return destination

    @classmethod
    def load(cls, path: str | Path, *, agent_resolver: AgentResolver | None = None,
             callback_resolver: CallbackResolver | None = None) -> "ExecutionGraph":
        """Load a graph snapshot into a new quiescent ExecutionGraph.

        Args:
            path: JSON file previously created by :meth:`save`.
            agent_resolver: Optional Agent spec resolver.
            callback_resolver: Required to resolve every saved mapper/router ID.

        Returns:
            New graph ready to execute.

        Raises:
            GraphPersistenceError: If snapshot structure or required resolvers are invalid.
        """
        try:
            snapshot = json.loads(Path(path).read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise GraphPersistenceError(f"Invalid graph snapshot JSON: {exc}") from exc
        if not isinstance(snapshot, Mapping) or snapshot.get("version") != _SNAPSHOT_VERSION:
            raise GraphPersistenceError("Unsupported graph snapshot version")
        try:
            graph = cls(int(snapshot["max_concurrency_agents"]))
            nodes, edges = snapshot["nodes"], snapshot["edges"]
            callbacks = snapshot.get("callbacks", {})
            if not isinstance(nodes, list) or not isinstance(edges, list) or not isinstance(callbacks, Mapping):
                raise ValueError("nodes, edges, and callbacks are required")
            routers = callbacks.get("routers", {})
            mappers = callbacks.get("mappers", {})
            if not isinstance(routers, Mapping) or not isinstance(mappers, Mapping):
                raise ValueError("callback maps must be objects")
            resolver = agent_resolver or cls._default_agent_resolver
            for node in nodes:
                name, kind = str(node["name"]), node["kind"]
                if kind == "agent":
                    if not graph.add_agent(name, resolver(name, node["spec"])): raise ValueError(f"Duplicate node {name}")
                elif kind == "routing":
                    if callback_resolver is None or name not in routers: raise GraphPersistenceError(f"Routing node {name!r} needs callback_resolver")
                    if not graph.add_routing_node(name, callback_resolver(name, "router", str(routers[name]))): raise ValueError(f"Duplicate node {name}")
                else: raise ValueError(f"Unknown node kind {kind!r}")
            for edge in edges:
                graph.add_connection(str(edge["source"]), str(edge["target"]))
            if (mappers or routers) and callback_resolver is None: raise GraphPersistenceError("Graph callbacks require callback_resolver")
            for name, callback_id in mappers.items(): graph.set_mapper(str(name), callback_resolver(str(name), "mapper", str(callback_id)))
            for name, callback_id in routers.items():
                if name not in graph._routing_nodes: graph.set_router(str(name), callback_resolver(str(name), "router", str(callback_id)))
            graph._router_scopes = {str(name): set(str(target) for target in targets) for name, targets in snapshot.get("router_scopes", {}).items()}
            graph.task_bus = TaskBus.from_snapshot(snapshot.get("task_bus", {}))
            graph._task_by_agent = {str(name): str(task_id) for name, task_id in snapshot.get("task_by_agent", {}).items()}
            graph._task_by_id = {str(task_id): str(name) for task_id, name in snapshot.get("task_by_id", {}).items()}
            return graph
        except GraphPersistenceError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise GraphPersistenceError(f"Invalid graph snapshot: {exc}") from exc

    # -- hook registration -------------------------------------------------

    def add_hook(self, hook: ExecutionHook) -> None:
        """Register a hook that receives every :class:`ExecutionEvent`.

        Args:
            hook: Callback invoked for future graph and Agent events.

        Returns:
            None.
        """
        with self._hooks_lock:
            self.hooks.append(hook)

    def view_snapshot(self) -> dict[str, Any]:
        """Return a JSON-safe live topology view without executable objects.

        The view is deliberately distinct from :meth:`to_snapshot`: it is
        safe to call while a graph is running and contains only the data a UI
        needs to draw nodes, hierarchy, edges, assignments, and current task states.

        Returns:
            Mapping with ``nodes``, ``edges``, concurrency limit, task
            assignments, and TaskBus states. Node entries never contain Agent
            instances, credentials, prompts, or tool handlers.
        """
        with self._topology_lock:
            task_parents = {}
            for task_id, agent_name in self._task_by_id.items():
                try:
                    task_parents[agent_name] = self.task_bus.get_assignment(task_id).reply_to
                except KeyError:
                    # A task can disappear between topology and mailbox reads.
                    # The graph view remains useful without that optional parent.
                    continue
            nodes = [
                {
                    "id": name,
                    "kind": "routing" if name in self._routing_nodes else "agent",
                    "dynamic": name in self._task_by_agent,
                    "parent": task_parents.get(name),
                }
                for name in sorted(self.agent_dict)
            ]
            edges = [
                {"source": source, "target": target, "kind": "dependency"}
                for source in sorted(self._successors)
                for target in sorted(self._successors[source])
            ]
            assignments = {
                task_id: agent_name for task_id, agent_name in self._task_by_id.items()
            }
            node_states = {
                agent_name: dict(record)
                for agent_name, record in self._node_states.items()
            }
        return {
            "nodes": nodes,
            "edges": edges,
            "max_concurrency_agents": self.max_concurrency_agents,
            "assignments": assignments,
            "task_states": self.task_bus.task_states(),
            "node_states": node_states,
        }

    def finalize_tasks(self) -> dict[str, str]:
        """Close every unfinished dynamic task after the scheduler stops.

        Running tasks become ``interrupted`` and never-started tasks become
        ``cancelled``. Existing completed or failed task outcomes are
        preserved.

        Returns:
            Mapping of task identifiers changed during finalization.

        Side Effects:
            Emits one ``task:finalized`` lifecycle event for every changed
            task so observers persist the same terminal view.
        """
        changed = self.task_bus.finalize_unfinished()
        with self._topology_lock:
            agents = dict(self._task_by_id)
        for task_id, state in changed.items():
            agent_name = agents.get(task_id, "")
            self._emit(
                "graph",
                agent_name,
                "task:finalized",
                f"Task {task_id} finalized as {state}",
                data={"task_id": task_id, "state": state},
            )
        return changed

    def request_shutdown(self) -> None:
        """Ask the scheduler to stop submitting further runnable Agents.

        Already-running Agents are not interrupted by this method because the
        graph deliberately does not hold locks across model or tool calls.

        Returns:
            None.
        """
        self._shutdown_requested.set()

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
        self._record_node_state(agent_name, event_type, message, data)
        event = ExecutionEvent(
            source=source,
            agent_name=agent_name,
            event_type=event_type,
            message=message,
            data=data,
        )
        with self._hooks_lock:
            hooks = tuple(self.hooks)
        for hook in hooks:
            try:
                hook(event)
            except Exception:
                pass  # hook must not crash the swarm

    def _record_node_state(
        self,
        agent_name: str,
        event_type: str,
        message: str,
        data: Any,
    ) -> None:
        """Project one lifecycle event into the UI-facing node state cache.

        Args:
            agent_name: Graph node named by the event; blank graph-wide events
                are ignored.
            event_type: Lifecycle type emitted by an Agent or scheduler.
            message: Human-readable latest activity.
            data: Optional event payload used for task terminal outcomes.

        Returns:
            None.

        Side Effects:
            Replaces the named entry in ``_node_states`` under the topology
            lock.
        """
        if not agent_name:
            return
        state = ""
        if event_type == "task:dispatched":
            state = "queued"
        elif event_type in {"agent:completed", "agent:complete"}:
            state = "completed"
        elif event_type in {"agent:failed", "agent:error"}:
            state = "failed"
        elif event_type == "agent:stopped":
            state = "interrupted"
        elif event_type == "task:report_missing":
            state = "failed"
        elif event_type == "task:reported":
            report_status = str(data.get("status", "")) if isinstance(data, Mapping) else ""
            state = TaskBus._state_for_report_status(report_status)
        elif event_type == "task:finalized":
            state = str(data.get("state", "")) if isinstance(data, Mapping) else ""
        elif event_type.startswith("agent:"):
            state = "running"
        if not state:
            return
        with self._topology_lock:
            task_id = self._task_by_agent.get(agent_name, "")
            record: dict[str, Any] = {
                "state": state,
                "message": message,
                "updated_at": time.time(),
            }
            if task_id:
                record["task_id"] = task_id
            self._node_states[agent_name] = record

    def _attach_agent_events(self, agent: Agent) -> None:
        """Forward one graph member's lifecycle events to graph hooks.

        Args:
            agent: Newly registered Agent whose model and tool events should
                be visible to graph observers.

        Side Effects:
            Registers a lightweight forwarding hook when ``agent`` implements
            ``add_hook``. Lightweight test or application runners that expose
            only ``run`` remain valid graph nodes. The graph never mutates a
            forwarded event and preserves its agent name, type and tool data.
        """
        def forward(event: ExecutionEvent) -> None:
            """Relay one Agent event through the graph's hook collection."""
            self._emit(event.source, event.agent_name, event.event_type, event.message, event.data)

        add_hook = getattr(agent, "add_hook", None)
        if callable(add_hook):
            add_hook(forward)

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
        with self._topology_lock:
            if agent_name in self.agent_dict:
                return False
            self.agent_dict[agent_name] = agent_instance
            self._successors[agent_name] = set()
            self._predecessors[agent_name] = set()
            self._node_states[agent_name] = {
                "state": "idle",
                "message": "尚未开始",
                "updated_at": 0.0,
            }
            # Tag the agent so its own hook events carry its graph name.
            agent_instance._agent_name_in_graph = agent_name
            self._attach_agent_events(agent_instance)
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
        with self._topology_lock:
            if name in self.agent_dict:
                return False
            self.agent_dict[name] = None  # sentinel — no Agent
            self._successors[name] = set()
            self._predecessors[name] = set()
            self._routing_nodes.add(name)
            self._routers[name] = router
            self._node_states[name] = {
                "state": "idle",
                "message": "尚未开始",
                "updated_at": 0.0,
            }
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
        with self._topology_lock:
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
            self._router_scopes.pop(agent_name, None)
            self._routing_nodes.discard(agent_name)
            self._node_states.pop(agent_name, None)
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
        with self._topology_lock:
            self._require_agent(source)
            self._require_agent(target)
            if source == target:
                raise ValueError("An agent cannot connect to itself.")
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
            self.set_mapper(target, mapper)

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
        with self._topology_lock:
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
        with self._topology_lock:
            self._require_agent(agent_name)
            if agent_name in self._routing_nodes:
                raise KeyError(
                    f"{agent_name!r} is a routing-only node — use "
                    "``add_routing_node`` to set the router at creation time"
                )
            self._routers[agent_name] = router
            self._router_scopes[agent_name] = set(self._successors[agent_name])

    def remove_router(self, agent_name: str) -> bool:
        """Remove a post-completion router from an agent.

        After removal, all registered successors are activated normally.

        Returns:
            ``True`` if a router existed and was removed.
        """
        with self._topology_lock:
            if agent_name not in self._routers:
                return False
            del self._routers[agent_name]
            self._router_scopes.pop(agent_name, None)
            return True

    # ------------------------------------------------------------------
    # Dynamic mutation  —  thread-safe, usable during run()
    # ------------------------------------------------------------------

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
        """Create a worker, deliver an explicit task, and queue it to run.

        Dependency edges are not required for this operation. The worker is
        scheduled independently so its coordinator can wait for reports while
        still running. The assignment, not a predecessor's raw output, is the
        only initial input delivered to the worker.

        Args:
            agent_name: Unique graph name for the new worker.
            agent_instance: Worker Agent configured with task-report tools.
            objective: Concrete worker objective.
            handoff: Bounded coordinator state relevant to the objective.
            reply_to: Coordinator Agent that receives the structured report.
            expected_artifacts: Optional paths or names expected at close.
            task_id: Optional caller-provided durable task identifier.

        Returns:
            Immutable task assignment accepted by the task bus.

        Raises:
            ValueError: If the Agent name already exists or task fields are invalid.
        """
        with self._topology_lock:
            if agent_name in self.agent_dict:
                raise ValueError(f"Agent {agent_name!r} 已存在")
            assignment = self.task_bus.create_assignment(
                recipient=agent_name,
                reply_to=reply_to,
                objective=objective,
                handoff=handoff,
                expected_artifacts=expected_artifacts,
                task_id=task_id,
            )
            self.agent_dict[agent_name] = agent_instance
            self._successors[agent_name] = set()
            self._predecessors[agent_name] = set()
            self._task_by_agent[agent_name] = assignment.id
            self._task_by_id[assignment.id] = agent_name
            self._node_states[agent_name] = {
                "state": "queued",
                "message": "等待调度",
                "task_id": assignment.id,
                "updated_at": time.time(),
            }
            agent_instance._agent_name_in_graph = agent_name
            self._attach_agent_events(agent_instance)
        self._dynamic_ready.put(agent_name)
        self._emit(
            "graph",
            agent_name,
            "task:dispatched",
            f"Task {assignment.id} dispatched to {agent_name}",
            data={
                "task_id": assignment.id,
                "reply_to": assignment.reply_to,
                "objective": assignment.objective,
            },
        )
        return assignment

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
        """Accept a structured worker report without forwarding raw output.

        Args:
            task_id: Task identifier supplied in the worker assignment.
            reporter: Logical name of the reporting worker.
            status: Terminal report status.
            summary: Bounded worker conclusion.
            findings: Key claims or observations.
            evidence: URLs or concise evidence descriptions.
            artifacts: References to persisted detailed output.
            open_questions: Unresolved follow-up questions.
            recommended_next_action: Suggested coordinator action.

        Returns:
            Accepted immutable report.
        """
        report = self.task_bus.submit_report(
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
        self._emit(
            "graph",
            reporter,
            "task:reported",
            f"Task {task_id} reported to {report.recipient}",
            data=report.as_dict(),
        )
        return report

    def wait_for_reports(
        self,
        task_ids: Iterable[str],
        timeout_seconds: float,
    ) -> list[TaskReport]:
        """Block until requested structured reports arrive or time expires.

        Args:
            task_ids: Task identifiers expected by the coordinator.
            timeout_seconds: Maximum wait duration in seconds.

        Returns:
            Available reports in requested task order.
        """
        return self.task_bus.wait_for_reports(task_ids, timeout_seconds)

    def dynamic_add_agent(
        self,
        agent_name: str,
        agent_instance: Agent,
    ) -> str:
        """Register an Agent node while a graph run is active.

        Args:
            agent_name: Unique logical name for the new node.
            agent_instance: Agent instance that executes when ready.

        Returns:
            Status text describing registration or a duplicate-name error.
        """
        with self._topology_lock:
            if agent_name in self.agent_dict:
                return f"Error: agent '{agent_name}' already exists"

            self.agent_dict[agent_name] = agent_instance
            self._successors[agent_name] = set()
            self._predecessors[agent_name] = set()
            agent_instance._agent_name_in_graph = agent_name
            self._attach_agent_events(agent_instance)

        self._emit("graph", agent_name, "dynamic:add_agent",
                    f"Agent '{agent_name}' created")
        return f"Agent '{agent_name}' created"

    def dynamic_remove_agent(self, agent_name: str) -> str:
        """Dynamically remove an agent and its edges during execution.

        Returns a status message for the calling LLM.
        """
        with self._topology_lock:
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
            self._router_scopes.pop(agent_name, None)
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
        with self._topology_lock:
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

    def dynamic_remove_connection(self, source: str, target: str) -> str:
        """Remove one dependency edge while the graph is editable.

        Args:
            source: Existing predecessor agent name.
            target: Existing successor agent name.

        Returns:
            Status text for the coordinator Agent.
        """
        with self._topology_lock:
            if source not in self.agent_dict or target not in self.agent_dict:
                return f"Error: unknown agent in connection {source} -> {target}"
            if target not in self._successors[source]:
                return f"Connection does not exist: {source} -> {target}"
            self._successors[source].remove(target)
            self._predecessors[target].remove(source)
        self._emit("graph", source, "dynamic:disconnect", f"{source} -/-> {target}", data={"source": source, "target": target})
        return f"Disconnected: {source} -/-> {target}"

    def dynamic_set_mapper(self, agent_name: str, mode: str) -> str:
        """Set a safe declarative input aggregator on an Agent node.

        Args:
            agent_name: Target Agent receiving predecessor outputs.
            mode: ``labelled``, ``concat``, or ``json``.

        Returns:
            Status text for the coordinator Agent.
        """
        import json
        modes = {
            "labelled": lambda outputs: "\n\n".join(f"[{name}]\n{value}" for name, value in sorted(outputs.items())),
            "concat": lambda outputs: "\n\n".join(str(value) for _, value in sorted(outputs.items())),
            "json": lambda outputs: json.dumps(outputs, ensure_ascii=False, indent=2),
        }
        if mode not in modes:
            return f"Error: mapper mode must be one of {', '.join(sorted(modes))}"
        with self._topology_lock:
            if agent_name not in self.agent_dict:
                return f"Error: agent '{agent_name}' does not exist"
            self._mappers[agent_name] = modes[mode]
        self._emit("graph", agent_name, "dynamic:set_mapper", f"Mapper '{mode}' set on {agent_name}", data={"agent": agent_name, "mode": mode})
        return f"Mapper '{mode}' set on {agent_name}"

    def dynamic_set_router(self, agent_name: str, targets: list[str]) -> str:
        """Set a declarative router selecting a fixed successor subset.

        Args:
            agent_name: Source Agent whose completion will route execution.
            targets: Successor names to activate after source completion.

        Returns:
            Status text for the coordinator Agent.
        """
        with self._topology_lock:
            if agent_name not in self.agent_dict:
                return f"Error: agent '{agent_name}' does not exist"
            unknown = [target for target in targets if target not in self.agent_dict]
            if unknown:
                return f"Error: unknown router targets: {', '.join(unknown)}"
            self._routers[agent_name] = lambda _output: list(targets)
            self._router_scopes[agent_name] = set(self._successors[agent_name])
        self._emit("graph", agent_name, "dynamic:set_router", f"Router set on {agent_name}", data={"agent": agent_name, "targets": targets})
        return f"Router set on {agent_name}: {', '.join(targets) or '(none)'}"

    def dynamic_get_info(self) -> str:
        """Return the current graph state as a structured string.

        Useful for LLM agents that need to inspect the graph topology
        before deciding which agents to create or connect.
        """
        with self._topology_lock:
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
            task_agents = dict(self._task_by_id)
        task_states = self.task_bus.task_states()
        if task_states:
            lines.append("")
            lines.append("Task assignments:")
            for task_id, state in sorted(task_states.items()):
                agent_name = task_agents.get(task_id, "(removed)")
                lines.append(f"  {task_id} -> {agent_name} ({state})")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def run(
        self,
        message: str,
        max_rounds: int | None = None,
        control: AgentRunControl | None = None,
    ) -> dict[str, Any]:
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
            max_rounds: Maximum rounds passed to every Agent; ``0`` means
                unlimited and ``None`` uses each Agent's default.
            control:
                Optional cooperative stop and steering source passed to each
                scheduled Agent at completed-step boundaries.

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
        with self._topology_lock:
            if not self.agent_dict:
                return {}
        self._shutdown_requested.clear()

        self._emit("graph", "", "graph:start", message)

        with self._topology_lock:
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
        running_agents: dict[Future[Any], Agent] = {}
        running_hooks: dict[Future[Any], list[ExecutionHook]] = {}
        routed_out: set[str] = set()

        with ThreadPoolExecutor(
            max_workers=self.max_concurrency_agents
        ) as executor:
            while (
                (ready or running or not self._dynamic_ready.empty())
                and not self._shutdown_requested.is_set()
            ):
                self._drain_dynamic_ready(ready, remaining_dependencies)
                # --- submit ready agents up to the concurrency limit ----
                while (
                    ready
                    and len(running) < self.max_concurrency_agents
                    and not self._shutdown_requested.is_set()
                ):
                    agent_name = ready.popleft()

                    with self._topology_lock:
                        is_routing_node = agent_name in self._routing_nodes
                        if agent_name not in self.agent_dict:
                            continue
                        input_message = self._build_input(
                            agent_name=agent_name,
                            initial_message=message,
                            outputs=outputs,
                        )
                        routing_fn = self._routers.get(agent_name)
                        agent_instance = self.agent_dict.get(agent_name)
                        task_id = self._task_by_agent.get(agent_name)

                    if task_id:
                        assignment = self.task_bus.claim_assignment(task_id)
                        input_message = self._render_assignment(assignment)

                    # Routing callbacks are external code and must run outside
                    # the topology lock.
                    if is_routing_node:
                        if routing_fn is None:
                            raise RuntimeError(f"Routing node {agent_name!r} has no router")
                        outputs[agent_name] = input_message
                        selected = routing_fn(input_message)
                        selected_set = set(selected)
                        with self._topology_lock:
                            successors = tuple(self._successors.get(agent_name, ()))
                            for successor in successors:
                                if successor not in selected_set:
                                    routed_out.add(successor)
                            self._activate(
                                agent_name, selected,
                                remaining_dependencies, ready,
                            )
                        continue

                    if agent_instance is None:
                        continue

                    self._emit(
                        "graph", agent_name, "agent:submitted",
                        message,
                    )

                    run_kwargs: dict[str, Any] = {"control": control}
                    if max_rounds is not None:
                        run_kwargs["max_rounds"] = max_rounds
                    with self._hooks_lock:
                        agent_hooks = list(self.hooks)
                    for hook in agent_hooks:
                        add_hook = getattr(agent_instance, "add_hook", None)
                        if add_hook is not None:
                            add_hook(hook)
                    future: Future = executor.submit(
                        agent_instance.run,
                        input_message,
                        **run_kwargs,
                    )
                    running[future] = agent_name
                    running_agents[future] = agent_instance
                    running_hooks[future] = agent_hooks

                if not running:
                    continue
                if self._shutdown_requested.is_set():
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
                    agent_instance = running_agents.pop(future)
                    for hook in running_hooks.pop(future, []):
                        remove_hook = getattr(agent_instance, "remove_hook", None)
                        if remove_hook is not None:
                            remove_hook(hook)
                    with self._topology_lock:
                        task_id = self._task_by_agent.get(agent_name)

                    try:
                        outputs[agent_name] = future.result()
                        self._emit(
                            "graph", agent_name, "agent:completed",
                            f"Agent completed",
                            data={"output_len": len(str(outputs[agent_name]))},
                        )
                        if task_id:
                            missing_report = self.task_bus.fail_unreported_task(
                                task_id,
                                agent_name,
                                "Worker 已完成，但没有通过 report_task 提交结构化报告。",
                            )
                            if missing_report is not None:
                                self._emit(
                                    "graph",
                                    agent_name,
                                    "task:report_missing",
                                    f"Task {task_id} finished without report_task",
                                    data=missing_report.as_dict(),
                                )
                    except Exception as exc:
                        if isinstance(exc, AgentRunStopped):
                            if task_id:
                                self.task_bus.set_terminal_state(task_id, "interrupted")
                            for pending_future in running:
                                pending_future.cancel()
                            raise
                        if task_id:
                            self.task_bus.fail_unreported_task(
                                task_id,
                                agent_name,
                                f"Worker 运行失败：{str(exc)[:1000]}",
                            )
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

                    # Snapshot topology state, then invoke any user-defined
                    # router without blocking concurrent dynamic mutations.
                    with self._topology_lock:
                        routing_fn = self._routers.get(agent_name)
                        successors = tuple(self._successors.get(agent_name, ()))
                        router_scope = set(self._router_scopes.get(agent_name, successors))
                    if routing_fn is not None:
                        output_text = self._output_to_text(outputs[agent_name])
                        selected = list(routing_fn(output_text))
                        selected.extend(
                            successor for successor in successors
                            if successor not in router_scope
                        )
                        selected_set = set(selected)
                        with self._topology_lock:
                            for successor in successors:
                                if successor not in selected_set:
                                    routed_out.add(successor)
                            self._activate(
                                agent_name, selected,
                                remaining_dependencies, ready,
                            )
                    else:
                        with self._topology_lock:
                            self._activate(
                                agent_name, successors,
                                remaining_dependencies, ready,
                            )

        # --- final validation: detect deadlocks -------------------------
        with self._topology_lock:
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
        successors: Iterable[str],
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

    def _drain_dynamic_ready(
        self,
        ready: deque[str],
        remaining_dependencies: dict[str, int],
    ) -> None:
        """Move explicitly dispatched workers into the local scheduler queue.

        Args:
            ready: Local FIFO queue owned by the scheduler loop.
            remaining_dependencies: Mutable dependency counters for this run.

        Returns:
            None.
        """
        while True:
            try:
                agent_name = self._dynamic_ready.get_nowait()
            except Empty:
                return
            with self._topology_lock:
                if agent_name not in self.agent_dict:
                    continue
                if agent_name in remaining_dependencies:
                    continue
                remaining_dependencies[agent_name] = 0
            ready.append(agent_name)

    @staticmethod
    def _render_assignment(assignment: TaskAssignment) -> str:
        """Render one explicit task package without exposing raw peer output.

        Args:
            assignment: Structured task package claimed by a worker.

        Returns:
            Bounded model input containing task and coordinator handoff only.
        """
        artifact_text = ", ".join(assignment.expected_artifacts) or "None"
        handoff = assignment.handoff or "No more assignment info."
        return (
            f"Quest ID: {assignment.id}\n"
            f"Target: {assignment.objective}\n"
            f"Assigner: {handoff}\n"
            f"Expected artifact: {artifact_text}\n\n"
            "After finishing your job, a call for tool report_task for structured abstract, evidence, reference for artifact and problems needs to solve SHOULD be done."
        )

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
