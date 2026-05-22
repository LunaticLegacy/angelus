"""
llmfetcher Demo – showcases core framework features.

Usage:
    python -m llmfetcher.tests.test_llmdemo

Ensure at least one LLM backend is configured via environment variables:
    OPENAI_API_KEY=...  (or set LLM_BACKEND_CONFIG as a JSON string)
"""

import asyncio
import os
import sys
from typing import Any, Dict, List

# Add package parent to path if running directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from llmfetcher.llm_fetcher import LLMFetcher, LLMBackendConfig
from llmfetcher.agent import Agent
from llmfetcher.tool import Tool
from llmfetcher.swarm.swarm import AgentSwarm
from llmfetcher.thinking_graph import ThinkingGraph
from llmfetcher.swarm.execution_graph import Edge


# ---------------------------------------------------------------------------
# 1. Minimal custom tool – echoes the argument back
# ---------------------------------------------------------------------------
def echo_tool(message: str = "") -> str:
    """Simply returns the message unchanged."""
    return message


# ---------------------------------------------------------------------------
# 2. Demo helpers
# ---------------------------------------------------------------------------
def get_backend() -> LLMBackendConfig:
    """Create a backend config from environment or a default mock."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key:
        return LLMBackendConfig(
            name="openai",
            provider="openai",
            model="gpt-4o-mini",
            api_key=api_key,
        )
    # Fallback: you can implement a local mock or raise a friendly error
    raise RuntimeError(
        "No LLM backend configured. Set OPENAI_API_KEY or provide a custom YAML."
    )


# ---------------------------------------------------------------------------
# 3. Standalone Agent Demo
# ---------------------------------------------------------------------------
async def demo_agent():
    print("=== Agent Demo ===")
    fetcher = LLMFetcher(backends=[get_backend()])
    agent = Agent(
        llm_handler=fetcher,
        system_prompt="You are a helpful assistant that uses tools when needed. You have an 'echo' tool that repeats your input.",
        tools=[Tool(name="echo", description="Echoes the input", parameters={"message": {"type": "string"}}, handler=echo_tool)],
    )
    result = await agent.round_call("Say hello and echo back 'world'.")
    print("Agent response:", result)
    print()


# ---------------------------------------------------------------------------
# 4. Swarm Demo – simple linear graph
# ---------------------------------------------------------------------------
async def demo_swarm():
    print("=== Swarm Demo ===")
    fetcher = LLMFetcher(backends=[get_backend()])
    swarm = AgentSwarm(llm_fetcher=fetcher, name="demo_swarm")

    # Manually build graph: input -> agent -> output
    swarm.add_input_node("input")
    swarm.add_agent("assistant", system_prompt="You are a concise assistant.")
    swarm.add_output_node("output", collector=lambda inputs: inputs)

    swarm.connect("input", "assistant")
    swarm.connect("assistant", "output")

    ctx = await swarm.run(initial_input="Explain quantum computing in two sentences.")
    print("Swarm output:", ctx.get_output("output"))
    print()


# ---------------------------------------------------------------------------
# 5. Thinking Graph Demo
# ---------------------------------------------------------------------------
async def demo_thinking_graph():
    print("=== Thinking Graph Demo ===")
    graph = ThinkingGraph()
    n1 = graph.add_node("GOAL", "Understand user intent", created_by="demo")
    n2 = graph.add_node("ACTION", "Search knowledge base", created_by="demo")
    graph.add_edge("LEADS_TO", source_id=n1, target_id=n2, created_by="demo")
    full = await graph.get_full_graph()
    print("Graph snapshot:", full["nodes"])
    print("Edges:", full["edges"])
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main():
    await demo_agent()
    await demo_swarm()
    await demo_thinking_graph()

if __name__ == "__main__":
    asyncio.run(main())
