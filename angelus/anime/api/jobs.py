"""/api/anime/jobs/* 路由：生成任务可观测/可取消/可重试。"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException

from .. import storage
from ..queue import GenerationQueue

router = APIRouter()

_queue: Optional[GenerationQueue] = None


def set_queue(queue: GenerationQueue) -> None:
    global _queue
    _queue = queue


def _get_queue() -> GenerationQueue:
    if _queue is None:
        raise HTTPException(status_code=503, detail="Generation queue not initialized")
    return _queue


@router.get("/api/anime/projects/{project_id}/jobs")
def list_jobs(project_id: str) -> dict[str, list[dict[str, Any]]]:
    """列出项目全部生成任务。"""
    jobs = storage.list_collection(project_id, "jobs")
    jobs.sort(key=lambda j: j.get("created_at", 0), reverse=True)
    return {"jobs": jobs}


@router.get("/api/anime/projects/{project_id}/jobs/{job_id}")
def get_job(project_id: str, job_id: str) -> dict[str, Any]:
    """读取单个任务。"""
    job = storage.get_item(project_id, "jobs", job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/api/anime/projects/{project_id}/jobs/{job_id}/cancel")
def cancel_job(project_id: str, job_id: str) -> dict[str, Any]:
    """取消任务（仅非终态可取消）。"""
    if not _get_queue().cancel(project_id, job_id):
        raise HTTPException(status_code=409, detail="Job is terminal or not found")
    return {"ok": True, "job_id": job_id}


@router.post("/api/anime/projects/{project_id}/jobs/{job_id}/retry")
def retry_job(project_id: str, job_id: str) -> dict[str, Any]:
    """重试 FAILED 任务（受 Retry Policy 约束）。"""
    job = _get_queue().retry(project_id, job_id)
    if job is None:
        raise HTTPException(status_code=409, detail="Job is not retryable")
    return {"ok": True, "job": job.to_dict()}
