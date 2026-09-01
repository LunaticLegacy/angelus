"""Composition root for the new Angelus execution backend."""

from __future__ import annotations

from pathlib import Path
import sys
import threading

from .modules.session_module import SessionHandler
from .modules.execution_module import SigintSupervisor
from .modules.workspace_module import WorkspaceCatalog
from .modules.conversation_module import ConversationStore
from .modules.application_module import ExecutionService, SessionService, SettingsService
from .modules.console_module import ConsoleProjectionService
from .modules.console_module.tool_provider import console_tool_registration
from .modules.connector_module import ConnectorStore, ProviderCatalog
from .modules.settings_module import RunProfileStore
from .modules.tool_module import ToolRegistry, runtime_tool_registration
from .modules.plugin_module import PluginManager


class AngelusCore:
    """Compose the one process-local Angelus application.

    It provides object ownership, never request handling: API/CLI adapters
    use its services, while a :class:`Session` remains the owner of its own
    AgentSwarm and execution boundary.  Stores are process-wide authorities
    for durable configuration and history, not caches duplicated by routes.

    Args:
        sessions: Optional session registry, useful for tests or alternate
            hosts that supply their own session lifecycle implementation.
    """

    def __init__(
        self,
        *,
        state_root: Path | None = None,
        sessions: SessionHandler | None = None,
    ) -> None:
        """Create one isolated application backend composition root.

        Args:
            state_root: Directory for all new Angelus-owned durable state.
                ``None`` selects ``.angelus-state`` in the current directory.
            sessions: Optional prebuilt aggregate registry, mainly for tests
                and alternate hosts.  Existing sessions are rehydrated into it.
        """
        # Root of new state only; never a user project directory.
        self.state_root = (state_root or (Path.cwd() / ".angelus-state")).resolve()
        # Process-local registry.  Each value is a complete Session aggregate.
        self.sessions = sessions or SessionHandler()
        # Durable list of selectable Sessions and their user project bindings.
        self.workspaces = WorkspaceCatalog(self.state_root / "workspaces.json")
        # Read/delete bridge for pre-refactor session archives; it is not a
        # write target for new state.
        self.legacy_workspace_index = Path.cwd() / "workspace" / "sessions.json"
        default_state_root = (Path.cwd() / ".angelus-state").resolve()
        if self.state_root == default_state_root:
            self.workspaces.import_legacy_sessions(
                self.legacy_workspace_index,
                self.state_root / "sessions",
            )
        # Runtime discovery only; this catalog neither stores secrets nor
        # configures an Agent.
        self.providers = ProviderCatalog()
        # Global connector metadata and their separate secret documents.
        self.connectors = ConnectorStore(self.state_root)
        # Global defaults plus Session-local future-run profile overrides.
        self.run_profiles = RunProfileStore(self.state_root)
        # Sole process-wide directory of capability definitions and runtime
        # materializers. Domain modules register providers once at startup.
        self.tool_registry = ToolRegistry()
        self.tool_registry.register(console_tool_registration(self))
        self.tool_registry.register(runtime_tool_registration(self))
        # Plugins can only extend the application through this same ToolRegistry.
        bundled_plugins = Path(__file__).resolve().parent.parent / "plugins"
        self.plugin_manager = PluginManager(self.state_root, self.tool_registry, bundled_plugins)
        self.plugin_manager.restore_enabled()
        # Legacy transcript reader/remover during the conversation migration.
        self.conversations = ConversationStore(Path.cwd() / "workspace")
        for workspace in self.workspaces.list():
            if not self.sessions.exists(workspace.session_id):
                self.sessions.create(
                    workspace.session_id,
                    execution_root=workspace.state_path,
                )
        # Application use cases: adapters call these rather than mutating a
        # store or Session aggregate directly.
        self.session_service = SessionService(self)
        self.execution_service = ExecutionService(self)
        self.settings_service = SettingsService(self)
        self.console_service = ConsoleProjectionService(self)
        # SIGINT coordinator obtains live attempts from Session ownership.
        self.sigint = SigintSupervisor(self.sessions.live_attempts)
        # Event used to stop the helper thread that drains signal requests.
        self._signal_loop_stop = threading.Event()
        # Daemon helper; created only after handlers are installed.
        self._signal_loop: threading.Thread | None = None
        # Serializes first Ctrl+C receipt with orderly host shutdown.
        self._shutdown_lock = threading.RLock()
        # Immutable snapshot of attempts selected by the first Ctrl+C.
        self._sigint_attempts: tuple = ()
        # Makes repeated Ctrl+C idempotent instead of reissuing cancellation.
        self._sigint_received = False
        # Ensures the terminal completion line appears exactly once.
        self._shutdown_reported = False

    def install_signal_handlers(self) -> None:
        """Install SIGINT receipt and start a non-blocking drain helper.

        This must be invoked by the host main thread because Python signal
        registration is main-thread-only.  The helper only drains queued work;
        it never replaces Uvicorn's own lifecycle handling.
        """
        self.sigint.install()
        if self._signal_loop is None or not self._signal_loop.is_alive():
            self._signal_loop_stop.clear()
            self._signal_loop = threading.Thread(
                target=self._drain_signal_loop,
                name="angelus-signal-drain",
                daemon=True,
            )
            self._signal_loop.start()

    def drain_signals(self) -> bool:
        """Force-stop pending attempts outside the Python signal handler.

        Returns:
            ``True`` when a queued signal request was consumed.
        """
        return self.sigint.drain()

    def receive_sigint(self) -> None:
        """Announce Ctrl+C and immediately force-stop every current attempt.

        The ASGI host calls this from its own SIGINT handler before it begins
        shutdown.  It intentionally does not wait there: Uvicorn must first
        transition into its shutdown lifecycle, whose ``shutdown`` hook calls
        :meth:`shutdown` to await completion and persist any interruption.
        """
        with self._shutdown_lock:
            if self._sigint_received:
                return
            self._sigint_received = True
            print(
                "\nAngelus: received Ctrl+C; force-stopping active executions and persisting state...",
                file=sys.stderr,
                flush=True,
            )
            self._sigint_attempts = self.sigint.request_force_stop_all(reason="sigint")

    def shutdown(self) -> None:
        """Durably stop live attempts before releasing host resources.

        This method is deliberately synchronous.  ASGI hosts call it from
        their shutdown lifecycle after receiving Ctrl+C, so every attempt gets
        one bounded force-stop and checkpoint/journal opportunity before the
        server process is allowed to leave.
        """
        with self._shutdown_lock:
            if self._sigint_received:
                attempts = self._sigint_attempts
                reason = "sigint"
            else:
                attempts = self.sigint.request_force_stop_all(reason="host_shutdown")
                reason = "host_shutdown"
        self.sigint.wait_for_stop_all(attempts, reason=reason)
        with self._shutdown_lock:
            if self._sigint_received and not self._shutdown_reported:
                print(
                    "Angelus: execution shutdown state persisted; exiting.",
                    file=sys.stderr,
                    flush=True,
                )
                self._shutdown_reported = True
        self._signal_loop_stop.set()
        if self._signal_loop is not None:
            self._signal_loop.join(timeout=1)
        self.sigint.restore()

    def _drain_signal_loop(self) -> None:
        """Poll the signal supervisor until shutdown requests this daemon exit.

        The short wait bounds CTRL+C-to-force-stop latency while avoiding a
        busy loop.  Actual checkpoint and journal writes remain in the
        supervisor, outside the interpreter's signal callback.
        """
        while not self._signal_loop_stop.wait(0.05):
            self.drain_signals()
