"""
LLM Fetcher - Multi-Agent Orchestration Framework

A powerful Python framework for building, orchestrating, and executing
LLM-powered multi-agent systems with structured reasoning capabilities.

Example usage:
    from llmfetcher import Agent, LLMFetcher, Tool

    fetcher = LLMFetcher(backends=[...])
    agent = Agent(llm_handler=fetcher, system_prompt="...", provider="anthropic")
"""

__version__ = "0.3.0"
__author__ = "LunaticLegacy"

# ============================================================================
# Core Classes
# ============================================================================
from .llm_fetcher import (
    LLMFetcher,
    LLMBackendConfig,
    LLMOutput,
    TokenUsage,
    LLMError,
    LLMTimeoutError,
    LLMBackendError,
)
from .agent import Agent
from .tool import Tool, ToolRegistry
from .ctf_module.ctf_skill_router import (
    CTFSkill,
    SkillClassification,
    build_ctf_skill_context,
    classify_ctf_challenge,
    discover_ctf_skills,
    enrich_prompt_with_ctf_skills,
)
from .thinking_graph import (
    ThinkingGraph,
    ThinkingNodeType,
    ThinkingEdgeType,
    ThinkingGraphNode,
    ThinkingGraphEdge,
    ThinkingGraphTransactionRecord,
)

# ============================================================================
# Context Management
# ============================================================================
from .llm_context import (
    ContextCompressionProfile,
    LLMContextHandler,
    LLMContext,
    LLMContextCompacted,
)

# ============================================================================
# Swarm Orchestration
# ============================================================================
from .swarm.swarm import AgentSwarm, SwarmSpec
from .swarm.execution_graph import (
    GraphContext,
    Edge,
    ExecutionStopState,
    ExecutionNode,
    AgentNode,
    ToolNode,
    RouterNode,
    InputNode,
    OutputNode,
    JoinNode,
    ExecutionGraph,
)
from .swarm.runtime_slot import (
    RuntimeSlot,
    RuntimeSlotManager,
    SlotStatus,
)

# ============================================================================
# Streaming
# ============================================================================
from .streamers import Streamer, ThinkColorStreamer

# ============================================================================
# Backend Handlers
# ============================================================================
from .handlers import (
    LLMBackendHandler,
    AnthropicHandler,
    OpenAIHandler,
    LiteLLMHandler,
    OpenVINOHandler,
)


# ============================================================================
# Tool Factories
# ============================================================================
from .tools.shell_tools import create_shell_tools
from .tools.builtin_tools import create_builtin_tools
from .tools.ctf_tools import create_ctf_tools
from .tools.obscura_tools import create_obscura_tools

# ============================================================================
# Agent I/O (Optional - for advanced file operations)
# ============================================================================
from .agent_io import (
    AgentFileIOManager,
    AgentWorkspacePolicy,
    AgentFileLocations,
    AgentFileSnapshot,
)

# ============================================================================
# Submodules (for advanced usage)
# ============================================================================
from . import tools as tool_modules
from . import swarm as swarm_modules

# ============================================================================
# Public API Exports
# ============================================================================
__all__ = [
    # Version info
    "__version__",
    "__author__",

    # Core classes
    "LLMFetcher",
    "LLMBackendConfig",
    "LLMOutput",
    "TokenUsage",
    "LLMToolCall",
    "LLMError",
    "LLMTimeoutError",
    "LLMBackendError",
    "LLMBackendHandler",
    "AnthropicHandler",
    "OpenAIHandler",
    "LiteLLMHandler",
    "OpenVINOHandler",
    "Agent",
    "Tool",
    "ToolRegistry",
    "CTFSkill",
    "SkillClassification",
    "build_ctf_skill_context",
    "classify_ctf_challenge",
    "discover_ctf_skills",
    "enrich_prompt_with_ctf_skills",

    # Thinking Graph
    "ThinkingGraph",
    "ThinkingNodeType",
    "ThinkingEdgeType",
    "ThinkingGraphNode",
    "ThinkingGraphEdge",
    "ThinkingGraphTransactionRecord",

    # Context Management
    "ContextCompressionProfile",
    "LLMContextHandler",
    "LLMContext",
    "LLMContextCompacted",

    # Swarm orchestration
    "AgentSwarm",
    "SwarmSpec",
    "GraphContext",
    "Edge",
    "ExecutionStopState",
    "ExecutionNode",
    "AgentNode",
    "ToolNode",
    "RouterNode",
    "InputNode",
    "OutputNode",
    "JoinNode",
    "ExecutionGraph",

    # Runtime slots
    "RuntimeSlot",
    "RuntimeSlotManager",
    "SlotStatus",

    # Tool factories
    "create_shell_tools",
    "create_builtin_tools",
    "create_ctf_tools",
    "create_obscura_tools",

    # Agent I/O
    "AgentFileIOManager",
    "AgentWorkspacePolicy",
    "AgentFileLocations",
    "AgentFileSnapshot",

    # Submodules (for advanced usage)
    "tool_modules",
    "swarm_modules",

    # Streamers for streaming output
    "Streamer",
    "ThinkColorStreamer"
]
