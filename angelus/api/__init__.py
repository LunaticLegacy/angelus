"""HTTP installation for the rebuilt Angelus backend."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from ..core import AngelusCore
from .error_reporting import install_error_reporting
from .runs import router as runs_router
from .sessions import router as sessions_router
from .providers import router as providers_router
from .workspace_directory import router as workspace_directory_router
from .settings import router as settings_router
from .session_console import router as session_console_router
from .plugins import router as plugins_router
from .external_agent_hub import router as external_agent_hub_router
from .mcp import router as mcp_router
from .attachments import router as attachments_router
from .memory import router as memory_router
from .compact import router as compact_router
from .notes import router as notes_router


def include_api_routes(app: FastAPI, core: AngelusCore) -> None:
    """Install API routes and the local workbench assets on one host."""
    app.state.angelus_core = core
    install_error_reporting(app, core.state_root)
    frontend_root = Path(__file__).resolve().parents[2] / "frontend"
    # A built React bundle wins when the host ships one.  A host that only
    # carries the template workbench (the library checkout) is served from
    # ``templates/`` with ``static/`` mounted beside it instead of failing to
    # mount a directory that was never built.
    frontend_dist = frontend_root / "dist"
    templates_dir = frontend_root / "templates"
    static_dir = frontend_root / "static"
    has_dist = (frontend_dist / "index.html").is_file()
    has_templates = (templates_dir / "index.html").is_file()

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        """Serve the built workbench shell, or the template workbench.

        Raises:
            HTTPException: When this host ships neither frontend.
        """
        if has_dist:
            return FileResponse(
                frontend_dist / "index.html",
                headers={"Cache-Control": "no-store"},
            )
        if has_templates:
            return FileResponse(
                templates_dir / "index.html",
                headers={"Cache-Control": "no-store"},
            )
        raise HTTPException(status_code=404, detail="frontend is not installed")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> FileResponse:
        """Serve the Angelus mark to clients that request the default icon URL.

        Raises:
            HTTPException: When this host ships no frontend.
        """
        if has_dist and (frontend_dist / "logo.svg").is_file():
            return FileResponse(frontend_dist / "logo.svg", media_type="image/svg+xml")
        icon = static_dir / "angelus-icon.svg"
        if icon.is_file():
            return FileResponse(icon, media_type="image/svg+xml")
        raise HTTPException(status_code=404, detail="frontend is not installed")

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
    app.include_router(plugins_router)
    app.include_router(external_agent_hub_router)
    app.include_router(mcp_router)
    app.include_router(attachments_router)
    app.include_router(memory_router)
    app.include_router(compact_router)
    app.include_router(notes_router)
    assets = frontend_dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="frontend-assets")
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=static_dir), name="frontend-static")

    @app.get("/{path:path}", include_in_schema=False)
    def react_routes(path: str) -> FileResponse:
        """Fall back to the SPA shell for client-side routes.

        Raises:
            HTTPException: When this host ships no frontend.
        """
        if has_dist:
            candidate = (frontend_dist / path).resolve()
            if candidate.is_file() and frontend_dist.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(frontend_dist / "index.html")
        if has_templates:
            candidate = (templates_dir / path).resolve()
            if candidate.is_file() and templates_dir.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(templates_dir / "index.html")
        raise HTTPException(status_code=404, detail="frontend is not installed")


__all__ = ["include_api_routes"]
