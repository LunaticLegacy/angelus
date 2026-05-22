# LLM Fetcher - Multi-Agent Orchestration Framework

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

A powerful Python framework for building, orchestrating, and executing LLM-powered multi-agent systems with structured reasoning capabilities.

## 🌟 Features

- **🤖 Single & Multi-Agent Support**: Build individual agents or coordinate swarms of specialized agents
- **🧠 Structured Reasoning**: Thinking Graph system enables step-by-step cognitive processes with 15+ node types
- **🔗 DAG-Based Execution**: Execution graphs for complex workflow orchestration and dependency management
- **🛠️ Extensible Tool System**: Modular architecture supporting shell commands, web scraping, and custom tools
- **⚡ Async-Native**: Full asyncio support with configurable concurrency controls
- **🔄 Multiple LLM Backends**: Flexible backend configuration supporting OpenAI, Anthropic, DeepSeek, and other providers
- **💾 State Persistence**: Checkpoint/resume functionality for long-running tasks
- **📊 Rich Observability**: Track agent decisions through ThinkingGraph transaction records

## 📋 Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Core Concepts](#core-concepts)
- [Architecture](#architecture)
- [Usage Examples](#usage-examples)
- [API Reference](#api-reference)
- [Testing](#testing)
- [Contributing](#contributing)
- [License](#license)

## 🚀 Installation

### Method 1: Install from PyPI (Recommended - when published)

```bash
pip install llmfetcher
```

### Method 2: Install from GitHub

```bash
pip install git+https://github.com/LunaticLegacy/llmfetcher.git
```

### Method 3: Install from Source

```bash
# Clone the repository
git clone https://github.com/LunaticLegacy/llmfetcher.git
cd llmfetcher

# Create virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install in development mode
pip install -e .

# Or install normally
pip install .
```

### Verify Installation

```python
from llmfetcher import Agent, LLMFetcher, Tool
print("✅ Installation successful!")
```

For detailed installation instructions, see [INSTALLATION_GUIDE.md](INSTALLATION_GUIDE.md).

### Prerequisites

- Python 3.10 or higher
- pip package manager

### Environment Setup

Set your OpenAI API key:

```bash
export OPENAI_API_KEY="your-api-key-here"
```

Or configure via environment variable with custom backend:

```bash
export LLM_BACKEND_CONFIG='{"name":"openai","provider":"openai","model":"gpt-4o-mini","api_key":"your-key"}'
```

## 🎯 Quick Start

### Simple Agent Example

```python
import asyncio
from llmfetcher import Agent, LLMFetcher, LLMBackendConfig

async def main():
    # Configure LLM backend
    backend = LLMBackendConfig(
        name="openai",
        provider="openai",
        model="gpt-4o-mini",
        api_key="your-api-key"
    )
    
    fetcher = LLMFetcher(backends=[backend])
    
    # Create an agent
    agent = Agent(
        llm_handler=fetcher,
        system_prompt="You are a helpful assistant.",
        max_concurrent_tools=2
    )
    
    # Execute a round
    response = await agent.round_call("What is quantum computing?")
    print(response)

asyncio.run(main())
```

### Multi-Agent Swarm Example

```python
import asyncio
from llmfetcher import AgentSwarm, LLMFetcher, LLMBackendConfig

async def main():
    backend = LLMBackendConfig(
        name="openai",
        provider="openai",
        model="gpt-4o-mini",
        api_key="your-api-key"
    )
    
    fetcher = LLMFetcher(backends=[backend])
    
    # Build a swarm
    swarm = AgentSwarm(llm_fetcher=fetcher, name="research-team")
    
    # Add specialized agents
    swarm.add_agent(
        "researcher",
        system_prompt="You are a research expert. Gather information on topics."
    )
    
    swarm.add_agent(
        "analyst",
        system_prompt="You analyze research findings and extract key insights."
    )
    
    swarm.add_agent(
        "writer",
        system_prompt="You synthesize analysis into clear, concise reports."
    )
    
    # Define workflow
    swarm.add_input("input")
    swarm.connect("input", "researcher")
    swarm.connect("researcher", "analyst")
    swarm.connect("analyst", "writer")
    swarm.add_output("output")
    swarm.connect("writer", "output")
    
    # Execute
    ctx = await swarm.run(
        initial_input="Research recent AI developments",
        entry_node_id="input"
    )
    
    print(ctx.get_output("output"))

asyncio.run(main())
```

### News Monitoring Demo

The repository includes a complete news monitoring example in [`main.py`](main.py):

```bash
# Interactive mode
python main.py

# Direct query
python main.py "artificial intelligence breakthroughs 2025"
```

## 📚 Core Concepts

### Agent

An `Agent` is the fundamental unit that interacts with LLMs and executes tools. Key features:

- **System Prompt**: Defines agent behavior and capabilities
- **Tool Registry**: Dynamic tool management (add/remove at runtime)
- **Multi-turn Execution**: Agents can call multiple tools in a single round
- **Concurrent Tools**: Execute multiple tools in parallel when `max_concurrent_tools > 1`

### Thinking Graph

A directed graph representing structured reasoning with rich semantics:

**Node Types** (15 types):
- `GOAL`, `QUESTION`, `CLAIM`, `HYPOTHESIS`
- `EVIDENCE`, `ASSUMPTION`, `PLAN`, `STEP`
- `ACTION`, `OBSERVATION`, `CRITIQUE`
- `DECISION`, `SUMMARY`, `MEMORY`, `ARTIFACT`, `ERROR`

**Edge Types** (12 types):
- `SUPPORTS`, `OPPOSES`, `LEADS_TO`, `DERIVES_FROM`
- `REQUIRES`, `ANSWERS`, `REFINES`, `CONTRADICTS`
- `BLOCKS`, `PRODUCES`, `OBSERVES`

Example usage:

```python
from llmfetcher import ThinkingGraph, ThinkingNodeType

graph = ThinkingGraph()

# Add reasoning nodes
goal_id = graph.add_node(
    node_type=ThinkingNodeType.GOAL,
    info="Understand quantum entanglement",
    created_by="user"
)

hypothesis_id = graph.add_node(
    node_type=ThinkingNodeType.HYPOTHESIS,
    info="Entangled particles share quantum states",
    created_by="agent"
)

# Connect with semantic relationship
graph.add_edge(
    source_id=hypothesis_id,
    target_id=goal_id,
    edge_type="answers",
    strength=0.8,
    created_by="agent"
)
```

### Execution Graph

A DAG (Directed Acyclic Graph) for orchestrating agent workflows:

**Node Types**:
- `InputNode`: Entry points for data
- `AgentNode`: Executes agent logic
- `ToolNode`: Runs specific tools
- `RouterNode`: Conditional branching
- `JoinNode`: Merge parallel paths
- `OutputNode`: Collect results

Example:

```python
from llmfetcher.swarm.execution_graph import ExecutionGraph

graph = ExecutionGraph(llm_fetcher=fetcher)

# Build workflow
input_node = graph.add_input_node()
agent_node = graph.add_agent_node(agent)
output_node = graph.add_output_node()

graph.connect(input_node.id, agent_node.id)
graph.connect(agent_node.id, output_node.id)

# Execute
ctx = await graph.run(initial_data="task input")
```

### Agent Swarm

Top-level container coordinating multiple agents with shared state:

```python
swarm = AgentSwarm(llm_fetcher=fetcher, name="my-swarm")

# Add global tools available to all agents
from llmfetcher.tools.shell_tools import create_shell_tools
swarm.add_tools(create_shell_tools())

# Add agents with different capabilities
swarm.add_agent(
    "planner",
    system_prompt="Plan execution strategy",
    share_thinking_tools=True  # Share ThinkingGraph access
)

swarm.add_agent(
    "executor",
    system_prompt="Execute planned tasks",
    share_thinking_tools=True
)

# Wire the workflow
swarm.connect("input", "planner")
swarm.connect("planner", "executor")
swarm.connect("executor", "output")
```

### Tools

Modular functions agents can invoke. Built-in tools include:

- **Shell Tools**: Execute shell commands safely (with dangerous command filtering)
- **Thinking Graph Tools**: Manipulate reasoning graphs
- **Execution Graph Tools**: Modify execution workflows
- **Runtime Slot Tools**: Access per-agent state
- **Builtin Tools**: Control flow (e.g., `round_end`)

Create custom tools:

```python
from llmfetcher import Tool

async def my_custom_tool(param1: str, param2: int = 10) -> str:
    """Custom tool description."""
    return f"Processed {param1} with {param2}"

tool = Tool(
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
    handler=my_custom_tool
)

agent.add_tool(tool)
```

## 🏗️ Architecture

```
┌─────────────────────────────────────────────┐
│              Agent Swarm                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │ Agent 1  │  │ Agent 2  │  │ Agent 3  │  │
│  │          │  │          │  │          │  │
│  │ Tools    │  │ Tools    │  │ Tools    │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  │
│       │             │             │         │
│       └─────────────┼─────────────┘         │
│                     │                       │
│         ┌───────────▼───────────┐           │
│         │   Execution Graph     │           │
│         │   (Workflow DAG)      │           │
│         └───────────┬───────────┘           │
└─────────────────────┼───────────────────────┘
                      │
         ┌────────────▼────────────┐
         │    Thinking Graph       │
         │  (Shared Memory/State)  │
         └────────────┬────────────┘
                      │
         ┌────────────▼────────────┐
         │     LLM Fetcher         │
         │  (Backend Abstraction)  │
         └─────────────────────────┘
```

### Key Components

| Component | File | Purpose |
|-----------|------|---------|
| `Agent` | [`agent.py`](agent.py) | Core agent lifecycle and tool dispatch |
| `AgentSwarm` | [`swarm/swarm.py`](swarm/swarm.py) | Multi-agent orchestration |
| `ThinkingGraph` | [`thinking_graph.py`](thinking_graph.py) | Structured reasoning engine |
| `ExecutionGraph` | [`swarm/execution_graph.py`](swarm/execution_graph.py) | DAG-based workflow execution |
| `LLMFetcher` | [`llm_fetcher.py`](llm_fetcher.py) | LLM API abstraction layer |
| `Tool` | [`tool.py`](tool.py) | Base class for extensible tools |
| `RuntimeSlot` | [`swarm/runtime_slot.py`](swarm/runtime_slot.py) | Per-agent state management |

## 📖 Usage Examples

### Example 1: Research Assistant with Thinking Graph

```python
import asyncio
from llmfetcher import AgentSwarm, LLMFetcher, LLMBackendConfig
from llmfetcher.thinking_graph import ThinkingNodeType

async def research_assistant():
    backend = LLMBackendConfig(
        name="openai",
        provider="openai",
        model="gpt-4o",
        api_key="your-api-key"
    )
    
    fetcher = LLMFetcher(backends=[backend])
    swarm = AgentSwarm(llm_fetcher=fetcher, name="researcher")
    
    # Research agent that documents its thinking
    swarm.add_agent(
        "researcher",
        system_prompt="""You are a thorough researcher. 
        Use the thinking graph to:
        1. Break down complex questions
        2. Record hypotheses and evidence
        3. Track your reasoning process
        4. Document conclusions with confidence levels""",
        share_thinking_tools=True
    )
    
    swarm.add_input("input")
    swarm.connect("input", "researcher")
    swarm.add_output("output")
    swarm.connect("researcher", "output")
    
    ctx = await swarm.run(
        initial_input="Explain the implications of room-temperature superconductors",
        entry_node_id="input"
    )
    
    # Access the thinking graph to see reasoning trail
    tg = await swarm.thinking_graph.get_full_graph()
    print(f"Reasoning involved {len(tg['nodes'])} thought nodes")
    
    print("\nFinal Answer:")
    print(ctx.get_output("output"))

asyncio.run(research_assistant())
```

### Example 2: Parallel Data Processing Pipeline

```python
import asyncio
from llmfetcher import AgentSwarm, LLMFetcher, LLMBackendConfig

async def parallel_pipeline():
    backend = LLMBackendConfig(
        name="openai",
        provider="openai",
        model="gpt-4o-mini",
        api_key="your-api-key"
    )
    
    fetcher = LLMFetcher(backends=[backend])
    swarm = AgentSwarm(llm_fetcher=fetcher, name="pipeline")
    
    # Three parallel analyzers
    swarm.add_agent(
        "sentiment_analyzer",
        system_prompt="Analyze text sentiment (positive/negative/neutral)"
    )
    
    swarm.add_agent(
        "entity_extractor",
        system_prompt="Extract named entities (people, places, organizations)"
    )
    
    swarm.add_agent(
        "topic_classifier",
        system_prompt="Classify text topic (technology, politics, sports, etc.)"
    )
    
    swarm.add_agent(
        "synthesizer",
        system_prompt="Combine all analyses into a comprehensive summary"
    )
    
    # Parallel execution pattern
    swarm.add_input("input")
    swarm.connect("input", "sentiment_analyzer")
    swarm.connect("input", "entity_extractor")
    swarm.connect("input", "topic_classifier")
    
    # Join results
    swarm.add_join("join_results")
    swarm.connect("sentiment_analyzer", "join_results")
    swarm.connect("entity_extractor", "join_results")
    swarm.connect("topic_classifier", "join_results")
    
    swarm.connect("join_results", "synthesizer")
    swarm.add_output("output")
    swarm.connect("synthesizer", "output")
    
    ctx = await swarm.run(
        initial_input="Apple announced new AI features for iPhone at their developer conference",
        entry_node_id="input"
    )
    
    print(ctx.get_output("output"))

asyncio.run(parallel_pipeline())
```

### Example 3: Custom Tool Integration

``python
import asyncio
from llmfetcher import Agent, LLMFetcher, LLMBackendConfig, Tool

# Define custom tool
async def web_search(query: str, max_results: int = 5) -> str:
    """Search the web for information."""
    # Implementation here (e.g., using requests library)
    return f"Search results for: {query}"

async def calculate(expression: str) -> str:
    """Evaluate mathematical expressions."""
    try:
        result = eval(expression, {"__builtins__": {}}, {})
        return f"Result: {result}"
    except Exception as e:
        return f"Error: {str(e)}"

async def main():
    backend = LLMBackendConfig(
        name="openai",
        provider="openai",
        model="gpt-4o-mini",
        api_key="your-api-key"
    )
    
    fetcher = LLMFetcher(backends=[backend])
    
    agent = Agent(
        llm_handler=fetcher,
        system_prompt="""You have access to web search and calculator tools.
        Use them to answer questions accurately.""",
        max_concurrent_tools=2
    )
    
    # Register custom tools
    search_tool = Tool(
        name="web_search",
        description="Search the web for current information",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {"type": "integer", "description": "Max results to return"}
            },
            "required": ["query"]
        },
        handler=web_search
    )
    
    calc_tool = Tool(
        name="calculate",
        description="Perform mathematical calculations",
        parameters={
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "Math expression"}
            },
            "required": ["expression"]
        },
        handler=calculate
    )
    
    agent.add_tool(search_tool)
    agent.add_tool(calc_tool)
    
    response = await agent.round_call(
        "What is the square root of 144 plus the current year?"
    )
    print(response)

asyncio.run(main())
```

## 🔧 API Reference

### LLMFetcher

Configure and manage LLM backends:

```python
from llmfetcher import LLMFetcher, LLMBackendConfig

# Single backend
backend = LLMBackendConfig(
    name="openai",
    provider="openai",
    model="gpt-4o-mini",
    api_key="sk-...",
    timeout=120.0,
    temperature=0.7,
    max_tokens=2000
)

fetcher = LLMFetcher(backends=[backend])

# Multiple backends with fallback
backends = [
    LLMBackendConfig(name="primary", provider="openai", model="gpt-4o", ...),
    LLMBackendConfig(name="fallback", provider="openai", model="gpt-4o-mini", ...)
]

fetcher = LLMFetcher(backends=backends, fallback_order=["primary", "fallback"])
```

OpenVINO local inference is available as an optional backend:

```bash
pip install "llmfetcher[openvino]"
```

```python
from llmfetcher import LLMBackendConfig, LLMFetcher

backend = LLMBackendConfig(
    name="local-openvino",
    provider="openvino",
    model="/path/to/openvino_model",
    extra={
        "device": "CPU",  # CPU, GPU, NPU, or AUTO
        "generation_config": {"top_p": 0.9},
        "extra_context": {"enable_thinking": True},
    },
)

fetcher = LLMFetcher(backends=[backend])
response = await fetcher.fetch("Say hello", backend_name="local-openvino")
```

### Agent

Create and configure agents:

```python
from llmfetcher import Agent

agent = Agent(
    llm_handler=fetcher,
    system_prompt="Your instructions here",
    tools=[tool1, tool2],  # Optional initial tools
    max_concurrent_tools=3,  # Parallel tool execution
    fallback_order=["backend1", "backend2"]  # Backend priority
)

# Dynamic tool management
agent.add_tool(new_tool)
agent.remove_tool("tool_name")
agent.update_system_prompt("New instructions")

# Execute
response = await agent.round_call(
    msg="User message",
    stream=False,
    verbose_info=True,
    max_turns=5  # Max tool call iterations
)
```

### AgentSwarm

Build multi-agent systems:

```python
from llmfetcher import AgentSwarm

swarm = AgentSwarm(
    llm_fetcher=fetcher,
    name="my-swarm",
    max_concurrency=5  # Max parallel nodes
)

# Add tools globally
swarm.add_tools([tool1, tool2])
swarm.remove_tool("tool_name")

# Add agents
swarm.add_agent(
    node_id="agent1",
    system_prompt="Instructions",
    share_thinking_tools=True,  # Access to shared ThinkingGraph
    share_graph_tools=False,    # Can modify execution graph
    max_concurrent_tools=2
)

# Build workflow
swarm.add_input("input")
swarm.add_output("output")
swarm.add_router("router", routes={"condition_a": "path_a", "default": "path_b"})
swarm.add_join("join_point")

swarm.connect("input", "agent1")
swarm.connect("agent1", "router")
swarm.connect("router", "join_point")
swarm.connect("join_point", "output")

# Configure timeouts
swarm.set_timeout("agent1", seconds=180.0)

# Execute
ctx = await swarm.run(
    initial_input="Starting data",
    entry_node_id="input"
)

# Access results
output = ctx.get_output("output")

# Checkpoint and resume
checkpoint = swarm.checkpoint()
# ... later ...
swarm.resume(checkpoint)
```

### ThinkingGraph

Structured reasoning operations:

```python
from llmfetcher import ThinkingGraph, ThinkingNodeType, ThinkingEdgeType

graph = ThinkingGraph()

# Add nodes
node_id = graph.add_node(
    node_type=ThinkingNodeType.CLAIM,
    info="Statement or conclusion",
    tags=["important", "verified"],
    confidence=0.9,
    payload={"source": "research_paper"},
    created_by="agent_name"
)

# Add edges
graph.add_edge(
    source_id=node1,
    target_id=node2,
    edge_type=ThinkingEdgeType.SUPPORTS,
    strength=0.85,
    created_by="agent_name"
)

# Query graph
nodes = graph.get_nodes_by_type(ThinkingNodeType.EVIDENCE)
edges = graph.get_edges_by_type(ThinkingEdgeType.CONTRADICTS)

# Get full state
state = await graph.get_full_graph()

# Transaction history
transactions = graph.get_transaction_log()
```

## 🧪 Testing

Run the test suite:

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_agent_concurrency.py -v

# Run with coverage
pytest tests/ --cov=llmfetcher --cov-report=html
```

### Test Coverage

- **Concurrency Tests**: Verify parallel tool execution
- **I/O Tests**: Validate message formatting and context building
- **Integration Tests**: End-to-end LLM interaction scenarios

## 📝 Development Guidelines

### Code Style

This project follows standard Python conventions:

- Type hints for all public APIs
- Docstrings for classes and methods
- Async/await for I/O operations
- Dataclasses for structured data

### Adding New Tools

1. Create tool function with proper type hints:

```python
async def my_tool(param: str) -> str:
    """Tool description for LLM understanding."""
    # Implementation
    return result
```

2. Wrap in Tool object:

```python
tool = Tool(
    name="my_tool",
    description="Clear description",
    parameters={
        "type": "object",
        "properties": {
            "param": {"type": "string"}
        },
        "required": ["param"]
    },
    handler=my_tool
)
```

3. Register with agent or swarm:

```python
agent.add_tool(tool)
# or
swarm.add_tool(tool)
```

### Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built with inspiration from modern agent orchestration frameworks
- Leverages OpenAI's SDK for LLM interactions
- Implements concepts from multi-agent systems research

## 📞 Support

For issues, questions, or contributions:

- 📧 Email: [lunaticlegagcy@163.com]
- 🐛 Issues: [GitHub Issues](https://github.com/LunaticLegacy/llmfetcher/issues)
- 💬 Discussions: [GitHub Discussions](https://github.com/LunaticLegacy/llmfetcher/discussions)

---

**Made with ❤️ by the LLM Fetcher Team**
