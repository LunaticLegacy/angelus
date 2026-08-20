"""Plugin runtime core: the ``AngelusPlugin`` base class and ``PluginRuntime``.

The runtime handed to :meth:`AngelusPlugin.setup` is the *only* way a plugin
may contribute extensions to the host.  All ``register_*`` calls are confined
to the ``setup()`` phase (contract ``docs/plugin-api.md`` §4): the runtime
collects registrations while setup runs and the :class:`PluginManager`
publishes them into its live tables only after setup returns successfully
("先登记后生效" — register first, then take effect).  A setup failure
discards every collected registration and marks the plugin ``blocked``
without crashing the host process.
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable

__all__ = [
    "HOOK_EVENTS",
    "HTTP_METHODS",
    "AngelusPlugin",
    "PluginError",
    "PluginRuntime",
]

#: Whitelist of agent events plugins may subscribe to (docs/plugin-api.md §5).
#: Events use dot naming; the bridge layer maps them to the internal
#: colon-namespaced execution events.  Registering any other event is rejected.
HOOK_EVENTS = frozenset(
    {
        "agent.started",
        "agent.stopped",
        "tool.before",
        "tool.after",
        "session.created",
    }
)

#: HTTP verbs accepted by :meth:`PluginRuntime.register_route`.
HTTP_METHODS = frozenset(
    {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}
)


class PluginError(Exception):
    """Raised for plugin lifecycle errors (missing plugin, bad entry, ...).

    Deliberately distinct from plugin *runtime* failures: a plugin whose
    ``setup()`` raises is never surfaced through this exception — the manager
    isolates it and flips the plugin to ``blocked`` instead.
    """


class PluginRuntime:
    """Setup-time registration surface handed to ``AngelusPlugin.setup()``.

    Attributes:
        name: Plugin name (equals ``manifest.name`` and the import namespace
            ``angelus_plugins.<name>``).
        state_dir: Plugin-private writable directory (``<plugin_dir>/data``),
            created before ``setup()`` runs.
        settings: Read-only view of the plugin configuration persisted in the
            registry (empty when the plugin has none).
        logger: Logger named ``angelus.plugins.<name>``.
    """

    def __init__(
        self,
        *,
        name: str,
        state_dir: Path | str,
        settings: dict[str, Any] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.name = name
        self.state_dir = Path(state_dir)
        self.settings: MappingProxyType[str, Any] = MappingProxyType(
            dict(settings or {})
        )
        self.logger = logger or logging.getLogger(f"angelus.plugins.{name}")

        # Registration phase machine (manager-controlled):
        #   idle -> setup -> active | blocked -> torn_down
        self._phase = "idle"
        self._tools: list[dict[str, Any]] = []
        self._routes: list[dict[str, Any]] = []
        self._hooks: list[dict[str, Any]] = []
        self._connectors: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # phase control (manager-only; underscore API)
    # ------------------------------------------------------------------
    def _begin_setup(self) -> None:
        """Enter the setup phase: the only phase where register_* works."""
        self._phase = "setup"

    def _commit(self) -> dict[str, list[dict[str, Any]]]:
        """Finalize a successful setup and return the collected registrations.

        The manager publishes the returned snapshot into its live tables
        ("先登记后生效").  After this call the runtime is ``active`` and all
        ``register_*`` calls are rejected.
        """
        if self._phase != "setup":
            raise RuntimeError("runtime is not in the setup phase")
        self._phase = "active"
        return {
            "tools": list(self._tools),
            "routes": list(self._routes),
            "hooks": list(self._hooks),
            "connectors": list(self._connectors),
        }

    def _abort(self) -> None:
        """Discard every collected registration after a failed setup."""
        self._phase = "blocked"
        self._tools = []
        self._routes = []
        self._hooks = []
        self._connectors = []

    def _shutdown(self) -> None:
        """Mark the runtime torn down (idempotent teardown bookkeeping)."""
        self._phase = "torn_down"
        self._tools = []
        self._routes = []
        self._hooks = []
        self._connectors = []

    def _ensure_setup(self) -> None:
        if self._phase != "setup":
            raise RuntimeError(
                f"register_* may only be called during plugin setup "
                f"(current phase: {self._phase!r})"
            )

    # ------------------------------------------------------------------
    # registration API — setup phase only
    # ------------------------------------------------------------------
    def register_tool(self, name: str, schema: dict, handler: Callable) -> None:
        """Register a plugin tool.

        Args:
            name: Tool name (without the ``plugin.<plugin>.`` prefix; the
                manager namespaces it automatically).
            schema: JSON-Schema style parameter declaration mapped to
                ToolParameter by the tools bridge.
            handler: Callable implementing the tool.
        """
        self._ensure_setup()
        if not isinstance(name, str) or not name:
            raise ValueError("tool name must be a non-empty string")
        if not callable(handler):
            raise TypeError("tool handler must be callable")
        if not isinstance(schema, dict):
            raise TypeError("tool schema must be a dict")
        if any(tool["name"] == name for tool in self._tools):
            raise ValueError(
                f"tool {name!r} already registered by plugin {self.name!r}"
            )
        self._tools.append(
            {"name": name, "schema": dict(schema), "handler": handler}
        )

    def register_route(self, method: str, path: str, handler: Callable) -> None:
        """Register a plugin route, mounted under ``/plugins/<name>/api``.

        Args:
            method: HTTP verb (case-insensitive).
            path: Path fragment starting with ``/``, appended to the plugin
                prefix by the routes bridge.
            handler: Callable (FastAPI-compatible endpoint).
        """
        self._ensure_setup()
        verb = str(method).upper()
        if verb not in HTTP_METHODS:
            raise ValueError(f"unsupported HTTP method {method!r}")
        if not isinstance(path, str) or not path.startswith("/"):
            raise ValueError("route path must start with '/'")
        if not callable(handler):
            raise TypeError("route handler must be callable")
        self._routes.append({"method": verb, "path": path, "handler": handler})

    def register_hook(
        self, event: str, handler: Callable, *, priority: int = 0
    ) -> None:
        """Subscribe to an agent event from the whitelist.

        Args:
            event: One of :data:`HOOK_EVENTS`; anything else is rejected with
                ``ValueError`` (contract §5).
            handler: ``Callable[[ExecutionEvent], None]``.
            priority: Higher values run first.
        """
        self._ensure_setup()
        if event not in HOOK_EVENTS:
            raise ValueError(
                f"unknown hook event {event!r}; "
                f"allowed: {', '.join(sorted(HOOK_EVENTS))}"
            )
        if not callable(handler):
            raise TypeError("hook handler must be callable")
        self._hooks.append(
            {"event": event, "handler": handler, "priority": int(priority)}
        )

    def register_connector(self, kind: str, factory: Callable) -> None:
        """Register a connector provider factory (read-only path).

        Args:
            kind: Provider kind (e.g. ``"search"``).
            factory: Callable returning a connector/provider instance.  The
                plugin never touches stored credentials directly.
        """
        self._ensure_setup()
        if not isinstance(kind, str) or not kind:
            raise ValueError("connector kind must be a non-empty string")
        if not callable(factory):
            raise TypeError("connector factory must be callable")
        if any(conn["kind"] == kind for conn in self._connectors):
            raise ValueError(
                f"connector {kind!r} already registered by plugin {self.name!r}"
            )
        self._connectors.append({"kind": kind, "factory": factory})

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<PluginRuntime name={self.name!r} phase={self._phase!r} "
            f"state_dir={str(self.state_dir)!r}>"
        )


class AngelusPlugin:
    """Base class plugins subclass to become loadable by ``PluginManager``.

    Subclasses set ``name``/``version`` and override :meth:`setup` (and
    optionally :meth:`teardown`).  ``setup()`` receives the
    :class:`PluginRuntime`; all ``register_*`` calls must happen there.
    """

    name: str = ""
    version: str = ""

    def setup(self, runtime: PluginRuntime) -> None:
        """Called once when the plugin is loaded (inside the setup phase).

        Register tools/routes/hooks/connectors here via ``runtime``.
        """

    def teardown(self) -> None:
        """Release resources.  Must be idempotent (may be called multiple
        times); the manager guards against exceptions either way.
        """
