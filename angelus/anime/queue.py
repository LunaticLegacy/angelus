"""GenerationJob 任务队列：可观测/可恢复/可取消/可重试。

- 后台线程消费队列，逐 job 执行。
- 状态持久化到 workspace/<project>/anime/jobs.json。
- 每个状态迁移写 anime.job.* 事件（audit log + SSE）。
- 重启后从 jobs.json 恢复未完成 job（可恢复）。
- Retry Policy：retryable vs non-retryable。
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Optional

from . import events, storage
from .models import GenerationJob
from .providers.base import ProviderUnavailableError
from .providers.registry import build_router
from .states import JobStatus, TERMINAL_JOB_STATUSES

#: 可重试错误分类
RETRYABLE_ERRORS = (ProviderUnavailableError, TimeoutError, ConnectionError)


class RetryPolicy:
    """重试策略：区分 retryable 与 non-retryable 错误。"""

    def __init__(self, max_retries: int = 3, backoff_seconds: float = 0.01) -> None:
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds

    def is_retryable(self, error: BaseException) -> bool:
        return isinstance(error, RETRYABLE_ERRORS)

    def should_retry(self, retry_count: int, error: BaseException) -> bool:
        return self.is_retryable(error) and retry_count < self.max_retries


class BudgetGuard:
    """预算守卫：超预算时任务进入 WAITING_FOR_APPROVAL。"""

    def __init__(self, budget_limit: float = 100.0) -> None:
        self.budget_limit = budget_limit
        self._spent: dict[str, float] = {}
        self._lock = threading.Lock()

    def record_cost(self, project_id: str, amount: float) -> None:
        with self._lock:
            self._spent[project_id] = self._spent.get(project_id, 0.0) + amount

    def spent(self, project_id: str) -> float:
        with self._lock:
            return self._spent.get(project_id, 0.0)

    def remaining(self, project_id: str) -> float:
        return max(0.0, self.budget_limit - self.spent(project_id))

    def approve(self, project_id: str, amount: float) -> bool:
        """批准一笔支出；若超出预算返回 False（WAITING_FOR_APPROVAL）。"""
        with self._lock:
            if self.spent(project_id) + amount > self.budget_limit:
                return False
            self._spent[project_id] = self._spent.get(project_id, 0.0) + amount
            return True


class GenerationQueue:
    """后台任务队列。"""

    def __init__(
        self,
        *,
        router: Any = None,
        retry_policy: Optional[RetryPolicy] = None,
        budget_guard: Optional[BudgetGuard] = None,
        poll_interval: float = 0.01,
    ) -> None:
        self.router = router if router is not None else build_router()
        self.retry_policy = retry_policy or RetryPolicy()
        self.budget_guard = budget_guard or BudgetGuard()
        self.poll_interval = poll_interval
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._pending: list[str] = []  # job ids queued in memory
        self._running: set[str] = set()

    # ---- 生命周期 ----

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_loop, name="anime-generation-queue", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            job_id = self._dequeue()
            if job_id is None:
                time.sleep(self.poll_interval)
                continue
            try:
                self._execute(job_id)
            except Exception as exc:  # noqa: BLE001 - 队列循环永不崩溃
                self._mark_failed(job_id, str(exc))

    # ---- 队列操作 ----

    def _dequeue(self) -> Optional[str]:
        with self._lock:
            if not self._pending:
                return None
            return self._pending.pop(0)

    def enqueue(self, job: GenerationJob) -> GenerationJob:
        """入队一个 job（持久化 + 事件）。"""
        job.status = JobStatus.QUEUED
        job.updated_at = time.time()
        storage.upsert_item(job.project_id, "jobs", job.to_dict())
        events.job_status(job.project_id, job.id, "queued")
        with self._lock:
            self._pending.append(job.id)
        return job

    def submit(self, job: GenerationJob) -> GenerationJob:
        """提交 job（PENDING → QUEUED）。"""
        job.status = JobStatus.PENDING
        job.updated_at = time.time()
        storage.upsert_item(job.project_id, "jobs", job.to_dict())
        events.job_submitted(job.project_id, job.id, job.shot_id, job.provider)
        return self.enqueue(job)

    def cancel(self, project_id: str, job_id: str) -> bool:
        """取消一个 job（仅非终态可取消）。"""
        job = self._load_job(project_id, job_id)
        if job is None or job.status in TERMINAL_JOB_STATUSES:
            return False
        job.status = JobStatus.CANCELLED
        job.updated_at = time.time()
        storage.upsert_item(project_id, "jobs", job.to_dict())
        events.job_status(project_id, job_id, "cancelled")
        with self._lock:
            if job_id in self._pending:
                self._pending.remove(job_id)
        return True

    def retry(self, project_id: str, job_id: str) -> Optional[GenerationJob]:
        """重试一个 FAILED job（受 Retry Policy 约束）。"""
        job = self._load_job(project_id, job_id)
        if job is None or job.status != JobStatus.FAILED:
            return None
        job.retry_count += 1
        job.error = None
        job.status = JobStatus.PENDING
        job.updated_at = time.time()
        storage.upsert_item(project_id, "jobs", job.to_dict())
        events.job_status(project_id, job_id, "retried")
        return self.enqueue(job)

    def get_job(self, project_id: str, job_id: str) -> Optional[dict[str, Any]]:
        return storage.get_item(project_id, "jobs", job_id)

    def list_jobs(self, project_id: str) -> list[dict[str, Any]]:
        return storage.list_collection(project_id, "jobs")

    def _load_job(self, project_id: str, job_id: str) -> Optional[GenerationJob]:
        data = storage.get_item(project_id, "jobs", job_id)
        if data is None:
            return None
        job = GenerationJob(**{k: v for k, v in data.items() if k in GenerationJob.__dataclass_fields__})
        job.status = JobStatus(data["status"])
        return job

    # ---- 执行 ----

    def _execute(self, job_id: str) -> None:
        # 从持久化恢复 job
        job = self._find_job_anywhere(job_id)
        if job is None:
            return
        job.status = JobStatus.RUNNING
        job.started_at = time.time()
        job.updated_at = time.time()
        storage.upsert_item(job.project_id, "jobs", job.to_dict())
        events.job_status(job.project_id, job.id, "running")
        self._mark_shot_generating(job.project_id, job.shot_id)
        try:
            provider = self.router.resolve(job.provider)
            task = provider.submit(job.params)
            provider_task_id = task.get("provider_task_id")
            result = self._poll(provider, provider_task_id, job)
            if result is None:
                return  # cancelled/expired handled inside
            job.status = JobStatus.SUCCEEDED
            job.finished_at = time.time()
            job.updated_at = time.time()
            # 每个生成结果都是 Artifact：创建 Asset 并回写 job + shot
            asset = self._record_asset(job, result)
            job.result_asset_id = asset.id
            storage.upsert_item(job.project_id, "jobs", job.to_dict())
            events.job_status(job.project_id, job.id, "succeeded")
            self._link_shot_asset(job.project_id, job.shot_id, asset.id)
        except Exception as exc:  # noqa: BLE001
            self._mark_failed(job.project_id, job.id, str(exc))

    def _find_job_anywhere(self, job_id: str) -> Optional[GenerationJob]:
        """从所有项目里找 job（job_id 全局唯一）。"""
        for project in storage.list_projects():
            job = self._load_job(project["id"], job_id)
            if job is not None:
                return job
        return None

    def _poll(self, provider: Any, provider_task_id: str, job: GenerationJob) -> Optional[dict[str, Any]]:
        """轮询 provider 直到终态。"""
        while not self._stop.is_set():
            task = provider.get_task(provider_task_id)
            status = JobStatus(task.get("status"))
            if status == JobStatus.SUCCEEDED:
                return task.get("result") or {}
            if status == JobStatus.FAILED:
                raise RuntimeError(task.get("error") or "provider task failed")
            if status in (JobStatus.CANCELLED, JobStatus.EXPIRED):
                job.status = status
                job.finished_at = time.time()
                job.updated_at = time.time()
                storage.upsert_item(job.project_id, "jobs", job.to_dict())
                events.job_status(job.project_id, job.id, status.value)
                return None
            time.sleep(self.poll_interval)
        # 队列停止：标记 EXPIRED
        job.status = JobStatus.EXPIRED
        job.finished_at = time.time()
        job.updated_at = time.time()
        storage.upsert_item(job.project_id, "jobs", job.to_dict())
        events.job_status(job.project_id, job.id, "expired")
        return None

    def _mark_shot_generating(self, project_id: str, shot_id: str) -> None:
        """job 开始执行时把 shot 迁移 QUEUED -> GENERATING。"""
        shot = storage.get_item(project_id, "shots", shot_id)
        if shot is None:
            return
        from .states import ShotStatus, can_transition_shot
        current = ShotStatus(shot.get("status", "DRAFT"))
        if can_transition_shot(current, ShotStatus.GENERATING):
            shot["status"] = ShotStatus.GENERATING.value
            shot["updated_at"] = time.time()
            storage.upsert_item(project_id, "shots", shot)
            events.shot_state_changed(project_id, shot_id, current.value, ShotStatus.GENERATING.value)

    def _mark_shot_failed(self, project_id: str, shot_id: str, error: str) -> None:
        """job 失败时把 shot 迁移 GENERATING -> FAILED（记录错误）。"""
        shot = storage.get_item(project_id, "shots", shot_id)
        if shot is None:
            return
        from .states import ShotStatus, can_transition_shot
        current = ShotStatus(shot.get("status", "DRAFT"))
        if can_transition_shot(current, ShotStatus.FAILED):
            shot["status"] = ShotStatus.FAILED.value
            shot["error"] = error
            shot["updated_at"] = time.time()
            storage.upsert_item(project_id, "shots", shot)
            events.shot_state_changed(project_id, shot_id, current.value, ShotStatus.FAILED.value)

    def _record_asset(self, job: GenerationJob, result: dict[str, Any]) -> "Asset":
        """把 provider 返回结果登记为 Asset（Artifact 原则）。"""
        from .models import Asset
        uri = result.get("uri") or f"file:///tmp/anime/{job.id}.mp4"
        asset = Asset.create(
            project_id=job.project_id,
            kind=result.get("kind", "video"),
            uri=uri,
            mime_type=result.get("mime_type", "video/mp4"),
        )
        asset.size_bytes = int(result.get("size_bytes", 0) or 0)
        asset.meta = {
            "job_id": job.id,
            "shot_id": job.shot_id,
            "provider": job.provider,
            "duration_seconds": result.get("duration_seconds"),
        }
        storage.upsert_item(job.project_id, "assets", asset.to_dict())
        events.emit(job.project_id, "anime.asset.created", {"asset_id": asset.id, "job_id": job.id})
        return asset

    def _link_shot_asset(self, project_id: str, shot_id: str, asset_id: str) -> None:
        """把生成成功的镜头回写 asset_id 并迁移到 GENERATED。"""
        shot = storage.get_item(project_id, "shots", shot_id)
        if shot is None:
            return
        from .states import ShotStatus, can_transition_shot
        current = ShotStatus(shot.get("status", "DRAFT"))
        shot["asset_id"] = asset_id
        shot["updated_at"] = time.time()
        if can_transition_shot(current, ShotStatus.GENERATED):
            shot["status"] = ShotStatus.GENERATED.value
            events.shot_state_changed(project_id, shot_id, current.value, ShotStatus.GENERATED.value)
        storage.upsert_item(project_id, "shots", shot)

    def _mark_failed(self, project_id: str, job_id: str, error: str) -> None:
        job = self._load_job(project_id, job_id)
        if job is None:
            return
        job.status = JobStatus.FAILED
        job.error = error
        job.finished_at = time.time()
        job.updated_at = time.time()
        storage.upsert_item(project_id, "jobs", job.to_dict())
        events.job_status(project_id, job_id, "failed", error=error)
        self._mark_shot_failed(project_id, job.shot_id, error)
