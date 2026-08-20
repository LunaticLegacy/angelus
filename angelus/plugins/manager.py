"""PluginManager: application-level discovery, namespaced import, lifecycle (S3).

Responsibilities (contract ``docs/plugin-api.md`` §4, decisions D1/D2):

* **Discovery** — production instances scan the persistent
  ``<app_data>/plugins`` directory next to ``workspace/`` (via
  ``plugin_paths``).  Explicit legacy directory overrides remain available
  only for embeddings and tests.  Manifests are validated with the S2
  handwritten validator; invalid plugins are recorded with structured errors
  and never loaded.
* **Namespaced import** — every plugin is imported under the
  ``angelus_plugins.<name>`` namespace.  The plugin package is pre-registered
  in ``sys.modules`` bound to its resolved directory, so hyphenated manifest
  names work, and plugin imports never pollute the
  top-level namespace.
* **Lifecycle** — ``setup()`` failures isolate the plugin (state → ``blocked``,
  registrations rolled back) without crashing the host; ``teardown()`` is
  idempotent; repeated loads are de-duplicated and ``reload`` tears down first.
* **Register-first-then-take-effect** — ``PluginRuntime`` collects
  ``register_*`` calls during setup; the manager publishes the snapshot into
  its live tables only after setup succeeds.
* **Enable/disable state machine** — backed by the S2 ``plugin_registry``
  (``plugins.json``); only registry-enabled plugins are loaded by
  :meth:`load_all`.
"""

from __future__ import annotations

import enum
import importlib
import importlib.machinery
import importlib.util
import logging
import sys
import threading
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .base import AngelusPlugin, PluginError, PluginRuntime

__all__ = [
    "ConnectorRegistration",
    "HookRegistration",
    "PluginManager",
    "PluginRecord",
    "PluginState",
    "RouteRegistration",
    "ToolRegistration",
]

NAMESPACE_ROOT = "angelus_plugins"


class PluginState(str, enum.Enum):
    """Lifecycle state of a discovered/loaded plugin."""

    DISCOVERED = "discovered"  # found, manifest valid, not loaded yet
    LOADING = "loading"  # import/setup in progress
    ACTIVE = "active"  # setup succeeded, registrations published
    BLOCKED = "blocked"  # import/setup failed; never published
    DISABLED = "disabled"  # torn down (teardown ran, modules purged)
    ERROR = "error"  # invalid manifest; cannot be loaded


@dataclass
class PluginRecord:
    """One discovered plugin and its in-memory lifecycle state."""

    name: str
    plugin_dir: Path
    tier: str  # "workspace" | "global"
    manifest: dict[str, Any] | None = None
    version: str = ""
    state: PluginState = PluginState.DISCOVERED
    plugin: AngelusPlugin | None = None
    runtime: PluginRuntime | None = None
    error: str | None = None
    errors: list[dict[str, str]] = field(default_factory=list)

    @property
    def loadable(self) -> bool:
        return self.manifest is not None


@dataclass(frozen=True)
class ToolRegistration:
    """Published plugin tool (live name ``plugin.<plugin>.<tool>``)."""

    plugin: str
    name: str
    schema: dict[str, Any]
    handler: Callable

    @property
    def full_name(self) -> str:
        return f"plugin.{self.plugin}.{self.name}"


@dataclass(frozen=True)
class RouteRegistration:
    """Published plugin route (mounted under ``/plugins/<name>/api``)."""

    plugin: str
    method: str
    path: str
    handler: Callable


@dataclass(frozen=True)
class HookRegistration:
    """Published plugin hook for a whitelisted agent event."""

    plugin: str
    event: str
    handler: Callable
    priority: int = 0


@dataclass(frozen=True)
class ConnectorRegistration:
    """Published plugin connector provider factory."""

    plugin: str
    kind: str
    factory: Callable


