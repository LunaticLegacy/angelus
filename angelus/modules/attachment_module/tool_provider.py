"""Agent-authorized image inspection backed by the owning Session store."""
from __future__ import annotations

from typing import TYPE_CHECKING

from llmfetcher import Tool
from llmfetcher.llm_types import ToolParameter, ToolSchema
from llmfetcher.multimodal import ImageToolResult

from ..tool_module import ToolCategory, ToolDefinition, ToolPolicy
from ..tool_module.tool_registry import ToolProviderRegistration
from ..computer_use_module import ComputerUseProvider

if TYPE_CHECKING:
    from ...core import AngelusCore
    from ..session_module import Session


class ImageToolProvider:
    """Expose native image results without filesystem or provider leakage."""

    def __init__(self, core: "AngelusCore") -> None:
        self._core = core
        self._computer = ComputerUseProvider(core)

    def materialize(self, session: "Session", policy: ToolPolicy, role: str,
                    agent_name: str | None = None) -> list[Tool]:
        if role not in {"coordinator", "worker"}:
            return []
        if session.attachments is None or session.execution is None:
            return []
        store = session.attachments
        workspace = self._core.workspaces.get(session.execution.session_id)

        def view_image(attachment_id: str = "", path: str = "") -> ImageToolResult:
            if bool(attachment_id) == bool(path):
                raise ValueError("Provide exactly one attachment_id or project-relative path")
            if path:
                if not workspace.project_path:
                    raise ValueError("This Session has no project directory")
                metadata = store.import_file(path, workspace.project_path)
            else:
                metadata = store.get(attachment_id)
            ref = {"attachment_id": metadata["attachment_id"],
                   "media_type": metadata["media_type"], "detail": "auto"}
            return ImageToolResult(
                text=f"Image {ref['attachment_id']} ({metadata['width']}×{metadata['height']}). "
                     "Use this attachment_id to reopen the image after context compaction.",
                images=[ref],
            )

        tools: list[Tool] = []
        if policy.allows("vision", "view_image"):
            tools.append(Tool(
            "view_image",
            "Read an image natively with vision. Supply a same-Session attachment_id "
            "or a path confined to the current project. Returns the actual image, not OCR text.",
            ToolSchema(properties=[
                ToolParameter("attachment_id", description="Stored image ID", required=False, default=""),
                ToolParameter("path", description="Image path inside the current project", required=False, default=""),
            ]), view_image,
            ))
        if policy.allows("vision", "computer"):
            tools.extend(self._computer.materialize(session, policy, role, agent_name))
        return tools


def image_tool_registration(core: "AngelusCore") -> ToolProviderRegistration:
    roles = frozenset({"coordinator", "worker"})
    return ToolProviderRegistration(
        id="vision", provider=ImageToolProvider(core),
        categories=(ToolCategory("vision", "图像阅读", "读取当前会话图片并交给视觉模型分析"),),
        definitions=(
            ToolDefinition("view_image", "vision", "查看图片", "读取原图；需要支持视觉输入的模型。", "vision", roles),
            ToolDefinition("computer", "vision", "使用电脑", "截图、点击、输入文本和按键。", "vision", roles),
        ),
    )
