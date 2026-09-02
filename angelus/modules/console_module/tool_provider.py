"""Console registration for the unified ToolRegistry."""
from __future__ import annotations

from typing import TYPE_CHECKING

from llmfetcher import Tool

from ..tool_module import ToolCategory, ToolDefinition, ToolPolicy
from ..tool_module.tool_registry import ToolProviderRegistration
from .console_tools import SessionConsoleTools, ToolPermissionPolicy

if TYPE_CHECKING:
    from ...core import AngelusCore


class ConsoleToolProvider:
    """Materialize the Session-console plan and topology tools."""

    def __init__(self, core: "AngelusCore") -> None:
        """Retain the composition root used to make dynamic workers.

        Args:
            core: Application owner of Session profiles and connector secrets.
        """
        self._core = core

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
            self._core.session_service.create_runtime_worker,
        ).build()


def console_tool_registration(core: "AngelusCore") -> ToolProviderRegistration:
    """Return Console's complete, single registration with the Tool Registry.

    Args:
        core: Composition root used to construct dynamic Session workers.

    Returns:
        Provider registration containing its categories and Tool definitions.
    """
    return ToolProviderRegistration(
        id="console",
        provider=ConsoleToolProvider(core),
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
            ToolDefinition("swarm_add_worker", "swarm", "添加 Worker", "创建并持久化一个动态 Worker。", "console", frozenset({"coordinator", "worker"})),
            ToolDefinition("swarm_remove_worker", "swarm", "移除 Worker", "移除 Worker 及其图连接。", "console", frozenset({"coordinator", "worker"})),
            ToolDefinition("swarm_info", "swarm", "读取 Swarm 信息", "查看当前执行图和调度信息。", "console", frozenset({"coordinator", "worker"})),
            ToolDefinition("dispatch_subagent", "swarm", "分发子任务", "创建 Worker 并立即分发一个结构化任务。", "console", frozenset({"coordinator", "worker"})),
            ToolDefinition("dispatch_subagents", "swarm", "批量分发子任务", "创建多个 Worker 并分发独立任务。", "console", frozenset({"coordinator", "worker"})),
            ToolDefinition("revive_agent", "swarm", "复用 Worker", "为已完成的任务 Worker 分发新任务。", "console", frozenset({"coordinator", "worker"})),
            ToolDefinition("wait_for_reports", "swarm", "等待任务报告", "等待已分发 Worker 的结构化报告。", "console", frozenset({"coordinator", "worker"})),
        ),
    )
