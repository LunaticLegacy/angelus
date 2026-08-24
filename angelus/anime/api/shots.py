"""/api/anime/shots/* 路由：镜头 CRUD + 状态机迁移 + 生成提交。"""

from __future__ import annotations

import time
from typing import Any, Optional

from fastapi import APIRouter, HTTPException

from .. import events, storage
from ..models import GenerationJob, Shot
from ..queue import GenerationQueue
from ..states import ShotStatus, can_transition_shot

router = APIRouter()

#: 进程内共享队列（webapp 挂载时注入）
_queue: Optional[GenerationQueue] = None


def set_queue(queue: GenerationQueue) -> None:
    """注入共享 GenerationQueue（由 webapp 挂载时调用）。"""
    global _queue
    _queue = queue


def _get_queue() -> GenerationQueue:
    if _queue is None:
        raise HTTPException(status_code=503, detail="Generation queue not initialized")
    return _queue


def _require_scene(project_id: str, scene_id: str) -> None:
    if storage.get_item(project_id, "scenes", scene_id) is None:
        raise HTTPException(status_code=404, detail="Scene not found")


@router.get("/api/anime/projects/{project_id}/scenes/{scene_id}/shots")
def list_shots(project_id: str, scene_id: str) -> dict[str, list[dict[str, Any]]]:
    """列出场景全部镜头。"""
    _require_scene(project_id, scene_id)
    shots = [s for s in storage.list_collection(project_id, "shots") if s.get("scene_id") == scene_id]
    shots.sort(key=lambda s: s.get("order", 0))
    return {"shots": shots}


@router.post("/api/anime/projects/{project_id}/scenes/{scene_id}/shots")
def create_shot(project_id: str, scene_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """创建镜头。"""
    _require_scene(project_id, scene_id)
    scene = storage.get_item(project_id, "scenes", scene_id)
    episode_id = scene["episode_id"]
    order = int(payload.get("order", 0))
    shot = Shot.create(
        project_id=project_id,
        episode_id=episode_id,
        scene_id=scene_id,
        prompt=payload.get("prompt", ""),
        order=order,
    )
    shot.negative_prompt = payload.get("negative_prompt", "")
    shot.duration_seconds = float(payload.get("duration_seconds", 5.0))
    data = shot.to_dict()
    storage.upsert_item(project_id, "shots", data)
    events.emit(project_id, "anime.shot.created", {"shot_id": shot.id, "scene_id": scene_id})
    return data


@router.get("/api/anime/projects/{project_id}/shots/{shot_id}")
def get_shot(project_id: str, shot_id: str) -> dict[str, Any]:
    """读取单个镜头。"""
    shot = storage.get_item(project_id, "shots", shot_id)
    if shot is None:
        raise HTTPException(status_code=404, detail="Shot not found")
    return shot


@router.put("/api/anime/projects/{project_id}/shots/{shot_id}")
def update_shot(project_id: str, shot_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """更新镜头字段（prompt/negative_prompt/duration_seconds/order）。"""
    shot = storage.get_item(project_id, "shots", shot_id)
    if shot is None:
        raise HTTPException(status_code=404, detail="Shot not found")
    for key in ("prompt", "negative_prompt", "duration_seconds", "order"):
        if key in payload:
            shot[key] = payload[key]
    shot["updated_at"] = time.time()
    storage.upsert_item(project_id, "shots", shot)
    events.emit(project_id, "anime.shot.updated", {"shot_id": shot_id})
    return shot


@router.delete("/api/anime/projects/{project_id}/shots/{shot_id}")
def delete_shot(project_id: str, shot_id: str) -> dict[str, Any]:
    """删除镜头。"""
    if not storage.delete_item(project_id, "shots", shot_id):
        raise HTTPException(status_code=404, detail="Shot not found")
    events.emit(project_id, "anime.shot.deleted", {"shot_id": shot_id})
    return {"ok": True, "shot_id": shot_id}


@router.post("/api/anime/projects/{project_id}/shots/{shot_id}/transition")
def transition_shot_status(project_id: str, shot_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """执行镜头状态迁移（受状态机约束）。"""
    shot = storage.get_item(project_id, "shots", shot_id)
    if shot is None:
        raise HTTPException(status_code=404, detail="Shot not found")
    target = payload.get("status")
    if not target:
        raise HTTPException(status_code=422, detail="status is required")
    try:
        target_status = ShotStatus(target)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid status: {target}")
    current = ShotStatus(shot.get("status", "DRAFT"))
    if not can_transition_shot(current, target_status):
        raise HTTPException(status_code=409, detail=f"非法迁移: {current.value} -> {target_status.value}")
    shot["status"] = target_status.value
    shot["updated_at"] = time.time()
    storage.upsert_item(project_id, "shots", shot)
    events.shot_state_changed(project_id, shot_id, current.value, target_status.value)
    return shot


@router.post("/api/anime/projects/{project_id}/shots/{shot_id}/generate")
def generate_shot(project_id: str, shot_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """提交镜头生成任务（Shot READY → QUEUED，创建 GenerationJob 入队）。"""
    shot = storage.get_item(project_id, "shots", shot_id)
    if shot is None:
        raise HTTPException(status_code=404, detail="Shot not found")
    current = ShotStatus(shot.get("status", "DRAFT"))
    if not can_transition_shot(current, ShotStatus.QUEUED):
        raise HTTPException(status_code=409, detail=f"镜头状态 {current.value} 不可提交生成")
    shot["status"] = ShotStatus.QUEUED.value
    shot["updated_at"] = time.time()
    storage.upsert_item(project_id, "shots", shot)
    events.shot_state_changed(project_id, shot_id, current.value, ShotStatus.QUEUED.value)

    provider = payload.get("provider", "mock")
    job = GenerationJob.create(
        project_id=project_id,
        shot_id=shot_id,
        provider=provider,
        params={
            "prompt": shot.get("prompt", ""),
            "negative_prompt": shot.get("negative_prompt", ""),
            "duration_seconds": shot.get("duration_seconds", 5.0),
            "resolution": payload.get("resolution", "720p"),
        },
    )
    job = _get_queue().submit(job)
    return {"job": job.to_dict(), "shot": shot}
