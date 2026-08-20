"""Plugin directory resolution for the Angelus plugin system.

Plugins use one persistent application-level directory:
``<app_data>/plugins``, next to (not inside) ``<app_data>/workspace``.  This
keeps installed extensions independent from any one conversation workspace and
works with packaged desktop builds, whose sidecar itself is ephemeral.

The ``ANGELUS_PLUGIN_DIR`` environment variable can override that directory
for managed deployments.  The legacy ``workspace_plugin_dir`` and
``global_plugin_dir`` names remain aliases so older callers keep resolving the
same single directory.
"""

from __future__ import annotations

import os
from pathlib import Path

from . import storage

PLUGIN_DIR_ENV = "ANGELUS_PLUGIN_DIR"


def _default_app_data_root(state_root: Path | None = None) -> Path:
    """Return the app-data root that owns the given workspace root.

    The desktop release pins ``LLMFETCHER_STATE_DIR`` to ``<app_data>/workspace``,
    so the app-data root is exactly the parent of the state root.  Source
    checkouts keep the same shape: ``<project>/workspace`` is owned by the
    project root, placing global plugins at ``<project>/plugins``.

    Args:
        state_root: Optional workspace root; defaults to ``storage.STATE_ROOT``.
    """
    root = state_root if state_root is not None else storage.STATE_ROOT
    return Path(root).resolve().parent


def plugin_dir(state_root: Path | None = None) -> Path:
    """Return the app-level plugin directory, honoring ``ANGELUS_PLUGIN_DIR``.

    When ``ANGELUS_PLUGIN_DIR`` is set it takes precedence over the default
    sibling of the state-root ``workspace`` directory.
    """
    override = os.environ.get(PLUGIN_DIR_ENV)
    if override:
        return Path(override).resolve()
    return _default_app_data_root(state_root) / "plugins"


def workspace_plugin_dir(state_root: Path | None = None) -> Path:
    """Compatibility alias for :func:`plugin_dir`.

    Plugins intentionally no longer live under ``workspace/``.
    """
    return plugin_dir(state_root)


def global_plugin_dir(state_root: Path | None = None) -> Path:
    """Compatibility alias for :func:`plugin_dir`."""
    return plugin_dir(state_root)


def plugin_dirs(state_root: Path | None = None) -> tuple[Path, ...]:
    """Return the sole persistent plugin directory as a one-item tuple."""
    return (plugin_dir(state_root),)


def ensure_plugin_dirs(state_root: Path | None = None) -> Path:
    """Create and return the persistent application-level plugin directory."""
    root = plugin_dir(state_root)
    root.mkdir(parents=True, exist_ok=True)
    return root


__all__ = [
    "PLUGIN_DIR_ENV",
    "_default_app_data_root",
    "plugin_dir",
    "workspace_plugin_dir",
    "global_plugin_dir",
    "plugin_dirs",
    "ensure_plugin_dirs",
]
