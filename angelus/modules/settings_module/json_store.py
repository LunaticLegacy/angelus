"""Small atomic JSON primitive shared by Angelus settings stores."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def read_json(path: Path, default: object) -> object:
    """Read one JSON document, returning ``default`` only when it is absent.

    Args:
        path: Expected document location.
        default: Object returned for a missing file; it is not persisted.

    Raises:
        ValueError: If an existing document cannot be decoded.
    """
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid settings document: {path}") from exc


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
