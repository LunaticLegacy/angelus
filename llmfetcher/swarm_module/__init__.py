"""
Swarm module — multi-agent orchestration with DAG-based execution.
"""

from ..events import ExecutionEvent, ExecutionHook
from .execution_graph import (
    ExecutionGraph,
    GraphPersistenceError,
    MapperFn,
    RouterFn,
)
from .swarm import AgentSwarm
from .task_bus import TaskAssignment, TaskBus, TaskReport

__all__ = [
    "ExecutionGraph",
    "GraphPersistenceError",
    "ExecutionEvent",
    "ExecutionHook",
    "MapperFn",
    "RouterFn",
    "AgentSwarm",
    "TaskAssignment",
    "TaskBus",
    "TaskReport",
]
