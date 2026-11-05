"""ToolRegistry provider for bounded Session workspace file operations."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from llmfetcher import Tool
from llmfetcher.llm_types import ToolParameter, ToolSchema

from ..tool_module import ToolCategory, ToolDefinition, ToolPolicy
from ..tool_module.tool_registry import ToolProviderRegistration
from .file_service import FileService

if TYPE_CHECKING:
    from ...core import AngelusCore
    from ..session_module.session_handler import Session


def _schema(*parameters: ToolParameter) -> ToolSchema:
    return ToolSchema(properties=list(parameters))


class FileToolProvider:
    def __init__(self, core: "AngelusCore") -> None:
        self._core = core

    def materialize(self, session: "Session", policy: ToolPolicy, role: str, agent_name: str | None = None) -> list[Tool]:
        if role not in {"coordinator", "worker"}:
            return []
        session_id = session.execution.session_id if session.execution is not None else ""
        workspace = self._core.workspaces.get(session_id)
        service = FileService(workspace.project_path)

        def result(call):
            def handler(**kwargs: object) -> str:
                try:
                    return json.dumps(call(**kwargs), ensure_ascii=False)
                except (OSError, UnicodeError, ValueError) as exc:
                    return f"Error: {exc}"
            return handler

        tools: list[Tool] = []
        if policy.allows("file_discovery", "file_list"):
            tools.append(Tool("file_list", "List files and directories inside the current Session workspace.", _schema(ToolParameter("path", description="Relative directory path", required=False, default="."), ToolParameter("recursive", type="boolean", description="Whether to descend into subdirectories", required=False, default=False), ToolParameter("depth", type="integer", description="Maximum recursive depth", required=False, default=2), ToolParameter("pattern", description="Optional filename glob", required=False, default=""), ToolParameter("limit", type="integer", description="Maximum entries", required=False, default=100)), result(service.list)))
        if policy.allows("file_discovery", "file_read"):
            tools.append(Tool("file_read", "Read a bounded text range from a file inside the current Session workspace.", _schema(ToolParameter("path", description="Relative file path"), ToolParameter("start_line", type="integer", description="First line to read", required=False, default=1), ToolParameter("max_lines", type="integer", description="Maximum lines", required=False, default=200), ToolParameter("max_chars", type="integer", description="Maximum characters", required=False, default=30000)), result(service.read)))
        if policy.allows("file_discovery", "file_search"):
            tools.append(Tool("file_search", "Search bounded text matches inside files in the current Session workspace.", _schema(ToolParameter("query", description="Text to search for"), ToolParameter("path", description="Relative directory path", required=False, default="."), ToolParameter("pattern", description="Filename glob", required=False, default="*.py"), ToolParameter("limit", type="integer", description="Maximum matches", required=False, default=50), ToolParameter("context_lines", type="integer", description="Context lines around each match", required=False, default=2)), result(service.search)))
        if policy.allows("file_write", "file_write"):
            tools.append(Tool("file_write", "Create or explicitly update a text file inside the current Session workspace.", _schema(ToolParameter("path", description="Relative file path"), ToolParameter("content", description="Text content"), ToolParameter("mode", description="create, overwrite, or append", required=False, default="create")), result(service.write)))
        return tools


def file_tool_registration(core: "AngelusCore") -> ToolProviderRegistration:
    return ToolProviderRegistration(
        id="files",
        provider=FileToolProvider(core),
        categories=(
            ToolCategory("file_discovery", "文件检索", "在当前 Session 项目工作区内列出、读取和搜索文件。"),
            ToolCategory("file_write", "文件写入", "在当前 Session 项目工作区内创建或修改文本文件。"),
        ),
        definitions=(
            ToolDefinition("file_list", "file_discovery", "列出文件", "列出当前工作区内的文件和目录。", "files", frozenset({"coordinator", "worker"})),
            ToolDefinition("file_read", "file_discovery", "读取文件", "读取工作区内文件的受限文本范围。", "files", frozenset({"coordinator", "worker"})),
            ToolDefinition("file_search", "file_discovery", "搜索文件", "搜索工作区内文件内容。", "files", frozenset({"coordinator", "worker"})),
            ToolDefinition("file_write", "file_write", "写入文件", "在工作区内创建或修改文本文件。", "files", frozenset({"coordinator", "worker"})),
        ),
    )
