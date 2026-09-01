"""Console registration for the unified ToolRegistry."""
from __future__ import annotations

from llmfetcher import Tool

from ..tool_module import ToolCategory, ToolDefinition, ToolPolicy
from ..tool_module.tool_registry import ToolProviderRegistration
from .console_tools import SessionConsoleTools, ToolPermissionPolicy


class ConsoleToolProvider:
    """Materialize the Session-console plan and topology tools."""

    def materialize(self, session: object, policy: ToolPolicy, role: str) -> list[Tool]:
        """Build Console Tools authorized for the requested Agent role.

        Args:
            session: Session aggregate that owns console mutations.
            policy: Effective Session grants.
            role: Agent role requesting the Tools.

        Returns:
            Authorized concrete Console Tools, or no Tools for an unknown role.
        """
        if role not in {"coordinator", "worker"}:
            return []
        return SessionConsoleTools(
            session,
            ToolPermissionPolicy(policy.categories, policy.tools),
        ).build()


def console_tool_registration() -> ToolProviderRegistration:
    """Return Console's complete, single registration with the Tool Registry.

    Returns:
        Provider registration containing its categories and Tool definitions.
    """
    return ToolProviderRegistration(
        id="console",
        provider=ConsoleToolProvider(),
        categories=(
            ToolCategory("planning", "任务计划", "创建、更新并读取 Session 计划。"),
            ToolCategory("swarm", "Swarm 协作", "安全修改当前 Session 的动态拓扑。"),
        ),
        definitions=(
            ToolDefinition("plan_upsert", "planning", "创建或更新计划项", "写入任务状态与标题。", "console", frozenset({"coordinator", "worker"})),
            ToolDefinition("plan_read", "planning", "读取任务计划", "读取当前 Session 的持久化计划。", "console", frozenset({"coordinator", "worker"})),
            ToolDefinition("swarm_connect", "swarm", "添加连接", "新增动态依赖边。", "console", frozenset({"coordinator", "worker"})),
            ToolDefinition("swarm_disconnect", "swarm", "移除连接", "删除动态依赖边。", "console", frozenset({"coordinator", "worker"})),
            ToolDefinition("swarm_set_mapper", "swarm", "设置聚合器", "配置输入汇总方式。", "console", frozenset({"coordinator", "worker"})),
            ToolDefinition("swarm_set_router", "swarm", "设置路由", "配置固定后继目标。", "console", frozenset({"coordinator", "worker"})),
        ),
    )
