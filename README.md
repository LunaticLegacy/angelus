# LLM Fetcher

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

A Python framework for building LLM-powered multi-agent systems with structured reasoning, adaptive context management, and DAG-based workflow orchestration.

**Key differentiator**: Most agent frameworks use a fixed-size sliding window for context — old messages silently drop off. llmfetcher introduces an **LLM-driven graph mode** where the model periodically *chooses* what context to keep active, backed by tag-based and semantic vector retrieval. The result is a more relevant prompt for fewer tokens, with the model retaining access to important information from 50+ turns ago.

---

## Features

- **Single & multi-agent** — standalone agents or swarms of coordinated specialists
- **Structured reasoning** — `ThinkingGraph` with 17 typed node types, 12 typed edge types, and schema validation
- **DAG-based execution** — event-driven workflow engine with conditional routing, parallel branches, concurrency control, and checkpoint/resume
- **Dual context modes** — linear (conventional sliding window) or graph (LLM-driven selection with tag + semantic retrieval)
- **6 LLM backends** — OpenAI, Anthropic, LiteLLM, OpenAI-compatible, OpenVINO, ONNX Runtime, with automatic fallback
- **Async-native** — full `asyncio`, concurrent tool execution, background task slots
- **Self-modifying memory** — agents can read, select, and compress their own context via built-in tools
- **State persistence** — per-turn `AgentStateMachine` tracks phase, facts, and next actions; full session checkpoint/resume

---

## Quick Start

```python
import asyncio
from llmfetcher import Agent, LLMFetcher, LLMBackendConfig

async def main():
    fetcher = LLMFetcher(backends=[
        LLMBackendConfig(
            name="openai", 
            provider="openai",
            model="gpt-4o-mini", 
            api_key="sk-...",
        )
    ])

    agent = Agent(
        llm_handler=fetcher,
        system_prompt="You are a helpful assistant.",
        max_concurrent_tools=2,
    )

    response = await agent.run_agent_round("What is quantum computing?")
    print(response)

asyncio.run(main())
```

---

## Core Architecture

```
                    ┌─────────────────────────────┐
                    │        Agent Swarm           │
                    │  ┌────────┐  ┌────────┐     │
                    │  │Agent 1 │  │Agent 2 │ ... │
                    │  └───┬────┘  └───┬────┘     │
                    │      └────┬──────┘          │
                    │      ┌────▼────────┐        │
                    │      │ExecutionGraph│        │
                    │      └────┬────────┘        │
                    └───────────┼─────────────────┘
                                │
                     ┌──────────▼──────────┐
                     │   Thinking Graph    │
                     │  (Shared Reasoning) │
                     └──────────┬──────────┘
                                │
                     ┌──────────▼──────────┐
                     │    LLM Fetcher      │
                     │  (Backend Router)   │
                     └─────────────────────┘
```

### LLM Fetcher — Backend Abstraction

Router that registers backends, manages fallback ordering, and dispatches requests. Backend-specific SDK calls, message conversion, and tool-schema translation live in handlers discovered via subclass enumeration:

```
LLMBackendHandler ── OpenAIHandler
                   ├─ AnthropicHandler
                   ├─ LiteLLMHandler
                   ├─ OpenVINOHandler
                   └─ OnnxRuntimeGenAIHandler
```

All streaming output is normalized to a provider-agnostic protocol — reasoning blocks in `<think>...</think>` tags, tool calls in `<tool_call>...</tool_call>` XML.

### Agent — Tool-Calling Loop

The core lifecycle:
1. Build prompt from context (linear or graph mode)
2. Call LLM with registered tools
3. Execute tool calls concurrently via `asyncio.gather`
4. Compress large tool results into `ToolResultFact` bundles
5. Update `AgentStateMachine` (durable phase/facts/next-actions tracker)
6. Store assistant response + tool results as tagged context entries
7. Repeat until model calls no tools or `max_turns` is reached

Two context modes:
- **Linear** — conventional active window with LLM-based compression when it overflows
- **Graph** — periodic context reselection: the model chooses which past entries to keep, backed by tag indexes and semantic (sentence-transformer) retrieval

### ThinkingGraph — Structured Reasoning

A directed graph with typed nodes and edges, schema-validated connections, conflict detection, and full transaction logging.

Node types (17): `GOAL`, `QUESTION`, `CLAIM`, `HYPOTHESIS`, `EVIDENCE`, `ASSUMPTION`, `PLAN`, `STEP`, `ACTION`, `OBSERVATION`, `CRITIQUE`, `DECISION`, `SUMMARY`, `MEMORY`, `ARTIFACT`, `ERROR`

Edge types (12): `SUPPORTS`, `OPPOSES`, `LEADS_TO`, `DERIVES_FROM`, `REQUIRES`, `ANSWERS`, `REFINES`, `CONTRADICTS`, `BLOCKS`, `PRODUCES`, `OBSERVES`

