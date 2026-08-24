"""VideoGenerationProvider Protocol 与统一任务状态。

Provider 统一接口：
    capabilities / submit / get_task / cancel

统一任务状态：PENDING / QUEUED / RUNNING / SUCCEEDED / FAILED / CANCELLED / EXPIRED
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ..states import JobStatus


@runtime_checkable
class VideoGenerationProvider(Protocol):
    """视频生成 Provider 统一接口。"""

    name: str

    def capabilities(self) -> dict[str, Any]:
        """返回 provider 能力描述（支持的格式/分辨率/时长范围等）。"""
        ...

    def submit(self, params: dict[str, Any]) -> dict[str, Any]:
        """提交一个生成任务，返回 provider 侧任务句柄。

        Returns:
            {"provider_task_id": str, "status": JobStatus, ...}
        """
        ...

    def get_task(self, provider_task_id: str) -> dict[str, Any]:
        """查询任务状态。

        Returns:
            {"provider_task_id": str, "status": JobStatus, "result": {...} | None, "error": str | None}
        """
        ...

    def cancel(self, provider_task_id: str) -> bool:
        """取消任务，返回是否成功。"""
        ...


class ProviderError(RuntimeError):
    """Provider 层错误基类。"""


class ProviderUnavailableError(ProviderError):
    """Provider 不可用（连接失败/未配置）。"""


class ProviderTaskError(ProviderError):
    """Provider 任务执行错误。"""
