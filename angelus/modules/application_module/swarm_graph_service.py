"""Single read/write gateway for a Session's swarm execution graph.

Every HTTP graph edit, model-facing ``swarm_*`` tool, control pre-registration
and UI projection must go through this service.  It is the only place allowed
to combine the durable ``ConsoleState`` blueprint with the live ``AgentSwarm``
and the only place allowed to apply a topology mutation to either.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from typing import TYPE_CHECKING, Callable

from ..console_module import ConsoleDomainError, ConsoleState
from ..console_module.console_state import ConsoleBlueprint
from ..console_module.projection_service import RunGraphProjector
from ..execution_module import ExecutionState
from llmfetcher.swarm_module.snapshots import SwarmViewSnapshot
from llmfetcher.swarm_module.task_bus import append_subagent_report_instruction

if TYPE_CHECKING:
    from ...core import AngelusCore
    from ..session_module.session_handler import Session

_ACTIVE_STATES = {
    ExecutionState.RUNNING,
    ExecutionState.STOPPING,
    ExecutionState.FORCE_STOPPING,
}


def _rollback_failures(
    console: ConsoleState,
    previous: ConsoleBlueprint,
    cleanup: Callable[[], object] | None = None,
) -> list[BaseException]:
    """Attempt every rollback action and return failures for aggregation."""
    failures: list[BaseException] = []
    try:
        console.replace(previous)
    except BaseException as exc:
        failures.append(exc)
    if cleanup is not None:
        try:
            cleanup()
        except BaseException as exc:
            failures.append(exc)
    return failures


@dataclass(frozen=True)
class SwarmGraphResult:
    """Outcome of one topology mutation plus the canonical graph snapshot.

    Attributes:
        status: Model-facing status text describing the accepted mutation.
        snapshot: Canonical graph snapshot after the mutation.
        payload: Optional operation payload, such as a dispatched assignment.
    """

    status: str
    snapshot: dict[str, object]
    payload: object | None = None


class SwarmGraphService:
    """Read and mutate one Session's swarm execution graph through one path.

    The gateway is the only component that combines the durable
    ``ConsoleState`` blueprint with the live ``AgentSwarm``. Adapters must not
    call ``ConsoleState`` topology mutators or ``AgentSwarm`` dynamic methods
    directly.
    """

    def __init__(self, core: "AngelusCore") -> None:
        """Bind the gateway to the application composition root.

        Args:
            core: Process-wide composition root owning Sessions and services.
        """
        self._core = core
        self._projector = RunGraphProjector()

    def snapshot(self, session_id: str, execution_id: str | None = None) -> dict[str, object]:
        """Return the one canonical swarm execution graph snapshot.

        Args:
            session_id: Stable Session identity to inspect.
            execution_id: Optional attempt identity; ``None`` selects the
                latest/live attempt.

        Returns:
            Nodes, edges, assignments, task states and topology metadata.
            ``source`` is ``"live"`` when the active swarm supplied the graph,
            otherwise ``"durable"``.

        Raises:
            KeyError: If the Session does not exist.
        """
        session = self._session(session_id)
        executor = session.execution
        status = executor.snapshot() if executor is not None else None
        live_snapshot = self._live_view(session, execution_id)
        live = live_snapshot is not None
        live_status = None
        if live and status is not None:
            if is_dataclass(status):
                live_status = asdict(status)
            else:
                state = status.state
                live_status = {
                    "state": state.value if isinstance(state, ExecutionState) else state,
                    "execution_id": status.execution_id,
                }
        if executor is None:
            graph = self._projector.project(session_id, self._core.state_root / "sessions" / session_id)
        else:
            graph = self._projector.project(
                session_id,
                executor.root,
                execution_id=execution_id,
                live_snapshot=live_snapshot,
                live_status=live_status,
            )
        blueprint = session.console.blueprint() if session.console is not None else None
        if live_snapshot is not None and not graph.get("nodes"):
            graph["nodes"] = [node.to_json() for node in live_snapshot.nodes]
            graph["edges"] = [edge.to_json() for edge in live_snapshot.edges]
        self._decorate(graph, blueprint, live)
        return graph

    def live_view(
        self, session_id: str, execution_id: str | None = None
    ) -> SwarmViewSnapshot | None:
        """Return the typed live view for an active Session attempt.

        The gateway is the only component allowed to read the live swarm, so
        adapters that need the typed snapshot (for example the execution
        service while committing a checkpoint) come through here instead of
        touching ``Session.swarm`` directly.

        Args:
            session_id: Stable Session identity to inspect.
            execution_id: Optional attempt identity; ``None`` accepts the
                current attempt.

        Returns:
            The live snapshot, or ``None`` when the Session has no active
            attempt or no materialized swarm.

        Raises:
            KeyError: If the Session does not exist.
        """
        return self._live_view(self._session(session_id), execution_id)

    def _live_view(
        self, session: "Session", execution_id: str | None
    ) -> SwarmViewSnapshot | None:
        """Read one live snapshot, or ``None`` when the attempt is not live."""
        executor = session.execution
        swarm = session.swarm
        if executor is None or swarm is None:
            return None
        status = executor.snapshot()
        if status.state not in _ACTIVE_STATES:
            return None
        if execution_id is not None and execution_id != status.execution_id:
            return None
        return swarm.view_snapshot()

    def topology(self, session_id: str) -> dict[str, object]:
        """Return the editable static topology derived from :meth:`snapshot`.

        Args:
            session_id: Stable Session identity to inspect.

        Returns:
            Agent nodes, dependency edges, mappers, routers and revision.

        Raises:
            KeyError: If the Session does not exist.
        """
        graph = self.snapshot(session_id)
        nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
        edges = graph.get("edges") if isinstance(graph.get("edges"), list) else []
        return {
            "schema_version": 1,
            "kind": "angelus.workflow",
            "nodes": [node for node in nodes if isinstance(node, dict) and node.get("kind") == "agent"],
            "edges": [edge for edge in edges if isinstance(edge, dict) and edge.get("kind") == "dependency"],
            "mappers": graph.get("mappers", {}),
            "routers": graph.get("routers", {}),
            "revision": graph.get("revision", 0),
        }

    def materialize(self, session_id: str) -> None:
        """Rebuild the live swarm from the durable blueprint.

        This is the write path's only materializer; callers must reach it
        through :meth:`apply`-style methods rather than calling
        ``SessionService.rebuild_swarm`` directly.

        Args:
            session_id: Stable Session identity whose live swarm is rebuilt.

        Returns:
            None. The Session's live ``AgentSwarm`` is replaced in place.

        Raises:
            KeyError: If the Session does not exist.
        """
        self._core.session_service.rebuild_swarm(session_id)

    def control_nodes(self, session_id: str) -> list[dict[str, object]]:
        """Return agent nodes used to pre-register control views.

        Args:
            session_id: Stable Session identity whose attempt is starting.

        Returns:
            Agent nodes from the live graph when available, otherwise the
            durable blueprint. Routing and task nodes are excluded.

        Raises:
            KeyError: If the Session does not exist.
        """
        session = self._session(session_id)
        view = session.swarm.view_snapshot if session.swarm is not None else None
        if view is not None:
            try:
                candidate = view()
            except Exception:
                candidate = None
            if isinstance(candidate, dict):
                nodes = candidate.get("nodes")
                if isinstance(nodes, list):
                    agents = [node for node in nodes if isinstance(node, dict) and node.get("kind") == "agent"]
                    if agents:
                        return agents
        blueprint = session.console.blueprint() if session.console is not None else None
        if blueprint is None:
            return []
        return [
            {"id": "coordinator", "kind": "agent", "role": "coordinator"},
            *[
                {"id": worker.name, "kind": "agent", "role": worker.role}
                for worker in sorted(blueprint.workers.values(), key=lambda item: item.name)
            ],
        ]

    def add_agent(self, session_id: str, name: str, system_prompt: str) -> SwarmGraphResult:
        """Add one worker to the durable and live graph through one path.

        Args:
            session_id: Stable Session identity owning the graph.
            name: Unique worker identity.
            system_prompt: Worker-specific instructions; never a secret.

        Returns:
            Mutation status and the graph snapshot after the write.

        Raises:
            ConsoleDomainError: If the worker name is invalid or duplicated,
                or if the live swarm rejects the add.
            KeyError: If the Session does not exist.
        """
        session = self._session(session_id)
        console = self._require_console(session)
        with console.transaction():
            previous = console.blueprint()
            console.add_worker(name, system_prompt)
            worker = None
            try:
                if self._is_live(session):
                    swarm = self._require_live_swarm(session)
                    worker = self._core.session_service.create_runtime_worker(session_id, name, system_prompt)
                    result = swarm.dynamic_add_agent(name, worker)
                    if str(result).startswith("Error:"):
                        raise ConsoleDomainError(str(result))
                    session.agents.append(worker)
                    if session.run_control is not None:
                        session.run_control.for_agent(name)
                else:
                    self.materialize(session_id)
            except BaseException as exc:
                cleanup = (
                    (lambda: session.swarm.dynamic_remove_agent(name))
                    if worker is not None and session.swarm is not None
                    else None
                )
                failures = _rollback_failures(console, previous, cleanup)
                if failures:
                    raise BaseExceptionGroup(
                        "swarm graph mutation and rollback both failed",
                        [exc, *failures],
                    ) from exc
                raise
            return SwarmGraphResult(f"Agent '{name}' created", self.snapshot(session_id))

    def remove_agent(self, session_id: str, name: str) -> SwarmGraphResult:
        """Remove one worker from the durable and live graph through one path.

        Args:
            session_id: Stable Session identity owning the graph.
            name: Existing worker identity.

        Returns:
            Mutation status and the graph snapshot after the write.

        Raises:
            ConsoleDomainError: If the worker is unknown, is the coordinator,
                or if the live swarm rejects the removal.
            KeyError: If the Session does not exist.
        """
        session = self._session(session_id)
        console = self._require_console(session)
        with console.transaction():
            previous = console.blueprint()
            live = self._is_live(session)
            worker = None
            if live and session.swarm is not None:
                try:
                    worker = session.swarm.get_agent(name)
                except KeyError:
                    worker = None
            console.remove_worker(name)
            try:
                if live:
                    swarm = self._require_live_swarm(session)
                    result = swarm.dynamic_remove_agent(name)
                    if str(result).startswith("Error:"):
                        raise ConsoleDomainError(str(result))
                    session.agents = [agent for agent in session.agents if agent is not worker]
                    if session.run_control is not None:
                        session.run_control.forget_agent(name)
                else:
                    self.materialize(session_id)
            except BaseException as exc:
                failures = _rollback_failures(console, previous)
                if failures:
                    raise BaseExceptionGroup(
                        "swarm graph mutation and rollback both failed",
                        [exc, *failures],
                    ) from exc
                raise
            return SwarmGraphResult(f"Agent '{name}' removed", self.snapshot(session_id))

    def dispatch_agent(
        self,
        session_id: str,
        name: str,
        system_prompt: str,
        dispatch: Callable[[object], object],
    ) -> SwarmGraphResult:
        """Create one Worker and dispatch its first task through one path.

        Args:
            session_id: Stable Session identity owning the graph.
            name: Unique worker identity.
            system_prompt: Worker-specific instructions; never a secret.
            dispatch: Callback receiving the created worker and returning the
                TaskBus assignment; it must only dispatch, never persist.

        Returns:
            Mutation status, graph snapshot, and the dispatch payload.

        Raises:
            ConsoleDomainError: If the run is idle, the worker name is invalid,
                or the live swarm rejects the dispatch.
            KeyError: If the Session does not exist.
        """
        session = self._session(session_id)
        console = self._require_console(session)
        with console.transaction():
            previous = console.blueprint()
            worker_prompt = append_subagent_report_instruction(system_prompt)
            console.add_worker(name, worker_prompt)
            worker = None
            payload = None
            try:
                if not self._is_live(session):
                    raise ConsoleDomainError("dispatch requires an active run")
                worker = self._core.session_service.create_runtime_worker(session_id, name, worker_prompt)
                payload = dispatch(worker)
                session.agents.append(worker)
                if session.run_control is not None:
                    session.run_control.for_agent(name)
            except BaseException as exc:
                cleanup = (
                    (lambda: session.swarm.dynamic_remove_agent(name))
                    if worker is not None and session.swarm is not None
                    else None
                )
                failures = _rollback_failures(console, previous, cleanup)
                if failures:
                    raise BaseExceptionGroup(
                        "swarm graph mutation and rollback both failed",
                        [exc, *failures],
                    ) from exc
                raise
            return SwarmGraphResult(f"Task dispatched to '{name}'", self.snapshot(session_id), payload)

    def add_connection(self, session_id: str, source: str, target: str) -> SwarmGraphResult:
        """Add one acyclic dependency edge through one path.

        Args:
            session_id: Stable Session identity owning the graph.
            source: Existing upstream Agent identity.
            target: Existing downstream Agent identity.

        Returns:
            Mutation status and the graph snapshot after the write.

        Raises:
            ConsoleDomainError: If the edge is invalid, duplicated, cyclic, or
                rejected by the live swarm.
            KeyError: If the Session does not exist.
        """
        return self._mutate(
            session_id,
            lambda console: console.add_connection(source, target),
            lambda swarm: swarm.dynamic_add_connection(source, target),
            "Connection added",
        )

    def remove_connection(self, session_id: str, source: str, target: str) -> SwarmGraphResult:
        """Remove one dependency edge through one path.

        Args:
            session_id: Stable Session identity owning the graph.
            source: Existing upstream Agent identity.
            target: Existing downstream Agent identity.

        Returns:
            Mutation status and the graph snapshot after the write.

        Raises:
            ConsoleDomainError: If the edge is absent or rejected by the live
                swarm.
            KeyError: If the Session does not exist.
        """
        return self._mutate(
            session_id,
            lambda console: console.remove_connection(source, target),
            lambda swarm: swarm.dynamic_remove_connection(source, target),
            "Connection removed",
        )

    def set_mapper(self, session_id: str, agent: str, mode: str) -> SwarmGraphResult:
        """Set one declarative mapper through one path.

        Args:
            session_id: Stable Session identity owning the graph.
            agent: Existing receiving Agent identity.
            mode: One of ``concat``, ``json``, or ``labelled``.

        Returns:
            Mutation status and the graph snapshot after the write.

        Raises:
            ConsoleDomainError: If the Agent or mode is invalid, or the live
                swarm rejects the mapper.
            KeyError: If the Session does not exist.
        """
        return self._mutate(
            session_id,
            lambda console: console.mapper(agent, mode),
            lambda swarm: swarm.dynamic_set_mapper(agent, mode),
            f"Mapper for '{agent}' set to {mode}",
        )

    def set_router(self, session_id: str, agent: str, targets: list[str]) -> SwarmGraphResult:
        """Set one fixed router target list through one path.

        Args:
            session_id: Stable Session identity owning the graph.
            agent: Existing routing source Agent identity.
            targets: Existing successor Agent identities.

        Returns:
            Mutation status and the graph snapshot after the write.

        Raises:
            ConsoleDomainError: If any Agent is unknown or the live swarm
                rejects the router.
            KeyError: If the Session does not exist.
        """
        return self._mutate(
            session_id,
            lambda console: console.router(agent, targets),
            lambda swarm: swarm.dynamic_set_router(agent, targets),
            f"Router for '{agent}' updated",
        )

    def _mutate(
        self,
        session_id: str,
        mutate: Callable[[ConsoleState], None],
        apply_live: Callable[[object], str],
        status: str,
    ) -> SwarmGraphResult:
        """Apply one persisted topology mutation and mirror it to a live swarm.

        Args:
            session_id: Stable Session identity owning the graph.
            mutate: Callback that validates and persists the blueprint change.
            apply_live: Callback that mirrors the change to a live swarm.
            status: Model-facing status text for the accepted mutation.

        Returns:
            Mutation status and the graph snapshot after the write.

        Raises:
            ConsoleDomainError: If the live swarm rejects the change.
            KeyError: If the Session does not exist.
        """
        session = self._session(session_id)
        console = self._require_console(session)
        with console.transaction():
            previous = console.blueprint()
            mutate(console)
            try:
                if self._is_live(session):
                    swarm = self._require_live_swarm(session)
                    result = apply_live(swarm)
                    if str(result).startswith("Error:"):
                        raise ConsoleDomainError(str(result))
                else:
                    self.materialize(session_id)
            except BaseException:
                console.replace(previous)
                raise
            return SwarmGraphResult(status, self.snapshot(session_id))

    def _decorate(self, graph: dict[str, object], blueprint: object, live: bool) -> None:
        """Attach roles, mappers, routers, revision and the data source.

        Args:
            graph: Mutable projector output for the current Session.
            blueprint: Durable console blueprint, or ``None`` when unavailable.
            live: Whether the graph was built from the live swarm.

        Returns:
            None. ``graph`` is updated in place.
        """
        roles = {"coordinator": "coordinator"}
        mappers: dict[str, str] = {}
        routers: dict[str, list[str]] = {}
        revision = 0
        workers = blueprint.workers if isinstance(blueprint, ConsoleBlueprint) else None
        if isinstance(workers, dict):
            for worker in workers.values():
                name = worker.name
                if name:
                    roles[name] = worker.role
        raw_mappers = blueprint.mappers if isinstance(blueprint, ConsoleBlueprint) else None
        if isinstance(raw_mappers, dict):
            mappers = {str(name): str(mode) for name, mode in raw_mappers.items()}
        raw_routers = blueprint.routers if isinstance(blueprint, ConsoleBlueprint) else None
        if isinstance(raw_routers, dict):
            routers = {str(name): [str(target) for target in targets] for name, targets in raw_routers.items()}
        revision = blueprint.schema_version if isinstance(blueprint, ConsoleBlueprint) else 0
        nodes = graph.get("nodes")
        if isinstance(nodes, list):
            for node in nodes:
                if isinstance(node, dict):
                    node.setdefault("role", roles.get(str(node.get("id")), "worker"))
        # A durable RunGraph checkpoint can contain runtime nodes while its
        # edge list is empty (for example, if SIGINT lands between a runtime
        # snapshot and the next topology event).  The persisted workflow
        # blueprint remains the source of truth for static dependency edges;
        # restore those edges independently of whether nodes were checkpointed.
        if not live and isinstance(workers, dict):
            if not graph.get("nodes"):
                graph["nodes"] = [
                    {"id": "coordinator", "kind": "agent", "role": "coordinator"},
                    *[
                        {"id": worker.name, "kind": "agent", "role": worker.role, "dynamic": False, "parent": None}
                        for worker in sorted(workers.values(), key=lambda item: item.name)
                    ],
                ]
            if not graph.get("edges"):
                connections = blueprint.connections
                graph["edges"] = [
                    {"source": edge.source, "target": edge.target, "kind": "dependency"}
                    for edge in (connections if isinstance(connections, list) else [])
                ]
        graph["source"] = "live" if live else "durable"
        graph["mappers"] = mappers
        graph["routers"] = routers
        graph["revision"] = revision

    def _session(self, session_id: str) -> "Session":
        """Resolve one Session without hiding an unknown identity.

        Args:
            session_id: Stable Session identity to resolve.

        Returns:
            The process-local Session aggregate.

        Raises:
            KeyError: If the Session does not exist.
        """
        return self._core.sessions.get(session_id)

    @staticmethod
    def _is_live(session: "Session") -> bool:
        """Return whether the Session has an active execution attempt.

        Args:
            session: Session aggregate to inspect.

        Returns:
            ``True`` while an attempt is running, stopping, or force-stopping.
        """
        executor = session.execution
        return executor is not None and executor.snapshot().state in _ACTIVE_STATES

    @staticmethod
    def _require_console(session: "Session") -> ConsoleState:
        """Require the durable console state used by every topology mutation.

        Args:
            session: Session aggregate to inspect.

        Returns:
            The Session's durable console state.

        Raises:
            ConsoleDomainError: If the Session has no console state.
        """
        if session.console is None:
            raise ConsoleDomainError("Session console state is unavailable")
        return session.console

    @staticmethod
    def _require_live_swarm(session: "Session") -> object:
        """Require a materialized live swarm for an active mutation.

        Args:
            session: Session aggregate to inspect.

        Returns:
            The Session's live ``AgentSwarm``.

        Raises:
            ConsoleDomainError: If the Session has no materialized swarm.
        """
        if session.swarm is None:
            raise ConsoleDomainError("Session swarm is not materialized")
        return session.swarm
