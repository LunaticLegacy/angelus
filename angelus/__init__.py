"""Angelus local-agent control plane built on the LLMFetcher core library.

The package owns durable sessions, observable Swarm execution, and the local
web console. Model backends, core tool contracts, and RAG primitives remain
provided by the pinned :mod:`llmfetcher` dependency.
"""

from .agent import Agent, AgentRunControl, AgentRunStopped
from .swarm_module import AgentSwarm, ExecutionGraph, TaskAssignment, TaskBus, TaskReport

__all__ = [
    "Agent",
    "AgentRunControl",
    "AgentRunStopped",
    "AgentSwarm",
    "ExecutionGraph",
    "TaskAssignment",
    "TaskBus",
    "TaskReport",
]
