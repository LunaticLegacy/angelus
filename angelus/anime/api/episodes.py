"""/api/anime/episodes/* 路由：剧集 CRUD + 场景聚合。"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException

from .. import events, storage
from ..models import Episode

router = APIRouter()


def _require_project(project_id: str) -> None:
    if storage.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")


@router.get("/api/anime/projects/{project_id}/episodes")
def list_episodes(project_id: str) -> dict[str, list[dict[str, Any]]]:
    """列出项目全部剧集。"""
    _require_project(project_id)
    episodes = storage.list_collection(project_id, "episodes")
    episodes.sort(key=lambda e: e.get("order", 0))
    return {"episodes": episodes}


@router.post("/api/anime/projects/{project_id}/episodes")
def create_episode(project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """创建剧集。"""
    _require_project(project_id)
    title = (payload.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=422, detail="title is required")
    order = int(payload.get("order", 0))
    episode = Episode.create(
        project_id=project_id,
        title=title,
        order=order,
        arc_id=payload.get("arc_id", ""),
    )
    episode.outline = payload.get("outline", "")
    data = episode.to_dict()
    storage.upsert_item(project_id, "episodes", data)
    events.emit(project_id, "anime.episode.created", {"episode_id": episode.id, "title": title})
    return data


@router.get("/api/anime/projects/{project_id}/episodes/{episode_id}")
def get_episode(project_id: str, episode_id: str) -> dict[str, Any]:
    """读取单个剧集。"""
    episode = storage.get_item(project_id, "episodes", episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    return episode


@router.put("/api/anime/projects/{project_id}/episodes/{episode_id}")
def update_episode(project_id: str, episode_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """更新剧集字段。"""
    episode = storage.get_item(project_id, "episodes", episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    for key in ("title", "order", "arc_id", "outline", "status"):
        if key in payload:
            episode[key] = payload[key]
    episode["updated_at"] = time.time()
    storage.upsert_item(project_id, "episodes", episode)
    events.emit(project_id, "anime.episode.updated", {"episode_id": episode_id})
    return episode


@router.delete("/api/anime/projects/{project_id}/episodes/{episode_id}")
def delete_episode(project_id: str, episode_id: str) -> dict[str, Any]:
    """删除剧集（级联删除其场景与镜头）。"""
    if not storage.delete_item(project_id, "episodes", episode_id):
        raise HTTPException(status_code=404, detail="Episode not found")
    scenes = [s for s in storage.list_collection(project_id, "scenes") if s.get("episode_id") == episode_id]
    for scene in scenes:
        shots = [s for s in storage.list_collection(project_id, "shots") if s.get("scene_id") == scene["id"]]
        for shot in shots:
            storage.delete_item(project_id, "shots", shot["id"])
        storage.delete_item(project_id, "scenes", scene["id"])
    events.emit(project_id, "anime.episode.deleted", {"episode_id": episode_id})
    return {"ok": True, "episode_id": episode_id}
