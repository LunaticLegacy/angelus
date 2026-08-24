"""Narrative Gate：PASS / WARN / FAIL。

迁移自 novelist narrative_engine 的门禁规则：
- FAIL 不得交付；WARN 可交付但需说明。
- 检查：占位符 / 子大纲覆盖 / 分镜纲中间件 / 伏笔ID合法性 / 逾期伏笔 / 角色状态回写 / 长线统计刷新。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from ..states import GateVerdict

#: 常见占位符模式（迁移自 novelist）
PLACEHOLDER_PATTERNS = [
    r"\{\{.*?\}\}",
    r"\[待.*?\]",
    r"TODO",
    r"TBD",
    r"XXX",
    r"占位",
    r"待补",
]


@dataclass
class GateCheck:
    """单条门禁检查结果。"""

    name: str
    verdict: GateVerdict
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "verdict": self.verdict.value, "detail": self.detail}


@dataclass
class GateResult:
    """门禁整体结果。"""

    verdict: GateVerdict
    checks: list[GateCheck] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.verdict == GateVerdict.PASS

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "checks": [c.to_dict() for c in self.checks],
        }


def _check_placeholders(text: str) -> list[str]:
    found: list[str] = []
    for pattern in PLACEHOLDER_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            found.append(pattern)
    return found


def check_placeholders(text: str) -> GateCheck:
    found = _check_placeholders(text)
    if found:
        return GateCheck("placeholders", GateVerdict.FAIL, f"发现占位符: {', '.join(found)}")
    return GateCheck("placeholders", GateVerdict.PASS, "无占位符")


def check_outline_coverage(episode_outline: str, scene_titles: list[str]) -> GateCheck:
    """检查子大纲覆盖：每个场景标题应能在剧集大纲中找到对应。"""
    if not episode_outline:
        return GateCheck("outline_coverage", GateVerdict.FAIL, "剧集大纲为空")
    missing = [t for t in scene_titles if t and t not in episode_outline]
    if missing:
        return GateCheck("outline_coverage", GateVerdict.WARN, f"场景未覆盖大纲: {', '.join(missing)}")
    return GateCheck("outline_coverage", GateVerdict.PASS, "场景覆盖完整")


def check_storyboard_middleware(storyboard_content: str) -> GateCheck:
    """检查分镜纲中间件：分镜纲应包含镜头级信息。"""
    if not storyboard_content:
        return GateCheck("storyboard_middleware", GateVerdict.FAIL, "分镜纲为空")
    if len(storyboard_content.strip()) < 20:
        return GateCheck("storyboard_middleware", GateVerdict.WARN, "分镜纲过短")
    return GateCheck("storyboard_middleware", GateVerdict.PASS, "分镜纲完整")


def check_foreshadowing_ids(used_ids: list[str], valid_ids: set[str]) -> GateCheck:
    """检查伏笔 ID 合法性。"""
    invalid = [i for i in used_ids if i not in valid_ids]
    if invalid:
        return GateCheck("foreshadowing_ids", GateVerdict.FAIL, f"非法伏笔ID: {', '.join(invalid)}")
    return GateCheck("foreshadowing_ids", GateVerdict.PASS, "伏笔ID合法")


def check_overdue_foreshadowing(overdue_ids: list[str]) -> GateCheck:
    """检查逾期伏笔。"""
    if overdue_ids:
        return GateCheck("overdue_foreshadowing", GateVerdict.WARN, f"逾期伏笔: {', '.join(overdue_ids)}")
    return GateCheck("overdue_foreshadowing", GateVerdict.PASS, "无逾期伏笔")


def check_character_state_sync(character_updates: list[str]) -> GateCheck:
    """检查角色状态回写。"""
    if not character_updates:
        return GateCheck("character_state_sync", GateVerdict.WARN, "本集无角色状态更新")
    return GateCheck("character_state_sync", GateVerdict.PASS, f"角色状态已回写: {len(character_updates)} 项")


def run_gate(
    *,
    text: str = "",
    episode_outline: str = "",
    scene_titles: Optional[list[str]] = None,
    storyboard_content: str = "",
    used_foreshadowing_ids: Optional[list[str]] = None,
    valid_foreshadowing_ids: Optional[set[str]] = None,
    overdue_foreshadowing_ids: Optional[list[str]] = None,
    character_updates: Optional[list[str]] = None,
) -> GateResult:
    """运行完整门禁，返回 PASS/WARN/FAIL。"""
    checks: list[GateCheck] = []
    checks.append(check_placeholders(text))
    checks.append(check_outline_coverage(episode_outline, scene_titles or []))
    checks.append(check_storyboard_middleware(storyboard_content))
    if used_foreshadowing_ids is not None and valid_foreshadowing_ids is not None:
        checks.append(check_foreshadowing_ids(used_foreshadowing_ids, valid_foreshadowing_ids))
    if overdue_foreshadowing_ids is not None:
        checks.append(check_overdue_foreshadowing(overdue_foreshadowing_ids))
    if character_updates is not None:
        checks.append(check_character_state_sync(character_updates))

    if any(c.verdict == GateVerdict.FAIL for c in checks):
        verdict = GateVerdict.FAIL
    elif any(c.verdict == GateVerdict.WARN for c in checks):
        verdict = GateVerdict.WARN
    else:
        verdict = GateVerdict.PASS
    return GateResult(verdict=verdict, checks=checks)
