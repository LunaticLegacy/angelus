"""Connector-provider bridge: merge plugin ``register_connector`` providers
into the existing connector discovery/creation flow (S7, read-only path).

Contract (``docs/plugin-api.md`` §6):

* Plugins register connector provider factories through
  ``PluginRuntime.register_connector(kind, factory)``.  The
  :class:`~angelus.plugins.manager.PluginManager` publishes them into its
  live table reachable via ``manager.get_connectors()`` — a
  ``dict[str, ConnectorRegistration]`` keyed by ``kind`` with fields
  ``plugin``/``kind``/``factory``.

* This bridge is **read-only**: it only surfaces the *kinds* registered by
  plugins and hands back the registered *factory callables*.  It never
  reads the persisted connector store, never decrypts credentials and never
  forwards a stored API key to a plugin factory.  Secrets keep flowing
  through ``angelus/connectors.py`` unchanged (RSA-OAEP encrypted at rest
  via OpenSSL, decrypted only inside the server process, and redacted on
  every public read path by ``_public_connector``).

* No ``llmfetcher`` source is modified: built-in providers are reported by
  ``LLMFetcher.list_available_backend_providers()`` exactly as before and
  only the plugin *kinds* are merged into the aggregated view.

Wiring (done by the coordinator on merge — this module only provides the
entry points; ``angelus/connectors.py`` and ``angelus/api/connectors.py``
are not touched here):

    GET /api/providers (angelus/api/connectors.py)::

        from angelus.plugins import bridge_connectors
        ...
        return {"providers": list(
            bridge_connectors.aggregate_providers(manager)
        )}

    Connector creation for a plugin-registered provider (built-in providers
    keep the existing LLMFetcher path)::

        factory = bridge_connectors.resolve_connector_factory(
            request.provider, manager
        )
        if factory is not None:
            provider = bridge_connectors.create_plugin_connector(
                request.provider, manager
            )

``manager`` is the active :class:`~angelus.plugins.manager.PluginManager`;
every function accepts ``None`` (plugin system not wired up) and degrades
to the built-in behaviour, so the bridge is safe to import and call before
the plugin layer is connected.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Iterable, Optional

logger = logging.getLogger("angelus.plugins.bridge_connectors")

__all__ = [
    "aggregate_providers",
    "create_plugin_connector",
    "get_plugin_provider_kinds",
    "plugin_connector_factories",
    "resolve_connector_factory",
]


# ---------------------------------------------------------------------------
# internals
# ---------------------------------------------------------------------------
def _builtin_provider_kinds() -> tuple[str, ...]:
    """Provider kinds reported by the pinned ``llmfetcher`` library.

    Imported lazily so this module stays importable in isolation — the
    bridge must not hard-depend on ``llmfetcher`` internals at import time
    (it is also why ``llmfetcher`` is never modified).
    """
    from llmfetcher.llm_fetcher import LLMFetcher

    return tuple(LLMFetcher.list_available_backend_providers())


def _registrations(manager: Any) -> dict[str, Any]:
    """Duck-typed access to the manager's live connector registration table.

    Returns an empty dict when the plugin system is absent, ``manager`` is
    ``None``, or the table is unavailable — the bridge never raises because
    of host wiring differences.
    """
    if manager is None:
        return {}
    get_connectors = getattr(manager, "get_connectors", None)
    if not callable(get_connectors):
        return {}
    table = get_connectors()
    if not isinstance(table, dict):
        logger.warning(
            "PluginManager.get_connectors() returned %r; ignoring",
            type(table).__name__,
        )
        return {}
    return table


def _registration_factory(registration: Any) -> Optional[Callable]:
    """Extract the callable factory from a registration record.

    The record is duck-typed against the ``ConnectorRegistration`` contract
    (frozen dataclass with ``plugin``/``kind``/``factory`` fields); any
    record shape exposing a callable ``factory`` is accepted.
    """
    factory = getattr(registration, "factory", None)
    return factory if callable(factory) else None


# ---------------------------------------------------------------------------
# public surface — read-only provider discovery
# ---------------------------------------------------------------------------
def get_plugin_provider_kinds(manager: Any = None) -> tuple[str, ...]:
    """Sorted, de-duplicated provider kinds registered by plugins.

    Read-only: consults only the in-memory registration table
    (``manager.get_connectors()``), never the persisted connector store, so
    no credential material is ever touched or returned.
    """
    kinds = {str(kind) for kind in _registrations(manager)}
    return tuple(sorted(kinds))


def plugin_connector_factories(manager: Any = None) -> dict[str, Callable]:
    """Mapping ``kind -> factory`` for all plugin connector providers.

    Values are the plain factory callables a plugin registered; no stored
    credentials are attached to them.  Registrations without a callable
    factory are skipped with a warning.
    """
    factories: dict[str, Callable] = {}
    for kind, registration in _registrations(manager).items():
        factory = _registration_factory(registration)
        if factory is not None:
            factories[str(kind)] = factory
        else:
            logger.warning(
                "connector registration for kind %r has no callable factory",
                kind,
            )
    return factories


def aggregate_providers(
    manager: Any = None, builtin: Iterable[str] | None = None
) -> tuple[str, ...]:
    """Providers visible to ``GET /api/providers``.

    Union of the built-in ``llmfetcher`` backend providers (unless
    overridden with ``builtin`` for testing) and every plugin-registered
    connector kind, sorted and de-duplicated.

    Args:
        manager: Active ``PluginManager`` (``None`` = plugin system absent).
        builtin: Optional override of the built-in provider collection;
            defaults to ``LLMFetcher.list_available_backend_providers()``.
    """
    kinds = set(builtin) if builtin is not None else set(_builtin_provider_kinds())
    kinds.update(get_plugin_provider_kinds(manager))
    return tuple(sorted(kinds))


# ---------------------------------------------------------------------------
# public surface — factory resolution / creation (still read-only for secrets)
# ---------------------------------------------------------------------------
def resolve_connector_factory(
    kind: str, manager: Any = None
) -> Optional[Callable]:
    """Look up the plugin factory registered for a provider ``kind``.

    Returns ``None`` when the kind is not plugin-registered, so the caller
    can fall back to the existing built-in provider path.  This is the only
    bridge surface that yields plugin code; it returns the factory callable
    itself — never a secret, never a stored connector record.
    """
    if not isinstance(kind, str) or not kind:
        return None
    registration = _registrations(manager).get(kind)
    if registration is None:
        return None
    return _registration_factory(registration)


def create_plugin_connector(
    kind: str, manager: Any = None, **kwargs: Any
) -> Any:
    """Instantiate a plugin connector via its registered factory.

    Args:
        kind: Provider kind registered by a plugin.
        manager: Active ``PluginManager`` (``None`` = plugin system absent).
        **kwargs: Host-controlled arguments forwarded to the factory.  The
            bridge never injects stored credentials here — secrets continue
            to flow through ``angelus/connectors.py`` RSA-OAEP storage and
            are resolved per-run by ``_resolve_connector_key`` only.

    Raises:
        KeyError: no plugin factory registered for ``kind``.
    """
    factory = resolve_connector_factory(kind, manager)
    if factory is None:
        raise KeyError(
            f"no plugin connector factory registered for kind {kind!r}"
        )
    return factory(**kwargs)