Each edge is validated against a schema of allowed `(source_type, target_type)` pairs. Semantic conflicts (e.g., `SUPPORTS` + `CONTRADICTS` on the same pair) are detected at creation time.

```python
from llmfetcher import ThinkingGraph, ThinkingNodeType

graph = ThinkingGraph()

goal = await graph.add_node(
    node_type=ThinkingNodeType.GOAL,
    info="Understand quantum entanglement",
    created_by="user"
)

claim = await graph.add_node(
    node_type=ThinkingNodeType.CLAIM,
    info="Entangled particles share quantum states",
    created_by="agent",
    confidence=0.85,
)

await graph.add_edge(
    source_id=claim, target_id=goal,
    edge_type="answers", strength=0.9,
    created_by="agent"
)
```

### ExecutionGraph — DAG Workflow Engine

Event-driven DAG scheduler: nodes execute as soon as all upstream dependencies complete, naturally parallelizing independent branches.

| Node Type | Purpose |
|-----------|---------|
| `InputNode` | Entry point |
| `AgentNode` | Runs an agent round |
| `ToolNode` | Executes a single tool |
| `RouterNode` | LLM-based conditional routing |
| `JoinNode` | Merges parallel paths |
| `OutputNode` | Collects results |

Features: `asyncio.Semaphore` concurrency limit, per-node timeouts, soft/hard stop, event hooks, full checkpoint/resume.

### Agent Swarm

Coordinates multiple agents with shared state (`ThinkingGraph`), global tools, and DAG-defined workflows. Agents can share thinking-graph tools for collaborative reasoning.

```python
from llmfetcher import AgentSwarm, LLMFetcher, LLMBackendConfig

fetcher = LLMFetcher(backends=[...])
swarm = AgentSwarm(fetcher, name="research-team")

# Add domain agents
swarm.add_agent("researcher", "You gather information on topics.")
swarm.add_agent("analyst",    "You analyze findings for key insights.")
swarm.add_agent("writer",     "You synthesize analysis into reports.")

# Build pipeline
swarm.add_input("input")
swarm.connect("input", "researcher")
swarm.connect("researcher", "analyst")
swarm.connect("analyst", "writer")
swarm.add_output("output")
swarm.connect("writer", "output")

ctx = await swarm.run(
    initial_input="Research recent AI developments",
    entry_node_id="input"
)
print(ctx.get_output("output"))
```

---

## Tools

Agents use a `Tool` wrapper for extensible function calling:

```python
from llmfetcher import Tool

async def my_tool(param1: str, param2: int = 10) -> str:
    """Custom tool description."""
    return f"Processed {param1} with {param2}"

agent.add_tool(Tool(
    name="custom_tool",
    description="My custom functionality",
    parameters={
        "type": "object",
        "properties": {
            "param1": {"type": "string"},
            "param2": {"type": "integer"}
        },
        "required": ["param1"]
    },
    handler=my_tool,
))
```

Available tool factories:
- `create_shell_tools()` — safe shell execution with command whitelist/blacklist, timeout, and directory sandboxing
- `create_thinking_graph_tools()` — agents manipulate their shared reasoning graph
- `create_execution_graph_tools()` — agents modify the workflow DAG at runtime
- `create_runtime_slot_tools()` — submit/poll/collect for async background tasks
- `create_obscura_tools()` — web scraping utilities

Custom tools can be registered per-agent or globally at the swarm level.

---

## LLM Backend Configuration

```python
from llmfetcher import LLMFetcher, LLMBackendConfig

# Single backend
fetcher = LLMFetcher(backends=[
    LLMBackendConfig(
        name="primary", provider="openai",
        model="gpt-4o", api_key="sk-...",
        timeout=120.0,
    )
])

# Multiple backends with automatic fallback
fetcher = LLMFetcher(backends=[
    LLMBackendConfig(name="primary",  provider="openai",    model="gpt-4o",     api_key="..."),
    LLMBackendConfig(name="fallback", provider="openai",    model="gpt-4o-mini", api_key="..."),
    LLMBackendConfig(name="local",    provider="openvino",  model="/path/to/model", api_key=""),
])

# Local inference (OpenVINO)
# pip install "llmfetcher[openvino]"
backend = LLMBackendConfig(
    name="local", provider="openvino", model="/path/to/model",
    extra={"device": "CPU", "generation_config": {"top_p": 0.9}},
)
```

---

## Installation

```bash
pip install git+https://github.com/LunaticLegacy/llmfetcher.git

# Or from source
git clone https://github.com/LunaticLegacy/llmfetcher.git
cd llmfetcher
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

Requires Python 3.10+.

---

## Testing

```bash
pip install pytest pytest-asyncio
pytest tests/ -v --tb=short
```

---

## Project Status

**Version 0.3.0** — Active development. The graph-mode context selection and ThinkingGraph are the most mature subsystems. Built-in context-management tools (`context_read`, `context_select`, `context_compress`) are planned but not yet implemented.

---

## License

MIT
