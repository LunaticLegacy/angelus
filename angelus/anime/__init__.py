"""AI Drama Production Studio — 短剧生产领域包。

基于 Angelus 复用 Agent Runtime / LLM 调用层，新增短剧生产领域模型：
剧情规划 → 剧集拆分 → 场景拆分 → 分镜 → 生成 → QA → 导出。

依赖方向：Drama → Angelus（单向），不反向依赖浏览器控制面。
"""

from __future__ import annotations

from .models import (
    Asset,
    CostRecord,
    DramaProject,
    Episode,
    GenerationJob,
    QAReport,
    Scene,
    Shot,
)
from .states import (
    GateVerdict,
    JobStatus,
    ShotStatus,
    can_transition_shot,
    transition_shot,
)
from . import events, storage
from .providers import (
    DEFAULT_FALLBACK_ORDER,
    REAL_PROVIDER_ENV,
    MockVideoProvider,
    ProviderError,
    ProviderRouter,
    ProviderTaskError,
    ProviderUnavailableError,
    VideoGenerationProvider,
    build_router,
)
from .queue import BudgetGuard, GenerationQueue, RetryPolicy

__all__ = [
    "Asset",
    "CostRecord",
    "DramaProject",
    "Episode",
    "GenerationJob",
    "QAReport",
    "Scene",
    "Shot",
    "GateVerdict",
    "JobStatus",
    "ShotStatus",
    "can_transition_shot",
    "transition_shot",
    "events",
    "storage",
    "DEFAULT_FALLBACK_ORDER",
    "REAL_PROVIDER_ENV",
    "MockVideoProvider",
    "ProviderError",
    "ProviderRouter",
    "ProviderTaskError",
    "ProviderUnavailableError",
    "VideoGenerationProvider",
    "build_router",
    "BudgetGuard",
    "GenerationQueue",
    "RetryPolicy",
]
