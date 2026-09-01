"""Host-neutral session and workspace registration use cases."""

from __future__ import annotations

from pathlib import Path
import shutil
import hashlib
from typing import TYPE_CHECKING

from ..workspace_module import Workspace
from ..execution_module import ExecutionState
from ..session_module import create_agent, validate_session_id
from ..tool_module import ToolPolicy
from llmfetcher import Agent, LLMBackendConfig

if TYPE_CHECKING:
    from ...core import AngelusCore


class SessionService:
    """Create Sessions and materialize their required coordinator when runnable."""

    def __init__(self, core: "AngelusCore") -> None:
        """Use the process's core for session registration and workspace paths.

        Args:
            core: Owner of the registry, catalog, legacy archive bridge, and
                Angelus-owned state root participating in this use case.
        """
        # Service dependency; it is the only route to cross-store operations.
        self._core = core

    def create(self, session_id: str, name: str, project_path: Path) -> Workspace:
        """Register an empty Session and its durable workspace metadata.

        Agent configuration is deliberately a separate use case: a workspace
        may exist before the user selects backends, tools, or a swarm graph.
        """
        validate_session_id(session_id)
        if not name.strip():
            raise ValueError("name must not be blank")
        resolved_project = project_path.expanduser().resolve()
        if not resolved_project.is_dir():
            raise ValueError("project_path must be an existing directory")
        workspace = Workspace(
            session_id=session_id,
            name=name,
            project_path=resolved_project,
            state_path=self._core.state_root / "sessions" / session_id,
        )
        self._core.sessions.create(session_id, execution_root=workspace.state_path)
        try:
            self._core.workspaces.add(workspace)
        except BaseException:
            self._core.sessions.remove(session_id)
            raise
        return workspace

    def list(self) -> tuple[Workspace, ...]:
        """List durable workspace records, including sessions configured later.

        This does not read Agent context or start an execution; it only reads
        the compact workspace catalog.
        """
        return self._core.workspaces.list()

    def ensure_coordinator(self, session_id: str) -> None:
        """Build or retain the Session's required coordinator from saved profile.

        A Session always has the ``coordinator`` role, but llmfetcher eagerly
        builds provider clients and therefore an actual Agent is created only
        once a saved connector with a secret is selected.  This method is
        called immediately before execution, making profile persistence the
        single source of truth and preventing a stale browser draft from
        silently selecting credentials.

        Raises:
            RuntimeError: If no saved connector/secret is available.
            KeyError: If the Session does not exist.
        """
        session = self._core.sessions.get(session_id)
        profile = self._core.run_profiles.effective(session_id)
        permissions = ToolPolicy.from_profile(profile.get("tool_permissions"))
        connector_id = profile.get("connector_id")
        if not isinstance(connector_id, str) or not connector_id:
            raise RuntimeError("Session coordinator requires a saved connector")
        try:
            api_key = self._core.connectors.api_key(connector_id)
        except KeyError as exc:
            raise RuntimeError("Session coordinator connector has no saved API key") from exc
        fingerprint = (
            connector_id, hashlib.sha256(api_key.encode("utf-8")).hexdigest(),
            profile["provider"], profile["model"], profile["api_url"],
            profile["system_prompt"], profile["max_tokens"], profile["max_rounds"],
            profile["max_retries"], profile["max_context_threshold"], profile["max_swarm_agents"], permissions.fingerprint(),
        )
        if session.coordinator_matches(fingerprint):
            return
        workspace = self._core.workspaces.get(session_id)
        coordinator = create_agent(
            [LLMBackendConfig(
                name=session.coordinator_name,
                provider=profile["provider"],
                model=profile["model"],
                api_key=api_key,
                api_url=profile["api_url"] or None,
                max_retries=profile["max_retries"],
            )],
            self._core.tool_registry.materialize(session, permissions, "coordinator"),
            system_prompt=profile["system_prompt"],
            max_concurrency=profile["max_swarm_agents"],
            max_context_threshold=profile["max_context_threshold"],
            context_path=workspace.state_path / "agents" / session.coordinator_name / "context.json",
            default_max_rounds=profile["max_rounds"],
            default_max_tokens=profile["max_tokens"],
            enable_stop_turn=permissions.allows("turn_control", "stop_turn"),
        )
        session.set_coordinator(coordinator, fingerprint)
        # Unit-test and alternate-host factories may supply a sentinel role;
        # only a concrete llmfetcher Agent is valid for graph registration.
        if isinstance(coordinator, Agent):
            self.rebuild_swarm(session_id)

    def rebuild_swarm(self, session_id: str) -> None:
        """Materialize the safe console blueprint into the Session's one swarm.

        Workers inherit the effective profile; their persisted blueprint has
        only a name and instructions, never a connector secret.
        """
        from llmfetcher import AgentSwarm
        session = self._core.sessions.get(session_id)
        if session.coordinator is None or session.console is None:
            return
        profile = self._core.run_profiles.effective(session_id)
        permissions = ToolPolicy.from_profile(profile.get("tool_permissions"))
        api_key = self._core.connectors.api_key(profile["connector_id"])
        workspace = self._core.workspaces.get(session_id)
        swarm = AgentSwarm(max_concurrency_agents=profile["max_swarm_agents"])
        swarm.add_agent(session.coordinator_name, session.coordinator)
        blueprint = session.console.blueprint()
        workers = []
        for name, worker in blueprint.workers.items():
            agent = create_agent(
                [LLMBackendConfig(name=name, provider=profile["provider"], model=profile["model"], api_key=api_key, api_url=profile["api_url"] or None, max_retries=profile["max_retries"])], self._core.tool_registry.materialize(session, permissions, "worker"),
                system_prompt=worker.system_prompt or profile["system_prompt"], max_concurrency=profile["max_swarm_agents"], max_context_threshold=profile["max_context_threshold"],
                context_path=workspace.state_path / "agents" / name / "context.json", default_max_rounds=profile["max_rounds"], default_max_tokens=profile["max_tokens"], enable_stop_turn=permissions.allows("turn_control", "stop_turn"),
            )
            swarm.add_agent(name, agent); workers.append(agent)
        for connection in blueprint.connections:
            swarm.add_connection(connection.source, connection.target)
        for agent, mode in blueprint.mappers.items(): swarm.dynamic_set_mapper(agent, mode)
        for agent, targets in blueprint.routers.items(): swarm.dynamic_set_router(agent, targets)
        session.agents = [session.coordinator, *workers]
        session.swarm = swarm

    def preview_agent(self, session_id: str, name: str) -> Agent:
        """Build one detached Agent for a no-I/O request preview.

        Args:
            session_id: Stable Session identity providing profile and tools.
            name: Coordinator or persisted Worker identity to preview.

        Returns:
            Fresh Agent with the Session's effective profile, tools, and
            context path. The caller owns it and must not add it to a swarm.

        Raises:
            KeyError: If the Session or requested persisted role is missing.
            RuntimeError: If the effective profile lacks a usable connector.
        """
        session = self._core.sessions.get(session_id)
        blueprint = session.console.blueprint()
        if name != session.coordinator_name and name not in blueprint.workers:
            raise KeyError(name)
        profile = self._core.run_profiles.effective(session_id)
        permissions = ToolPolicy.from_profile(profile.get("tool_permissions"))
        connector_id = profile.get("connector_id")
        if not isinstance(connector_id, str) or not connector_id:
            raise RuntimeError("Session preview requires a saved connector")
        try:
            api_key = self._core.connectors.api_key(connector_id)
        except KeyError as exc:
            raise RuntimeError("Session preview connector has no saved API key") from exc
        workspace = self._core.workspaces.get(session_id)
        worker = blueprint.workers.get(name)
        role = "coordinator" if name == session.coordinator_name else "worker"
        system_prompt = profile["system_prompt"] if worker is None else worker.system_prompt or profile["system_prompt"]
        return create_agent(
            [LLMBackendConfig(
                name=name,
                provider=profile["provider"],
                model=profile["model"],
                api_key=api_key,
                api_url=profile["api_url"] or None,
                max_retries=profile["max_retries"],
            )],
            self._core.tool_registry.materialize(session, permissions, role),
            system_prompt=system_prompt,
            max_concurrency=profile["max_swarm_agents"],
            max_context_threshold=profile["max_context_threshold"],
            context_path=workspace.state_path / "agents" / name / "context.json",
            default_max_rounds=profile["max_rounds"],
            default_max_tokens=profile["max_tokens"],
            enable_stop_turn=permissions.allows("turn_control", "stop_turn"),
        )

    def delete(self, session_id: str, *, confirmation: str, wait_timeout: float = 5.0) -> Workspace:
        """Force-stop, durably remove, and unregister one confirmed Session.

        A session remains intact when its worker cannot reach a terminal state
        by the bounded deadline.  This prevents a still-running Agent from
        writing into directories that have already been removed.
        """
        if confirmation != session_id:
            raise ValueError("confirmation must equal the session ID")
        workspace = self._core.workspaces.get(session_id)
        executor = self._core.sessions.get(session_id).execution
        if executor is not None:
            state = executor.snapshot().state
            if state in {ExecutionState.RUNNING, ExecutionState.STOPPING, ExecutionState.FORCE_STOPPING}:
                executor.request_stop(force=True, reason="session_deleted")
                if not executor.wait(wait_timeout):
                    raise RuntimeError("execution did not stop before the deletion deadline")
        state_path = workspace.state_path.resolve()
        sessions_root = (self._core.state_root / "sessions").resolve()
        if state_path.parent != sessions_root:
            raise ValueError("invalid session state path")
        if state_path.exists():
            shutil.rmtree(state_path)
        self._core.conversations.remove(session_id)
        self._core.workspaces.remove_legacy_session(self._core.legacy_workspace_index, session_id)
        self._core.workspaces.remove(session_id)
        self._core.sessions.remove(session_id)
        return workspace
