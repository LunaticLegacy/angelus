"""Event model for the hook system — no dependency on Agent or ExecutionGraph.

This module exists at the package root to avoid circular imports:
``agent.py`` and ``swarm_module/execution_graph.py`` both need the event
types but each depends on the other.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ExecutionEvent:
    """Immutable event emitted during swarm execution.

    Each record carries a ``timestamp``, the emitting ``source``
    (``"graph"`` or ``"agent"``), the ``agent_name`` involved, an
    ``event_type`` string, a human-readable ``message``, and optional
    structured ``data``.

    Hook callbacks receive instances of this class; they must not mutate it.
    """

    timestamp: float = field(default_factory=time.time)
    source: str = ""
    agent_name: str = ""
    event_type: str = ""
    message: str = ""
    data: Any = None


ExecutionHook = Callable[[ExecutionEvent], None]
"""Signature for a hook function attached to ``ExecutionGraph`` or ``Agent``.

Hooks are called synchronously; a single failing hook does **not** crash
the execution — exceptions are caught and logged.  Hooks that do I/O (e.g.
WebSocket push) are responsible for their own thread safety.
"""
