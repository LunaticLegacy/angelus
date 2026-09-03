"""Registration for built-in project-aware llmfetcher tools."""
from __future__ import annotations

from typing import TYPE_CHECKING

from llmfetcher import LLMBackendConfig, LLMFetcher, Tool
from llmfetcher.rag_module_tlb import create_tlb_rag_tool
from llmfetcher.tools import create_shell_tools

from .tool_models import ToolCategory, ToolDefinition
from .tool_policy import ToolPolicy
from .tool_registry import ToolProviderRegistration

if TYPE_CHECKING:
    from ...core import AngelusCore
    from ..session_module import Session


class RuntimeToolProvider:
    """Materialize built-in tools that require Session profile state."""

    def __init__(self, core: "AngelusCore") -> None:
        """Bind the provider to its process-owned configuration authorities.

        Args:
            core: Composition root resolving workspace/profile/connector data.
        """
        self._core = core

    def materialize(self, session: "Session", policy: ToolPolicy, role: str) -> list[Tool]:
        """Build only explicitly authorized project-scoped runtime tools.

        Args:
            session: Session owning the receiving Agent.
            policy: Effective category and individual-tool grants.
            role: Coordinator or worker role receiving tools.

        Returns:
            Concrete safe tools; project-dependent tools are absent when the
            Session has no project directory.
        """
        if role not in {"coordinator", "worker"}:
            return []
        # Artifact inspection is an internal consequence of receiving a large
        # tool result, not a project capability. It is always available to the
        # same Session and never accepts host filesystem paths.
        if session.artifacts is None:
            raise RuntimeError("Session artifact storage is not configured")
        tools = session.artifacts.tools()
        workspace = self._core.workspaces.get(session.execution.session_id) if session.execution else None
        project_path = workspace.project_path if workspace is not None else None
        if project_path is None:
            return tools
        if policy.allows("shell", "shell"):
            tools.extend(create_shell_tools(sandbox_cwd=str(project_path)))
        if policy.allows("file_discovery", "tlb_rag"):
            profile = self._core.run_profiles.effective(session.execution.session_id)
            connector_id = profile.get("connector_id")
            if isinstance(connector_id, str) and connector_id:
                tools.append(create_tlb_rag_tool(
                    project_path,
                    LLMFetcher([LLMBackendConfig(
                        name="tlb_rag", provider=profile["provider"], model=profile["model"],
                        api_key=self._core.connectors.api_key(connector_id),
                        api_url=profile["api_url"] or None, max_retries=profile["max_retries"],
                    )]),
                ))
        return tools


def runtime_tool_registration(core: "AngelusCore") -> ToolProviderRegistration:
    """Return built-in runtime registration for the application's registry.

    Args:
        core: Process composition root used by project-aware materialization.

    Returns:
        One provider registration for Shell and TLB project retrieval.
    """
    return ToolProviderRegistration(
        id="runtime",
        provider=RuntimeToolProvider(core),
        categories=(
            ToolCategory("file_discovery", "文件检索", "在当前项目中检索 INDEX.md 与相关文件。"),
            ToolCategory("shell", "Shell", "在绑定项目目录中执行受限命令。"),
            ToolCategory("turn_control", "回合控制", "允许 Agent 在安全边界结束当前回合。"),
        ),
        definitions=(
            ToolDefinition("tlb_rag", "file_discovery", "项目检索", "从项目文件中检索相关上下文。", "runtime", frozenset({"coordinator", "worker"})),
            ToolDefinition("shell", "shell", "执行 Shell 命令", "在绑定项目目录中执行命令。", "runtime", frozenset({"coordinator", "worker"})),
            ToolDefinition("stop_turn", "turn_control", "结束当前回合", "在安全边界停止继续调用工具。", "runtime", frozenset({"coordinator", "worker"})),
        ),
    )
