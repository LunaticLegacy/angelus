"""Local browser UI for configuring and observing a single ``Agent`` run.

The monolithic control plane was split into focused modules (``storage``,
``connectors``, ``history``, ``runtime``, ``markdown`` and ``api/``). This file
remains the public FastAPI assembly point and backward-compatible re-export
surface: ``uvicorn angelus.webapp:app``, the CLI, and the regression suite all
keep working through this module.
"""

from __future__ import annotations

import logging
import threading

from typing import Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .classes import (
    ActiveRun,
    BrowserRunControl,
    BrowserSession,
    ConnectorRequest,
    RunConfig,
    RunRequest,
    SteerRequest,
    TaskPlanRequest,
    TaskStatusRequest,
    WorkspaceDeleteRequest,
    WorkspaceRequest,
)
from .connectors import *  # noqa: F401,F403
from .history import *  # noqa: F401,F403
from .markdown import *  # noqa: F401,F403
from .runtime import *  # noqa: F401,F403
from .storage import *  # noqa: F401,F403
from .api import include_api_routes
from .api.connectors import *  # noqa: F401,F403
from .api.runs import *  # noqa: F401,F403
from .api.sessions import *  # noqa: F401,F403

# Preserve the historical behaviour of migrating legacy state at import time.
migrate_legacy_state()

app = FastAPI(title="llmfetcher Console", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=FRONTEND_ROOT / "static"), name="static")
include_api_routes(app)


def _assemble_plugins(app: FastAPI) -> Any:
    """Wire the plugin system (swarm S2-S10) onto the console app.

    A single :class:`PluginManager` is created at import time, bound to the
    same ``STATE_ROOT`` that drives ``plugins.json`` and the two-tier plugin
    directories.  ``load_all()`` is isolated per plugin (a broken plugin is
    marked BLOCKED and never crashes the console).  The manager is also
    exposed on ``app.state`` so ``/api/providers`` can merge plugin-registered
    connector kinds.
    """
    from . import plugin_registry
    from .plugins.bridge_routes import include_plugin_routes
    from .plugins.manager import PluginManager

    manager = PluginManager(state_root=STATE_ROOT, registry=plugin_registry)
    try:
        manager.load_all()
    except Exception as exc:  # defensive: load_all isolates per plugin
        logging.getLogger("angelus.webapp").warning(
            "plugin load_all failed: %s", exc
        )
    include_plugin_routes(app, manager, registry=plugin_registry)
    app.state.plugin_manager = manager
    return manager


plugin_manager = _assemble_plugins(app)


def main() -> None:
    """Run the local console with ``llmfetcher-web``."""
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8765)
