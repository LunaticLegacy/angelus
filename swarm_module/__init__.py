"""
Swarm module — multi-agent orchestration with DAG-based execution.
"""

from .execution_graph import ExecutionGraph, MapperFn, RouterFn
from .swarm import AgentSwarm

__all__ = [
    "ExecutionGraph",
    "MapperFn",
    "RouterFn",
    "AgentSwarm",
]
