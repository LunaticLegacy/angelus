"""Small atomic JSON primitives shared by Angelus persistence stores.

Documents are written as JSON objects and read back through a typed decoder.
The helpers below are the only place allowed to turn an untrusted ``object``
from ``json.loads`` into a value a dataclass field can accept, so every store
validates the same way.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Collection, Mapping
from pathlib import Path


class JsonSchemaError(ValueError):
    """A decoded JSON document does not match the schema for its version."""


def require_mapping(value: object, where: str) -> dict[str, object]:
    """Return ``value`` as a JSON object.

    Args:
        value: Decoded value from an untrusted document.
        where: Dotted path used in the failure message.

    Raises:
        JsonSchemaError: If the value is not a JSON object.
    """
    if not isinstance(value, dict):
        raise JsonSchemaError(f"{where} must be a JSON object")
    return value


def reject_unknown_keys(
    value: Mapping[str, object], allowed: Collection[str], where: str
) -> None:
    """Reject fields the writer never emits for this schema version.

    Raises:
        JsonSchemaError: If the object carries any field outside ``allowed``.
    """
    unknown = sorted(set(value) - set(allowed))
    if unknown:
        raise JsonSchemaError(f"{where} has unknown fields: {', '.join(unknown)}")


def require_string(value: object, where: str) -> str:
    """Return ``value`` as a string.

    Raises:
        JsonSchemaError: If the value is not a string.
    """
    if not isinstance(value, str):
        raise JsonSchemaError(f"{where} must be a string")
    return value


def optional_string(
    value: Mapping[str, object], key: str, default: str, where: str
) -> str:
    """Return one optional string field, falling back to ``default``."""
    if key not in value:
        return default
    return require_string(value[key], f"{where}.{key}")


def require_int(value: object, where: str) -> int:
    """Return ``value`` as an integer, rejecting booleans.

    Raises:
        JsonSchemaError: If the value is not an integer.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise JsonSchemaError(f"{where} must be an integer")
    return value


def require_number(value: object, where: str) -> float:
    """Return ``value`` as a float, rejecting booleans and strings.

    Raises:
        JsonSchemaError: If the value is not a JSON number.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise JsonSchemaError(f"{where} must be a number")
    return float(value)


def require_list(value: object, where: str) -> list[object]:
    """Return ``value`` as a JSON array.

    Raises:
        JsonSchemaError: If the value is not an array.
    """
    if not isinstance(value, list):
        raise JsonSchemaError(f"{where} must be a JSON array")
    return value


def string_list(value: object, where: str) -> list[str]:
    """Return an array whose every element is a string."""
    return [
        require_string(item, f"{where}[{index}]")
        for index, item in enumerate(require_list(value, where))
    ]


def string_map(value: object, where: str) -> dict[str, str]:
    """Return an object whose every value is a string."""
    raw = require_mapping(value, where)
    return {
        key: require_string(item, f"{where}.{key}") for key, item in raw.items()
    }


def string_list_map(value: object, where: str) -> dict[str, list[str]]:
    """Return an object mapping string keys to arrays of strings."""
    raw = require_mapping(value, where)
    return {
        key: string_list(item, f"{where}.{key}") for key, item in raw.items()
    }


def read_json(path: Path, default: object) -> object:
    """Read one JSON document, returning ``default`` only when it is absent.

    Args:
        path: Expected document location.
        default: Object returned for a missing file; it is not persisted.

    Raises:
        ValueError: If an existing document cannot be decoded.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid settings document: {path}") from exc
    except OSError as exc:
        raise ValueError(f"cannot read settings document: {path}") from exc


def write_json(path: Path, value: object) -> None:
    """Atomically replace one JSON document after flushing file and directory.

    A sibling temporary file is fsynced then renamed into place.  A failure
    removes only that temporary file and leaves the prior committed document.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(value, file, ensure_ascii=False, indent=2, sort_keys=True)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
        if os.name == "posix":
            # Directory fsync is a POSIX durability idiom; os.open() on a
            # directory raises PermissionError on Windows, after the content
            # has already been committed by os.replace above.
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
