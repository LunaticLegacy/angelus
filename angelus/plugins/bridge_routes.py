"""S6 — REST/static route bridge for the Angelus plugin system.

Mounts the plugin extension surface onto the main FastAPI app (contract
``docs/plugin-api.md`` §6.1 / appendix D of the swarm execution spec):

* ``GET /plugins/{name}/static/{asset}`` — serves only files listed in
  ``manifest.frontend.assets``.  Every request is normalized with
  ``Path.resolve()`` + ``relative_to`` so ``../`` traversal (raw, encoded or
  symlink-escaped) can never leave the plugin directory; traversal, unknown
  assets and disabled plugins all answer 404.
* ``GET /plugins/{name}/api/*`` — a per-plugin ``APIRouter`` built from the
  :class:`RouteRegistration` records published by
  ``PluginManager.get_routes()`` (HTTP verb whitelist enforced, prefix
  isolation: a plugin route is never reachable outside its prefix).
* ``GET /api/plugins`` and ``GET /api/plugins/{id}`` — plugin listing built
  from the S2 registry.  List entries expose exactly the appendix-D fields
  (``id``/``name``/``version``/``api_version``/``enabled``/``checksum``/
  ``source``/``installed_at``); the detail view adds
  ``permissions_granted``.  The manifest, settings, source refs and any
  credential material are never serialized.

Only plugins that are **registry-enabled and manager-active** belong to the
loadable set: disabled plugins are not listed, their code is never mounted
and their static assets are never served.

The bridge is deliberately duck-typed against the runtime-core contract so it
stays importable while the plugin package is being merged: it only needs an
object exposing ``plugins()``/``plugin(name)``/``get_routes()`` plus an
optional S2 registry adapter (``list_plugins()``/``get_plugin(id)``).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterator

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse

__all__ = ["PluginBridge", "include_plugin_routes"]

logger = logging.getLogger("angelus.plugins.bridge_routes")

#: Appendix-D field whitelist for the REST listing.  Only these keys are ever
#: copied out of a registry record — nothing else (manifest, settings,
#: source_ref, credentials) can leak into a response.
LIST_FIELDS = (
    "id",
    "name",
    "version",
    "api_version",
    "enabled",
    "checksum",
    "source",
    "installed_at",
)

#: Mirror of ``angelus.plugins.base.HTTP_METHODS``.  When the runtime-core
#: package is importable the canonical frozenset is consulted instead; the
#: literal keeps this module importable during the branch merge.
DEFAULT_HTTP_METHODS = frozenset(
    {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}
)


def _http_methods() -> frozenset[str]:
    """Canonical HTTP verb whitelist (``angelus.plugins.base.HTTP_METHODS``)."""
    try:
        from angelus.plugins.base import HTTP_METHODS  # type: ignore[import-not-found]
    except ImportError:  # runtime-core not merged into this tree yet
        return DEFAULT_HTTP_METHODS
    return HTTP_METHODS


def _is_active(record: Any) -> bool:
    """True when the manager record is loaded (state == PluginState.ACTIVE).

    Accepts both the real ``PluginState`` enum and plain strings so fake
    managers in tests behave identically.
    """
    state = getattr(record, "state", None)
    if state is None:
        return False
    value = state.value if hasattr(state, "value") else state
    return value == "active"


class _EmptyRegistry:
    """Stand-in registry so the bridge works before S2 lands (empty view)."""

    def list_plugins(self) -> list[dict[str, Any]]:
        return []

    def get_plugin(self, plugin_id: str) -> dict[str, Any] | None:
        return None


def _resolve_registry(registry: Any | None) -> Any:
    if registry is not None:
        return registry
    try:
        from angelus import plugin_registry  # type: ignore[import-not-found]
    except ImportError:
        logger.warning(
            "angelus.plugin_registry unavailable; /api/plugins will be empty"
        )
        return _EmptyRegistry()
    return plugin_registry


class PluginBridge:
    """Routes + static mounting for one ``PluginManager``.

    Attributes:
        manager: PluginManager-compatible object (duck-typed).
        registry: S2 registry adapter (``list_plugins``/``get_plugin``).
    """

    def __init__(self, manager: Any, *, registry: Any | None = None) -> None:
        self.manager = manager
        self.registry = _resolve_registry(registry)

    # ------------------------------------------------------------------
    # public entry
    # ------------------------------------------------------------------
    def mount(self, app: FastAPI) -> None:
        """Attach the plugin REST/static surface to ``app``."""
        api = APIRouter()
        api.get("/api/plugins", tags=["plugins"])(self._list_plugins)
        api.get("/api/plugins/{plugin_id}", tags=["plugins"])(self._get_plugin)
        api.get(
            "/plugins/{name}/static/{asset:path}",
            include_in_schema=False,
        )(self._static_asset)
        app.include_router(api)
        self._mount_plugin_routers(app)

    # ------------------------------------------------------------------
    # /api/plugins — loadable set = registry-enabled AND manager-active
    # ------------------------------------------------------------------
    def _registry_by_name(self) -> dict[str, dict[str, Any]]:
        entries: dict[str, dict[str, Any]] = {}
        for item in self.registry.list_plugins():
            if isinstance(item, dict) and item.get("name"):
                entries[item["name"]] = item
        return entries

    def _loadable(self) -> Iterator[tuple[Any, dict[str, Any]]]:
        """``(manager record, registry item)`` for enabled+active plugins."""
        by_name = self._registry_by_name()
        for record in self.manager.plugins() or []:
            if not _is_active(record):
                continue
            item = by_name.get(getattr(record, "name", None))
            if item is None or not item.get("enabled"):
                continue
            yield record, item

    @staticmethod
    def _public_entry(item: dict[str, Any]) -> dict[str, Any]:
        """Copy exactly the appendix-D list fields (no manifest/credentials)."""
        return {field: item.get(field) for field in LIST_FIELDS}

    def _list_plugins(self) -> dict[str, Any]:
        return {
            "plugins": [self._public_entry(item) for _, item in self._loadable()]
        }

    def _get_plugin(self, plugin_id: str) -> dict[str, Any]:
        item = self.registry.get_plugin(plugin_id)
        if not isinstance(item, dict) or not item.get("name"):
            raise HTTPException(status_code=404, detail="plugin not found")
        record = self.manager.plugin(item["name"])
        if record is None or not _is_active(record) or not item.get("enabled"):
            raise HTTPException(status_code=404, detail="plugin not found")
        entry = self._public_entry(item)
        entry["permissions_granted"] = list(item.get("permissions_granted") or [])
        return entry

    # ------------------------------------------------------------------
    # /plugins/{name}/static/{asset} — whitelist + Path normalization
    # ------------------------------------------------------------------
    def _static_asset(self, name: str, asset: str) -> FileResponse:
        target = self._resolve_static_asset(name, asset)
        if target is None:
            raise HTTPException(status_code=404, detail="asset not found")
        return FileResponse(target)

    def _resolve_static_asset(self, name: str, asset: str) -> Path | None:
        """Resolve ``asset`` inside the plugin dir under the whitelist.

        Returns ``None`` for unknown/disabled plugins, unknown assets, path
        traversal (``resolve`` escapes the plugin dir, symlinks included) and
        missing files — the caller answers 404 in every case.
        """
        record = self.manager.plugin(name)
        if record is None or not _is_active(record):
            return None
        manifest = getattr(record, "manifest", None) or {}
        assets = (manifest.get("frontend") or {}).get("assets") or []
        whitelist = {
            _normalise_asset_key(entry)
            for entry in assets
            if isinstance(entry, str) and entry
        }
        plugin_dir = getattr(record, "plugin_dir", None)
        if not plugin_dir:
            return None
        try:
            base = Path(plugin_dir).resolve()
            target = (base / asset).resolve(strict=False)
            relative = target.relative_to(base)
        except (TypeError, ValueError, OSError):
            return None
        if relative.as_posix() not in whitelist:
            return None
        if not target.is_file():
            return None
        return target

    # ------------------------------------------------------------------
    # /plugins/{name}/api/* — prefixed per-plugin APIRouter
    # ------------------------------------------------------------------
    def _mount_plugin_routers(self, app: FastAPI) -> None:
        """Attach one prefixed ``APIRouter`` per plugin with published routes."""
        methods = _http_methods()
        loadable = {getattr(record, "name", None) for record, _ in self._loadable()}
        by_plugin: dict[str, list[tuple[str, str, Any]]] = {}
        for registration in self.manager.get_routes() or []:
            plugin = getattr(registration, "plugin", None)
            method = str(getattr(registration, "method", "")).upper()
            path = getattr(registration, "path", None)
            handler = getattr(registration, "handler", None)
            if not plugin or not isinstance(path, str) or not path.startswith("/"):
                continue
            if not callable(handler):
                continue
            if method not in methods:
                logger.warning(
                    "plugin %r route %s %s skipped: method not in HTTP whitelist",
                    plugin,
                    method,
                    path,
                )
                continue
            by_plugin.setdefault(plugin, []).append((method, path, handler))

        for plugin, routes in by_plugin.items():
            if plugin not in loadable:
                continue  # prefix isolation: disabled plugins never mounted
            router = APIRouter(
                prefix=f"/plugins/{plugin}/api", tags=[f"plugin:{plugin}"]
            )
            seen: set[tuple[str, str]] = set()
            for method, path, handler in routes:
                key = (method, path)
                if key in seen:
                    continue
                seen.add(key)
                router.add_api_route(
                    path,
                    handler,
                    methods=[method],
                    name=f"plugin:{plugin}:{method}:{path}",
                )
            app.include_router(router)


def _normalise_asset_key(entry: str) -> str:
    """Normalise a whitelist entry to the same key space as resolved paths."""
    key = entry.replace("\\", "/")
    while key.startswith("./"):
        key = key[2:]
    return key.lstrip("/")


def include_plugin_routes(
    app: FastAPI,
    manager: Any,
    *,
    registry: Any | None = None,
) -> None:
    """Mount the plugin REST/static surface onto the main app (S6 entry).

    Designed to be called from ``angelus.webapp`` right after
    ``include_api_routes(app)``::

        manager = PluginManager(state_root=state_root)
        manager.load_all()
        include_api_routes(app)
        include_plugin_routes(app, manager)

    Args:
        app: Main FastAPI application.
        manager: PluginManager-compatible object (duck-typed: needs
            ``plugins()``, ``plugin(name)``, ``get_routes()``).
        registry: Optional S2 registry adapter (``list_plugins()`` and
            ``get_plugin(id)``); defaults to ``angelus.plugin_registry``.
    """
    PluginBridge(manager, registry=registry).mount(app)
