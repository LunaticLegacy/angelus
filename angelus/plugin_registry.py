"""plugins.json v1 registry with atomic persistence.

The registry stores installed-plugin metadata (see ``docs/plugin-api.md``
appendix B / ``docs/plugin-swarm-execution.md`` appendix B) at
``<STATE_ROOT>/plugins.json`` next to ``sessions.json``/``connectors.json``.
Writes follow the connector store's atomic pattern — write to a ``.tmp``
sibling then ``Path.replace()`` — so readers never observe a half-written
file and no ``.tmp`` residue remains (see ``angelus/connectors.py``
``_write_connectors``).  A module-level lock serializes concurrent writers.
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from . import storage

REGISTRY_VERSION = 1
REGISTRY_INDEX = storage.STATE_ROOT / "plugins.json"
REGISTRY_LOCK = threading.Lock()

ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
SOURCES = ("local", "git", "zip")


def _registry_path() -> Path:
    """Return the registry file location (overridable in tests)."""
    return REGISTRY_INDEX


def empty_registry() -> dict[str, Any]:
    """Return the canonical empty registry document."""
    return {"version": REGISTRY_VERSION, "plugins": []}


def _read_registry() -> dict[str, Any]:
    """Read the registry; a missing or corrupt file yields an empty registry.

    Mirrors ``angelus/connectors.py::_read_connector_records``: storage
    problems must never crash the caller, so malformed files degrade to an
    empty registry rather than raising.
    """
    registry_path = _registry_path()
    if not registry_path.exists():
        return empty_registry()
    try:
        data = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_registry()
    if not isinstance(data, dict) or data.get("version") != REGISTRY_VERSION:
        return empty_registry()
    plugins = data.get("plugins")
    if not isinstance(plugins, list):
        return empty_registry()
    return {"version": REGISTRY_VERSION, "plugins": plugins}


def _write_registry(data: dict[str, Any]) -> None:
    """Atomically persist the registry (``.tmp`` + ``replace()``, mode 0600).

    Side Effects:
        Creates or replaces ``REGISTRY_INDEX``; the temporary sibling is
        always consumed by the atomic replacement.
    """
    registry_path = _registry_path()
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = registry_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        temporary.chmod(0o600)
    except OSError:
        pass
    temporary.replace(registry_path)


def list_plugins() -> list[dict[str, Any]]:
    """Return the installed plugin records (copy-safe)."""
    with REGISTRY_LOCK:
        return [dict(record) for record in _read_registry()["plugins"]]


def get_plugin(plugin_id: str) -> dict[str, Any] | None:
    """Return one plugin record by id, or ``None`` when absent."""
    with REGISTRY_LOCK:
        for record in _read_registry()["plugins"]:
            if record.get("id") == plugin_id:
                return dict(record)
    return None


def add_plugin(record: dict[str, Any]) -> dict[str, Any]:
    """Insert a plugin record (replacing an existing record with the same id).

    A 32-hex id is generated when omitted; ``installed_at``/``last_modified``
    default to the current time and ``api_version`` defaults to ``"1"``.
    """
    entry = dict(record)
    if not entry.get("id"):
        entry["id"] = uuid.uuid4().hex
    entry.setdefault("api_version", "1")
    entry.setdefault("enabled", False)
    entry.setdefault("permissions_granted", [])
    now = time.time()
    entry.setdefault("installed_at", now)
    entry.setdefault("last_modified", now)
    with REGISTRY_LOCK:
        data = _read_registry()
        data["plugins"] = [item for item in data["plugins"] if item.get("id") != entry["id"]]
        data["plugins"].append(entry)
        _write_registry(data)
    return dict(entry)


def update_plugin(plugin_id: str, changes: dict[str, Any]) -> dict[str, Any] | None:
    """Apply field updates to a plugin record; returns the updated record."""
    with REGISTRY_LOCK:
        data = _read_registry()
        for record in data["plugins"]:
            if record.get("id") != plugin_id:
                continue
            record.update(changes)
            record["last_modified"] = time.time()
            _write_registry(data)
            return dict(record)
    return None


def remove_plugin(plugin_id: str) -> bool:
    """Remove a plugin record; returns ``True`` when something was removed."""
    with REGISTRY_LOCK:
        data = _read_registry()
        before = len(data["plugins"])
        data["plugins"] = [item for item in data["plugins"] if item.get("id") != plugin_id]
        if len(data["plugins"]) == before:
            return False
        _write_registry(data)
        return True


def set_enabled(
    plugin_id: str,
    enabled: bool,
    *,
    permissions: list[str] | None = None,
) -> dict[str, Any] | None:
    """Flip the ``enabled`` flag and persist it.

    Args:
        plugin_id: The 32-hex registry id.
        enabled: Desired state.
        permissions: ``"action:scope"`` strings granted at install time.  On
            the **first enable** of a plugin with no recorded grants these are
            written into ``permissions_granted``; later grants go through
            :func:`grant_permissions` so existing grants are never silently
            overwritten.
    """
    with REGISTRY_LOCK:
        data = _read_registry()
        for record in data["plugins"]:
            if record.get("id") != plugin_id:
                continue
            record["enabled"] = bool(enabled)
            if enabled and permissions is not None and not record.get("permissions_granted"):
                record["permissions_granted"] = _merge_unique([], permissions)
            record["last_modified"] = time.time()
            _write_registry(data)
            return dict(record)
    return None


def grant_permissions(plugin_id: str, permissions: list[str]) -> dict[str, Any] | None:
    """Merge additional ``"action:scope"`` grants into a plugin record."""
    with REGISTRY_LOCK:
        data = _read_registry()
        for record in data["plugins"]:
            if record.get("id") != plugin_id:
                continue
            granted = record.get("permissions_granted") or []
            record["permissions_granted"] = _merge_unique(granted, permissions)
            record["last_modified"] = time.time()
            _write_registry(data)
            return dict(record)
    return None


def _merge_unique(existing: list[str], additions: list[str]) -> list[str]:
    """Concatenate grant lists preserving order and uniqueness."""
    merged = list(existing)
    for item in additions:
        if item not in merged:
            merged.append(item)
    return merged


__all__ = [
    "REGISTRY_VERSION",
    "REGISTRY_INDEX",
    "REGISTRY_LOCK",
    "ID_PATTERN",
    "NAME_PATTERN",
    "VERSION_PATTERN",
    "SOURCES",
    "empty_registry",
    "list_plugins",
    "get_plugin",
    "add_plugin",
    "update_plugin",
    "remove_plugin",
    "set_enabled",
    "grant_permissions",
]
