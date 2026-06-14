"""Aggregate the local tool factories exposed by :mod:`modules.llmfetcher.tools`.

The package keeps the most commonly used factories easy to import while loading
the heavier tool modules lazily to avoid circular imports during Agent startup.
Use explicit names for the two different knowledge-tool families:
`create_workspace_knowledge_tools` for CTF workspaces and
`create_rag_knowledge_tools` for the RAG knowledge base.

"""

from __future__ import annotations

from importlib import import_module
from typing import Any

from .builtin_tools import create_builtin_tools
from .shell_tools import create_shell_tools

__all__ = [
    "create_builtin_tools",
    "create_shell_tools",
    "create_ctf_tools",
    "create_workspace_knowledge_tools",
    "create_knowledge_tools",
    "create_rag_knowledge_tools",
    "create_workflow_tool",
    "create_runtime_slot_tools",
    "create_obscura_tools",
    "create_thinking_graph_tools",
    "create_execution_graph_tools",
]


_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "create_ctf_tools": (".ctf_tools", "create_ctf_tools"),
    "create_workspace_knowledge_tools": (".workspace_knowledge_tools", "create_workspace_knowledge_tools"),
    "create_knowledge_tools": (".workspace_knowledge_tools", "create_knowledge_tools"),
    "create_rag_knowledge_tools": ("..rag_module.tools.knowledge_base_tools", "create_knowledge_tools"),
    "create_workflow_tool": (".workflow_tool", "create_workflow_tool"),
    "create_runtime_slot_tools": (".runtime_slot_tools", "create_runtime_slot_tools"),
    "create_obscura_tools": (".obscura_tools", "create_obscura_tools"),
    "create_thinking_graph_tools": (".thinking_graph_tools", "create_thinking_graph_tools"),
    "create_execution_graph_tools": (".execution_graph_tools", "create_execution_graph_tools"),
}


def __getattr__(name: str) -> Any:
    """Lazily load heavier tool factories on first access."""
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attr_name = target
    module = import_module(module_name, __name__)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Expose lazily loaded tool factories in interactive completion."""
    return sorted(set(globals()) | set(__all__))
