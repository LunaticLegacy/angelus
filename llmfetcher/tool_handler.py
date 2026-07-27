from __future__ import annotations

from typing import Any, Dict, List

from .llm_types import LLMToolCall, Tool


class ToolHandler:
    """Register, look up, and describe ``Tool`` objects.

    This is a pure **registry** — it tracks what tools exist and how to
    describe them.  Execution is delegated to ``ToolExecutor`` so that
    the two concerns (registration vs. execution) can evolve independently.
    """

    def __init__(self) -> None:
        self.tool_dict: Dict[str, Tool] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def add_tool(self, tool: Tool) -> bool:
        """Register a tool.  No-op if a tool with the same name exists.

        Returns:
            ``True`` if the tool was added, ``False`` if a tool with
            the same name was already registered.
        """
        if tool.name in self.tool_dict:
            return False
        self.tool_dict[tool.name] = tool
        return True

    def remove_tool(self, name: str) -> bool:
        """Unregister a tool by name.

        Returns:
            ``True`` if the tool was removed, ``False`` if no tool
        """
        if name not in self.tool_dict:
            return False
        del self.tool_dict[name]
        return True

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, name: str) -> Tool | None:
        """Look up a tool by name.

        Returns:
            The ``Tool`` instance, or ``None`` if not found.
        """
        return self.tool_dict.get(name)

    def get_handler(self, name: str) -> Any | None:
        """Return the callable handler for a named tool.

        Returns:
            The handler callable, or ``None`` if not found.
        """
        tool = self.tool_dict.get(name)
        return tool.handler if tool else None

    def get_handlers_and_arguments(
        self,
        calls: List[LLMToolCall],
    ) -> tuple[List[Any | None], List[Dict[str, Any]]]:
        """Resolve a list of tool calls into (handlers, arguments).

        Handlers for unknown tool names are set to ``None``.

        Args:
            calls: Tool calls to resolve.

        Returns:
            A ``(handlers, arguments_list)`` tuple suitable for passing
            directly to ``ToolExecutor.execute_batch``.
        """
        handlers: List[Any | None] = []
        arguments_list: List[Dict[str, Any]] = []
        for tc in calls:
            tool = self.tool_dict.get(tc.name)
            handlers.append(tool.handler if tool else None)
            arguments_list.append(tc.arguments)
        return handlers, arguments_list

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_all_tool_description(self) -> str:
        """Concatenated ``__str__`` of all registered tools, newline-separated."""
        return "\n".join(str(v) for v in self.tool_dict.values())

    def get_all_tools(self) -> List[Tool]:
        """Return all registered tools as a list."""
        return list(self.tool_dict.values())
