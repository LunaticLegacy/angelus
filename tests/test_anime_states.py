"""anime 领域状态机与模型单元测试（纯逻辑，无网络）。"""

from __future__ import annotations

import pytest

from angelus.anime.models import (
    Asset,
    CostRecord,
    DramaProject,
    Episode,
    GenerationJob,
    QAReport,
    Scene,
    Shot,
)
from angelus.anime.states import (
    JobStatus,
    ShotStatus,
    TERMINAL_JOB_STATUSES,
    can_transition_shot,
    transition_shot,
)


class TestShotStateMachine:
    def test_happy_path_transitions(self) -> None:
        """DRAFT → READY → QUEUED → GENERATING → GENERATED → QA_PENDING → QA_PASSED → APPROVED。"""
        path = [
            ShotStatus.DRAFT,
            ShotStatus.READY,
            ShotStatus.QUEUED,
            ShotStatus.GENERATING,
            ShotStatus.GENERATED,
            ShotStatus.QA_PENDING,
            ShotStatus.QA_PASSED,
            ShotStatus.APPROVED,
        ]
        for current, target in zip(path, path[1:]):
            assert can_transition_shot(current, target), f"{current} -> {target}"

    def test_illegal_transition_raises(self) -> None:
        """DRAFT 不能直接 APPROVED。"""
        assert not can_transition_shot(ShotStatus.DRAFT, ShotStatus.APPROVED)
        with pytest.raises(ValueError):
            transition_shot(ShotStatus.DRAFT, ShotStatus.APPROVED)

    def test_failure_and_retry_path(self) -> None:
        """GENERATING → FAILED → RETRY_PENDING → QUEUED。"""
        assert can_transition_shot(ShotStatus.GENERATING, ShotStatus.FAILED)
        assert can_transition_shot(ShotStatus.FAILED, ShotStatus.RETRY_PENDING)
        assert can_transition_shot(ShotStatus.RETRY_PENDING, ShotStatus.QUEUED)

    def test_terminal_job_statuses(self) -> None:
        assert JobStatus.SUCCEEDED in TERMINAL_JOB_STATUSES
        assert JobStatus.FAILED in TERMINAL_JOB_STATUSES
        assert JobStatus.CANCELLED in TERMINAL_JOB_STATUSES
        assert JobStatus.EXPIRED in TERMINAL_JOB_STATUSES
        assert JobStatus.RUNNING not in TERMINAL_JOB_STATUSES


class TestModels:
    def test_project_create(self) -> None:
        project = DramaProject.create("测试短剧", "都市逆袭")
        assert project.id.startswith("proj_")
        assert project.name == "测试短剧"
        data = project.to_dict()
        assert data["status"] == "DRAFT"

    def test_shot_to_dict_serializes_status(self) -> None:
        shot = Shot.create("p1", "e1", "s1", prompt="主角登场", order=1)
        data = shot.to_dict()
        assert data["status"] == "DRAFT"
        assert data["prompt"] == "主角登场"

    def test_generation_job_defaults(self) -> None:
        job = GenerationJob.create("p1", "shot1", provider="mock")
        assert job.status == JobStatus.PENDING
        assert job.max_retries == 3
        assert job.params == {}
        data = job.to_dict()
        assert data["status"] == "PENDING"

    def test_asset_and_cost_and_qa(self) -> None:
        asset = Asset.create("p1", "video", "file:///tmp/x.mp4", "video/mp4")
        assert asset.kind == "video"
        cost = CostRecord.create("p1", 0.5, job_id="j1")
        assert cost.amount == 0.5
        report = QAReport.create("p1", "shot1", verdict="PASS")
        assert report.verdict == "PASS"
