"""
News Monitoring Agent Swarm
===========================

A multi-agent pipeline that:
  1. Fetches news articles/topics via web scraping tools
  2. Analyzes content for relevance and key information
  3. Produces a final structured summary

Usage:
  python news_monitoring.py "artificial intelligence breakthroughs 2025"
  python news_monitoring.py   (prompts interactively)

Requires: DEEPSEEK_API_KEY environment variable.
"""

import asyncio
import os
import sys
from typing import Any, Dict, List

# ── Add package parent for direct script execution ────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llmfetcher.llm_fetcher import LLMFetcher, LLMBackendConfig
from llmfetcher.prompt import (
    NEWS_ANALYZER_SYSTEM_PROMPT,
    NEWS_FETCHER_SYSTEM_PROMPT,
    NEWS_SUMMARIZER_SYSTEM_PROMPT,
)
from llmfetcher.tool import Tool
from llmfetcher.swarm.swarm import AgentSwarm
from llmfetcher.tools.shell_tools import create_shell_tools
from llmfetcher.swarm.execution_graph import GraphContext


# ======================================================================
# 1. Custom news analysis tools
# ======================================================================

def extract_source(url: str = "") -> str:
    """Extract domain or source name from a URL."""
    if not url:
        return "unknown"
    # strip protocol and path
    domain = url.replace("http://", "").replace("https://", "").split("/")[0]
    return domain if domain else "unknown"


def format_news_digest(articles: List[Dict[str, str]]) -> str:
    """Format a list of article dicts into a readable digest string.

    Each article dict should have keys: ``source``, ``title``, ``snippet``.
    """
    if not articles:
        return "No articles to report."

    lines = ["# News Digest", ""]
    for i, art in enumerate(articles, 1):
        lines.append(f"## {i}. {art.get('title', '(no title)')}")
        lines.append(f"   **Source:** {art.get('source', 'unknown')}")
        lines.append(f"   {art.get('snippet', '(no content)')}")
        lines.append("")
    return "\n".join(lines)


# ======================================================================
# 2. Backend configuration
# ======================================================================

def get_backend() -> LLMBackendConfig:
    """Read LLM backend config from environment."""
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if api_key:
        return LLMBackendConfig(
            name="deepseek",
            provider="anthropic",  # DeepSeek uses Anthropic-compatible format
            model="deepseek-chat",
            api_key=api_key,
            api_url="https://api.deepseek.com/anthropic",
            timeout=120.0,
        )

    # Optional: support a JSON-encoded env var with multiple backends
    fallback = os.environ.get("LLM_BACKEND_CONFIG")
    if fallback:
        import json
        cfg = json.loads(fallback)
        return LLMBackendConfig(**cfg)

    raise RuntimeError(
        "No LLM backend configured. Set DEEPSEEK_API_KEY or LLM_BACKEND_CONFIG."
    )


# ======================================================================
# 3. Swarm topology builder
# ======================================================================

