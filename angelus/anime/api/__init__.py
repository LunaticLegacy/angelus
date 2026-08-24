"""/api/anime/* 路由装配：短剧生产领域 API。

与旧 API（connectors/runs/sessions/compact/plugins）并存，互不干扰。
"""

from __future__ import annotations

from fastapi import FastAPI

from . import episodes, events, jobs, projects, providers, qa, scenes, shots

__all__ = ["include_anime_routes"]


def include_anime_routes(app: FastAPI) -> None:
    """Attach every anime router onto the FastAPI app."""
    app.include_router(projects.router)
    app.include_router(episodes.router)
    app.include_router(scenes.router)
    app.include_router(shots.router)
    app.include_router(jobs.router)
    app.include_router(qa.router)
    app.include_router(providers.router)
    app.include_router(events.router)
