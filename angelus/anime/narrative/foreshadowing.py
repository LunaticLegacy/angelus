"""伏笔管理：迁移自 novelist 的 05-长线伏笔.csv。

CSV 表头：id,主线,伏笔内容,首次埋设章节,计划回收章节,实际回收章节,状态,关联人物,备注
状态：埋设中/回收中/已回收/弃用
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

FORESHADOWING_HEADERS = [
    "id", "主线", "伏笔内容", "首次埋设章节", "计划回收章节", "实际回收章节", "状态", "关联人物", "备注",
]

FORESHADOWING_STATUSES = {"埋设中", "回收中", "已回收", "弃用"}
#: dataclass 字段名 -> CSV 中文表头
FORESHADOWING_FIELD_MAP = {
    "id": "id",
    "content": "伏笔内容",
    "mainline": "主线",
    "planted_chapter": "首次埋设章节",
    "planned_recovery_chapter": "计划回收章节",
    "actual_recovery_chapter": "实际回收章节",
    "status": "状态",
    "related_characters": "关联人物",
    "notes": "备注",
}



@dataclass
class Foreshadowing:
    """单条伏笔。"""

    id: str
    content: str
    mainline: str = ""
    planted_chapter: str = ""
    planned_recovery_chapter: str = ""
    actual_recovery_chapter: str = ""
    status: str = "埋设中"
    related_characters: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_foreshadowing_csv(text: str) -> list[Foreshadowing]:
    """解析伏笔 CSV 文本。"""
    reader = csv.DictReader(io.StringIO(text))
    result: list[Foreshadowing] = []
    for row in reader:
        result.append(
            Foreshadowing(
                id=row.get("id", "").strip(),
                content=row.get("伏笔内容", "").strip(),
                mainline=row.get("主线", "").strip(),
                planted_chapter=row.get("首次埋设章节", "").strip(),
                planned_recovery_chapter=row.get("计划回收章节", "").strip(),
                actual_recovery_chapter=row.get("实际回收章节", "").strip(),
                status=row.get("状态", "埋设中").strip(),
                related_characters=row.get("关联人物", "").strip(),
                notes=row.get("备注", "").strip(),
            )
        )
    return result


def serialize_foreshadowing_csv(items: list[Foreshadowing]) -> str:
    """序列化伏笔列表为 CSV 文本。"""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=FORESHADOWING_HEADERS)
    writer.writeheader()
    for item in items:
        d = item.to_dict()
        writer.writerow({FORESHADOWING_FIELD_MAP[k]: v for k, v in d.items() if k in FORESHADOWING_FIELD_MAP})
    return buf.getvalue()


def overdue_foreshadowing(items: list[Foreshadowing], current_chapter: str) -> list[str]:
    """返回逾期未回收的伏笔 ID 列表。"""
    overdue: list[str] = []
    for item in items:
        if item.status in ("埋设中", "回收中") and item.planned_recovery_chapter:
            try:
                if int(item.planned_recovery_chapter) < int(current_chapter):
                    overdue.append(item.id)
            except ValueError:
                continue
    return overdue


def valid_foreshadowing_ids(items: list[Foreshadowing]) -> set[str]:
    """返回合法伏笔 ID 集合。"""
    return {item.id for item in items if item.id}
