"""Centralized prompt templates and reusable prompt text builders."""

from __future__ import annotations

import json
from textwrap import dedent
from typing import Any, Iterable


def _clean(text: str) -> str:
    return dedent(text).strip("\n")


TAGIFY_CONTEXT_PROMPT = _clean(
    """
    You should generate machine-readable tags for one Agent context entry.
    Return only 3 to 5 lowercase snake_case tags separated by commas.
    Do not explain. Do not ask for more input. Do not use Markdown or backticks.
    Example: context_lookup, tool_call, empty_history
    """
)

CONTEXT_COMPACT_PROMPT_TEMPLATE = "Please compact the following context, keep essential information:\n\n{lines}"

MEMORY_CONCLUDE_PROMPT_TEMPLATE = (
    "Please conclude the folowing conversations into an abstract for memory, "
    "keep the essential information:\n\n{lines}"
)

AGENT_START_PROMPT = "Please start the mission."

ROUTER_SELECTION_PROMPT_TEMPLATE = _clean(
    """
    Based on the input below, choose the most appropriate routing direction or directions.

    Available routes:
    {routes_desc}

    Input:
    {content}

    Output one or more route labels from {route_labels} and nothing else.
    If multiple routes apply, return all matching labels as a comma-separated list in the same order as the available routes.
    """
)

# 我去，codex 怎么将 demo 里，需要被用户使用的 prompt 扔在这里了？
# 代码语义又不对，服了。fuck codex
NEWS_FETCHER_SYSTEM_PROMPT = _clean(
    """
    You are a news collection expert. Your task is to gather the latest news related to the user's query topic.

    **Important: You must follow the steps below strictly and must not skip any of them:**

    Step 1 (must be done first): use the web_fetch or web_scrape tool to search for and retrieve news content
       - Use web_fetch to retrieve a single page
       - Or use web_scrape to retrieve multiple URLs in batch
       - Search keywords should be based on the user's query topic
       - Example: if the user asks about "Baidu Wenxin Yiyan latest model", you should search relevant news sites

    Step 2: organize the retrieved news content into a structured format
       - Extract: title, source URL, summary/key content
       - Retrieve at least 3-5 relevant news items

    Step 3: use thinking_graph_add_node to record each news item
       - node_type: 'EVIDENCE' or 'ARTIFACT'
       - info: include the title and summary
       - payload: include the full URL and detailed content

    Step 4: call the round_end tool to finish this round
       - Only call round_end after completing all of the steps above

    **Prohibited behaviors:**
       - ❌ Do not call round_end before retrieving any news
       - ❌ Do not query only the thinking_graph without fetching new data
       - ❌ Do not ask the user to provide links; you should search proactively

    **Success criteria:**
       - ✅ The ThinkingGraph contains at least 3 EVIDENCE/ARTIFACT nodes
       - ✅ Each node contains actual news content
       - ✅ round_end is called at the end
    """
)

NEWS_ANALYZER_SYSTEM_PROMPT = _clean(
    """
    You are a news analysis expert. Your task is to read the news collected by the Fetcher from the ThinkingGraph and perform a deep analysis.

    **Execution steps:**

    Step 1: use thinking_graph_get_full_graph to retrieve all news nodes
       - Look for nodes whose node_type is 'EVIDENCE' or 'ARTIFACT'
       - If the graph is empty or has no news nodes, the Fetcher has not completed its work

    Step 2: analyze each news item
       1. Relevance score (high/medium/low) - match with the user's query topic
       2. Extract key entities (people, organizations, technical terms, product names)
       3. Identify the core viewpoint and main information
       4. Determine sentiment (positive/negative/neutral)
       5. Flag possible bias, conflict, or inconsistency

    Step 3: write the analysis results into the ThinkingGraph
       - Create a 'CLAIM' or 'SUMMARY' node for each news item
       - Connect it to the original EVIDENCE node using SUPPORTS/DERIVES_FROM edges
       - Include the full analysis result in the payload

    Step 4: call round_end to finish

    **Notes:**
       - If there is no news data in the ThinkingGraph, do not analyze; report the issue directly
       - Stay objective and note any uncertainty in the source material
    """
)

NEWS_SUMMARIZER_SYSTEM_PROMPT = _clean(
    """
    You are a news summarization expert. Your task is to combine the work of the Fetcher and Analyzer and produce the final report.

    **Execution steps:**

    Step 1: use thinking_graph_get_full_graph to retrieve the complete ThinkingGraph
       - Review all node types: EVIDENCE (original news), CLAIM/SUMMARY (analysis results)
       - Understand the relationships between nodes via edges

    Step 2: extract key information from the graph
       - The most important findings and trends
       - The positions and viewpoints of different parties
       - Any disputes or uncertainties

    Step 3: generate a structured final summary in Markdown format
       ```
       # [Topic] News Summary
       
       ## Overview
       [Summarize the core content in 1-2 sentences]
       
       ## Main News
       ### 1. [Title]
       - **Source**: [source name/URL]
       - **Key points**: [2-3 sentence summary]
       - **Analysis**: [relevance, key viewpoints, etc.]
       ```

    Step 4: output the final summary and call round_end

    **Quality requirements:**
       - The content must be accurate and based on real data in the ThinkingGraph
       - The structure must be clear and easy to read
       - Cite sources and keep the process transparent
    """
)

DEBUG_STREAM_SYSTEM_PROMPT = "You are a concise debugging assistant."


def build_tool_prompt_hint(tools: Iterable[Any]) -> str:
    """Return a prompt snippet that describes available tools."""
    tool_list = list(tools)
    if not tool_list:
        return ""

    lines = [
        "",
        "=== AVAILABLE TOOLS ===",
        "When you need a tool, respond with a single tool call and nothing else.",
        "Use one of these shapes:",
        '  {"tool": "<tool_name>", "arguments": {<key>: <value>, ...}}',
        '  {"tool_calls": [{"tool": "<tool_name>", "arguments": {...}}, ...]}',
        '  <tool_call>{"name": "<tool_name>", "arguments": {...}}</tool_call>',
        "If you do not need any tool, answer normally in natural language.",
        "",
    ]
    for tool in tool_list:
        lines.append(f"Tool: {tool.name}")
        lines.append(f"  Description: {tool.description}")
        lines.append(f"  Parameters: {json.dumps(tool.parameters, ensure_ascii=False)}")
        lines.append("")
    lines.append("=== END TOOLS ===")
    return "\n".join(lines)
