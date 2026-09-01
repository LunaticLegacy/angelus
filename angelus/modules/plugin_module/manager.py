"""Controlled plugin discovery, loading, settings, and static asset access."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import importlib.util
from pathlib import Path
import sys
import threading
from types import ModuleType
from typing import TYPE_CHECKING, Protocol

from ..tool_module import ToolCategory, ToolDefinition, ToolProviderRegistration, ToolRegistry
from .manifest import ManifestError, load_manifest
from .models import (
    PluginManifest,
    PluginPermission,
    PluginRecord,
    PluginRuntime,
    PluginSettingScalar,
    PluginSettingValue,
    PluginToolContribution,
)
from .store import PluginStore

if TYPE_CHECKING:
    from ..session_module import Session
    from ..tool_module import ToolPolicy
    from llmfetcher import Tool


class PluginEntrypoint(Protocol):
    """Minimal executable plugin lifecycle expected by the host."""

    def setup(self, runtime: PluginRuntime) -> None:
        """Register contributions using the supplied constrained runtime.

        Args:
            runtime: Host-owned registration and settings context.

        Returns:
            None.
        """

    def teardown(self) -> None:
        """Release plugin-owned process resources before removal.

        Returns:
            None.
        """


@dataclass(frozen=True)
class DiscoveredPlugin:
    """A manifest-validated package that has not necessarily been registered.

    Attributes:
        manifest: Declarative package metadata discovered without importing code.
        package_path: Resolved package directory.
        error: User-safe reason for an invalid package, if present.
    """

    manifest: PluginManifest | None
    package_path: Path
    error: str = ""


@dataclass
class LoadedPlugin:
    """In-process runtime state for an explicitly enabled plugin.

    Attributes:
        manifest: Validated declarative metadata.
        record: Durable approval/configuration state.
        module_name: Unique import namespace to remove at unload.
        entrypoint: Optional executable plugin object for tool plugins.
        provider_ids: Registry provider IDs published by setup.
    """

    manifest: PluginManifest
    record: PluginRecord
    module_name: str = ""
    entrypoint: PluginEntrypoint | None = None
    provider_ids: tuple[str, ...] = ()


class PluginManager:
    """Single process authority for plugin package lifecycle and settings."""

    def __init__(
        self,
        state_root: Path,
        tool_registry: ToolRegistry,
        development_root: Path | None = None,
    ) -> None:
        """Create an initially unloaded plugin manager.

        Args:
            state_root: Angelus-owned root for registry and managed packages.
            tool_registry: Existing global tool registry receiving loaded tools.
            development_root: Optional read-only source package directory. When
                omitted, Angelus discovers repository ``plugins/`` packages.
        """
        self.store = PluginStore(state_root)
        self._tool_registry = tool_registry
        source_root = development_root if development_root is not None else Path.cwd() / "plugins"
        self._discovery_roots = (
            self.store.package_root.resolve(),
            source_root.resolve(),
        )
        self._loaded: dict[str, LoadedPlugin] = {}
        self._lock = threading.RLock()

    def rescan(self) -> tuple[DiscoveredPlugin, ...]:
        """Discover managed and local development manifests without imports.

        Returns:
            Every package directory with its validated manifest or safe error.
        """
        self.store.package_root.mkdir(parents=True, exist_ok=True)
        discoveries: list[DiscoveredPlugin] = []
        names: set[str] = set()
        for root in self._discovery_roots:
            if not root.exists():
                continue
            for path in sorted(root.iterdir()):
                if not path.is_dir() or path.is_symlink():
                    continue
                resolved = path.resolve()
                try:
                    manifest = load_manifest(resolved)
                    if manifest.name in names:
                        discoveries.append(DiscoveredPlugin(None, resolved, f"duplicate plugin name: {manifest.name}"))
                        continue
                    names.add(manifest.name)
                    discoveries.append(DiscoveredPlugin(manifest, resolved))
                except ManifestError as exc:
                    discoveries.append(DiscoveredPlugin(None, resolved, str(exc)))
        return tuple(discoveries)

    def statuses(self) -> tuple[dict[str, object], ...]:
        """Project discovered and registered package states for the workbench.

        Returns:
            Public non-secret status objects; discovered invalid packages expose
            only their user-safe validation error.
        """
        records = {record.name: record for record in self.store.records()}
        result: list[dict[str, object]] = []
        for item in self.rescan():
            if item.manifest is None:
                result.append({"name": item.package_path.name, "state": "error", "registered": False, "enabled": False, "error": item.error, "settings_available": False})
                continue
            record = records.get(item.manifest.name)
            state = "active" if item.manifest.name in self._loaded else ("inactive" if record is not None else "discovered")
            result.append(_status(item.manifest, record, state, ""))
        return tuple(result)

    def active(self) -> tuple[dict[str, object], ...]:
        """Return the browser-loadable subset of active packages.

        Returns:
            Public active plugin entries used by the frontend bridge.
        """
        return tuple(_status(item.manifest, item.record, "active", "") for item in self._loaded.values())

    def restore_enabled(self) -> None:
        """Restore previously approved enabled plugins after host startup.

        Loading is limited to records whose requested permissions are already
        persisted as granted. Invalid or failed packages remain discoverable
        and are not allowed to prevent Angelus itself from starting.

        Returns:
            None.
        """
        for record in self.store.records():
            if not record.enabled:
                continue
            try:
                self.load(record.id, grant_permissions=False)
            except (KeyError, RuntimeError, ValueError):
                continue

    def register(self, name: str) -> dict[str, object]:
        """Persist a discovered package after validation without executing it.

        Args:
            name: Manifest name selected from current discovery results.

        Returns:
            Public registered plugin status.

        Raises:
            KeyError: If no valid discovered package has that name.
        """
        discovered = self._discovery(name)
        if discovered.manifest is None:
            raise KeyError(name)
        current = self._record_by_name(name)
        defaults = tuple(PluginSettingValue(field.key, field.default) for field in discovered.manifest.settings_schema if field.default is not None)
        record = current or PluginRecord(id=name, name=name, package_path=str(discovered.package_path), settings=defaults)
        if current is not None and current.package_path != str(discovered.package_path):
            record = PluginRecord(current.id, current.name, str(discovered.package_path), current.enabled, current.permissions_granted, current.settings)
        self.store.put(record)
        return _status(discovered.manifest, record, "inactive", "")

    def load(self, plugin_id: str, *, grant_permissions: bool) -> dict[str, object]:
        """Load one registered plugin after explicit capability approval.

        Args:
            plugin_id: Durable registered plugin identity.
            grant_permissions: Whether this request confirms all newly declared
                manifest permissions.

        Returns:
            Active plugin status after contributions are published.

        Raises:
            KeyError: If the plugin is unknown or its package disappeared.
            ValueError: If undeclared permissions still require confirmation.
            RuntimeError: If package code fails setup or violates tool rules.
        """
        with self._lock:
            record = self.store.get(plugin_id)
            if record is None:
                raise KeyError(plugin_id)
            manifest = self._manifest_for_record(record)
            missing = tuple(permission for permission in manifest.permissions if permission not in record.permissions_granted)
            if missing and not grant_permissions:
                raise ValueError("plugin permissions require explicit confirmation")
            updated = PluginRecord(record.id, record.name, record.package_path, True, tuple((*record.permissions_granted, *missing)), record.settings)
            self.store.put(updated)
            if manifest.name in self._loaded:
                return _status(manifest, updated, "active", "")
            loaded = self._load(manifest, updated)
            self._loaded[manifest.name] = loaded
            return _status(manifest, updated, "active", "")

    def unload(self, plugin_id: str) -> dict[str, object]:
        """Stop one loaded plugin without deleting its package or settings.

        Args:
            plugin_id: Durable plugin identity to disable.

        Returns:
            Inactive public status.

        Raises:
            KeyError: If no registered plugin has the supplied ID.
        """
        with self._lock:
            record = self.store.get(plugin_id)
            if record is None:
                raise KeyError(plugin_id)
            manifest = self._manifest_for_record(record)
            loaded = self._loaded.pop(manifest.name, None)
            if loaded is not None:
                for provider_id in loaded.provider_ids:
                    self._tool_registry.unregister(provider_id)
                if loaded.entrypoint is not None:
                    try:
                        loaded.entrypoint.teardown()
                    except Exception:
                        pass
                if loaded.module_name:
                    sys.modules.pop(loaded.module_name, None)
            updated = PluginRecord(record.id, record.name, record.package_path, False, record.permissions_granted, record.settings)
            self.store.put(updated)
            return _status(manifest, updated, "inactive", "")

    def settings(self, plugin_id: str) -> dict[str, object]:
        """Return one registered plugin's typed settings and schema.

        Args:
            plugin_id: Durable plugin identity.

        Returns:
            Public settings object including schema and values.

        Raises:
            KeyError: If the plugin is unknown or does not expose settings.
        """
        record = self.store.get(plugin_id)
        if record is None:
            raise KeyError(plugin_id)
        manifest = self._manifest_for_record(record)
        if not manifest.settings_enabled:
            raise KeyError(plugin_id)
        return {"id": record.id, "name": manifest.name, "settings": _settings_json(record.settings), "settings_schema": [_field_json(field) for field in manifest.settings_schema]}

    def replace_settings(self, plugin_id: str, values: Mapping[str, object]) -> dict[str, object]:
        """Validate and persist non-secret scalar settings for one plugin.

        Args:
            plugin_id: Durable plugin identity.
            values: JSON object sent by the settings form.

        Returns:
            Persisted public settings object.

        Raises:
            KeyError: If the plugin is unknown or settings are unsupported.
            ValueError: If keys, scalar types, or field constraints are invalid.
        """
        record = self.store.get(plugin_id)
        if record is None:
            raise KeyError(plugin_id)
        manifest = self._manifest_for_record(record)
        if not manifest.settings_enabled:
            raise KeyError(plugin_id)
        settings = _validate_settings(manifest, values)
        updated = PluginRecord(record.id, record.name, record.package_path, record.enabled, record.permissions_granted, settings)
        self.store.put(updated)
        return {"id": updated.id, "name": updated.name, "settings": _settings_json(updated.settings)}

    def static_asset(self, name: str, asset: str) -> Path | None:
        """Resolve a manifest-whitelisted static asset without traversal.

        Args:
            name: Active plugin manifest name.
            asset: Requested package-relative asset name.

        Returns:
            Resolved regular asset file, or ``None`` when unauthorized/missing.
        """
        loaded = self._loaded.get(name)
        if loaded is None or asset not in loaded.manifest.assets:
            return None
        root = Path(loaded.record.package_path).resolve()
        target = (root / asset).resolve()
        return target if target.is_file() and root in target.parents else None

    def _discovery(self, name: str) -> DiscoveredPlugin:
        """Locate one valid discovered manifest by name.

        Args:
            name: Manifest name requested by a UI discovery action.

        Returns:
            Matching discovery record.

        Raises:
            KeyError: If no current valid manifest has the name.
        """
        item = next((candidate for candidate in self.rescan() if candidate.manifest is not None and candidate.manifest.name == name), None)
        if item is None:
            raise KeyError(name)
        return item

    def _record_by_name(self, name: str) -> PluginRecord | None:
        """Find a durable record by manifest name.

        Args:
            name: Manifest name.

        Returns:
            Registered record, if any.
        """
        return next((record for record in self.store.records() if record.name == name), None)

    def _manifest_for_record(self, record: PluginRecord) -> PluginManifest:
        """Revalidate one durable package before any active operation.

        Args:
            record: Persisted record pointing at the managed package.

        Returns:
            Current validated manifest.

        Raises:
            KeyError: If the package was removed or manifest name changed.
        """
        path = Path(record.package_path).resolve()
        try:
            manifest = load_manifest(path)
        except ManifestError as exc:
            raise KeyError(record.id) from exc
        if manifest.name != record.name or not self._is_discovery_package(path):
            raise KeyError(record.id)
        return manifest

    def _is_discovery_package(self, package_path: Path) -> bool:
        """Return whether a record points at a direct child of a trusted root.

        Args:
            package_path: Resolved package directory from a durable record.

        Returns:
            ``True`` only for a direct non-symlink package inside a configured
            managed or local development discovery root.
        """
        return any(package_path.parent == root for root in self._discovery_roots)

    def _load(self, manifest: PluginManifest, record: PluginRecord) -> LoadedPlugin:
        """Execute one approved tool plugin and atomically publish providers.

        Args:
            manifest: Revalidated package declaration.
            record: Persisted approval and settings state.

        Returns:
            Loaded in-process record.

        Raises:
            RuntimeError: If entry import/setup fails or contributes invalid tools.
        """
        if manifest.kind != "tool":
            return LoadedPlugin(manifest, record)
        if manifest.entry is None:
            raise RuntimeError("tool plugin is missing an entry module")
        module_name = f"angelus_plugins_{manifest.name.replace('-', '_')}"
        entry_path = Path(record.package_path) / f"{manifest.entry}.py"
        spec = importlib.util.spec_from_file_location(module_name, entry_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("cannot create plugin module loader")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
            entrypoint = _entrypoint(module)
            runtime = PluginRuntime(manifest, record.settings, str(self.store.data_root / record.id))
            Path(runtime.state_path).mkdir(parents=True, exist_ok=True)
            entrypoint.setup(runtime)
            provider_ids = self._publish(manifest, runtime.contributions)
            return LoadedPlugin(manifest, record, module_name, entrypoint, provider_ids)
        except Exception as exc:
            sys.modules.pop(module_name, None)
            raise RuntimeError(f"plugin setup failed: {type(exc).__name__}: {exc}") from exc

    def _publish(self, manifest: PluginManifest, contributions: list[PluginToolContribution]) -> tuple[str, ...]:
        """Namespace and publish setup contributions after complete validation.

        Args:
            manifest: Owning plugin declaration.
            contributions: Providers staged by its setup call.

        Returns:
            Published global provider IDs.

        Raises:
            RuntimeError: If identifiers conflict or no declared tools are provided.
        """
        provider_ids: list[str] = []
        try:
            for index, contribution in enumerate(contributions):
                provider_id = f"plugin.{manifest.name}.{index}"
                categories = tuple(ToolCategory(f"plugin.{manifest.name}.{item.id}", item.title, item.description) for item in contribution.categories)
                category_ids = {item.id for item in contribution.categories}
                definitions = tuple(ToolDefinition(
                    f"plugin.{manifest.name}.{item.id}", f"plugin.{manifest.name}.{item.category_id}", item.title, item.description, provider_id, item.roles,
                ) for item in contribution.definitions)
                if not categories or any(item.category_id not in category_ids for item in contribution.definitions):
                    raise RuntimeError("plugin contribution has invalid categories")
                self._tool_registry.register(ToolProviderRegistration(provider_id, _PluginProvider(manifest.name, contribution.provider), categories, definitions))
                provider_ids.append(provider_id)
            return tuple(provider_ids)
        except Exception:
            for provider_id in provider_ids:
                self._tool_registry.unregister(provider_id)
            raise


class _PluginProvider:
    """Adapt a package-local provider to the host Session tool protocol."""

    def __init__(self, name: str, provider: object) -> None:
        """Retain plugin identity and its declared provider.

        Args:
            name: Owning manifest name for tool namespace validation.
            provider: Plugin-supplied provider implementing ``materialize``.
        """
        self._name = name
        self._provider = provider

    def materialize(self, session: "Session", policy: "ToolPolicy", role: str) -> list["Tool"]:
        """Create namespaced concrete Tools for one Agent.

        Args:
            session: Owning Session aggregate.
            policy: Effective Session Tool policy.
            role: Receiving Agent role.

        Returns:
            Plugin-provided concrete Tools matching the plugin namespace.

        Raises:
            RuntimeError: If the plugin returns an un-namespaced Tool.
        """
        session_id = session.execution.session_id if session.execution is not None else ""
        tools = self._provider.materialize(session_id, policy, role)
        prefix = f"plugin.{self._name}."
        if any(not tool.name.startswith(prefix) for tool in tools):
            raise RuntimeError("plugin emitted a Tool outside its namespace")
        return tools


def _entrypoint(module: ModuleType) -> PluginEntrypoint:
    """Extract a valid module-level plugin lifecycle object.

    Args:
        module: Successfully imported plugin module.

    Returns:
        Object exposing ``setup`` and optional ``teardown`` methods.

    Raises:
        RuntimeError: If the module does not provide ``angelus_plugin``.
    """
    entrypoint = getattr(module, "angelus_plugin", None)
    if entrypoint is None or not callable(getattr(entrypoint, "setup", None)):
        raise RuntimeError("plugin module must expose angelus_plugin.setup(runtime)")
    if not callable(getattr(entrypoint, "teardown", None)):
        setattr(entrypoint, "teardown", lambda: None)
    return entrypoint


def _status(manifest: PluginManifest, record: PluginRecord | None, state: str, error: str) -> dict[str, object]:
    """Build a non-secret plugin projection for browser controls.

    Args:
        manifest: Valid declaration being projected.
        record: Optional durable registration state.
        state: Current discovery/lifecycle state.
        error: User-safe lifecycle or validation error.

    Returns:
        JSON-safe status object.
    """
    return {
        "id": record.id if record is not None else "", "name": manifest.name, "display_name": manifest.display_name,
        "version": manifest.version, "kind": manifest.kind, "state": state, "error": error,
        "registered": record is not None, "enabled": record.enabled if record is not None else False,
        "settings_available": manifest.settings_enabled,
        "permissions_requested": [_permission_json(item) for item in manifest.permissions],
        "permissions_granted": [_permission_json(item) for item in record.permissions_granted] if record is not None else [],
        "themes": [_theme_json(item) for item in manifest.themes],
    }


def _permission_json(value: PluginPermission) -> dict[str, str]:
    """Serialize one permission to its public JSON shape.

    Args:
        value: Typed permission value.

    Returns:
        JSON-safe permission object.
    """
    return {"action": value.action, "scope": value.scope}


def _theme_json(value: object) -> dict[str, str]:
    """Serialize one typed theme without exposing package filesystem paths.

    Args:
        value: Typed :class:`PluginTheme` instance.

    Returns:
        JSON-safe skin metadata.
    """
    return {"id": value.id, "title": value.title, "asset": value.asset, "mode": value.mode}


def _field_json(value: object) -> dict[str, object]:
    """Serialize one typed schema field for form rendering.

    Args:
        value: Typed :class:`PluginSettingField` instance.

    Returns:
        JSON-safe restricted field metadata.
    """
    return {
        "key": value.key, "type": value.value_type, "title": value.title, "description": value.description,
        "required": value.required, "default": value.default, "enum": list(value.choices), "minimum": value.minimum,
        "maximum": value.maximum, "format": value.value_format,
    }


def _settings_json(values: tuple[PluginSettingValue, ...]) -> dict[str, PluginSettingScalar]:
    """Serialize typed settings into an API object.

    Args:
        values: Persisted typed scalar settings.

    Returns:
        Keyed JSON-safe scalar settings.
    """
    return {value.key: value.value for value in values}


def _validate_settings(manifest: PluginManifest, values: Mapping[str, object]) -> tuple[PluginSettingValue, ...]:
    """Validate a submitted object against the plugin's declared schema.

    Args:
        manifest: Plugin declaration owning the schema.
        values: Browser-submitted candidate settings.

    Returns:
        Ordered typed setting values.

    Raises:
        ValueError: If a field is unknown, missing, sensitive, or invalid.
    """
    fields = {field.key: field for field in manifest.settings_schema}
    unknown = sorted(set(values) - set(fields))
    if unknown:
        raise ValueError(f"unknown settings fields: {', '.join(unknown)}")
    result: list[PluginSettingValue] = []
    for field in manifest.settings_schema:
        if field.key not in values:
            if field.required:
                raise ValueError(f"missing required setting: {field.key}")
            continue
        value = values[field.key]
        if not _setting_type(value, field.value_type):
            raise ValueError(f"setting {field.key} has invalid type")
        if field.choices and value not in field.choices:
            raise ValueError(f"setting {field.key} is not an allowed option")
        if field.minimum is not None and isinstance(value, (int, float)) and value < field.minimum:
            raise ValueError(f"setting {field.key} is below its minimum")
        if field.maximum is not None and isinstance(value, (int, float)) and value > field.maximum:
            raise ValueError(f"setting {field.key} exceeds its maximum")
        result.append(PluginSettingValue(field.key, value))
    return tuple(result)


def _setting_type(value: object, kind: str) -> bool:
    """Check an API scalar against one schema scalar type.

    Args:
        value: Submitted candidate scalar.
        kind: Declared manifest scalar type.

    Returns:
        Whether the value exactly matches the declared type.
    """
    if kind == "string":
        return isinstance(value, str)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, (int, float)) and not isinstance(value, bool)
