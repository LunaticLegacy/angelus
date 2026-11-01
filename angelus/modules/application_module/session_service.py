"""Host-neutral session and workspace registration use cases."""

from __future__ import annotations

from pathlib import Path
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from uuid import uuid4
import hashlib
from contextlib import contextmanager
from typing import TYPE_CHECKING, Callable, Iterator

from ..workspace_module import Workspace
from ..execution_module import ExecutionState
from ..session_module import create_agent, validate_session_id
from ..tool_module import ToolPolicy
from ..context_module import ContextProviderRequest
from llmfetcher import Agent, LLMBackendConfig
from llmfetcher.context_handlers import ContextProvider, DEFAULT_CONTEXT_HANDLER, context_handler_revision

if TYPE_CHECKING:
    from llmfetcher.context_handlers import ContextHandlerLinear

    from ...core import AngelusCore
    from ..session_module.session_handler import Session


@contextmanager
def _tap_compaction_stream(
    linear: "ContextHandlerLinear",
    on_delta: Callable[[str], None],
) -> Iterator[None]:
    """Forward the compaction model output to ``on_delta`` while it streams.

    The linear context handler consumes ``fetch_stream`` itself and, since
    Issue 7, publishes only lifecycle events - never per-chunk ones - so a host
    that wants to show the summary while it is being written has to observe that
    one generator.  The tap wraps the Agent's own fetcher instance for the
    duration of a single explicit compaction and is removed in ``finally``; it
    never reaches the durable event ledger, whose trace stays four events long.
    """
    # Both members are declared by the handler and its compaction protocol, so
    # they are read directly: this module allows no dynamic-access escape hatch.
    fetcher = linear.llm_handler
    original = fetcher.fetch_stream

    def tee(*args: object, **kwargs: object) -> Iterator[str]:
        """Yield every model chunk unchanged, reporting it to ``on_delta``."""
        for chunk in original(*args, **kwargs):
            if isinstance(chunk, str) and chunk:
                try:
                    on_delta(chunk)
                except Exception:
                    # A broken UI stream must never corrupt the compaction.
                    pass
            yield chunk

    # Writing the member the tap just read: this shadows one bound method on
    # the Agent's own fetcher instead of building a second handler, and the
    # class method is back as soon as the shadow is removed below.
    setattr(fetcher, "fetch_stream", tee)
    try:
        yield
    finally:
        if fetcher.fetch_stream is tee:
            del fetcher.fetch_stream


