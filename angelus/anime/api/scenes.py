"""/api/anime/scenes/* 路由：场景 CRUD + 镜头聚合。"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException

from .. import events, storage
from ..models import Scene

router = APIRouter()


def _require_episode(project_id: str, episode_id: str) -> None:
    if storage.get_item(project_id, "episodes", episode_id) is None:
        raise HTTPException(status_code=404, detail="Episode not found")


@router.get("/api/anime/projects/{project_id}/episodes/{episode_id}/scenes")
def list_scenes(project_id: str, episode_id: str) -> dict[str, list[dict[str, Any]]]:
    """列出剧集全部场景。"""
    _require_episode(project_id, episode_id)
    scenes = [s for s in storage.list_collection(project_id, "scenes") if s.get("episode_id") == episode_id]
    scenes.sort(key=lambda s: s.get("order", 0))
    return {"scenes": scenes}


@router.post("/api/anime/projects/{project_id}/episodes/{episode_id}/scenes")
def create_scene(project_id: str, episode_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """创建场景。"""
    _require_episode(project_id, episode_id)
    title = (payload.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=422, detail="title is required")
    order = int(payload.get("order", 0))
    scene = Scene.create(project_id=project_id, episode_id=episode_id, title=title, order=order)
    scene.description = payload.get("description", "")
    scene.location = payload.get("location", "")
    data = scene.to_dict()
    storage.upsert_item(project_id, "scenes", data)
    events.emit(project_id, "anime.scene.created", {"scene_id": scene.id, "episode_id": episode_id, "title": title})
    return data


@router.get("/api/anime/projects/{project_id}/scenes/{scene_id}")
def get_scene(project_id: str, scene_id: str) -> dict[str, Any]:
    """读取单个场景。"""
    scene = storage.get_item(project_id, "scenes", scene_id)
    if scene is None:
        raise HTTPException(status_code=404, detail="Scene not found")
    return scene


@router.put("/api/anime/projects/{project_id}/scenes/{scene_id}")
def update_scene(project_id: str, scene_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """更新场景字段。"""
    scene = storage.get_item(project_id, "scenes", scene_id)
    if scene is None:
        raise HTTPException(status_code=404, detail="Scene not found")
    for key in ("title", "order", "description", "location", "status"):
        if key in payload:
            scene[key] = payload[key]
    scene["updated_at"] = time.time()
    storage.upsert_item(project_id, "scenes", scene)
    events.emit(project_id, "anime.scene.updated", {"scene_id": scene_id})
    return scene


@router.delete("/api/anime/projects/{project_id}/scenes/{scene_id}")
def delete_scene(project_id: str, scene_id: str) -> dict[str, Any]:
    """删除场景（级联删除其镜头）。"""
    if not storage.delete_item(project_id, "scenes", scene_id):
        raise HTTPException(status_code=404, detail="Scene not found")
    shots = [s for s in storage.list_collection(project_id, "shots") if s.get("scene_id") == scene_id]
    for shot in shots:
        storage.delete_item(project_id, "shots", shot["id"])
    events.emit(project_id, "anime.scene.deleted", {"scene_id": scene_id})
    return {"ok": True, "scene_id": scene_id}
