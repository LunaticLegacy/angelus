"""Regression coverage for message-level Angelus tool permission filtering."""

from __future__ import annotations

from llmfetcher import Tool, ToolSchema

from angelus.modules.tool_module import ToolPolicy


def _tool(name: str) -> Tool:
    """Create one inert native tool for permission-filter assertions.

    Args:
        name: Registered name that the session policy will inspect.

    Returns:
        A callable-free-effect ``Tool`` suitable for unit tests.
    """
    return Tool(name=name, description=name, schemas=ToolSchema(), handler=lambda: None)


def test_message_policy_requires_category_and_exact_tool() -> None:
    """A category alone never exposes an unrelated or disabled native tool."""
    policy = ToolPolicy.from_profile({
        "categories": {"shell": True, "planning": False},
        "tools": {"shell": True, "set_task_plan": True},
    })

    assert policy.allows("shell", "shell")
    assert not policy.allows("planning", "set_task_plan")
    assert [tool.name for tool in [_tool("shell"), _tool("other")] if policy.allows("shell", tool.name)] == ["shell"]


def test_mcp_category_toggle_can_authorize_discovered_tools() -> None:
    """The synthetic MCP switch is represented in the policy for discovered names."""
    policy = ToolPolicy.from_profile({
        "categories": {"mcp": True},
        "tools": {"mcp": True},
    })

    assert policy.allows("mcp", "mcp")
    assert not policy.allows("mcp", "mcp.ctf.lookup")
