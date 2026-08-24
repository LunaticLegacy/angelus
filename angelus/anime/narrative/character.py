"""Character State 结构化：迁移自 novelist 的「当前角色状态」概念。

角色状态是结构化数据（而非自由文本），支持回写与门禁检查。
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional


@dataclass
class CharacterState:
    """单个角色的结构化状态。"""

    id: str
    project_id: str
    name: str
    role: str = ""  # 主角/配角/反派/工具人
    status: str = "alive"  # alive / dead / missing / unknown
    location: str = ""
    relationships: dict[str, str] = field(default_factory=dict)  # 角色ID -> 关系描述
    goals: list[str] = field(default_factory=list)
    secrets: list[str] = field(default_factory=list)
    notes: str = ""
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CharacterStateStore:
    """角色状态存储：按项目维护结构化角色状态。"""

    def __init__(self) -> None:
        self._states: dict[str, dict[str, CharacterState]] = {}  # project_id -> {char_id -> state}

    def upsert(self, project_id: str, state: CharacterState) -> CharacterState:
        self._states.setdefault(project_id, {})[state.id] = state
        return state

    def get(self, project_id: str, char_id: str) -> Optional[CharacterState]:
        return self._states.get(project_id, {}).get(char_id)

    def list(self, project_id: str) -> list[CharacterState]:
        return list(self._states.get(project_id, {}).values())

    def apply_updates(self, project_id: str, updates: list[dict[str, Any]]) -> list[str]:
        """应用一批角色状态更新，返回被更新的角色名列表。"""
        updated: list[str] = []
        for update in updates:
            char_id = update.get("id")
            if not char_id:
                continue
            state = self.get(project_id, char_id)
            if state is None:
                state = CharacterState(id=char_id, project_id=project_id, name=update.get("name", char_id))
            for key, value in update.items():
                if key in ("id", "project_id"):
                    continue
                if hasattr(state, key):
                    setattr(state, key, value)
            self.upsert(project_id, state)
            updated.append(state.name)
        return updated
