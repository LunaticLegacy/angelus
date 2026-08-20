"""Angelus plugin runtime core (swarm S3).

Public surface:

* :class:`PluginManager` — two-tier discovery, ``angelus_plugins.<name>``
  namespaced import, lifecycle (setup/teardown isolation), enable/disable
  state machine backed by ``plugins.json``, duplicate-load de-duplication.
* :class:`AngelusPlugin` — base class plugins subclass.
* :class:`PluginRuntime` — setup-time registration API
  (``register_tool``/``register_route``/``register_hook``/``register_connector``
  plus ``state_dir``/``logger``/``settings``).
* :data:`HOOK_EVENTS` — whitelist of agent events plugins may subscribe to.
* Registration record dataclasses published by the manager (consumed by the
  S4–S7 bridges): :class:`ToolRegistration`, :class:`RouteRegistration`,
  :class:`HookRegistration`, :class:`ConnectorRegistration`.

Contract: ``docs/plugin-api.md`` §4/§5; decisions ``docs/decisions.md`` D1/D2.
"""

from .base import (
    HOOK_EVENTS,
    HTTP_METHODS,
    AngelusPlugin,
    PluginError,
    PluginRuntime,
)
from .manager import (
    ConnectorRegistration,
    HookRegistration,
    PluginManager,
    PluginRecord,
    PluginState,
    RouteRegistration,
    ToolRegistration,
)

__version__ = "1.0.0"

__all__ = [
    "HOOK_EVENTS",
    "HTTP_METHODS",
    "AngelusPlugin",
    "ConnectorRegistration",
    "HookRegistration",
    "PluginError",
    "PluginManager",
    "PluginRecord",
    "PluginRuntime",
    "PluginState",
    "RouteRegistration",
    "ToolRegistration",
]
