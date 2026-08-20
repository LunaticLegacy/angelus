"""Install bundled starter plugins into the persistent application data area.

The desktop sidecar is packaged as a one-file executable, so files shipped
inside it are extracted to a temporary directory for each launch.  Starter
plugins must therefore be copied once into the persistent directory resolved
by :mod:`angelus.plugin_paths`; they are discovered afterwards but are never
registered, granted permissions, or executed automatically.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from .plugin_paths import plugin_dir

BUNDLED_PLUGIN_ROOT_ENV = "ANGELUS_BUNDLED_PLUGIN_ROOT"


def install_bundled_plugins(state_root: Path | None = None) -> list[str]:
    """Copy valid bundled plugin folders on first run without overwriting users.

    Returns the names copied during this invocation.  A missing bundle is a
    normal source-development case and deliberately produces an empty list.
    """
    configured = os.environ.get(BUNDLED_PLUGIN_ROOT_ENV)
    if not configured:
        return []
    source_root = Path(configured)
    if not source_root.is_dir():
        return []

    destination_root = plugin_dir(state_root)
    destination_root.mkdir(parents=True, exist_ok=True)
    installed: list[str] = []
    for source in sorted(source_root.iterdir()):
        if not source.is_dir() or not (source / "manifest.json").is_file():
            continue
        destination = destination_root / source.name
        if destination.exists():
            continue
        try:
            shutil.copytree(
                source,
                destination,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
        except FileExistsError:
            # A second local process completed the same first-run copy.
            continue
        installed.append(source.name)
    return installed


__all__ = ["BUNDLED_PLUGIN_ROOT_ENV", "install_bundled_plugins"]
