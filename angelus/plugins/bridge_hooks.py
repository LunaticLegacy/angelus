"""Plugin event-hook bridge — connect plugin ``register_hook`` to the agent bus.

S5 artifact: this module adapts the plugin hook registrations published by
:class:`~angelus.plugins.manager.PluginManager` (``HookRegistration`` records
with ``plugin``/``event``/``handler``/``priority`` fields) onto the agent
event bus exposed by ``llmfetcher`` (the ``ExecutionHook`` /
``ExecutionEvent`` model defined in ``llmfetcher/events.py``).  Hooks are
invoked **synchronously** with the ``ExecutionEvent``, exactly like the bus's
own hooks.

Event-name mapping (whitelist v1 = ``angelus.plugins.base.HOOK_EVENTS``)
-----------------------------------------------------------------------

Plugin hooks use dot-named events; the agent bus emits colon-namespaced
execution events.  The bridge maps them as follows (internal names verified
against the actual ``_emit`` call sites in ``llmfetcher/agent.py`` and
``llmfetcher/swarm_module/execution_graph.py``):

+-----------------+------------------------------------------------------+
| plugin event    | internal execution event(s)                          |
+=================+======================================================+
| ``agent.started`` | ``agent:start`` — an agent run begins              |
+-----------------+------------------------------------------------------+
| ``agent.stopped`` | ``agent:stopped`` — an agent run is stopped/       |
|                 | interrupted (agent and graph emitters both use      |
|                 | this event type)                                    |
+-----------------+------------------------------------------------------+
| ``tool.before``  | ``agent:tools_requested`` — a tool batch is about  |
|                 | to run; ``data["tool_calls"]`` carries the          |
|                 | requested ``call_id``/``name``/``args`` records     |
+-----------------+------------------------------------------------------+
| ``tool.after``   | ``agent:tools_completed`` — a tool batch finished;  |
|                 | ``data["tool_calls"]`` carries the per-call results |
+-----------------+------------------------------------------------------+
| ``session.created`` | no native emitter in the current bus; the host   |
|                 | announces it via ``PluginHookBridge.notify(         |
|                 | "session.created", ...)``                           |
+-----------------+------------------------------------------------------+

The bus emits no literal ``tool:before``/``tool:after``/``agent:started``/
``session:created`` events in the pinned submodule revision; the closest
semantic equivalents above are used instead.  Other internal events
(``agent:complete``, ``agent:completed``, ``agent:failed``,
``agent:submitted``, ``task:*``, ``dynamic:*``, ``graph:*``, ...) are not
exposed to plugins in v1.

Semantics
---------

* Hooks are invoked synchronously with the ``ExecutionEvent`` (the event must
  be treated as immutable by handlers).
* Registrations for one event run in **priority-descending order** (stable
  tie-break keeps registration order).
* A single failing hook is isolated: the exception is caught and logged on
  the ``angelus.plugins.hooks`` logger, and dispatch continues with the next
  hook — mirroring the failure-isolation semantics of ``ExecutionGraph._emit``
  and ``tests/test_swarm_failure_isolation.py``: a failed hook must never
  crash the agent/swarm main flow.
* Registering events outside the whitelist is rejected with ``ValueError`` —
  at registration time by ``PluginRuntime.register_hook`` (upstream S3) and
  here by :func:`validate_event_name` / :meth:`PluginHookBridge.notify`.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional, Protocol, Union

__all__ = [
    "PluginHookBridge",
    "attach_plugin_hooks",
    "validate_event_name",
]

#: Internal colon-namespaced execution event -> plugin dot event (v1).
#: Keys were verified against the actual ``_emit`` call sites; see the module
#: docstring for the full mapping rationale.
_COLON_TO_DOT: dict[str, str] = {
    "agent:start": "agent.started",
    "agent:stopped": "agent.stopped",
    "agent:tools_requested": "tool.before",
    "agent:tools_completed": "tool.after",
}

#: Plugin dot event -> internal colon event(s) that trigger it (v1).  An
#: empty tuple means the bus has no native emitter (host uses notify()).
DOT_TO_COLON: dict[str, tuple[str, ...]] = {
    "agent.started": ("agent:start",),
    "agent.stopped": ("agent:stopped",),
    "tool.before": ("agent:tools_requested",),
    "tool.after": ("agent:tools_completed",),
    "session.created": (),
}


class HookRegistrationLike(Protocol):
    """Structural view of the manager's ``HookRegistration`` records.

    The bridge deliberately depends on the shape only, so it keeps working
    with any manager exposing the documented ``get_hooks`` contract.
    """

    plugin: str
    event: str
    handler: Callable[[Any], None]
    priority: int


def validate_event_name(event: str) -> str:
    """Return ``event`` if it is whitelisted, else raise ``ValueError``.

    The error message lists every allowed event so callers can fix their
    registration without guessing.
    """
    from angelus.plugins.base import HOOK_EVENTS

    if event not in HOOK_EVENTS:
        raise ValueError(
            f"unknown hook event {event!r}; "
            f"allowed: {', '.join(sorted(HOOK_EVENTS))}"
        )
    return event


class PluginHookBridge:
    """Route agent-bus execution events to plugin hooks.

    The bridge registers one lightweight :class:`ExecutionHook` dispatcher on
    the host bus (an ``ExecutionGraph``, ``AgentSwarm`` or ``Agent`` — any
    object exposing ``add_hook``/``remove_hook``).  Every bus event is mapped
    through :data:`_COLON_TO_DOT`; matching plugin hooks then run in priority
    order, each isolated in its own ``try/except``.

    Args:
        manager: ``PluginManager``-like object exposing
            ``get_hooks(event=None)`` that returns ``HookRegistration``
            records (a priority-descending list for a given event, or a dict
            of such lists when ``event`` is ``None``).
        host: Optional event bus to attach to (see :meth:`attach`).
        logger: Optional logger (default ``logging.getLogger(
            "angelus.plugins.hooks")``).
    """

    def __init__(
        self,
        manager: Any,
        host: Any = None,
        *,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._manager = manager
        self._host = host
        self._logger = logger or logging.getLogger("angelus.plugins.hooks")
        self._attached = False
        self._enabled = False

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    @property
    def attached(self) -> bool:
        """True when the dispatcher is registered on the host bus."""
        return self._attached

    def attach(self, host: Any = None) -> None:
        """Register the dispatcher with the host's ``add_hook``.

        Idempotent: attaching twice keeps a single registration.  A ``host``
        argument overrides the one given at construction time.

        Raises:
            ValueError: no host was provided (construction or argument).
            TypeError: the host does not expose a callable ``add_hook``.
        """
        if host is not None:
            self._host = host
        if self._attached:
            return
        if self._host is None:
            raise ValueError("no event-bus host to attach to")
        add_hook = getattr(self._host, "add_hook", None)
        if not callable(add_hook):
            raise TypeError(
                f"hook host {type(self._host).__name__!r} has no "
                f"callable add_hook"
            )
        add_hook(self._dispatch)
        self._attached = True
        self._enabled = True

    def detach(self) -> None:
        """Stop dispatching bus events (idempotent).

        When the host exposes ``remove_hook`` the dispatcher is unregistered
        from the bus; hosts without ``remove_hook`` (e.g. ``ExecutionGraph``
        and ``AgentSwarm``) simply stop receiving events because the bridge
        flips an internal enabled flag first.
        """
        self._enabled = False
        if not self._attached:
            return
        remove_hook = getattr(self._host, "remove_hook", None)
        if callable(remove_hook):
            try:
                remove_hook(self._dispatch)
            except Exception:
                self._logger.exception(
                    "failed to remove plugin hook dispatcher from host"
                )
        self._attached = False

    # ------------------------------------------------------------------
    # dispatch
    # ------------------------------------------------------------------
    def _dispatch(self, event: Any) -> None:
        """``ExecutionHook`` entry point: route one bus event to plugins."""
        if not self._enabled:
            return
        dot_event = _COLON_TO_DOT.get(getattr(event, "event_type", ""))
        if dot_event is None:
            return  # internal event not exposed to plugins (v1)
        self._invoke(dot_event, event)

    def _invoke(self, dot_event: str, event: Any) -> None:
        """Run every registration for one whitelisted dot event, isolating
        each handler so one failure never affects the others nor the caller.
        """
        from angelus.plugins.base import HOOK_EVENTS

        if dot_event not in HOOK_EVENTS:
            return  # defensive: the whitelist is enforced at registration
        for registration in self._registrations_for(dot_event):
            handler = registration.handler
            try:
                handler(event)
            except Exception:
                # A failing hook must not crash the agent/swarm main flow
                # (same isolation semantics as ExecutionGraph._emit and
                # tests/test_swarm_failure_isolation.py).
                self._logger.exception(
                    "hook %r of plugin %r failed on event %r",
                    getattr(handler, "__name__", handler),
                    registration.plugin,
                    dot_event,
                )

    def _registrations_for(self, event: str) -> list[HookRegistrationLike]:
        """HookRegistration list for one event, priority-descending.

        ``PluginManager.get_hooks(event)`` already returns a priority-desc
        list; the explicit sort here makes the ordering contract robust
        against any manager variant and keeps a stable tie-break (equal
        priorities run in registration order).
        """
        hooks = self._manager.get_hooks(event)
        if not hooks:
            return []
        if not isinstance(hooks, (list, tuple)):
            # Tolerate dict-shaped responses ({event: [registrations]}).
            hooks = hooks.get(event, [])
        return sorted(
            hooks,
            key=lambda reg: int(getattr(reg, "priority", 0) or 0),
            reverse=True,
        )

    # ------------------------------------------------------------------
    # synthetic events (e.g. session.created)
    # ------------------------------------------------------------------
    def notify(
        self,
        event: str,
        *,
        source: str = "plugin",
        agent_name: str = "",
        message: str = "",
        data: Any = None,
    ) -> Any:
        """Synthesize and dispatch a whitelisted event the bus does not emit.

        ``session.created`` has no native emitter in the current bus, so the
        host announces it by calling this method (typically right after a
        session record is created).  The synthetic ``ExecutionEvent`` is
        dispatched to every registered hook with ``event_type`` set to the
        dot event name.

        Returns:
            The synthesized ``ExecutionEvent`` (useful for tests/logging).

        Raises:
            ValueError: ``event`` is not in the whitelist.
        """
        validate_event_name(event)
        from llmfetcher.events import ExecutionEvent

        execution_event = ExecutionEvent(
            source=source,
            agent_name=agent_name,
            event_type=event,
            message=message,
            data=data,
        )
        self._invoke(event, execution_event)
        return execution_event


def attach_plugin_hooks(
    manager: Any,
    host: Any = None,
    *,
    logger: Optional[logging.Logger] = None,
) -> PluginHookBridge:
    """Create a :class:`PluginHookBridge` for ``manager`` and attach it.

    Mirrors the ``create_plugin_tools(manager)`` factory pattern used by the
    tools bridge.  When ``host`` is provided the bridge is attached to the
    bus immediately and returned ready to dispatch; call :meth:`attach` later
    otherwise.  The caller must keep the returned bridge alive for the
    lifetime of the plugin session (it owns the dispatcher).
    """
    bridge = PluginHookBridge(manager, host=host, logger=logger)
    if host is not None:
        bridge.attach()
    return bridge
