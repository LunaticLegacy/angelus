"""HTTP installation for the rebuilt Angelus backend."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from ..core import AngelusCore
from .runs import router as runs_router
from .sessions import router as sessions_router
from .providers import router as providers_router
from .workspace_directory import router as workspace_directory_router
from .settings import router as settings_router
from .session_console import router as session_console_router


def include_api_routes(app: FastAPI, core: AngelusCore) -> None:
    """Install API routes and the local workbench assets on one host."""
    app.state.angelus_core = core
    frontend_root = Path(__file__).resolve().parents[2] / "frontend"

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        """Serve an uncached workbench shell during the API migration."""
        return FileResponse(
            frontend_root / "templates" / "index.html",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> Response:
        """Avoid a noisy 404 until the rebuilt workbench owns an icon asset."""
        return Response(status_code=204)

    @app.on_event("startup")
    def start_core() -> None:
        """Start the app without taking ownership of Uvicorn's SIGINT handler.

        Uvicorn receives Ctrl+C, initiates ASGI shutdown, and then this app's
        shutdown hook calls ``core.shutdown`` to force-stop and persist live
        attempts.  Replacing Uvicorn's handler here would consume Ctrl+C and
        leave the server running.
        """

    @app.on_event("shutdown")
    def stop_core() -> None:
        """Force-stop live attempts before the ASGI host exits."""
        core.shutdown()

    app.include_router(runs_router)
    app.include_router(sessions_router)
    app.include_router(providers_router)
    app.include_router(workspace_directory_router)
    app.include_router(settings_router)
    app.include_router(session_console_router)
    app.mount("/static", StaticFiles(directory=frontend_root / "static"), name="static")


__all__ = ["include_api_routes"]
