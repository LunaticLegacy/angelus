"""MockVideoProvider：默认测试用 provider，真实 API 需 opt-in 环境变量。

行为：submit 立即返回 RUNNING，get_task 在若干次轮询后返回 SUCCEEDED，
可配置失败/延迟以测试 Retry Policy 与取消路径。
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from ..states import JobStatus
from .base import VideoGenerationProvider


class MockVideoProvider:
    """确定性 mock provider，默认不产生真实 API 调用。"""

    name = "mock"

    def __init__(
        self,
        *,
        succeed_after_polls: int = 2,
        fail_after_polls: Optional[int] = None,
        poll_interval: float = 0.01,
        fail_with: Optional[str] = None,
    ) -> None:
        self._succeed_after_polls = succeed_after_polls
        self._fail_after_polls = fail_after_polls
        self._poll_interval = poll_interval
        self._fail_with = fail_with or "mock provider failure"
        self._tasks: dict[str, dict[str, Any]] = {}
        self._polls: dict[str, int] = {}

    def capabilities(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "formats": ["mp4"],
            "resolutions": ["720p", "1080p"],
            "max_duration_seconds": 60.0,
            "supports_cancel": True,
        }

    def submit(self, params: dict[str, Any]) -> dict[str, Any]:
        task_id = f"mock_{uuid.uuid4().hex[:12]}"
        self._tasks[task_id] = {
            "provider_task_id": task_id,
            "status": JobStatus.RUNNING.value,
            "params": params,
            "created_at": time.time(),
        }
        self._polls[task_id] = 0
        return {"provider_task_id": task_id, "status": JobStatus.RUNNING.value}

    def get_task(self, provider_task_id: str) -> dict[str, Any]:
        if provider_task_id not in self._tasks:
            return {
                "provider_task_id": provider_task_id,
                "status": JobStatus.FAILED.value,
                "error": "unknown task",
            }
        self._polls[provider_task_id] = self._polls.get(provider_task_id, 0) + 1
        polls = self._polls[provider_task_id]
        if self._fail_after_polls is not None and polls >= self._fail_after_polls:
            self._tasks[provider_task_id]["status"] = JobStatus.FAILED.value
            self._tasks[provider_task_id]["error"] = self._fail_with
        elif polls >= self._succeed_after_polls:
            self._tasks[provider_task_id]["status"] = JobStatus.SUCCEEDED.value
            self._tasks[provider_task_id]["result"] = {
                "uri": f"file:///tmp/mock/{provider_task_id}.mp4",
                "mime_type": "video/mp4",
                "duration_seconds": float(self._tasks[provider_task_id].get("params", {}).get("duration_seconds", 5.0)),
            }
        return dict(self._tasks[provider_task_id])

    def cancel(self, provider_task_id: str) -> bool:
        if provider_task_id not in self._tasks:
            return False
        self._tasks[provider_task_id]["status"] = JobStatus.CANCELLED.value
        return True
