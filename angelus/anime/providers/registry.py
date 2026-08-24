"""Provider 注册表：集中管理 provider 实例与默认回退顺序。

真实 API 需 opt-in 环境变量（ANIME_REAL_PROVIDER=1）；默认只注册 mock。
"""

from __future__ import annotations

import os
from typing import Optional

from .base import VideoGenerationProvider
from .mock import MockVideoProvider
from .router import ProviderRouter

#: 默认回退顺序（高优先在前）
DEFAULT_FALLBACK_ORDER = ["mock"]

#: 真实 provider 的 opt-in 开关
REAL_PROVIDER_ENV = "ANIME_REAL_PROVIDER"


def build_router(real_provider: Optional[VideoGenerationProvider] = None) -> ProviderRouter:
    """构建默认 ProviderRouter。

    - 默认只注册 mock（测试安全）。
    - 当 ANIME_REAL_PROVIDER=1 且传入 real_provider 时，将其注册为高优先。
    """
    router = ProviderRouter()
    router.register(MockVideoProvider())
    if os.environ.get(REAL_PROVIDER_ENV) == "1" and real_provider is not None:
        router.register(real_provider)
    return router
