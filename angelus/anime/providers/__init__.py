"""视频生成 Provider 层：统一接口 + 路由 + 注册表 + mock。"""

from .base import (
    ProviderError,
    ProviderTaskError,
    ProviderUnavailableError,
    VideoGenerationProvider,
)
from .mock import MockVideoProvider
from .registry import DEFAULT_FALLBACK_ORDER, REAL_PROVIDER_ENV, build_router
from .router import ProviderRouter

__all__ = [
    "ProviderError",
    "ProviderTaskError",
    "ProviderUnavailableError",
    "VideoGenerationProvider",
    "MockVideoProvider",
    "DEFAULT_FALLBACK_ORDER",
    "REAL_PROVIDER_ENV",
    "build_router",
    "ProviderRouter",
]
