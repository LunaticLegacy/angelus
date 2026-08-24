"""/api/anime/qa/* 路由：QA 报告 + 导出端点。"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException

from .. import export, qa as qa_service
from ..narrative.gate import run_gate

router = APIRouter()


@router.get("/api/anime/projects/{project_id}/qa")
def list_qa(project_id: str) -> dict[str, list[dict[str, Any]]]:
    """列出项目 QA 报告。"""
    return {"reports": qa_service.list_qa(project_id)}


@router.get("/api/anime/projects/{project_id}/qa/{report_id}")
def get_qa(project_id: str, report_id: str) -> dict[str, Any]:
    """读取单条 QA 报告。"""
    report = qa_service.get_qa(project_id, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="QA report not found")
    return report


@router.post("/api/anime/projects/{project_id}/shots/{shot_id}/qa")
def run_shot_qa(project_id: str, shot_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """对镜头运行 QA（结构检查 + 可选 Narrative Gate）。"""
    shot = qa_service.storage.get_item(project_id, "shots", shot_id)
    if shot is None:
        raise HTTPException(status_code=404, detail="Shot not found")

    gate = None
    if payload.get("run_gate"):
        gate = run_gate(
            text=shot.get("prompt", ""),
            episode_outline=payload.get("episode_outline", ""),
            scene_titles=payload.get("scene_titles"),
            storyboard_content=payload.get("storyboard_content", ""),
        )
    report = qa_service.run_qa(
        project_id,
        shot_id,
        gate=gate,
        notes=payload.get("notes", ""),
    )
    return report.to_dict()


# ---- 导出端点 ----

@router.get("/api/anime/projects/{project_id}/export/final-cut")
def export_final_cut(project_id: str, only_approved: bool = True) -> dict[str, Any]:
    """导出成片清单。"""
    return export.export_final_cut(project_id, only_approved=only_approved)


@router.get("/api/anime/projects/{project_id}/export/script")
def export_script(project_id: str, episode_id: Optional[str] = None) -> dict[str, Any]:
    """导出 Markdown 剧本。"""
    return export.export_script(project_id, episode_id=episode_id)


@router.get("/api/anime/projects/{project_id}/export/assets")
def export_assets(project_id: str) -> dict[str, Any]:
    """导出资产包 manifest。"""
    return export.export_asset_manifest(project_id)


@router.get("/api/anime/projects/{project_id}/export/subtitles")
def export_subtitles(project_id: str, episode_id: str, fmt: str = "srt") -> dict[str, Any]:
    """导出剧集字幕（srt/vtt）。"""
    return export.export_subtitles(project_id, episode_id, fmt=fmt)
