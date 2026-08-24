"""QA 管线：镜头/场景/剧集一致性校验 + Narrative Gate + QAReport 持久化。

QA 是生成结果进入交付前的门禁：
- 结构一致性：Shot 必须属于存在的 Scene/Episode/Project，顺序连续。
- 内容门禁：复用 narrative.gate 的 PASS/WARN/FAIL 规则。
- 产出 QAReport 并写 anime.qa.* 事件。
"""

from __future__ import annotations

import time
from typing import Any, Optional

from . import events, storage
from .models import QAReport
from .narrative.gate import GateResult, run_gate
from .states import ShotStatus


def _now() -> float:
    return time.time()


def check_structure(
    project_id: str,
    *,
    episode_ids: Optional[list[str]] = None,
    scene_ids: Optional[list[str]] = None,
    shot_ids: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """结构一致性检查：返回 check 列表（name/verdict/detail）。

    - 场景必须属于存在的剧集
    - 镜头必须属于存在的场景
    - 镜头必须有 prompt（生成前提）
    """
    checks: list[dict[str, Any]] = []
    episode_ids = episode_ids or []
    scene_ids = scene_ids or []
    shot_ids = shot_ids or []

    # 场景 → 剧集
    episodes = {e["id"] for e in storage.list_collection(project_id, "episodes")}
    scenes = storage.list_collection(project_id, "scenes")
    orphan_scenes = [s["id"] for s in scenes if s.get("episode_id") not in episodes]
    if orphan_scenes:
        checks.append({
            "name": "scene_episode_link",
            "verdict": "FAIL",
            "detail": f"孤儿场景（无对应剧集）: {', '.join(orphan_scenes)}",
        })
    else:
        checks.append({"name": "scene_episode_link", "verdict": "PASS", "detail": "场景均挂载于剧集"})

    # 镜头 → 场景
    scene_set = {s["id"] for s in scenes}
    shots = storage.list_collection(project_id, "shots")
    orphan_shots = [s["id"] for s in shots if s.get("scene_id") not in scene_set]
    if orphan_shots:
        checks.append({
            "name": "shot_scene_link",
            "verdict": "FAIL",
            "detail": f"孤儿镜头（无对应场景）: {', '.join(orphan_shots)}",
        })
    else:
        checks.append({"name": "shot_scene_link", "verdict": "PASS", "detail": "镜头均挂载于场景"})

    # 镜头 prompt 完整性
    no_prompt = [s["id"] for s in shots if not (s.get("prompt") or "").strip()]
    if no_prompt:
        checks.append({
            "name": "shot_prompt",
            "verdict": "WARN",
            "detail": f"镜头缺少 prompt: {', '.join(no_prompt)}",
        })
    else:
        checks.append({"name": "shot_prompt", "verdict": "PASS", "detail": "镜头 prompt 完整"})

    # 顺序连续性（order 无重复）
    orders = [s.get("order", 0) for s in shots]
    if len(orders) != len(set(orders)):
        checks.append({"name": "shot_order", "verdict": "WARN", "detail": "镜头 order 存在重复"})
    else:
        checks.append({"name": "shot_order", "verdict": "PASS", "detail": "镜头 order 唯一"})

    return checks


def run_qa(
    project_id: str,
    shot_id: str,
    *,
    gate: Optional[GateResult] = None,
    structural_checks: Optional[list[dict[str, Any]]] = None,
    notes: str = "",
) -> QAReport:
    """运行一次 QA 并持久化报告 + 事件。

    Args:
        project_id: 项目 ID。
        shot_id: 被检镜头 ID。
        gate: 可选 Narrative Gate 结果；为 None 时跳过内容门禁。
        structural_checks: 可选结构检查列表；为 None 时自动运行 check_structure。
        notes: 人工备注。

    Returns:
        持久化后的 QAReport。
    """
    checks: list[dict[str, Any]] = list(structural_checks or check_structure(project_id))
    if gate is not None:
        checks.extend(gate.to_dict().get("checks", []))

    if any(c.get("verdict") == "FAIL" for c in checks):
        verdict = "FAIL"
    elif any(c.get("verdict") == "WARN" for c in checks):
        verdict = "WARN"
    else:
        verdict = "PASS"

    report = QAReport.create(project_id=project_id, shot_id=shot_id, verdict=verdict)
    report.checks = checks
    report.notes = notes
    storage.upsert_item(project_id, "qa", report.to_dict())
    events.qa_result(project_id, shot_id, verdict, report.id)

    # 联动镜头状态：沿状态机逐级迁移到 QA_PASSED（GENERATED → QA_PENDING → QA_PASSED）
    shot = storage.get_item(project_id, "shots", shot_id)
    if shot is not None:
        from .states import can_transition_shot
        current = ShotStatus(shot.get("status", "DRAFT"))
        if verdict == "PASS":
            # 逐级走状态机：GENERATED -> QA_PENDING -> QA_PASSED
            target = ShotStatus.QA_PASSED
            if can_transition_shot(current, ShotStatus.QA_PENDING):
                shot["status"] = ShotStatus.QA_PENDING.value
                shot["updated_at"] = _now()
                storage.upsert_item(project_id, "shots", shot)
                events.shot_state_changed(project_id, shot_id, current.value, ShotStatus.QA_PENDING.value)
                current = ShotStatus.QA_PENDING
            if can_transition_shot(current, target):
                shot["status"] = target.value
                shot["updated_at"] = _now()
                storage.upsert_item(project_id, "shots", shot)
                events.shot_state_changed(project_id, shot_id, current.value, target.value)

    return report


def list_qa(project_id: str) -> list[dict[str, Any]]:
    """列出项目 QA 报告。"""
    return storage.list_collection(project_id, "qa")


def get_qa(project_id: str, report_id: str) -> Optional[dict[str, Any]]:
    """读取单条 QA 报告。"""
    return storage.get_item(project_id, "qa", report_id)
