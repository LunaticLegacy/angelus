"""Built-in tools for Agent lifecycle and context management."""

from typing import Any, List, Optional

from ..llm_types import LLMContextCompacted
from ..tool import Tool

def create_builtin_tools(agent: Any = None) -> List[Tool]:
    """Create Agent built-in tools for context and memory management."""
    return []