def build_news_monitor_swarm(fetcher: LLMFetcher) -> AgentSwarm:
    """Construct the news-monitoring DAG.

    Topology::

        input ──► fetcher ──► analyzer ──► summarizer ──► output
                     │                        │
                     └────────────────────────┘
                           (thinking graph
                            shared across all)
    """
    swarm = AgentSwarm(
        llm_fetcher=fetcher,
        name="news-monitor",
    )

    # ── Register global tools ──────────────────────────────────────────
    # All agents get the shell tool for web fetching (with security restrictions)
    shell_tools = create_shell_tools(
        allowed_commands=["ls", "cat", "grep", "find", "pwd", "curl", "wget"],
        max_timeout=60.0,
        sandbox_cwd=os.getcwd(),  # Restrict to current directory
    )
    swarm.add_tools(shell_tools)  # "shell" tool added globally

    # ── Build DAG nodes ────────────────────────────────────────────────
    swarm.add_input("input")

    # Agent 1: News Fetcher – uses web scraping tools to retrieve articles
    swarm.add_agent(
        "fetcher",
        system_prompt=NEWS_FETCHER_SYSTEM_PROMPT,
        share_thinking_tools=True,      # can record findings in ThinkingGraph
        share_graph_tools=False,
        max_concurrent_tools=3,         # 允许并行获取多条新闻
    )

    # Agent 2: News Analyzer – evaluates relevance, extracts entities
    swarm.add_agent(
        "analyzer",
        system_prompt=NEWS_ANALYZER_SYSTEM_PROMPT,
        share_thinking_tools=True,
        share_graph_tools=False,
        max_concurrent_tools=2,
    )

    # Agent 3: Summarizer – produces final digest
    swarm.add_agent(
        "summarizer",
        system_prompt=NEWS_SUMMARIZER_SYSTEM_PROMPT,
        share_thinking_tools=True,      # reads ThinkingGraph nodes from previous agents
        share_graph_tools=False,
        max_concurrent_tools=1,
    )

    # Output node – collects final summary
    swarm.add_output("output", collector=lambda inputs: inputs[0] if inputs else "")

    # ── Wire the DAG ───────────────────────────────────────────────────
    swarm.connect("input", "fetcher")
    swarm.connect("fetcher", "analyzer")
    swarm.connect("analyzer", "summarizer")
    swarm.connect("summarizer", "output")

    # Optional: set timeouts for individual nodes (in seconds)
    swarm.set_timeout("fetcher", 180.0)    # allow extra time for web fetches
    swarm.set_timeout("analyzer", 120.0)
    swarm.set_timeout("summarizer", 90.0)

    return swarm


# ======================================================================
# 4. Interactive / CLI entry point
# ======================================================================

async def run_once(swarm: AgentSwarm, query: str) -> GraphContext:
    """Execute a single news-monitoring run."""
    print(f"\n{'='*60}")
    print(f"🔍  News Monitor: {query}")
    print(f"{'='*60}\n")

    # Show available tools for debugging
    print("📋 Available Tools:")
    for tool_name in swarm.tool_schemas():
        print(f"   - {tool_name}")
    print()

    ctx = await swarm.run(initial_input=query, entry_node_id="input")

    print(f"\n{'='*60}")
    print("📰  Final Output")
    print(f"{'='*60}\n")
    print(ctx.get_output("output"))
    print()

    # Show ThinkingGraph state for debugging
    tg = await swarm.thinking_graph.get_full_graph()
    nodes = tg.get("nodes", [])
    edges = tg.get("edges", [])
    if nodes:
        print(f"\n[ThinkingGraph Summary]")
        print(f"   Total Nodes: {len(nodes)}")
        print(f"   Total Edges: {len(edges)}")
        
        # Show node types distribution
        from collections import Counter
        node_types = Counter(node.get("node_type", "unknown") for node in nodes)
        print(f"   Node Types: {dict(node_types)}")
        
        # Show first few nodes as sample
        print(f"\n   Sample Nodes (first 3):")
        for i, node in enumerate(nodes[:3]):
            print(f"     [{i+1}] Type: {node.get('node_type')}")
            print(f"         Info: {node.get('info', '')[:100]}...")
    else:
        print("\n⚠️  Warning: ThinkingGraph is empty! This indicates the fetcher didn't collect any data.")
    
    return ctx


async def main(query: str | None = None) -> None:
    # ── Bootstrap ──────────────────────────────────────────────────────
    fetcher = LLMFetcher(
            api_url="https://api.deepseek.com",
            api_key=os.environ.get("DEEPSEEK_API_KEY"),
            model="deepseek-v4-flash",
            timeout=120.0
        )

    swarm = build_news_monitor_swarm(fetcher)

    # ── Interactive loop ───────────────────────────────────────────────
    if query:
        await run_once(swarm, query)
    else:
        print("📡  News Monitor Swarm  📡")
        print("Type your news query, or 'quit' to exit.\n")
        while True:
            try:
                q = input("Query> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not q:
                continue
            if q.lower() in ("quit", "exit", "q"):
                break
            await run_once(swarm, q)


if __name__ == "__main__":
    import sys

    query = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(main(query=query))
