from typing import Dict, Any, List

from .llm_types import Tool

class ToolHandler:
    def __init__(self):
        self.tool_dict: Dict[str, Tool] = {}
        pass

    def add_tool(self, tool: Tool) -> bool:
        """
        Add tool for tool handler. Cannot add repeated tool.

        Args:
            tool: target tool.
        
        Returns:
            (bool): whether successfully add tool or not.
        """
        if tool not in self.tool_dict:
            self.tool_dict[tool.name] = tool
            return True
        else:
            return False
        
    def remove_tool(self, tool_name: str) -> bool:
        """
        Remove a tool from handler.
        Args:
            tool_name: the name of tool.
        Returns:
            (bool): whetehr successfully removed tool or not.
        """
        if tool_name not in self.tool_dict.keys():
            return False
        
        self.tool_dict.pop(tool_name)
        return True
    
    def execute(self, tool: Tool) -> Any:
        """
        Execute a tool.

        Args:
            tool: target tool.

        Returns:
            the result that tool runs.
        """
        return tool.handler(**tool.schemas.to_dict())
    
    def get_all_tool_description(self) -> str:
        """
        Get all the description of tools.
        """
        tool_desc: str = ""
        for k, v in self.tool_dict:
            tool_desc += str(v)
        
    def get_all_tools(self) -> List[Tool]:
        return list(self.tool_dict.values())
