"""AI Drama Production Studio 领域模型。

领域模型：DramaProject / Episode / Scene / Shot / Asset / GenerationJob / QAReport / CostRecord
Shot 是最小调度单位。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from .states import ShotStatus, JobStatus


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _now() -> float:
    return time.time()


@dataclass
class DramaProject:
    """短剧项目：顶层聚合根。"""

    id: str
    name: str
    series_brief: str = ""
    global_outline: str = ""
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)
    status: str = "DRAFT"  # DRAFT / ACTIVE / ARCHIVED

    @classmethod
    def create(cls, name: str, series_brief: str = "") -> "DramaProject":
        return cls(id=_new_id("proj"), name=name, series_brief=series_brief)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Episode:
    """剧集：属于项目，包含多个场景。"""

    id: str
    project_id: str
    title: str
    order: int = 0
    arc_id: str = ""
    outline: str = ""
    status: str = "DRAFT"
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)

    @classmethod
    def create(cls, project_id: str, title: str, order: int = 0, arc_id: str = "") -> "Episode":
        return cls(id=_new_id("ep"), project_id=project_id, title=title, order=order, arc_id=arc_id)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Scene:
    """场景：属于剧集，包含多个镜头。"""

    id: str
    episode_id: str
    project_id: str
    title: str
    order: int = 0
    description: str = ""
    location: str = ""
    status: str = "DRAFT"
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)

    @classmethod
    def create(cls, project_id: str, episode_id: str, title: str, order: int = 0) -> "Scene":
        return cls(id=_new_id("scn"), project_id=project_id, episode_id=episode_id, title=title, order=order)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Shot:
    """镜头：最小调度单位，拥有完整状态机。"""

    id: str
    scene_id: str
    episode_id: str
    project_id: str
    order: int = 0
    prompt: str = ""
    negative_prompt: str = ""
    duration_seconds: float = 5.0
    status: ShotStatus = ShotStatus.DRAFT
    asset_id: Optional[str] = None
    retry_count: int = 0
    error: Optional[str] = None
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)

    @classmethod
    def create(
        cls,
        project_id: str,
        episode_id: str,
        scene_id: str,
        prompt: str = "",
        order: int = 0,
    ) -> "Shot":
        return cls(
            id=_new_id("shot"),
            project_id=project_id,
            episode_id=episode_id,
            scene_id=scene_id,
            prompt=prompt,
            order=order,
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


@dataclass
class Asset:
    """生成结果 Artifact：每个生成结果都是 Asset。"""

    id: str
    project_id: str
    kind: str  # video / image / audio / subtitle / script / storyboard
    uri: str  # 本地文件路径或 provider 返回的 URL
    mime_type: str = ""
    size_bytes: int = 0
    meta: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=_now)

    @classmethod
    def create(cls, project_id: str, kind: str, uri: str, mime_type: str = "") -> "Asset":
        return cls(id=_new_id("ast"), project_id=project_id, kind=kind, uri=uri, mime_type=mime_type)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GenerationJob:
    """生成任务：队列最小单元，可观测/可恢复/可取消/可重试。"""

    id: str
    project_id: str
    shot_id: str
    provider: str = "mock"
    status: JobStatus = JobStatus.PENDING
    params: dict[str, Any] = field(default_factory=dict)
    result_asset_id: Optional[str] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None

    @classmethod
    def create(cls, project_id: str, shot_id: str, provider: str = "mock", params: Optional[dict[str, Any]] = None) -> "GenerationJob":
        return cls(
            id=_new_id("job"),
            project_id=project_id,
            shot_id=shot_id,
            provider=provider,
            params=params or {},
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


@dataclass
class QAReport:
    """QA 报告：QA 管线输出。"""

    id: str
    project_id: str
    shot_id: str
    verdict: str = "PASS"  # PASS / WARN / FAIL
    checks: list[dict[str, Any]] = field(default_factory=list)
    notes: str = ""
    created_at: float = field(default_factory=_now)

    @classmethod
    def create(cls, project_id: str, shot_id: str, verdict: str = "PASS") -> "QAReport":
        return cls(id=_new_id("qa"), project_id=project_id, shot_id=shot_id, verdict=verdict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CostRecord:
    """成本记录：BudgetGuard 依据。"""

    id: str
    project_id: str
    job_id: str = ""
    amount: float = 0.0
    currency: str = "USD"
    meta: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=_now)

    @classmethod
    def create(cls, project_id: str, amount: float, job_id: str = "", currency: str = "USD") -> "CostRecord":
        return cls(id=_new_id("cost"), project_id=project_id, amount=amount, job_id=job_id, currency=currency)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
