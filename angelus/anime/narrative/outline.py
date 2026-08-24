"""剧情编排：Series Brief → Global Outline → Arc → Episode → Scene → Storyboard → Shot。

迁移自 novelist 参考仓库的层级结构，适配短剧领域模型。
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional


@dataclass
class Arc:
    """故事弧：介于 Global Outline 与 Episode 之间。"""

    id: str
    project_id: str
    title: str
    order: int = 0
    summary: str = ""
    status: str = "DRAFT"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Storyboard:
    """分镜纲：Scene 与 Shot 之间的中间层。"""

    id: str
    scene_id: str
    project_id: str
    content: str = ""
    status: str = "DRAFT"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


#: 场景数推断规则（迁移自 novelist narrative_engine）：按字数推断场景数
def infer_scene_count(word_count: int) -> int:
    """按字数推断场景数：≤1500→2，≤3000→3，≤5000→4，否则 5。"""
    if word_count <= 1500:
        return 2
    if word_count <= 3000:
        return 3
    if word_count <= 5000:
        return 4
    return 5


#: 场景权重分布（迁移自 novelist）：按场景数给出权重
SCENE_WEIGHTS: dict[int, list[int]] = {
    2: [45, 55],
    3: [25, 45, 30],
    4: [20, 30, 30, 20],
    5: [18, 24, 24, 20, 14],
}


def scene_weights(scene_count: int) -> list[int]:
    """返回指定场景数的权重分布。"""
    return SCENE_WEIGHTS.get(scene_count, SCENE_WEIGHTS[5])


def build_series_brief(title: str, logline: str, genre: str = "", target_audience: str = "") -> dict[str, Any]:
    """构造 Series Brief（项目级）。"""
    return {
        "title": title,
        "logline": logline,
        "genre": genre,
        "target_audience": target_audience,
    }


def build_global_outline(series_brief: dict[str, Any], arcs: list[Arc]) -> dict[str, Any]:
    """构造 Global Outline（项目级总大纲）。"""
    return {
        "series_brief": series_brief,
        "arcs": [arc.to_dict() for arc in arcs],
        "arc_count": len(arcs),
    }
