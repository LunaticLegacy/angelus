"""Plugin directory resolution for the Angelus plugin system.

Plugins live in two tiers (decision D2 in ``docs/decisions.md``):

* session tier: ``<workspace>/plugins`` — ``angelus.storage.STATE_ROOT``
  (``WORKSPACE_ROOT``), tied to the active workbench workspace;
* global tier:  ``<app_data>/plugins`` — the app-data root that owns the
  workspace root (the workspace's parent, mirroring the desktop build's
  ``<app_data>/workspace`` layout).

The ``ANGELUS_PLUGIN_DIR`` environment variable overrides the global tier for
deployments that want plugins in a custom location.  The session tier is
never overridden.
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


def workspace_plugin_dir(state_root: Path | None = None) -> Path:
    """Return the session-scoped plugin directory (``<workspace>/plugins``)."""
    root = state_root if state_root is not None else storage.STATE_ROOT
    return Path(root).resolve() / "plugins"


def global_plugin_dir(state_root: Path | None = None) -> Path:
    """Return the global plugin directory, honoring ``ANGELUS_PLUGIN_DIR``.

    When ``ANGELUS_PLUGIN_DIR`` is set it takes precedence over the default
    ``<app_data>/plugins`` location (decision D2).
    """
    override = os.environ.get(PLUGIN_DIR_ENV)
    if override:
        return Path(override).resolve()
    return _default_app_data_root(state_root) / "plugins"


def plugin_dirs(state_root: Path | None = None) -> tuple[Path, Path]:
    """Return ``(workspace_plugins, global_plugins)`` in discovery order.

    Workspace plugins shadow global plugins with the same name during
    discovery (session tier wins).
    """
    return (workspace_plugin_dir(state_root), global_plugin_dir(state_root))


def ensure_plugin_dirs(state_root: Path | None = None) -> tuple[Path, Path]:
    """Create both plugin tiers and return them as ``(workspace, global)``."""
    workspace, global_plugins = plugin_dirs(state_root)
    workspace.mkdir(parents=True, exist_ok=True)
    global_plugins.mkdir(parents=True, exist_ok=True)
    return workspace, global_plugins


__all__ = [
    "PLUGIN_DIR_ENV",
    "_default_app_data_root",
    "workspace_plugin_dir",
    "global_plugin_dir",
    "plugin_dirs",
    "ensure_plugin_dirs",
]
