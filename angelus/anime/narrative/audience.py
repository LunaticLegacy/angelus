"""Audience Information：迁移自 novelist 的「读者面信息」。

面向受众的信息约束：目标受众画像、禁忌、偏好，供编排与 QA 使用。
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class AudienceInformation:
    """受众信息。"""

    target_audience: str = ""
    age_rating: str = ""  # 全年龄 / 12+ / 16+ / 18+
    preferences: list[str] = field(default_factory=list)
    taboos: list[str] = field(default_factory=list)
    platform: str = ""  # 竖屏短剧 / 横屏 / 多平台
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