@dataclass
class SessionDeleteOperation:
    operation_id: str
    session_id: str
    state: str = "queued"
    error: str | None = None


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
        self._delete_lock = threading.RLock()
        self._delete_ops: dict[str, SessionDeleteOperation] = {}
        self._delete_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="angelus-session-delete")

    def delete_async(self, session_id: str, confirmation: str) -> "SessionDeleteOperation":
        if confirmation != session_id:
            raise ValueError("confirmation must equal the session ID")
        if not self._core.sessions.exists(session_id):
            raise KeyError(session_id)
        operation = SessionDeleteOperation(uuid4().hex, session_id)
        with self._delete_lock:
            self._delete_ops[operation.operation_id] = operation
        self._delete_pool.submit(self._run_delete, operation.operation_id, confirmation)
        return operation

    def delete_operation(self, operation_id: str) -> "SessionDeleteOperation":
        with self._delete_lock:
            operation = self._delete_ops.get(operation_id)
            if operation is None:
                raise KeyError(operation_id)
            return replace(operation)

    def is_deleting(self, session_id: str) -> bool:
        with self._delete_lock:
            return any(
                operation.session_id == session_id
                and operation.state not in {"completed", "failed"}
                for operation in self._delete_ops.values()
            )

    def _run_delete(self, operation_id: str, confirmation: str) -> None:
        with self._delete_lock:
            operation = self._delete_ops[operation_id]
            operation.state = "stopping_execution"
        try:
            with self._delete_lock:
                operation.state = "cleaning"
            self.delete(operation.session_id, confirmation=confirmation)
        except Exception as exc:
            with self._delete_lock:
                operation.state = "failed"
                operation.error = f"{type(exc).__name__}: {exc}"
        else:
            with self._delete_lock:
                operation.state = "completed"

    def _context_providers(
        self,
        session_id: str,
        session: "Session",
        workspace: Workspace,
        policy: ToolPolicy,
        role: str,
        agent_name: str,
    ) -> tuple[ContextProvider, ...]:
        """Materialize every module and plugin source for one Agent.

        Args:
            session_id: Owning Session identity used by plugin providers.
            session: Live Session aggregate the sources project.
            workspace: Bound project and Angelus state directories.
            policy: Effective grants for the Agent being built.
            role: Agent role receiving the sources.
            agent_name: Concrete Agent identity owning per-agent state.

        Returns:
            Module sources in registration order, followed by plugin sources.
        """
        return (
            *self._core.context_registry.materialize(
                ContextProviderRequest(session, workspace, policy, role, agent_name)
            ),
            *self._core.plugin_manager.materialize_context_providers(
                session_id, role, agent_name,
            ),
        )

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
            created_at=time.time(),
            updated_at=time.time(),
            last_activity_at=time.time(),
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

    def touch_activity(self, session_id: str) -> None:
        workspace = self._core.workspaces.get(session_id)
        now = time.time()
        self._core.workspaces.replace(replace(workspace, updated_at=now, last_activity_at=now))

    def ensure_coordinator(self, session_id: str, *, connector_id: str | None = None) -> None:
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
        session.active_tool_policy = permissions
        connector_id = self._resolve_connector_id(session_id, connector_id, profile)
        try:
            api_key = self._core.connectors.api_key(connector_id)
        except KeyError as exc:
            raise RuntimeError("Session coordinator connector has no saved API key") from exc
        # The connector catalog is authoritative for endpoint metadata. Older
        # frontend builds persisted only connector_id/provider/model, leaving
        # api_url empty and silently routing a DeepSeek (or other custom)
        # connector to the OpenAI default endpoint. Resolve the URL here as a
        # compatibility fallback so every execution uses the selected
        # connector's endpoint even when its profile predates this fix.
        connector = self._core.connectors.config(connector_id)
        provider, model, api_url = connector.provider, connector.model, connector.api_url
        max_rounds, max_tokens, max_context_threshold = self._agent_budget(
            profile, session.coordinator_name,
        )
        fingerprint = (
            connector_id, hashlib.sha256(api_key.encode("utf-8")).hexdigest(),
            provider, model, api_url,
            profile["system_prompt"], profile["temperature"], profile["thinking_mode"], profile["reasoning_effort"], max_tokens, max_rounds,
            profile["max_retries"], profile["request_timeout_seconds"], max_context_threshold, profile["compaction_output_max_tokens"], profile.get("context_keep_recent", 0), profile.get("tool_result_context_limit", 0), profile["max_swarm_agents"], profile.get("agent_overrides", {}), profile.get("context_handler", DEFAULT_CONTEXT_HANDLER), profile.get("context_handler_settings", {}), profile.get("context_block_order", {}), context_handler_revision(), permissions.fingerprint(), self._core.tool_registry.revision,
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
                provider=provider,
                model=model,
                api_key=api_key,
                api_url=api_url or None,
                timeout=profile["request_timeout_seconds"],
                max_retries=profile["max_retries"],
            )],
            self._core.tool_registry.materialize(session, permissions, "coordinator", session.coordinator_name),
            system_prompt=profile["system_prompt"],
            max_concurrency=profile["max_swarm_agents"],
            max_context_threshold=max_context_threshold,
            compaction_output_max_tokens=profile["compaction_output_max_tokens"],
            context_keep_recent=profile.get("context_keep_recent", 0),
            tool_result_context_limit=profile.get("tool_result_context_limit", 0),
            context_handler_name=profile.get("context_handler", DEFAULT_CONTEXT_HANDLER),
            context_handler_settings=profile.get("context_handler_settings", {}),
            context_block_order=profile.get("context_block_order", {}),
            context_path=workspace.state_path / "agents" / session.coordinator_name / "context.json",
            context_providers=self._context_providers(
                session_id, session, workspace, permissions, "coordinator",
                session.coordinator_name,
            ),
            default_max_rounds=max_rounds,
            default_max_tokens=max_tokens,
            default_temperature=profile["temperature"],
            thinking_mode=profile["thinking_mode"],
            reasoning_effort=profile["reasoning_effort"],
            enable_stop_turn=permissions.allows("turn_control", "stop_turn"),
            tool_result_transformer=session.artifacts.transform_tool_result,
            image_resolver=session.attachments.resolve if session.attachments else None,
        )
        session.set_coordinator(coordinator, fingerprint)
        session.runtime_agents_dirty = False
        # Unit-test and alternate-host factories may supply a sentinel role;
        # only a concrete llmfetcher Agent is valid for graph registration.
        if isinstance(coordinator, Agent):
            self._core.swarm_graph.materialize(session_id)

    def compact(
        self,
        session_id: str,
        agent_name: str = "coordinator",
        *,
        on_event: Callable[[str, str, dict], None] | None = None,
        on_delta: Callable[[str], None] | None = None,
    ) -> Agent:
        """Compact one existing Session Agent through its configured fetcher."""
        session: Session = self._core.sessions.get(session_id)
        execution = session.execution
        if execution is not None:
            state = execution.snapshot().state
            if str(state) in {"running", "stopping", "force_stopping"}:
                raise RuntimeError("Cannot compact while a run is active in this session")
        self.ensure_coordinator(session_id)
        agent = next(
            (
                item
                for item in session.agents
                if isinstance(item, Agent) and item._agent_name_in_graph == agent_name
            ),
            None,
        )
        if agent is None and agent_name == session.coordinator_name:
            agent = session.coordinator
        if not isinstance(agent, Agent):
            raise RuntimeError(f"Session agent is not configured: {agent_name}")
        linear = agent.context_handler.linear
        # A host restart rebuilds this Agent without running it, so the durable
        # transcript still lives only in the saved checkpoint: ``Agent.run``
        # rehydrates it on entry.  An explicit user compaction must resolve the
        # same saved context, otherwise a session with a visible history reports
        # "no active messages" and the UI shows a failure card.
        if not linear.messages and agent.context_path is not None:
            context_file = Path(agent.context_path)
            if context_file.exists() and agent.context_handler.load(context_file):
                # ``run`` re-applies the configured budget after loading; a
                # manual compaction must not act on the checkpoint's own value
                # when the run profile asked for a different one.
                linear = agent.context_handler.linear
                linear.compress_threshold = agent.max_context_threshold
        original_hook = linear.event_hook
        if on_event is not None:
            def forward(event_type: str, message: str, data: dict) -> None:
                if callable(original_hook):
                    original_hook(event_type, message, data)
                on_event(event_type, message, data)
            linear.set_compaction_event_hook(forward)
        try:
            if on_delta is None:
                compacted = agent.compact_context()
            else:
                # Only an explicit user compaction wants the summary token
                # by token; automatic compaction keeps the quiet trace.
                with _tap_compaction_stream(linear, on_delta):
                    compacted = agent.compact_context()
        finally:
            if on_event is not None:
                linear.set_compaction_event_hook(original_hook)
        if not compacted:
            if not linear.messages:
                # The handler emitted ``context:compact_skipped``: this Agent
                # holds no active transcript to summarise.  That is a no-op,
                # not a failure, so the API can answer with the retained
                # summary instead of a failure card.
                return agent
            raise RuntimeError(linear.last_compaction_error or "Context compaction failed")
        return agent

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
        permissions = session.active_tool_policy or ToolPolicy.from_profile(profile.get("tool_permissions"))
        connector_id = self._resolve_connector_id(session_id, None, profile)
        api_key = self._core.connectors.api_key(connector_id)
        connector = self._core.connectors.config(connector_id)
        workspace = self._core.workspaces.get(session_id)
        swarm = AgentSwarm(max_concurrency_agents=profile["max_swarm_agents"])
        swarm.add_agent(session.coordinator_name, session.coordinator)
        blueprint = session.console.blueprint()
        workers = []
        for name, worker in blueprint.workers.items():
            agent = self.create_runtime_worker(session_id, name, worker.system_prompt, connector_id=connector_id)
            swarm.add_agent(name, agent); workers.append(agent)
        for connection in blueprint.connections:
            swarm.add_connection(connection.source, connection.target)
        for agent, mode in blueprint.mappers.items(): swarm.dynamic_set_mapper(agent, mode)
        for agent, targets in blueprint.routers.items(): swarm.dynamic_set_router(agent, targets)
        session.agents = [session.coordinator, *workers]
        session.swarm = swarm

    def create_runtime_worker(self, session_id: str, name: str, system_prompt: str, *, connector_id: str | None = None) -> Agent:
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
        connector_id = self._resolve_connector_id(session_id, connector_id, profile)
        api_key = self._core.connectors.api_key(connector_id)
        connector = self._core.connectors.config(connector_id)
        permissions = session.active_tool_policy or ToolPolicy.from_profile(profile.get("tool_permissions"))
        max_rounds, max_tokens, max_context_threshold = self._agent_budget(profile, name)
        workspace = self._core.workspaces.get(session_id)
        if session.artifacts is None:
            raise RuntimeError("Session artifact storage is not configured")
        return create_agent(
            [LLMBackendConfig(
                name=name, provider=connector.provider, model=connector.model, api_key=api_key,
                api_url=connector.api_url or None, timeout=profile["request_timeout_seconds"], max_retries=profile["max_retries"],
            )],
            self._core.tool_registry.materialize(session, permissions, "worker", name),
            system_prompt=system_prompt or profile["system_prompt"],
            max_concurrency=profile["max_swarm_agents"],
            max_context_threshold=max_context_threshold,
            compaction_output_max_tokens=profile["compaction_output_max_tokens"],
            context_keep_recent=profile.get("context_keep_recent", 0),
            tool_result_context_limit=profile.get("tool_result_context_limit", 0),
            context_handler_name=profile.get("context_handler", DEFAULT_CONTEXT_HANDLER),
            context_handler_settings=profile.get("context_handler_settings", {}),
            context_block_order=profile.get("context_block_order", {}),
            context_path=workspace.state_path / "agents" / name / "context.json",
            context_providers=self._context_providers(
                session_id, session, workspace, permissions, "worker", name,
            ),
            default_max_rounds=max_rounds,
            default_max_tokens=max_tokens,
            default_temperature=profile["temperature"],
            thinking_mode=profile["thinking_mode"],
            reasoning_effort=profile["reasoning_effort"],
            enable_stop_turn=permissions.allows("turn_control", "stop_turn"),
            tool_result_transformer=session.artifacts.transform_tool_result,
            image_resolver=session.attachments.resolve if session.attachments else None,
        )

    def preview_agent(
        self,
        session_id: str,
        name: str,
        *,
        connector_id: str | None = None,
        context_handler_name: str | None = None,
    ) -> Agent:
        """Build one detached Agent for a no-I/O request preview.

        Args:
            session_id: Stable Session identity providing profile and tools.
            name: Coordinator or persisted Worker identity to preview.
            connector_id: Optional connector override; the saved
                Session connector is used when omitted.
            context_handler_name: Optional handler override so a
                caller can preview a strategy switch that is not
                saved yet.

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
        connector_id = self._resolve_connector_id(session_id, connector_id, profile)
        try:
            api_key = self._core.connectors.api_key(connector_id)
        except KeyError as exc:
            raise RuntimeError("Session preview connector has no saved API key") from exc
        connector = self._core.connectors.config(connector_id)
        workspace = self._core.workspaces.get(session_id)
        if session.artifacts is None:
            raise RuntimeError("Session artifact storage is not configured")
        worker = blueprint.workers.get(name)
        role = "coordinator" if name == session.coordinator_name else "worker"
        max_rounds, max_tokens, max_context_threshold = self._agent_budget(profile, name)
        system_prompt = profile["system_prompt"] if worker is None else worker.system_prompt or profile["system_prompt"]
        return create_agent(
            [LLMBackendConfig(
                name=name,
                provider=connector.provider,
                model=connector.model,
                api_key=api_key,
                api_url=connector.api_url or None,
                timeout=profile["request_timeout_seconds"],
                max_retries=profile["max_retries"],
            )],
            self._core.tool_registry.materialize(session, permissions, role, name),
            system_prompt=system_prompt,
            max_concurrency=profile["max_swarm_agents"],
            max_context_threshold=max_context_threshold,
            compaction_output_max_tokens=profile["compaction_output_max_tokens"],
            context_keep_recent=profile.get("context_keep_recent", 0),
            tool_result_context_limit=profile.get("tool_result_context_limit", 0),
            context_handler_name=context_handler_name
            or profile.get("context_handler", DEFAULT_CONTEXT_HANDLER),
            context_handler_settings=profile.get("context_handler_settings", {}),
            context_block_order=profile.get("context_block_order", {}),
            context_path=workspace.state_path / "agents" / name / "context.json",
            context_providers=self._context_providers(
                session_id, session, workspace, permissions, role, name,
            ),
            default_max_rounds=max_rounds,
            default_max_tokens=max_tokens,
            default_temperature=profile["temperature"],
            thinking_mode=profile["thinking_mode"],
            reasoning_effort=profile["reasoning_effort"],
            enable_stop_turn=permissions.allows("turn_control", "stop_turn"),
            tool_result_transformer=session.artifacts.transform_tool_result,
            image_resolver=session.attachments.resolve if session.attachments else None,
        )

    def _resolved_api_url(self, profile: dict[str, object], connector_id: str) -> str:
        """Resolve a profile endpoint, falling back to connector metadata."""
        value = profile.get("api_url")
        if isinstance(value, str) and value.strip():
            return value.strip()
        return self._core.connectors.api_url(connector_id)

    @staticmethod
    def _agent_budget(profile: dict[str, object], name: str) -> tuple[int, int, int]:
        """Resolve one Agent's optional execution overrides from the profile."""
        overrides = profile.get("agent_overrides", {})
        override = overrides.get(name, {}) if isinstance(overrides, dict) else {}
        if not isinstance(override, dict):
            override = {}
        return (
            int(override.get("max_rounds", profile["max_rounds"])),
            int(override.get("max_tokens", profile["max_tokens"])),
            int(override.get("max_context_threshold", profile["max_context_threshold"])),
        )

    def _resolve_connector_id(self, session_id: str, connector_id: str | None, profile: dict[str, object]) -> str:
        """Resolve a per-run connector, then optional Session default."""
        selected = connector_id or self._core.session_preferences.get(session_id).default_connector_id
        # Legacy profiles remain readable until the explicit migration runs.
        if not selected:
            legacy = profile.get("connector_id")
            selected = legacy if isinstance(legacy, str) else ""
        if not isinstance(selected, str) or not selected:
            raise RuntimeError("Session run requires a connector")
        if not self._core.connectors.exists(selected):
            raise RuntimeError("Selected connector does not exist")
        return selected

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
            if state in {ExecutionState.QUEUED, ExecutionState.PREPARING, ExecutionState.MATERIALIZING_TOOLS, ExecutionState.CONNECTING_MCP, ExecutionState.MATERIALIZING_SWARM, ExecutionState.LOADING_CONTEXT, ExecutionState.RUNNING, ExecutionState.STOPPING, ExecutionState.FORCE_STOPPING}:
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
