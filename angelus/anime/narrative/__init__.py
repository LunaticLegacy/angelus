"""剧情编排子包：迁移自 novelist 参考仓库的层级创作工作流。

Series Brief → Global Outline → Arc → Episode → Scene → Storyboard → Shot，
并附带 Narrative Gate / Character State / Foreshadowing / Audience Information。
"""

from __future__ import annotations

from .audience import AudienceInformation
from .character import CharacterState, CharacterStateStore
from .foreshadowing import (
    FORESHADOWING_HEADERS,
    FORESHADOWING_STATUSES,
    Foreshadowing,
    overdue_foreshadowing,
    parse_foreshadowing_csv,
    serialize_foreshadowing_csv,
    valid_foreshadowing_ids,
)
from .gate import (
    GateCheck,
    GateResult,
    check_character_state_sync,
    check_foreshadowing_ids,
    check_outline_coverage,
    check_overdue_foreshadowing,
    check_placeholders,
    check_storyboard_middleware,
    run_gate,
)
from .outline import (
    Arc,
    SCENE_WEIGHTS,
    Storyboard,
    build_global_outline,
    build_series_brief,
    infer_scene_count,
    scene_weights,
)

__all__ = [
    "AudienceInformation",
    "CharacterState",
    "CharacterStateStore",
    "FORESHADOWING_HEADERS",
    "FORESHADOWING_STATUSES",
    "Foreshadowing",
    "overdue_foreshadowing",
    "parse_foreshadowing_csv",
    "serialize_foreshadowing_csv",
    "valid_foreshadowing_ids",
    "GateCheck",
    "GateResult",
    "check_character_state_sync",
    "check_foreshadowing_ids",
    "check_outline_coverage",
    "check_overdue_foreshadowing",
    "check_placeholders",
    "check_storyboard_middleware",
    "run_gate",
    "Arc",
    "SCENE_WEIGHTS",
    "Storyboard",
    "build_global_outline",
    "build_series_brief",
    "infer_scene_count",
    "scene_weights",
]
