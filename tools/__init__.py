"""Aggregate tool factories exposed by :mod:`modules.llmfetcher.tools`.

Heavy factories are loaded lazily to avoid circular imports during agent
startup. ``create_knowledge_tools`` is the sole knowledge-tool factory.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

from .shell_tools import create_shell_tools
from .spawn_tools import create_swarm_tools

_LAZY_FACTORIES = {
    "create_knowledge_tools": (".knowledge_tools", "create_knowledge_tools"),
    "create_obscura_tools": (".obscura_tools", "create_obscura_tools"),
}

__all__ = [
    "create_shell_tools",
    "create_knowledge_tools",
    "create_obscura_tools",
    "create_swarm_tools",
]


def __getattr__(name: str) -> Any:
    """Resolve a lazily exported tool factory.

    Args:
        name: Package attribute requested by the importer.

    Returns:
        The requested factory function.

    Raises:
        AttributeError: If ``name`` is not a public lazy factory.
    """
    target = _LAZY_FACTORIES.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attribute_name = target
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value
