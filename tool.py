import asyncio
from dataclasses import dataclass
from re import I
from typing import Any, Callable, Dict, List

from .llm_types import Tool
from .prompt import build_tool_prompt_hint


class ToolRegistry:
    """Registers and executes tools, and produces LLM-compatible schemas."""

    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> Tool:
        """Register a tool. Returns the tool for decorator usage."""
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered.")
        self._tools[tool.name] = tool
        return tool

    def unregister(self, name: str) -> Tool:
        """Unregister a tool by name. Returns the removed tool."""
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' is not registered.")
        return self._tools.pop(name)

    def get(self, name: str) -> Tool:
        """Retrieve a registered tool by name."""
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name}")
        return self._tools[name]

    async def execute(self, name: str, arguments: Dict[str, Any]) -> Any:
        """Execute a registered tool by name."""
        tool = self.get(name)
        return await tool.execute(**arguments)

    @property
    def schemas(self) -> List[Dict[str, Any]]:
        """Return tool metadata in OpenAI-compatible format.
        
        This is the default format used by OpenAI and many compatible providers.
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in self._tools.values()
        ]
    
    def get_schemas_for_provider(self, provider: str = "openai") -> List[Dict[str, Any]]:
        """Return tool schemas formatted for a specific LLM provider.
        
        Args:
            provider: Target provider name. Supported: "openai", "anthropic", "openvino", "custom_json"
            
        Returns:
            List of tool definitions in provider-specific format
            
        Examples:
            OpenAI format:
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "...",
                    "parameters": {...}
                }
            }
            
            Anthropic format:
            {
                "name": "search",
                "description": "...",
                "input_schema": {...}  # Note: different key name
            }
        """
        if provider == "openai":
            return self.schemas  # Already OpenAI-compatible
        
        elif provider == "anthropic":
            return self._to_anthropic_format()
        
        elif provider in {"custom_json", "openvino"}:
            # For prompt-based tool calling, reuse the OpenAI-compatible schema shape.
            # OpenVINO chat templates can consume these tool definitions, and custom_json
            # providers can still benefit from explicit schema hints in the prompt.
            return self.schemas
        
        else:
            raise ValueError(
                f"Unsupported provider: {provider}. "
                "Use 'openai', 'anthropic', 'openvino', or 'custom_json'."
            )
    
    def _to_anthropic_format(self) -> List[Dict[str, Any]]:
        """Convert internal tool definitions to Anthropic Claude format.
        
        Anthropic uses a slightly different schema:
        - No "type": "function" wrapper
        - Uses "input_schema" instead of "parameters"
        """
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.parameters,  # Anthropic uses input_schema
            }
            for t in self._tools.values()
        ]

    def get_prompt_hint(self) -> str:
        """Return a prompt snippet that instructs the LLM how to call tools."""
        return build_tool_prompt_hint(self._tools.values())
