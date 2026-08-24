"""/api/anime/projects/* 路由：项目聚合根 CRUD。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from .. import events, storage
from ..models import DramaProject

router = APIRouter()


@router.get("/api/anime/projects")
def list_projects() -> dict[str, list[dict[str, Any]]]:
    """列出全部短剧项目。"""
    return {"projects": storage.list_projects()}


@router.post("/api/anime/projects")
def create_project(payload: dict[str, Any]) -> dict[str, Any]:
    """创建短剧项目。"""
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")
    project = DramaProject.create(name=name, series_brief=payload.get("series_brief", ""))
    data = project.to_dict()
    storage.upsert_project(data)
    events.project_created(project.id, name)
    return data


@router.get("/api/anime/projects/{project_id}")
def get_project(project_id: str) -> dict[str, Any]:
    """读取单个项目。"""
    project = storage.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.put("/api/anime/projects/{project_id}")
def update_project(project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """更新项目字段（name / series_brief / global_outline / status）。"""
    project = storage.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    allowed = {"name", "series_brief", "global_outline", "status"}
    changed: dict[str, Any] = {}
    for key in allowed:
        if key in payload:
            project[key] = payload[key]
            changed[key] = payload[key]
    import time
    project["updated_at"] = time.time()
    storage.upsert_project(project)
    if changed:
        events.project_updated(project_id, changed)
    return project


@router.delete("/api/anime/projects/{project_id}")
def delete_project(project_id: str) -> dict[str, Any]:
    """删除项目（含其目录）。"""
    if not storage.delete_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    events.project_deleted(project_id)
    return {"ok": True, "project_id": project_id}
