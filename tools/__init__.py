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

from .shell_tools import create_shell_tools

__all__ = [
    "create_shell_tools",
    "create_workspace_knowledge_tools",
    "create_obscura_tools",
]

