"""Handwritten manifest v1 validation for Angelus plugins.

The validator intentionally avoids a ``jsonschema`` runtime dependency (see
``docs/plugin-swarm-execution.md`` §6 dependency constraint): it checks the
manifest v1 contract from ``docs/plugin-api.md`` appendix A field by field and
returns *field-level structured errors*::

    [{"field": "permissions[0].action", "error": "..."}, ...]

``validate_manifest`` returns an empty list for a valid manifest, so callers
can treat ``not errors`` as "passed".
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

MANIFEST_FILENAME = "manifest.json"
API_VERSION = "1"

NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
CHECKSUM_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
DEPENDENCY_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")

ENTRY_TYPES = ("module", "function", "package")
PERMISSION_ACTIONS = (
    "shell",
    "network",
    "fs.read",
    "fs.write",
    "env",
    "http",
    "connector.read",
    "connector.write",
    "event.subscribe",
)
FRONTEND_KEYS = ("assets", "panels", "commands", "settings")
MAX_LENGTHS = {
    "display_name": 120,
    "description": 2000,
    "author": 200,
    "license": 200,
    "entry": 512,
    "scope": 512,
    "tool": 128,
}
TOP_LEVEL_KEYS = frozenset(
    (
        "name",
        "display_name",
        "version",
        "api_version",
        "description",
        "author",
        "license",
        "entry",
        "entry_type",
        "tools",
        "permissions",
        "frontend",
        "dependencies",
        "checksum",
    )
)


def _add(errors: list[dict[str, str]], field: str, message: str) -> None:
    errors.append({"field": field, "error": message})


def _check_string(
    errors: list[dict[str, str]],
    data: dict[str, Any],
    field: str,
    *,
    required: bool = False,
    min_len: int | None = None,
    max_len: int | None = None,
    pattern: re.Pattern[str] | None = None,
    label: str | None = None,
) -> Any:
    """Validate an optional/required string field, returning its value."""
    value = data.get(field)
    if value is None:
        if required:
            _add(errors, field, f"missing required field '{field}'")
        return None
    if not isinstance(value, str):
        _add(errors, field, f"'{field}' must be a string")
        return None
    if min_len is not None and len(value) < min_len:
        _add(errors, field, f"'{field}' must be at least {min_len} characters")
        return value
    if max_len is not None and len(value) > max_len:
        _add(errors, field, f"'{field}' must be at most {max_len} characters")
    if pattern is not None and not pattern.fullmatch(value):
        _add(errors, field, f"'{field}' does not match {label or pattern.pattern}")
    return value


def _validate_string_array(
    errors: list[dict[str, str]],
    data: dict[str, Any],
    field: str,
    *,
    min_len: int = 1,
    max_len: int = 128,
    unique: bool = True,
) -> None:
    """Validate an array of bounded, unique strings (tools / frontend lists)."""
    value = data.get(field)
    if value is None:
        return
    if not isinstance(value, list):
        _add(errors, field, f"'{field}' must be an array")
        return
    seen: set[str] = set()
    for index, item in enumerate(value):
        item_field = f"{field}[{index}]"
        if not isinstance(item, str):
            _add(errors, item_field, "array item must be a string")
            continue
        if len(item) < min_len or len(item) > max_len:
            _add(errors, item_field, f"array item must be {min_len}..{max_len} characters")
        if unique:
            if item in seen:
                _add(errors, item_field, "duplicate array item")
            seen.add(item)


def _validate_entry_type(errors: list[dict[str, str]], data: dict[str, Any]) -> None:
    value = data.get("entry_type")
    if value is None:
        return
    if not isinstance(value, str) or value not in ENTRY_TYPES:
        _add(errors, "entry_type", f"'entry_type' must be one of {', '.join(ENTRY_TYPES)}")


def _validate_permissions(errors: list[dict[str, str]], data: dict[str, Any]) -> None:
    """Validate the permissions array (permission objects with action+scope)."""
    value = data.get("permissions")
    if value is None:
        return
    if not isinstance(value, list):
        _add(errors, "permissions", "'permissions' must be an array")
        return
    seen: set[str] = set()
    for index, item in enumerate(value):
        field = f"permissions[{index}]"
        if not isinstance(item, dict):
            _add(errors, field, "permission must be an object")
            continue
        for key in item:
            if key not in ("action", "scope"):
                _add(errors, f"{field}.{key}", f"unknown field '{key}' in permission")
        action = item.get("action")
        if "action" not in item:
            _add(errors, f"{field}.action", "missing required field 'action'")
        elif not isinstance(action, str) or action not in PERMISSION_ACTIONS:
            _add(
                errors,
                f"{field}.action",
                f"invalid permission action {action!r}; allowed: {', '.join(PERMISSION_ACTIONS)}",
            )
        scope = item.get("scope")
        if "scope" not in item:
            _add(errors, f"{field}.scope", "missing required field 'scope'")
        elif not isinstance(scope, str) or not (1 <= len(scope) <= MAX_LENGTHS["scope"]):
            _add(errors, f"{field}.scope", "'scope' must be a string of 1..512 characters")
        signature = f"{action}:{scope}"
        if signature in seen:
            _add(errors, field, "duplicate permission")
        seen.add(signature)


def _validate_frontend(errors: list[dict[str, str]], data: dict[str, Any]) -> None:
    value = data.get("frontend")
    if value is None:
        return
    if not isinstance(value, dict):
        _add(errors, "frontend", "'frontend' must be an object")
        return
    for key in value:
        if key not in FRONTEND_KEYS:
            _add(errors, f"frontend.{key}", f"unknown field '{key}' in frontend")
    for key in ("assets", "panels", "commands"):
        _validate_string_array(errors, value, f"frontend.{key}")
    if "settings" in value and not isinstance(value["settings"], bool):
        _add(errors, "frontend.settings", "'frontend.settings' must be a boolean")


def _validate_dependencies(errors: list[dict[str, str]], data: dict[str, Any]) -> None:
    value = data.get("dependencies")
    if value is None:
        return
    if not isinstance(value, dict):
        _add(errors, "dependencies", "'dependencies' must be an object")
        return
    for name, version in value.items():
        if not DEPENDENCY_NAME_PATTERN.fullmatch(name):
            _add(errors, f"dependencies.{name}", f"invalid dependency name {name!r}")
        if not isinstance(version, str) or not VERSION_PATTERN.fullmatch(version):
            _add(errors, f"dependencies.{name}", "dependency version must be a semver string like '1.2.3'")


def validate_manifest(data: Any) -> list[dict[str, str]]:
    """Validate a parsed manifest against the v1 contract.

    Args:
        data: The decoded ``manifest.json`` content.

    Returns:
        A list of ``{"field": ..., "error": ...}`` dictionaries; empty means
        the manifest is valid.
    """
    if not isinstance(data, dict):
        return [{"field": "$", "error": "manifest must be a JSON object"}]

    errors: list[dict[str, str]] = []

    for key in data:
        if key not in TOP_LEVEL_KEYS:
            _add(errors, key, f"unknown field '{key}'")

    _check_string(errors, data, "name", required=True, pattern=NAME_PATTERN, label="^[a-z][a-z0-9_-]{1,63}$")
    _check_string(errors, data, "version", required=True, pattern=VERSION_PATTERN, label="^\\d+\\.\\d+\\.\\d+$")
    api_version = _check_string(errors, data, "api_version", required=True)
    if api_version is not None and api_version != API_VERSION:
        _add(errors, "api_version", f"api_version must be {API_VERSION!r}")
    _check_string(errors, data, "entry", required=True, min_len=1, max_len=MAX_LENGTHS["entry"])

    for field in ("display_name", "description", "author", "license"):
        _check_string(errors, data, field, max_len=MAX_LENGTHS[field])
    _check_string(errors, data, "checksum", pattern=CHECKSUM_PATTERN, label="^sha256:[0-9a-f]{64}$")

    _validate_entry_type(errors, data)
    _validate_string_array(errors, data, "tools", max_len=MAX_LENGTHS["tool"])
    _validate_permissions(errors, data)
    _validate_frontend(errors, data)
    _validate_dependencies(errors, data)

    return errors


def load_manifest(path: Path) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    """Read, parse and validate a ``manifest.json`` file.

    Returns:
        ``(manifest, errors)`` — ``manifest`` is ``None`` when the file is
        missing, unparsable or invalid; otherwise the validated manifest.
    """
    manifest_path = Path(path)
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, [{"field": "$", "error": f"manifest file not found: {manifest_path}"}]
    except json.JSONDecodeError as exc:
        return None, [{"field": "$", "error": f"invalid JSON in manifest: {exc}"}]
    errors = validate_manifest(data)
    if errors:
        return None, errors
    return data, []


__all__ = [
    "MANIFEST_FILENAME",
    "API_VERSION",
    "NAME_PATTERN",
    "VERSION_PATTERN",
    "CHECKSUM_PATTERN",
    "ENTRY_TYPES",
    "PERMISSION_ACTIONS",
    "validate_manifest",
    "load_manifest",
]
