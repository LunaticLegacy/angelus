"""ProviderRouter：explicit provider + auto fallback。

- explicit provider：调用方指定 provider 名，找不到即报错。
- auto fallback：首选 provider 不可用时按优先级列表回退。
"""

from __future__ import annotations

from typing import Any, Optional

from .base import ProviderUnavailableError, VideoGenerationProvider


class ProviderRouter:
    """按名称解析 provider，支持显式选择与自动回退。"""

    def __init__(self, providers: Optional[dict[str, VideoGenerationProvider]] = None) -> None:
        #: name -> provider 实例
        self._providers: dict[str, VideoGenerationProvider] = dict(providers or {})

    def register(self, provider: VideoGenerationProvider) -> None:
        self._providers[provider.name] = provider

    def unregister(self, name: str) -> None:
        self._providers.pop(name, None)

    def names(self) -> list[str]:
        return sorted(self._providers.keys())

    def get(self, name: str) -> VideoGenerationProvider:
        provider = self._providers.get(name)
        if provider is None:
            raise ProviderUnavailableError(f"provider 未注册: {name}")
        return provider

    def resolve(self, name: Optional[str] = None, fallback_order: Optional[list[str]] = None) -> VideoGenerationProvider:
        """显式选择或按 fallback_order 自动回退。

        Args:
            name: 显式 provider 名；为 None 时使用 fallback_order。
            fallback_order: 回退优先级列表（高优先在前）。

        Raises:
            ProviderUnavailableError: 全部候选均不可用。
        """
        if name:
            return self.get(name)
        order = fallback_order or list(self._providers.keys())
        for candidate in order:
            provider = self._providers.get(candidate)
            if provider is not None:
                return provider
        raise ProviderUnavailableError("没有可用的 provider")
