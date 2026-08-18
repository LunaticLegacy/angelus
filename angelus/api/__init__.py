"""FastAPI routers for the Angelus browser control plane."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import FileResponse

from ..storage import FRONTEND_ROOT
from .connectors import router as connectors_router
from .runs import router as runs_router
from .sessions import router as sessions_router

__all__ = ["include_api_routes"]


def include_api_routes(app: FastAPI) -> None:
    """Attach every browser API router plus the static console index."""
    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        """Serve the standalone chat console."""
        return FileResponse(FRONTEND_ROOT / "templates" / "index.html")

    app.include_router(connectors_router)
    app.include_router(runs_router)
    app.include_router(sessions_router)
