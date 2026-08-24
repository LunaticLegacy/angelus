"""Shot 状态机与统一任务状态枚举。

Shot 是最小调度单位，状态机：
    DRAFT → READY → QUEUED → GENERATING → GENERATED → QA_PENDING → QA_PASSED → APPROVED
失败路径：
    FAILED → RETRY_PENDING → QUEUED

统一任务状态（Provider 层）：
    PENDING / QUEUED / RUNNING / SUCCEEDED / FAILED / CANCELLED / EXPIRED
"""

from __future__ import annotations

from enum import Enum


class ShotStatus(str, Enum):
    """Shot 生命周期状态机。"""

    DRAFT = "DRAFT"
    READY = "READY"
    QUEUED = "QUEUED"
    GENERATING = "GENERATING"
    GENERATED = "GENERATED"
    QA_PENDING = "QA_PENDING"
    QA_PASSED = "QA_PASSED"
    APPROVED = "APPROVED"
    FAILED = "FAILED"
    RETRY_PENDING = "RETRY_PENDING"


#: 合法状态迁移表：key 为当前状态，value 为可到达状态集合。
SHOT_TRANSITIONS: dict[ShotStatus, set[ShotStatus]] = {
    ShotStatus.DRAFT: {ShotStatus.READY, ShotStatus.FAILED},
    ShotStatus.READY: {ShotStatus.QUEUED, ShotStatus.DRAFT, ShotStatus.FAILED},
    ShotStatus.QUEUED: {ShotStatus.GENERATING, ShotStatus.FAILED, ShotStatus.RETRY_PENDING},
    ShotStatus.GENERATING: {ShotStatus.GENERATED, ShotStatus.FAILED, ShotStatus.RETRY_PENDING},
    ShotStatus.GENERATED: {ShotStatus.QA_PENDING, ShotStatus.FAILED, ShotStatus.RETRY_PENDING},
    ShotStatus.QA_PENDING: {ShotStatus.QA_PASSED, ShotStatus.FAILED, ShotStatus.RETRY_PENDING},
    ShotStatus.QA_PASSED: {ShotStatus.APPROVED, ShotStatus.FAILED, ShotStatus.RETRY_PENDING},
    ShotStatus.APPROVED: {ShotStatus.FAILED, ShotStatus.RETRY_PENDING},
    ShotStatus.FAILED: {ShotStatus.RETRY_PENDING, ShotStatus.READY, ShotStatus.DRAFT},
    ShotStatus.RETRY_PENDING: {ShotStatus.QUEUED, ShotStatus.FAILED},
}


class JobStatus(str, Enum):
    """统一任务状态（Provider 层与队列层共用）。"""

    PENDING = "PENDING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


#: 终态集合：进入后不再自动迁移。
TERMINAL_JOB_STATUSES = frozenset(
    {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.EXPIRED}
)


class GateVerdict(str, Enum):
    """Narrative Gate 判定。"""

    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


def can_transition_shot(current: ShotStatus, target: ShotStatus) -> bool:
    """判断 Shot 状态迁移是否合法。"""
    return target in SHOT_TRANSITIONS.get(current, set())


def transition_shot(current: ShotStatus, target: ShotStatus) -> ShotStatus:
    """执行 Shot 状态迁移，非法迁移抛 ValueError。"""
    if not can_transition_shot(current, target):
        raise ValueError(f"非法 Shot 状态迁移: {current.value} -> {target.value}")
    return target
