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

The local settings workbench can explicitly load and unload a registered
plugin.  Loading always needs a confirmation flag and never grants a newly
declared permission unless the caller confirms that grant separately.

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
import math
from pathlib import Path
from typing import Any, Iterator

from fastapi import APIRouter, Body, Depends, FastAPI, HTTPException
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

_SENSITIVE_SETTINGS_KEY_PARTS = (
    "api_key", "apikey", "authorization", "credential", "password", "secret", "token",
)
_MAX_SETTINGS_DEPTH = 8
_MAX_SETTINGS_ITEMS = 100
_MAX_SETTINGS_STRING_LENGTH = 8_000

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


def _settings_are_safe(value: Any, *, depth: int = 0) -> bool:
    """Accept bounded JSON settings while rejecting credential-shaped keys.

    Plugin settings are displayed back in the local browser workbench.  They
    are deliberately not a second connector-secret store; credentials belong
    to the encrypted connector path instead.
    """
    if depth > _MAX_SETTINGS_DEPTH:
        return False
    if value is None or isinstance(value, bool):
        return True
    if isinstance(value, str):
        return len(value) <= _MAX_SETTINGS_STRING_LENGTH
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return not isinstance(value, float) or math.isfinite(value)
    if isinstance(value, list):
        return len(value) <= _MAX_SETTINGS_ITEMS and all(
            _settings_are_safe(item, depth=depth + 1) for item in value
        )
    if isinstance(value, dict):
        if len(value) > _MAX_SETTINGS_ITEMS:
            return False
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > 120:
                return False
            normalized = key.replace("-", "_").lower()
            if any(part in normalized for part in _SENSITIVE_SETTINGS_KEY_PARTS):
                return False
            if not _settings_are_safe(item, depth=depth + 1):
                return False
        return True
    return False


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
        self._app: FastAPI | None = None
        self._mounted_route_keys: set[tuple[str, str, str]] = set()
        self._mounted_route_names: dict[str, set[str]] = {}

    # ------------------------------------------------------------------
    # public entry
    # ------------------------------------------------------------------
    def mount(self, app: FastAPI) -> None:
        """Attach the plugin REST/static surface to ``app``."""
        self._app = app
        api = APIRouter()
        api.get("/api/plugins", tags=["plugins"])(self._list_plugins)
        api.get("/api/plugins/status", tags=["plugins"])(self._plugin_status)
        api.post("/api/plugins/discovered/{name}/register", tags=["plugins"])(
            self._register_discovered_plugin
        )
        api.post("/api/plugins/{plugin_id}/load", tags=["plugins"])(
            self._load_plugin
        )
        api.post("/api/plugins/{plugin_id}/unload", tags=["plugins"])(
            self._unload_plugin
        )
        api.get("/api/plugins/{plugin_id}/settings", tags=["plugins"])(
            self._get_plugin_settings
        )
        api.put("/api/plugins/{plugin_id}/settings", tags=["plugins"])(
            self._put_plugin_settings
        )
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

    def _plugin_status(self) -> dict[str, Any]:
        """Return the complete discovered-plugin status for the settings UI.

        Unlike ``/api/plugins``, this management view includes disabled and
        blocked records so a user can diagnose why a plugin is not loadable.
        It intentionally omits source references and any persisted settings.
        """
        by_name = self._registry_by_name()
        return {
            "plugins": [
                self._status_entry(record, by_name.get(getattr(record, "name", "")) or {})
                for record in self.manager.plugins() or []
            ]
        }

    @staticmethod
    def _requested_permissions(manifest: dict[str, Any]) -> list[str]:
        """Return canonical manifest permissions without importing plugin code."""
        try:
            from .security import declared_permissions

            return sorted(declared_permissions(manifest))
        except Exception:  # pragma: no cover - defensive bridge fallback
            return []

    def _status_entry(self, record: Any, item: dict[str, Any]) -> dict[str, Any]:
        """Non-secret lifecycle metadata for the local management surface."""
        manifest = getattr(record, "manifest", None) or {}
        frontend = manifest.get("frontend") if isinstance(manifest, dict) else {}
        configurable = bool(
            isinstance(frontend, dict) and frontend.get("settings") is True
        )
        requested = self._requested_permissions(manifest) if isinstance(manifest, dict) else []
        granted = item.get("permissions_granted") or []
        return {
            "id": item.get("id"),
            "name": getattr(record, "name", ""),
            "version": getattr(record, "version", ""),
            "tier": getattr(record, "tier", ""),
            "state": getattr(getattr(record, "state", None), "value", getattr(record, "state", "unknown")),
            "enabled": bool(item.get("enabled")),
            "registered": bool(item.get("id")),
            "error": getattr(record, "error", None),
            "settings_available": configurable,
            "has_saved_settings": bool(item.get("settings")),
            "permissions_requested": requested,
            "permissions_granted": [grant for grant in granted if isinstance(grant, str)],
        }

    def _management_record(self, plugin_id: str) -> tuple[Any, dict[str, Any]]:
        """Resolve a discovered, registry-installed plugin for lifecycle control."""
        item = self.registry.get_plugin(plugin_id)
        if not isinstance(item, dict) or not item.get("name"):
            raise HTTPException(status_code=404, detail="plugin not found")
        record = self.manager.plugin(item["name"])
        if record is None:
            raise HTTPException(status_code=409, detail="plugin is not discovered")
        if not isinstance(getattr(record, "manifest", None), dict):
            raise HTTPException(status_code=409, detail="plugin manifest is invalid")
        return record, item

    def _register_discovered_plugin(
        self, name: str, payload: dict[str, Any] = Body(default={})
    ) -> dict[str, Any]:
        """Add one already-discovered local plugin to the local registry.

        This is intentionally narrower than the CLI installer: it accepts no
        path, URL, archive or source reference.  The manager has already
        validated and resolved the named plugin directory, and registration
        itself never imports or executes its entry code.
        """
        if not isinstance(payload, dict) or payload.get("confirm") is not True:
            raise HTTPException(status_code=409, detail="plugin registration requires confirmation")
        record = self.manager.plugin(name)
        manifest = getattr(record, "manifest", None) if record is not None else None
        plugin_dir = getattr(record, "plugin_dir", None) if record is not None else None
        if not isinstance(manifest, dict) or not plugin_dir:
            raise HTTPException(status_code=404, detail="discovered plugin not found")
        existing = self._registry_by_name().get(name)
        if existing is not None:
            return {"plugin": self._status_entry(record, existing)}
        try:
            from .security import compute_plugin_integrity

            checksum = compute_plugin_integrity(plugin_dir, manifest)
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=f"plugin integrity check failed: {exc}") from exc
        added = self.registry.add_plugin(
            {
                "name": name,
                "version": getattr(record, "version", manifest.get("version", "")),
                "api_version": manifest.get("api_version", "1"),
                "manifest_path": str(Path(plugin_dir) / "manifest.json"),
                "entry_path": str(manifest.get("entry") or ""),
                "source": "local",
                "enabled": False,
                "checksum": checksum,
                "permissions_granted": [],
            }
        )
        return {"plugin": self._status_entry(record, added)}

    def _load_plugin(
        self, plugin_id: str, payload: dict[str, Any] = Body(default={})
    ) -> dict[str, Any]:
        """Confirm, optionally grant declared permissions, then load one plugin.

        This endpoint deliberately accepts no arbitrary capabilities: the only
        grants it can persist are exactly the permissions declared in the
        validated manifest.  It is intended for the loopback workbench, not a
        remote marketplace installer.
        """
        if not isinstance(payload, dict) or payload.get("confirm") is not True:
            raise HTTPException(status_code=409, detail="plugin load requires confirmation")
        record, item = self._management_record(plugin_id)
        manifest = record.manifest
        requested = self._requested_permissions(manifest)
        granted = {
            grant for grant in item.get("permissions_granted") or [] if isinstance(grant, str)
        }
        missing = [grant for grant in requested if grant not in granted]
        if missing and payload.get("grant_permissions") is not True:
            raise HTTPException(
                status_code=409,
                detail="plugin declares ungranted permissions; confirm permission grant",
            )
        if missing:
            updated = self.registry.grant_permissions(item["id"], missing)
            if not isinstance(updated, dict):  # pragma: no cover - registry race
                raise HTTPException(status_code=404, detail="plugin not found")
        try:
            record = self.manager.enable(item["name"])
        except Exception as exc:
            logger.warning("plugin %r could not be loaded from workbench: %s", item["name"], exc)
            raise HTTPException(status_code=409, detail=f"plugin could not be loaded: {exc}") from exc
        if _is_active(record) and self._app is not None:
            self._mount_plugin_routers(self._app)
        current = self.registry.get_plugin(item["id"]) or item
        return {"plugin": self._status_entry(record, current)}

    def _unload_plugin(
        self, plugin_id: str, payload: dict[str, Any] = Body(default={})
    ) -> dict[str, Any]:
        """Confirm and tear down a plugin without deleting its installed files."""
        if not isinstance(payload, dict) or payload.get("confirm") is not True:
            raise HTTPException(status_code=409, detail="plugin unload requires confirmation")
        record, item = self._management_record(plugin_id)
        try:
            self.manager.disable(item["name"])
        except Exception as exc:
            logger.warning("plugin %r could not be unloaded from workbench: %s", item["name"], exc)
            raise HTTPException(status_code=409, detail=f"plugin could not be unloaded: {exc}") from exc
        self._unmount_plugin_routers(item["name"])
        refreshed = self.manager.plugin(item["name"]) or record
        current = self.registry.get_plugin(item["id"]) or item
        return {"plugin": self._status_entry(refreshed, current)}

    def _settings_record(self, plugin_id: str) -> tuple[Any, dict[str, Any]]:
        item = self.registry.get_plugin(plugin_id)
        if not isinstance(item, dict) or not item.get("name"):
            raise HTTPException(status_code=404, detail="plugin not found")
        record = self.manager.plugin(item["name"])
        if record is None:
            raise HTTPException(status_code=404, detail="plugin is not discovered")
        manifest = getattr(record, "manifest", None) or {}
        frontend = manifest.get("frontend") if isinstance(manifest, dict) else {}
        if not isinstance(frontend, dict) or frontend.get("settings") is not True:
            raise HTTPException(status_code=409, detail="plugin does not declare configurable settings")
        return record, item

    def _get_plugin_settings(self, plugin_id: str) -> dict[str, Any]:
        """Read one plugin's non-secret persisted settings."""
        record, item = self._settings_record(plugin_id)
        settings = item.get("settings") or {}
        return {
            "id": item["id"],
            "name": item["name"],
            "version": getattr(record, "version", item.get("version", "")),
            "settings": settings if isinstance(settings, dict) else {},
        }

    def _put_plugin_settings(
        self, plugin_id: str, settings: dict[str, Any] = Body(...)
    ) -> dict[str, Any]:
        """Persist JSON settings without accepting credential-like values."""
        _, item = self._settings_record(plugin_id)
        if not _settings_are_safe(settings):
            raise HTTPException(
                status_code=422,
                detail="settings must be bounded JSON and may not contain credentials",
            )
        updated = self.registry.update_plugin(item["id"], {"settings": settings})
        if not isinstance(updated, dict):  # pragma: no cover - registry race
            raise HTTPException(status_code=404, detail="plugin not found")
        return {"id": updated["id"], "name": updated["name"], "settings": settings}

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
                route_key = (plugin, method, path)
                if key in seen or route_key in self._mounted_route_keys:
                    continue
                seen.add(key)
                self._mounted_route_keys.add(route_key)
                route_name = f"plugin:{plugin}:{method}:{path}"
                self._mounted_route_names.setdefault(plugin, set()).add(route_name)
                router.add_api_route(
                    path,
                    handler,
                    methods=[method],
                    name=route_name,
                    dependencies=[Depends(self._active_plugin_dependency(plugin))],
                )
            app.include_router(router)

    def _active_plugin_dependency(self, plugin: str) -> Any:
        """Build a request-time guard for an already-mounted plugin route."""
        def require_active_plugin() -> None:
            item = self._registry_by_name().get(plugin)
            record = self.manager.plugin(plugin)
            if item is None or not item.get("enabled") or not _is_active(record):
                raise HTTPException(status_code=404, detail="plugin route not found")

        return require_active_plugin

    def _unmount_plugin_routers(self, plugin: str) -> None:
        """Remove routes owned by a stopped plugin so stale handlers cannot run."""
        names = self._mounted_route_names.pop(plugin, set())
        if self._app is not None:
            plugin_tag = f"plugin:{plugin}"
            self._app.router.routes[:] = [
                route for route in self._app.router.routes
                if getattr(route, "name", None) not in names
                and plugin_tag not in (getattr(route, "tags", None) or [])
            ]
        self._mounted_route_keys = {
            key for key in self._mounted_route_keys if key[0] != plugin
        }


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
) -> PluginBridge:
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
    bridge = PluginBridge(manager, registry=registry)
    bridge.mount(app)
    return bridge
