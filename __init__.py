"""
LLM Fetcher - Multi-Agent Orchestration Framework

A powerful Python framework for building, orchestrating, and executing
LLM-powered multi-agent systems with structured reasoning capabilities.

Example usage:
    from llmfetcher import Agent, LLMFetcher, Tool

    fetcher = LLMFetcher(backends=[...])
    agent = Agent(llm_handler=fetcher, system_prompt="...", provider="anthropic")
"""

__version__ = "0.4.0"
__author__ = "LunaticLegacy"

from .llm_fetcher import (
    LLMBackendConfig,
    LLMBackendHandler,
    LLMFetcher,
    LLMOutput
)

from .agent import (
    Agent,
    AgentRunControl,
    AgentRunStopped,
)

from .tool_handler import (
    Tool,
)

from .tool_executor import (
    ToolExecutor,
)

from .swarm_module import (
    AgentSwarm,
    TaskAssignment,
    TaskBus,
    TaskReport,
)

from .context_handlers.linear import (
    ContextHandlerLinear
)
