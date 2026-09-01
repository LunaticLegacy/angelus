"""Atomic persistence for registered Angelus plugin packages."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
import threading

from ..settings_module.json_store import read_json, write_json
from .models import PluginPermission, PluginRecord, PluginSettingScalar, PluginSettingValue


class PluginStore:
    """Own global plugin registration state below the Angelus state root."""

    def __init__(self, state_root: Path) -> None:
        """Create one store with a managed package directory.

        Args:
            state_root: Angelus-owned durable state root.
        """
        self.package_root = state_root / "plugins" / "packages"
        self.data_root = state_root / "plugins" / "data"
        self._path = state_root / "plugins" / "registry.json"
        self._lock = threading.RLock()

    def records(self) -> tuple[PluginRecord, ...]:
        """Return every persisted record in stable document order.

        Returns:
            Immutable plugin-record snapshot.
        """
        with self._lock:
            return self._read()

    def get(self, plugin_id: str) -> PluginRecord | None:
        """Find one registered plugin by stable ID.

        Args:
            plugin_id: Persisted plugin identity.

        Returns:
            Matching record, or ``None`` when it is not registered.
        """
        return next((record for record in self.records() if record.id == plugin_id), None)

    def put(self, record: PluginRecord) -> PluginRecord:
        """Atomically create or replace one plugin record.

        Args:
            record: Fully validated record to persist.

        Returns:
            Stored record.
        """
        with self._lock:
            records = [item for item in self._read() if item.id != record.id]
            records.append(record)
            self._write(tuple(records))
        return record

    def _read(self) -> tuple[PluginRecord, ...]:
        """Decode the registered plugin document without executing packages.

        Returns:
            Valid durable records, or an empty tuple for absent state.

        Raises:
            ValueError: If an existing registry is malformed.
        """
        raw = read_json(self._path, {"schema_version": 1, "plugins": []})
        if not isinstance(raw, Mapping) or raw.get("schema_version") != 1:
            raise ValueError("invalid plugin registry")
        items = raw.get("plugins")
        if not isinstance(items, Sequence) or isinstance(items, str):
            raise ValueError("invalid plugin registry plugins")
        return tuple(_record(item) for item in items)

    def _write(self, records: tuple[PluginRecord, ...]) -> None:
        """Publish one complete plugin registry generation atomically.

        Args:
            records: Complete replacement record sequence.

        Returns:
            None.
        """
        write_json(self._path, {"schema_version": 1, "plugins": [_record_json(record) for record in records]})


def _record(raw: object) -> PluginRecord:
    """Decode a record stored by :class:`PluginStore`.

    Args:
        raw: One raw registry list item.

    Returns:
        Typed persisted record.

    Raises:
        ValueError: If the persisted record is malformed.
    """
    if not isinstance(raw, Mapping):
        raise ValueError("invalid plugin record")
    fields = ("id", "name", "package_path")
    if any(not isinstance(raw.get(field), str) or not raw.get(field) for field in fields):
        raise ValueError("invalid plugin record identity")
    enabled = raw.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ValueError("invalid plugin enabled state")
    return PluginRecord(
        id=str(raw["id"]), name=str(raw["name"]), package_path=str(raw["package_path"]), enabled=enabled,
        permissions_granted=_permissions(raw.get("permissions_granted", [])), settings=_settings(raw.get("settings", [])),
    )


def _permissions(raw: object) -> tuple[PluginPermission, ...]:
    """Decode persisted approved plugin permissions.

    Args:
        raw: Raw JSON permissions list.

    Returns:
        Typed immutable permission tuple.

    Raises:
        ValueError: If an item is malformed.
    """
    if not isinstance(raw, Sequence) or isinstance(raw, str):
        raise ValueError("invalid granted plugin permissions")
    values: list[PluginPermission] = []
    for item in raw:
        if not isinstance(item, Mapping) or not isinstance(item.get("action"), str) or not isinstance(item.get("scope"), str):
            raise ValueError("invalid granted plugin permission")
        values.append(PluginPermission(str(item["action"]), str(item["scope"])))
    return tuple(values)


def _settings(raw: object) -> tuple[PluginSettingValue, ...]:
    """Decode bounded scalar settings.

    Args:
        raw: Raw JSON settings list.

    Returns:
        Typed persisted scalar values.

    Raises:
        ValueError: If a value is missing, duplicated, or non-scalar.
    """
    if not isinstance(raw, Sequence) or isinstance(raw, str):
        raise ValueError("invalid plugin settings")
    values: list[PluginSettingValue] = []
    for item in raw:
        if not isinstance(item, Mapping) or not isinstance(item.get("key"), str) or not _scalar(item.get("value")):
            raise ValueError("invalid plugin setting")
        key = str(item["key"])
        if any(value.key == key for value in values):
            raise ValueError("duplicate plugin setting")
        values.append(PluginSettingValue(key, item["value"]))
    return tuple(values)


def _scalar(value: object) -> bool:
    """Return whether a value is a supported persisted scalar.

    Args:
        value: Candidate JSON value.

    Returns:
        ``True`` for string, number, or boolean scalar values.
    """
    return isinstance(value, (str, int, float, bool)) and not (isinstance(value, float) and not value.is_finite())


def _record_json(record: PluginRecord) -> dict[str, object]:
    """Project a typed record into JSON-safe primitive containers.

    Args:
        record: Typed durable plugin record.

    Returns:
        JSON-safe record object for atomic persistence.
    """
    return {
        "id": record.id, "name": record.name, "package_path": record.package_path, "enabled": record.enabled,
        "permissions_granted": [{"action": item.action, "scope": item.scope} for item in record.permissions_granted],
        "settings": [{"key": item.key, "value": item.value} for item in record.settings],
    }
