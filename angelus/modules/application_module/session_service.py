"""Host-neutral session and workspace registration use cases."""

from __future__ import annotations

from pathlib import Path
import shutil
import hashlib
from typing import TYPE_CHECKING, Callable

from ..workspace_module import Workspace
from ..execution_module import ExecutionState
from ..session_module import create_agent, validate_session_id
from ..tool_module import ToolPolicy
from llmfetcher import Agent, LLMBackendConfig
from llmfetcher.execution import ExecutionController, StopMode

if TYPE_CHECKING:
    from ...core import AngelusCore
    from ..session_module.session_handler import Session


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

    def create(self, session_id: str, name: str, project_path: Path | None = None) -> Workspace:
        """Register an empty Session and its durable workspace metadata.

        Agent configuration is deliberately a separate use case: a workspace
        may exist before the user selects backends, tools, or a swarm graph.
        """
        validate_session_id(session_id)
        if not name.strip():
            raise ValueError("name must not be blank")
        state_path = self._core.state_root / "sessions" / session_id
        if project_path is None:
            # Keep an unbound session usable without exposing the host CWD.
            resolved_project = state_path / "workspace"
            resolved_project.mkdir(parents=True, exist_ok=True)
        else:
            resolved_project = project_path.expanduser().resolve()
            if not resolved_project.is_dir():
                raise ValueError("project_path must be an existing directory")
        workspace = Workspace(
            session_id=session_id,
            name=name,
            project_path=resolved_project,
            state_path=state_path,
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
        session: Session = self._core.sessions.get(session_id)
        profile = self._core.run_profiles.effective(session_id)
        permissions = ToolPolicy.from_profile(profile.get("tool_permissions"))
        connector_id = profile.get("connector_id")
        if not isinstance(connector_id, str) or not connector_id:
            raise RuntimeError("Session coordinator requires a saved connector")
        try:
            api_key = self._core.connectors.api_key(connector_id)
            connection = self._core.connectors.connection_config(connector_id)
        except KeyError as exc:
            raise RuntimeError("Session coordinator connector has no saved API key") from exc
        fingerprint = (
            connector_id, hashlib.sha256(api_key.encode("utf-8")).hexdigest(),
            connection["provider"], connection["model"], connection["api_url"],
            profile["system_prompt"], profile["max_tokens"], profile["max_rounds"],
            profile["max_retries"], profile["request_timeout_seconds"], profile["max_context_threshold"], profile["compaction_output_max_tokens"], profile["max_swarm_agents"], permissions.fingerprint(), self._core.tool_registry.revision,
            self._core.mcp_service.fingerprint(session_id, "coordinator"),
        )
        # A forced stop closes the cached coordinator's clients, so rebuild
        # even when the profile fingerprint is unchanged; otherwise the next
        # run would reuse a closed provider client.  Durable context preserves
        # conversation continuity across the rebuild.
        if session.coordinator_matches(fingerprint) and not session.runtime_agents_dirty:
            return
        workspace = self._core.workspaces.get(session_id)
        if session.artifacts is None:
            raise RuntimeError("Session artifact storage is not configured")
        coordinator = create_agent(
            [LLMBackendConfig(
                name=session.coordinator_name,
                provider=connection["provider"],
                model=connection["model"],
                api_key=api_key,
                api_url=connection["api_url"] or None,
                timeout=profile["request_timeout_seconds"],
                max_retries=profile["max_retries"],
            )],
            self._core.tool_registry.materialize(session, permissions, "coordinator", session.coordinator_name),
            system_prompt=profile["system_prompt"],
            max_concurrency=profile["max_swarm_agents"],
            max_context_threshold=profile["max_context_threshold"],
            compaction_output_max_tokens=profile["compaction_output_max_tokens"],
            keep_recent=profile["compaction_keep_recent"],
            context_handler_name=profile["context_handler"],
            context_path=workspace.state_path / "agents" / session.coordinator_name / "context.json",
            default_max_rounds=profile["max_rounds"],
            default_max_tokens=profile["max_tokens"],
            enable_stop_turn=permissions.allows("turn_control", "stop_turn"),
            tool_result_transformer=session.artifacts.transform_tool_result,
            image_resolver=session.attachments.resolve if session.attachments else None,
        )
        session.set_coordinator(coordinator, fingerprint)
        session.runtime_agents_dirty = False
        # Unit-test and alternate-host factories may supply a sentinel role;
        # only a concrete llmfetcher Agent is valid for graph registration.
        if isinstance(coordinator, Agent):
            self.rebuild_swarm(session_id)

    def compact(
        self,
        session_id: str,
        agent_name: str = "coordinator",
        *,
        observer: Callable[[str, str, dict], None] | None = None,
    ) -> tuple[ExecutionController, Agent]:
        """Start one explicit compaction using the session's live Agent.

        The returned controller is published on the Session while the caller
        performs the operation, allowing the HTTP stop endpoint to cancel the
        provider request without constructing a second connector.

        Args:
            session_id: Session whose Agent compacts its own context.
            agent_name: Graph name of the Agent to compact.
            observer: Optional synchronous observer for this compaction's
                lifecycle events (started / delta / success / failed). It is
                chained behind the handler's existing observer rather than
                replacing it, so borrowing the hook never silences the durable
                event path.
        """
        session = self._core.sessions.get(session_id)
        if session.execution is not None:
            state = session.execution.snapshot().state
            if state in {ExecutionState.RUNNING, ExecutionState.STOPPING, ExecutionState.FORCE_STOPPING}:
                raise RuntimeError("Cannot compact while a run is active in this session")
        self.ensure_coordinator(session_id)
        agent = next(
            (candidate for candidate in session.agents
             if getattr(candidate, "_agent_name_in_graph", "") == agent_name),
            session.coordinator if agent_name == session.coordinator_name else None,
        )
        if agent is None:
            raise RuntimeError(f"Session agent is not configured: {agent_name}")
        control = ExecutionController()
        with session.compaction_lock:
            if session.compaction_control is not None:
                raise RuntimeError("Compaction is already running")
            session.compaction_control = control
        try:
            context_path = getattr(agent, "context_path", None)
            if context_path is not None and Path(context_path).exists():
                if not agent.context_handler.load(context_path):
                    raise RuntimeError("Could not load context checkpoint")
            profile = self._core.run_profiles.effective(session_id)
            linear = getattr(agent.context_handler, "linear", agent.context_handler)
            if hasattr(linear, "compress_threshold"):
                linear.compress_threshold = profile["max_context_threshold"]
            install = getattr(linear, "set_compaction_event_hook", None)
            previous_hook = getattr(linear, "event_hook", None)
            borrowing = observer is not None and callable(install)
            if borrowing:
                def relay(event_type: str, message: str, data: dict) -> None:
                    if callable(previous_hook):
                        previous_hook(event_type, message, data)
                    observer(event_type, message, data)

                install(relay)
            try:
                agent.compact_context(control=control)
            finally:
                # An un-restored borrowed hook would keep routing this
                # compaction's events to a caller that has already returned.
                if borrowing:
                    install(previous_hook)
            return control, agent
        finally:
            with session.compaction_lock:
                session.compaction_control = None

    def stop_compaction(self, session_id: str, *, force: bool = False, reason: str = "user_requested") -> bool:
        session = self._core.sessions.get(session_id)
        with session.compaction_lock:
            control = session.compaction_control
        if control is None:
            return False
        control.request_stop(StopMode.FORCE if force else StopMode.GRACEFUL, reason=reason)
        return True

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
            agent = self.create_runtime_worker(session_id, name, worker.system_prompt)
            swarm.add_agent(name, agent); workers.append(agent)
        for connection in blueprint.connections:
            swarm.add_connection(connection.source, connection.target)
        for agent, mode in blueprint.mappers.items(): swarm.dynamic_set_mapper(agent, mode)
        for agent, targets in blueprint.routers.items(): swarm.dynamic_set_router(agent, targets)
        session.agents = [session.coordinator, *workers]
        session.swarm = swarm

    def create_runtime_worker(self, session_id: str, name: str, system_prompt: str) -> Agent:
        """Build one worker using the effective Session profile and ToolRegistry.

        This helper is the sole worker factory for both restored blueprint
        nodes and Agent-authorized dynamic swarm additions. It reads connector
        secrets only at construction time and never persists them.

        Args:
            session_id: Owning Session identity.
            name: Valid graph-safe worker identity.
            system_prompt: Worker-specific instructions; blank inherits the
                Session profile prompt.

        Returns:
            Fresh persistent worker Agent with the current authorized tools.

        Raises:
            KeyError: If the Session or configured connector is missing.
            RuntimeError: If the profile has no saved connector identity.
        """
        session = self._core.sessions.get(session_id)
        profile = self._core.run_profiles.effective(session_id)
        connector_id = profile.get("connector_id")
        if not isinstance(connector_id, str) or not connector_id:
            raise RuntimeError("Session worker requires a saved connector")
        api_key = self._core.connectors.api_key(connector_id)
        connection = self._core.connectors.connection_config(connector_id)
        permissions = ToolPolicy.from_profile(profile.get("tool_permissions"))
        workspace = self._core.workspaces.get(session_id)
        if session.artifacts is None:
            raise RuntimeError("Session artifact storage is not configured")
        return create_agent(
            [LLMBackendConfig(
                name=name, provider=connection["provider"], model=connection["model"], api_key=api_key,
                api_url=connection["api_url"] or None, timeout=profile["request_timeout_seconds"], max_retries=profile["max_retries"],
            )],
            self._core.tool_registry.materialize(session, permissions, "worker", name),
            system_prompt=system_prompt or profile["system_prompt"],
            max_concurrency=profile["max_swarm_agents"],
            max_context_threshold=profile["max_context_threshold"],
            compaction_output_max_tokens=profile["compaction_output_max_tokens"],
            keep_recent=profile["compaction_keep_recent"],
            context_handler_name=profile["context_handler"],
            context_path=workspace.state_path / "agents" / name / "context.json",
            default_max_rounds=profile["max_rounds"],
            default_max_tokens=profile["max_tokens"],
            enable_stop_turn=permissions.allows("turn_control", "stop_turn"),
            tool_result_transformer=session.artifacts.transform_tool_result,
            image_resolver=session.attachments.resolve if session.attachments else None,
        )

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
            connection = self._core.connectors.connection_config(connector_id)
        except KeyError as exc:
            raise RuntimeError("Session preview connector has no saved API key") from exc
        workspace = self._core.workspaces.get(session_id)
        if session.artifacts is None:
            raise RuntimeError("Session artifact storage is not configured")
        worker = blueprint.workers.get(name)
        role = "coordinator" if name == session.coordinator_name else "worker"
        system_prompt = profile["system_prompt"] if worker is None else worker.system_prompt or profile["system_prompt"]
        return create_agent(
            [LLMBackendConfig(
                name=name,
                provider=connection["provider"],
                model=connection["model"],
                api_key=api_key,
                api_url=connection["api_url"] or None,
                timeout=profile["request_timeout_seconds"],
                max_retries=profile["max_retries"],
            )],
            self._core.tool_registry.materialize(session, permissions, role, name),
            system_prompt=system_prompt,
            max_concurrency=profile["max_swarm_agents"],
            max_context_threshold=profile["max_context_threshold"],
            compaction_output_max_tokens=profile["compaction_output_max_tokens"],
            keep_recent=profile["compaction_keep_recent"],
            context_handler_name=profile["context_handler"],
            context_path=workspace.state_path / "agents" / name / "context.json",
            default_max_rounds=profile["max_rounds"],
            default_max_tokens=profile["max_tokens"],
            enable_stop_turn=permissions.allows("turn_control", "stop_turn"),
            tool_result_transformer=session.artifacts.transform_tool_result,
            image_resolver=session.attachments.resolve if session.attachments else None,
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
        self._core.mcp_service.invalidate(session_id)
        if state_path.exists():
            shutil.rmtree(state_path)
        self._core.conversations.remove(session_id)
        self._core.workspaces.remove_legacy_session(self._core.legacy_workspace_index, session_id)
        self._core.workspaces.remove(session_id)
        self._core.sessions.remove(session_id)
        return workspace
