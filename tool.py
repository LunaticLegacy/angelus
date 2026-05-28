from typing import Any, Dict, List

from .llm_types import Tool
from .prompt import build_tool_prompt_hint


class ToolRegistry:
    """Store executable tools and expose provider-neutral tool metadata.

    `ToolRegistry` is intentionally unaware of concrete LLM providers. Provider
    handlers own the final wire-format conversion because fallback can route one
    request through different providers.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> Tool:
        """
        注册一个工具。返回工具，用于装饰器使用。

        Args:
            tool: 被注册的工具。
        
        Returns:
            返回被注册的工具自身。
        """
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered.")
        self._tools[tool.name] = tool
        return tool

    def unregister(self, name: str) -> Tool:
        """
        取消注册一个工具，并返回被取消注册的工具。

        Args:
            name: 工具名。
        """
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' is not registered.")
        return self._tools.pop(name)

    def get(self, name: str) -> Tool:
        """
        根据工具名，获取一个被注册的工具。
        Raises:
            KeyError: 如果工具未被注册，则报错。
        """
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' is not registered.")
        return self._tools[name]

    async def execute(self, name: str, arguments: Dict[str, Any]) -> Any:
        """
        根据工具名，执行已注册的工具。

        Args:
            name: 工具名
            arguments: 工具参数
        
        Returns:
            工具执行结果，可能是任意类型的——取决于工具输入的类型。
        """
        tool = self.get(name)   # 从工具名获取工具
        return await tool.execute(**arguments)  # 并执行

    @property
    def tools(self) -> List[Tool]:
        """
        Return registered tools in registration order.
        """
        return list(self._tools.values())

    def get_prompt_hint(self) -> str:
        """
        Return a prompt snippet that instructs the LLM how to call tools.
        """
        return build_tool_prompt_hint(self._tools.values())
