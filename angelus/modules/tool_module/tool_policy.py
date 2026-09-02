"""Session-owned interpretation and migration of persisted tool grants."""
from __future__ import annotations

from dataclasses import dataclass


_LEGACY_TOOL_IDS = {
    "set_task_plan": "plan_upsert",
    "update_task_status": "plan_upsert",
    "read_task_plan": "plan_read",
    "dynamic_add_connection": "swarm_connect",
    "dynamic_remove_connection": "swarm_disconnect",
    "dynamic_set_mapper": "swarm_set_mapper",
    "dynamic_set_router": "swarm_set_router",
}


@dataclass(frozen=True)
class ToolPolicy:
    """Effective category-and-tool grants for one future Agent construction.

    Attributes:
        categories: Explicitly granted category IDs.
        tools: Explicitly granted canonical Tool IDs.
    """

    categories: frozenset[str]
    tools: frozenset[str]

    @classmethod
    def from_profile(cls, value: object) -> "ToolPolicy":
        """Decode profile grants and migrate recognized historic Tool names.

        Args:
            value: Raw ``tool_permissions`` field from a validated profile.

        Returns:
            Explicit effective grants using canonical registry Tool IDs.
        """
        if not isinstance(value, dict):
            return cls(frozenset(), frozenset())
        raw_categories = value.get("categories")
        raw_tools = value.get("tools")
        categories = frozenset(
            name for name, enabled in raw_categories.items()
            if isinstance(name, str) and enabled is True
        ) if isinstance(raw_categories, dict) else frozenset()
        tools = frozenset(
            _LEGACY_TOOL_IDS.get(name, name)
            for name, enabled in raw_tools.items()
            if isinstance(name, str) and enabled is True
        ) if isinstance(raw_tools, dict) else frozenset()
        return cls(categories, tools)

    def allows(self, category_id: str, tool_id: str) -> bool:
        """Return whether both grants needed to expose a Tool are present.

        Args:
            category_id: Category owning the Tool.
            tool_id: Canonical Tool identity.

        Returns:
            ``True`` when the Agent may receive the Tool.
        """
        return category_id in self.categories and tool_id in self.tools

    def fingerprint(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Return a deterministic configuration identity for Agent rebuilding.

        Returns:
            Sorted category and Tool grant tuples.
        """
        return tuple(sorted(self.categories)), tuple(sorted(self.tools))
