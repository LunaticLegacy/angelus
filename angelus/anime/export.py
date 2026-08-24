"""导出模块：成片清单 / 剧本 / 资产包。

- 成片清单：按剧集聚合已 APPROVED 镜头，生成可交付清单（含时长、资产 URI）。
- 剧本导出：剧集 → 场景 → 镜头 prompt 的 Markdown 剧本。
- 资产包：收集项目内所有 Asset 元数据，生成 manifest。
- 字幕导出：按镜头时长生成 SRT/VTT 时间轴（供剪辑使用）。
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional

from . import storage
from .states import ShotStatus


def _now() -> float:
    return time.time()


def _shot_sort_key(shot: dict[str, Any]) -> tuple[int, int, int]:
    """按 episode.order / scene.order / shot.order 排序。"""
    ep_order = 0
    scn_order = 0
    ep = storage.get_item(shot.get("project_id", ""), "episodes", shot.get("episode_id", ""))
    if ep:
        ep_order = ep.get("order", 0)
    scn = storage.get_item(shot.get("project_id", ""), "scenes", shot.get("scene_id", ""))
    if scn:
        scn_order = scn.get("order", 0)
    return (ep_order, scn_order, shot.get("order", 0))


def export_final_cut(project_id: str, *, only_approved: bool = True) -> dict[str, Any]:
    """导出成片清单。

    Args:
        project_id: 项目 ID。
        only_approved: 仅包含 APPROVED 镜头（默认 True）。

    Returns:
        {"project_id", "exported_at", "episodes": [...], "total_duration_seconds", "shot_count"}
    """
    shots = storage.list_collection(project_id, "shots")
    if only_approved:
        shots = [s for s in shots if s.get("status") == ShotStatus.APPROVED.value]
    shots.sort(key=_shot_sort_key)

    episodes: dict[str, dict[str, Any]] = {}
    for shot in shots:
        ep_id = shot.get("episode_id", "")
        ep = storage.get_item(project_id, "episodes", ep_id) or {"id": ep_id, "title": ep_id, "order": 0}
        bucket = episodes.setdefault(
            ep_id,
            {
                "episode_id": ep_id,
                "title": ep.get("title", ep_id),
                "order": ep.get("order", 0),
                "shots": [],
                "duration_seconds": 0.0,
            },
        )
        bucket["shots"].append(shot)
        bucket["duration_seconds"] += float(shot.get("duration_seconds", 0.0))

    episode_list = sorted(episodes.values(), key=lambda e: e["order"])
    total = sum(e["duration_seconds"] for e in episode_list)
    return {
        "project_id": project_id,
        "exported_at": _now(),
        "episodes": episode_list,
        "total_duration_seconds": total,
        "shot_count": len(shots),
    }


def export_script(project_id: str, episode_id: Optional[str] = None) -> dict[str, Any]:
    """导出 Markdown 剧本（剧集 → 场景 → 镜头 prompt）。"""
    episodes = storage.list_collection(project_id, "episodes")
    if episode_id:
        episodes = [e for e in episodes if e.get("id") == episode_id]
    episodes.sort(key=lambda e: e.get("order", 0))

    lines: list[str] = []
    for ep in episodes:
        lines.append(f"# 第 {ep.get('order', 0)} 集：{ep.get('title', ep['id'])}")
        if ep.get("outline"):
            lines.append("")
            lines.append(ep["outline"])
        scenes = [s for s in storage.list_collection(project_id, "scenes") if s.get("episode_id") == ep["id"]]
        scenes.sort(key=lambda s: s.get("order", 0))
        for scn in scenes:
            lines.append("")
            lines.append(f"## 场景 {scn.get('order', 0)}：{scn.get('title', scn['id'])}")
            if scn.get("description"):
                lines.append(f"> {scn['description']}")
            shots = [s for s in storage.list_collection(project_id, "shots") if s.get("scene_id") == scn["id"]]
            shots.sort(key=lambda s: s.get("order", 0))
            for shot in shots:
                lines.append("")
                lines.append(f"### 镜头 {shot.get('order', 0)} [{shot.get('status', 'DRAFT')}]")
                if shot.get("prompt"):
                    lines.append(shot["prompt"])
                if shot.get("negative_prompt"):
                    lines.append(f"负向: {shot['negative_prompt']}")

    return {
        "project_id": project_id,
        "episode_id": episode_id,
        "exported_at": _now(),
        "markdown": "\n".join(lines),
    }


def export_asset_manifest(project_id: str) -> dict[str, Any]:
    """导出资产包 manifest（所有 Asset 元数据）。"""
    assets = storage.list_collection(project_id, "assets")
    by_kind: dict[str, int] = {}
    for asset in assets:
        kind = asset.get("kind", "unknown")
        by_kind[kind] = by_kind.get(kind, 0) + 1
    return {
        "project_id": project_id,
        "exported_at": _now(),
        "asset_count": len(assets),
        "by_kind": by_kind,
        "assets": assets,
    }


def _format_timestamp(seconds: float) -> str:
    """SRT 时间戳格式：HH:MM:SS,mmm。"""
    ms = int(round(seconds * 1000))
    hours, ms = divmod(ms, 3600 * 1000)
    minutes, ms = divmod(ms, 60 * 1000)
    secs, ms = divmod(ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def export_subtitles(project_id: str, episode_id: str, fmt: str = "srt") -> dict[str, Any]:
    """导出剧集字幕（SRT/VTT），按镜头顺序生成时间轴。"""
    if fmt not in ("srt", "vtt"):
        raise ValueError(f"不支持的字幕格式: {fmt}")

    shots = [s for s in storage.list_collection(project_id, "shots") if s.get("episode_id") == episode_id]
    shots.sort(key=_shot_sort_key)

    lines: list[str] = []
    if fmt == "vtt":
        lines.append("WEBVTT")
        lines.append("")

    cursor = 0.0
    for index, shot in enumerate(shots, start=1):
        duration = float(shot.get("duration_seconds", 5.0))
        text = (shot.get("prompt") or "").strip().replace("\n", " ")
        if not text:
            text = f"[镜头 {shot.get('order', index)}]"
        start = cursor
        end = cursor + duration
        if fmt == "srt":
            lines.append(str(index))
            lines.append(f"{_format_timestamp(start)} --> {_format_timestamp(end)}")
        else:
            lines.append(f"{_format_timestamp(start).replace(',', '.')} --> {_format_timestamp(end).replace(',', '.')}")
        lines.append(text)
        lines.append("")
        cursor = end

    return {
        "project_id": project_id,
        "episode_id": episode_id,
        "fmt": fmt,
        "exported_at": _now(),
        "content": "\n".join(lines),
    }
