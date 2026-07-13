from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from ..llm_types import Tool
from .base import ToolDefinition, ToolSchemaDict

def tool_to_openai_schema(tool: Tool) -> ToolSchemaDict:
    """Serialize an executable tool into OpenAI-style function schema."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.schemas.to_dict(),
        },
    }


def to_openai_tool_schemas(
    tools: Optional[Sequence[ToolDefinition]],
) -> Optional[list[ToolSchemaDict]]:
    """Normalize runtime tools or legacy schemas into OpenAI-compatible payloads."""
    if not tools:
        return None

    openai_schemas: list[ToolSchemaDict] = []
    for tool in tools:
        if isinstance(tool, Tool):
            openai_schemas.append(tool_to_openai_schema(tool))
        else:
            openai_schemas.append(tool)
    return openai_schemas


def to_anthropic_tool_schemas(
    tools: Optional[Sequence[ToolDefinition]],
) -> Optional[list[ToolSchemaDict]]:
    """Normalize runtime tools or legacy schemas into Anthropic tool payloads."""
    openai_tools = to_openai_tool_schemas(tools)
    if not openai_tools:
        return None

    anthropic_tools: list[ToolSchemaDict] = []
    for tool in openai_tools:
        if tool.get("type") == "function":
            func = tool.get("function", {})
            anthropic_tools.append(
                {
                    "name": func.get("name", ""),
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {}),
                }
            )
        else:
            anthropic_tools.append(tool)
    return anthropic_tools