class PluginManager:
    """Owns plugin discovery, namespaced loading and the lifecycle state
    machine for every plugin visible in the current workspace.
    """

    def __init__(
        self,
        state_root: Path | str | None = None,
        *,
        workspace_dir: Path | str | None = None,
        global_dir: Path | str | None = None,
        registry: Any = None,
        logger: logging.Logger | None = None,
    ) -> None:
        """Create a manager.

        Args:
            state_root: Workspace root; when no directory overrides are
                injected, plugins resolve to its persistent sibling
                ``<app_data>/plugins`` via ``angelus.plugin_paths``.
            workspace_dir: Legacy test/embedding override for a higher-
                priority plugin directory.
            global_dir: Legacy test/embedding override for a lower-priority
                plugin directory.
            registry: Object exposing the S2 ``plugin_registry`` interface
                (``list_plugins``/``get_plugin``/``set_enabled``/...).
                Defaults to the ``angelus.plugin_registry`` module (lazily
                imported so this module stays importable in isolation).
            logger: Manager logger.
        """
        self._scan_tiers: tuple[tuple[str, Path], ...]
        if workspace_dir is None and global_dir is None:
            from angelus import plugin_paths

            persistent_dir = Path(plugin_paths.plugin_dir(state_root)).resolve()
            # The production application has exactly one plugin directory,
            # beside workspace/.  Keep legacy properties as aliases for
            # embedding code that still reads them.
            self._workspace_dir = persistent_dir
            self._global_dir = persistent_dir
            self._scan_tiers = (("application", persistent_dir),)
        else:
            # S2 dependency, imported lazily so this module can be imported
            # before the registry layer lands in the merged tree.
            from angelus import plugin_paths

            if workspace_dir is None:
                workspace_dir = plugin_paths.workspace_plugin_dir(state_root)
            if global_dir is None:
                global_dir = plugin_paths.global_plugin_dir(state_root)

            self._workspace_dir = Path(workspace_dir).resolve()
            self._global_dir = Path(global_dir).resolve()
            self._scan_tiers = (
                ("workspace", self._workspace_dir),
                ("global", self._global_dir),
            )
        self._registry: Any = registry
        self._manifest: Any = None  # lazy angelus.plugin_manifest
        self._logger = logger or logging.getLogger("angelus.plugins.manager")
        self._lock = threading.RLock()

        self._records: dict[str, PluginRecord] = {}
        self._discovered = False

        # Live registration tables (published only after successful setup).
        self._tools: dict[str, ToolRegistration] = {}
        self._routes: list[RouteRegistration] = []
        self._hooks: dict[str, list[HookRegistration]] = {}
        self._connectors: dict[str, ConnectorRegistration] = {}

    # ------------------------------------------------------------------
    # public surface
    # ------------------------------------------------------------------
    @property
    def workspace_dir(self) -> Path:
        return self._workspace_dir

    @property
    def global_dir(self) -> Path:
        return self._global_dir

    def discover(self) -> list[PluginRecord]:
        """Scan both tiers and (re)build the discovered record set.

        Workspace-tier plugins shadow global-tier plugins with the same
        manifest name.  Lifecycle state is preserved for records whose
        directory is unchanged, so re-discovery never tears down active
        plugins.
        """
        loader = self._manifest_loader()
        found: dict[str, PluginRecord] = {}

        for tier, base in self._scan_tiers:
            if not base.is_dir():
                continue
            for child in sorted(base.iterdir()):
                if not child.is_dir():
                    continue
                manifest, errors = loader.load_manifest(
                    child / loader.MANIFEST_FILENAME
                )
                if manifest is None:
                    name = child.name
                    if name not in found:
                        found[name] = PluginRecord(
                            name=name,
                            plugin_dir=child,
                            tier=tier,
                            manifest=None,
                            state=PluginState.ERROR,
                            errors=errors,
                        )
                    continue
                name = manifest["name"]
                if name in found:
                    continue  # Explicit legacy override order retains priority.
                found[name] = PluginRecord(
                    name=name,
                    plugin_dir=child,
                    tier=tier,
                    manifest=manifest,
                    version=manifest.get("version", ""),
                    state=PluginState.DISCOVERED,
                )

        for name, record in found.items():
            existing = self._records.get(name)
            if (
                existing is not None
                and existing.plugin_dir == record.plugin_dir
                and existing.manifest is not None
                and record.manifest is not None
            ):
                # Preserve lifecycle state across re-discovery.
                record.state = existing.state
                record.plugin = existing.plugin
                record.runtime = existing.runtime
                record.error = existing.error
            self._records[name] = record

        self._discovered = True
        return list(self._records.values())

    def load(self, name: str, *, reload: bool = False) -> PluginRecord:
        """Import and ``setup()`` one plugin; returns its record.

        * A plugin that is already ``active`` is returned as-is (dedupe: the
          setup phase never runs twice for the same load).
        * A plugin in ``blocked`` stays blocked until ``reload=True``.
        * ``reload=True`` tears the plugin down first, purging its modules so
          a fresh import happens.
        * Any plugin-caused failure (import error, missing ``angelus_plugin``,
          ``setup()`` exception) flips the record to ``blocked`` and is
          **not** raised — the host process is never taken down by a plugin.

        Raises:
            PluginError: plugin unknown, manifest invalid, or already loading.
        """
        with self._lock:
            record = self._require_loadable(name)
            if record.state == PluginState.ACTIVE and not reload:
                return record
            if record.state == PluginState.BLOCKED and not reload:
                return record
            if record.state == PluginState.LOADING:
                raise PluginError(f"plugin {name!r} is already loading")
            if reload:
                self._teardown_locked(name)
                record = self._records.get(name) or record

            record.state = PluginState.LOADING
            record.error = None
            try:
                module = self._import_entry(record)
                plugin = self._resolve_plugin(module, record)
                runtime = self._build_runtime(record)
                runtime._begin_setup()
                try:
                    plugin.setup(runtime)
                except Exception as exc:  # setup failure isolation
                    runtime._abort()
                    record.state = PluginState.BLOCKED
                    record.error = f"setup failed: {type(exc).__name__}: {exc}"
                    self._logger.exception("plugin %r setup failed", name)
                    return record
                snapshot = runtime._commit()
            except PluginError as exc:
                record.state = PluginState.BLOCKED
                record.error = str(exc)
                self._logger.exception("plugin %r failed to load", name)
                return record
            except Exception as exc:
                record.state = PluginState.BLOCKED
                record.error = f"load failed: {type(exc).__name__}: {exc}"
                self._logger.exception("plugin %r failed to load", name)
                return record

            record.plugin = plugin
            record.runtime = runtime
            record.state = PluginState.ACTIVE
            record.error = None
            self._publish(name, snapshot)
            self._logger.info(
                "plugin %r active: %d tool(s), %d route(s), %d hook(s), %d connector(s)",
                name,
                len(snapshot["tools"]),
                len(snapshot["routes"]),
                len(snapshot["hooks"]),
                len(snapshot["connectors"]),
            )
            return record

    def reload(self, name: str) -> PluginRecord:
        """Tear down and load a plugin fresh (modules purged, setup re-run)."""
        return self.load(name, reload=True)

    def teardown(self, name: str) -> PluginRecord | None:
        """Run ``teardown()``, unpublish registrations and purge modules.

        Idempotent: calling it again (or on a never-loaded plugin) is a
        no-op.  Plugin ``teardown()`` exceptions are logged, never raised.
        """
        with self._lock:
            return self._teardown_locked(name)

    def enable(
        self, name: str, *, permissions: list[str] | None = None
    ) -> PluginRecord:
        """Persist ``enabled=true`` in the registry, then load the plugin.

        Args:
            name: Plugin manifest name.
            permissions: ``"action:scope"`` grants recorded on first enable
                (S2 ``set_enabled(..., permissions=...)``).

        Raises:
            PluginError: plugin unknown/not installed in the registry.
        """
        with self._lock:
            record = self._require_loadable(name)
            item = self._registry_lookup(name)
            if item is None:
                raise PluginError(
                    f"plugin {name!r} is not installed in the registry; "
                    f"install it first (angelus plugin install)"
                )
            self._registry_module().set_enabled(
                item["id"], True, permissions=permissions
            )
            return self.load(name)

    def disable(self, name: str) -> PluginRecord | None:
        """Tear the plugin down and persist ``enabled=false`` in the registry."""
        with self._lock:
            record = self.teardown(name)
            item = self._registry_lookup(name)
            if item is not None:
                self._registry_module().set_enabled(item["id"], False)
            return record

    def load_all(self) -> list[PluginRecord]:
        """Load every discovered plugin that is enabled in the registry.

        Disabled plugins are never imported (their code is not executed).
        """
        with self._lock:
            self.discover()
            loaded: list[PluginRecord] = []
            for name, record in list(self._records.items()):
                if record.manifest is None:
                    continue
                item = self._registry_lookup(name)
                if item is None or not item.get("enabled"):
                    continue
                loaded.append(self.load(name))
            return loaded

    # ------------------------------------------------------------------
    # live registration tables (consumed by the S4–S7 bridges)
    # ------------------------------------------------------------------
    def get_tools(self) -> dict[str, ToolRegistration]:
        """Published tools keyed by their namespaced ``plugin.<name>.<tool>``."""
        return dict(self._tools)

    def get_routes(self) -> list[RouteRegistration]:
        return list(self._routes)

    def get_hooks(
        self, event: str | None = None
    ) -> dict[str, list[HookRegistration]] | list[HookRegistration]:
        """Return hooks for one event (priority-desc) or all events."""
        if event is None:
            return {ev: list(hooks) for ev, hooks in self._hooks.items()}
        return list(self._hooks.get(event, []))

    def get_connectors(self) -> dict[str, ConnectorRegistration]:
        return dict(self._connectors)

    def plugin(self, name: str) -> PluginRecord | None:
        return self._records.get(name)

    def plugins(self) -> list[PluginRecord]:
        self._ensure_discovered()
        return [self._records[key] for key in sorted(self._records)]

    def get_status(self) -> list[dict[str, Any]]:
        """Status snapshot for ``/api/plugins`` and CLI reporting."""
        statuses: list[dict[str, Any]] = []
        for record in self.plugins():
            item = self._registry_lookup(record.name)
            statuses.append(
                {
                    "name": record.name,
                    "version": record.version,
                    "tier": record.tier,
                    "state": record.state.value,
                    "enabled": bool(item and item.get("enabled")),
                    "error": record.error,
                }
            )
        return statuses

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    def _ensure_discovered(self) -> None:
        if not self._discovered:
            self.discover()

    def _require_loadable(self, name: str) -> PluginRecord:
        self._ensure_discovered()
        record = self._records.get(name)
        if record is None:
            raise PluginError(f"plugin {name!r} not found in either tier")
        if record.manifest is None:
            raise PluginError(
                f"plugin {name!r} has no valid manifest: {record.errors}"
            )
        return record

    def _manifest_loader(self) -> Any:
        if self._manifest is None:
            import angelus.plugin_manifest

            self._manifest = angelus.plugin_manifest
        return self._manifest

    def _registry_module(self) -> Any:
        if self._registry is None:
            import angelus.plugin_registry

            self._registry = angelus.plugin_registry
        return self._registry

    def _registry_lookup(self, name: str) -> dict[str, Any] | None:
        try:
            registry = self._registry_module()
        except ImportError:
            return None
        for item in registry.list_plugins():
            if item.get("name") == name:
                return item
        return None

    # -- namespaced import ------------------------------------------------
    def _ensure_namespace(self) -> types.ModuleType:
        """Create the ``angelus_plugins`` namespace package in ``sys.modules``."""
        pkg = sys.modules.get(NAMESPACE_ROOT)
        if pkg is None:
            pkg = types.ModuleType(NAMESPACE_ROOT)
            pkg.__package__ = NAMESPACE_ROOT
            pkg.__path__ = []
            pkg.__spec__ = importlib.machinery.ModuleSpec(
                NAMESPACE_ROOT, None, is_package=True
            )
            sys.modules[NAMESPACE_ROOT] = pkg
        for path in dict.fromkeys(str(base) for _, base in self._scan_tiers):
            if path not in pkg.__path__:
                pkg.__path__.append(path)
        return pkg

    def _import_entry(self, record: PluginRecord) -> types.ModuleType:
        """Import the plugin entry module under ``angelus_plugins.<name>``.

        The plugin package is pre-registered in ``sys.modules`` bound to the
        resolved plugin directory.  This keeps shadowing exact (workspace
        beats global), supports hyphenated manifest names, and confines all
        plugin modules inside the ``angelus_plugins.<name>`` namespace.
        """
        name = record.name
        plugin_dir = record.plugin_dir
        pkg_name = f"{NAMESPACE_ROOT}.{name}"

        self._ensure_namespace()
        if pkg_name not in sys.modules:
            init_py = plugin_dir / "__init__.py"
            if init_py.is_file():
                spec = importlib.util.spec_from_file_location(
                    pkg_name,
                    str(init_py),
                    submodule_search_locations=[str(plugin_dir)],
                )
                module = importlib.util.module_from_spec(spec)
                sys.modules[pkg_name] = module
                assert spec.loader is not None
                spec.loader.exec_module(module)
            else:
                module = types.ModuleType(pkg_name)
                module.__path__ = [str(plugin_dir)]
                module.__package__ = pkg_name
                module.__spec__ = importlib.machinery.ModuleSpec(
                    pkg_name, None, is_package=True
                )
                sys.modules[pkg_name] = module

        manifest = record.manifest or {}
        entry = (manifest.get("entry") or "main").strip()
        entry_type = manifest.get("entry_type") or "module"

        if entry.startswith(f"{NAMESPACE_ROOT}."):
            # Fully qualified entry: must stay inside this plugin's namespace.
            if not (entry == pkg_name or entry.startswith(pkg_name + ".")):
                raise PluginError(
                    f"plugin {name!r} entry {entry!r} escapes its namespace"
                )
            module_name = entry
        elif entry_type == "package" and entry in ("", ".", pkg_name):
            module_name = pkg_name
        else:
            module_name = f"{pkg_name}.{entry}" if entry else pkg_name

        return importlib.import_module(module_name)

    def _resolve_plugin(self, module: types.ModuleType, record: PluginRecord) -> AngelusPlugin:
        entry_type = (record.manifest or {}).get("entry_type") or "module"
        plugin: Any = None
        if entry_type == "function":
            factory = getattr(module, "create_plugin", None)
            if callable(factory):
                plugin = factory()
        if plugin is None:
            plugin = getattr(module, "angelus_plugin", None)
        if plugin is None:
            raise PluginError(
                f"entry module {module.__name__} exposes no 'angelus_plugin' "
                f"(an AngelusPlugin instance)"
            )
        if not isinstance(plugin, AngelusPlugin):
            raise PluginError(
                f"'angelus_plugin' in {module.__name__} is not an "
                f"AngelusPlugin instance"
            )
        if plugin.name and plugin.name != record.name:
            self._logger.warning(
                "plugin %r declares name %r; manifest name wins for namespacing",
                record.name,
                plugin.name,
            )
        return plugin

    def _build_runtime(self, record: PluginRecord) -> PluginRuntime:
        state_dir = record.plugin_dir / "data"
        state_dir.mkdir(parents=True, exist_ok=True)
        item = self._registry_lookup(record.name)
        settings = dict((item or {}).get("settings") or {})
        return PluginRuntime(
            name=record.name,
            state_dir=state_dir,
            settings=settings,
            logger=logging.getLogger(f"angelus.plugins.{record.name}"),
        )

    # -- publish / unpublish ---------------------------------------------
    def _publish(self, name: str, snapshot: dict[str, list[dict[str, Any]]]) -> None:
        """Apply a successful setup snapshot to the live tables."""
        for tool in snapshot["tools"]:
            registration = ToolRegistration(
                plugin=name,
                name=tool["name"],
                schema=tool["schema"],
                handler=tool["handler"],
            )
            self._tools[registration.full_name] = registration
        for route in snapshot["routes"]:
            self._routes.append(
                RouteRegistration(
                    plugin=name,
                    method=route["method"],
                    path=route["path"],
                    handler=route["handler"],
                )
            )
        for hook in snapshot["hooks"]:
            self._hooks.setdefault(hook["event"], []).append(
                HookRegistration(
                    plugin=name,
                    event=hook["event"],
                    handler=hook["handler"],
                    priority=hook["priority"],
                )
            )
            self._hooks[hook["event"]].sort(
                key=lambda item: item.priority, reverse=True
            )
        for connector in snapshot["connectors"]:
            self._connectors[connector["kind"]] = ConnectorRegistration(
                plugin=name,
                kind=connector["kind"],
                factory=connector["factory"],
            )

    def _unpublish(self, name: str) -> None:
        self._tools = {
            key: value
            for key, value in self._tools.items()
            if value.plugin != name
        }
        self._routes = [route for route in self._routes if route.plugin != name]
        self._hooks = {
            event: [hook for hook in hooks if hook.plugin != name]
            for event, hooks in self._hooks.items()
        }
        self._hooks = {
            event: hooks for event, hooks in self._hooks.items() if hooks
        }
        self._connectors = {
            key: value
            for key, value in self._connectors.items()
            if value.plugin != name
        }

    # -- teardown / module purging ---------------------------------------
    def _teardown_locked(self, name: str) -> PluginRecord | None:
        record = self._records.get(name)
        if record is None:
            return None
        if record.state not in (PluginState.ACTIVE, PluginState.BLOCKED):
            return record  # idempotent
        plugin = record.plugin
        if plugin is not None:
            try:
                plugin.teardown()
            except Exception:
                self._logger.exception("plugin %r teardown failed", name)
        self._unpublish(name)
        self._purge_modules(name)
        if record.runtime is not None:
            record.runtime._shutdown()
        record.plugin = None
        record.runtime = None
        record.state = PluginState.DISABLED
        record.error = None
        return record

    def _purge_modules(self, name: str) -> None:
        """Drop every module of this plugin from ``sys.modules`` so a later
        load imports a fresh copy (no stale registrations, no duplicates)."""
        pkg = f"{NAMESPACE_ROOT}.{name}"
        prefix = pkg + "."
        for key in [
            existing
            for existing in sys.modules
            if existing == pkg or existing.startswith(prefix)
        ]:
            del sys.modules[key]
