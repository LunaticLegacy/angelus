# llmfetcher

[![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/)

`llmfetcher` is a small synchronous Python framework for tool-using LLM
agents and concurrent multi-agent workflows. It provides a provider-neutral
LLM dispatcher, bounded conversation contexts, a dependency-driven execution
graph, and a TaskBus for structured subagent handoffs.

The library deliberately keeps orchestration explicit. An Agent owns its
model loop and tools. An `AgentSwarm` owns dependency scheduling. Dynamic
workers return bounded reports through the TaskBus instead of injecting raw
model transcripts into a coordinator context.

## Status

The package is under active development. APIs documented in this README match
the current source tree. The sections [Current limitations](#current-limitations)
and [Roadmap](#roadmap) are intentional boundaries, not implemented features.

## Features

- **Multi-backend LLM dispatch** with OpenAI-compatible, Anthropic, LiteLLM,
  OpenVINO, and ONNX Runtime handlers; ordered fallback and per-backend retry.
- **Synchronous Agent loop** with model tool calls, parallel tool batches,
  token accounting, event hooks, cooperative stop/steer controls, and bounded
  default execution budgets.
- **Context handling** with JSON persistence, bounded tool-result retention,
  and LLM-based compaction that uses a standalone bounded summary request.
- **Retrieval context contract** through `RetrievedContextHandler` and the
  provider-neutral `MemoryProvider` protocol.
- **Dependency-driven swarm execution** using a thread pool, DAG edges,
  split/gather, input mappers, post-completion routers, and thread-safe dynamic
  graph changes.
- **TaskBus subagents** with immutable task packages and report-only feedback
  loops. Raw worker `run()` output remains audit data, not coordinator input.
- **Structured tools** represented by Python callables plus JSON Schema-like
  `ToolParameter` definitions.
- **Execution events** for agent, graph, tool, routing, and task lifecycle
  visibility.

## Installation

Requires Python 3.12 or later.

```bash
git clone https://github.com/LunaticLegacy/llmfetcher.git
cd llmfetcher
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

The base dependencies install the OpenAI, Anthropic, and LiteLLM client
libraries. Local OpenVINO and ONNX Runtime handlers require their respective
runtime packages.

## Web Console

The repository includes a local, single-page frontend for chatting with an
`Agent` and observing its execution. It exposes the same backend configuration,
tool registration, budgets, event hooks, and cooperative stop controls used by
the Python API.

```bash
pip install -e .
llmfetcher-web
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765). Configure a provider,
model, optional API URL and key, then send a message. API keys are used only to
start the active run and are not stored in the persisted chat context. Context
files are saved locally under `.llmfetcher/sessions/`.

The optional Shell switch exposes the existing restricted `shell` tool with its
working directory limited to the process directory. Only enable it for models
you trust with local-machine access.

### Workspaces and CLI

Each workspace has its own persistent chat context. Select one in the console,
or manage it from the main CLI:

```bash
llmfetcher workspace list
llmfetcher workspace create "产品研究"
llmfetcher web --port 8765
```

`llmfetcher web` is equivalent to `llmfetcher-web`; the latter remains a
convenient dedicated console entry point.

## Quick Start

Create one text Agent. `Agent.run()` is synchronous and returns the final
normalized `LLMOutput`.

```python
from llmfetcher import Agent, LLMBackendConfig, LLMFetcher

fetcher = LLMFetcher([
    LLMBackendConfig(
        name="primary",
        provider="openai",
        model="gpt-4.1-mini",
        api_key="<api-key>",
        api_url="https://api.openai.com/v1",
    ),
])

agent = Agent(
    llm_fetcher=fetcher,
    system_prompt="Answer concisely and cite uncertainty.",
    default_max_rounds=6,
    default_max_tokens=2_048,
)

result = agent.run("Explain why shirts use different sleeve lengths.")
print(result.content)
print(agent.usage.total_tokens)
```

## LLM Backends and Fallback

Each `LLMBackendConfig` identifies one backend. `LLMFetcher` tries its default
backend first, retries timeouts according to `max_retries`, then falls through
to the remaining registered backends when appropriate.

```python
from llmfetcher import LLMBackendConfig, LLMFetcher

fetcher = LLMFetcher([
    LLMBackendConfig(
        name="primary",
        provider="openai",
        model="deepseek-v4-flash",
        api_key="<deepseek-key>",
        api_url="https://api.deepseek.com",
        timeout=90,
        max_retries=1,
    ),
    LLMBackendConfig(
        name="fallback",
        provider="anthropic",
        model="claude-sonnet-4-6",
        api_key="<anthropic-key>",
        max_retries=0,
    ),
])

# Use the primary with fallback.
response = fetcher.fetch("Summarize this note.")

# Force one named backend for this request only.
fallback_response = fetcher.fetch(
    "Independently check the conclusion.",
    backend_name="fallback",
)
```

Supported handler names are:

| Provider value | Handler | Typical use |
| --- | --- | --- |
| `openai` | OpenAI-compatible Chat Completions | OpenAI and compatible endpoints |
| `anthropic` | Anthropic Messages API | Claude-compatible endpoints |
| `litellm` | LiteLLM | LiteLLM-supported providers |
| `openvino` | OpenVINO | Local inference |
| `onnxruntime` | ONNX Runtime GenAI | Local inference |

Multi-backend fallback is not the same as task-aware model routing. See
[Current limitations](#current-limitations).

## Tools

A tool has a stable name, description, JSON Schema-like parameters, and a
synchronous handler. Agent tool calls in one model response execute in
parallel, while the resulting tool messages retain their original call order.

```python
from llmfetcher import Tool
from llmfetcher.llm_types import ToolParameter, ToolSchema

def convert_size(size: str) -> str:
    """Return an example normalized jersey size."""
    return {"s": "small", "m": "medium", "l": "large"}.get(
        size.lower(), "unknown"
    )

agent.add_tool(Tool(
    name="convert_size",
    description="Normalize a jersey size code.",
    schemas=ToolSchema(properties=[
        ToolParameter(
            name="size",
            type="string",
            description="Input size code such as S, M, or L.",
        ),
    ]),
    handler=convert_size,
))
```

Built-in factories currently include:

- `create_shell_tools()` for bounded shell execution.
- `create_knowledge_tools()` for the package's knowledge-base adapter.
- `create_obscura_tools()` for configured web search, fetch, and scrape tools.
- `create_swarm_tools()` for coordinator-controlled dynamic workers and graph
  mutation.

Tool handlers are local Python callables. They must validate their own inputs,
apply side-effect policy, and return bounded results suitable for model context.

## Context and Memory

`ContextHandlerLinear` stores short-term history and persists complete tool
results as JSON when an Agent has a `context_path`. If the conversation exceeds
the model context budget, a separate compaction request protects the next model
call; this does not overwrite the persisted tool result.
When its threshold is exceeded, the handler asks the configured LLM for a
bounded standalone summary instead of replaying an unbounded transcript.

```python
from pathlib import Path

agent = Agent(
    llm_fetcher=fetcher,
    system_prompt="You are a research assistant.",
    context_path=Path("sessions/research.json"),
    max_context_threshold=48_000,
)
```

`RetrievedContextHandler` composes linear history with a `MemoryProvider`:

```python
from llmfetcher.context_handlers import RetrievedContextHandler
from llmfetcher.memory import MemoryProvider

# Implement MemoryProvider.search(...) and MemoryProvider.add(...)
# with a vector, hybrid, or remote store, then pass it to the Agent.
context = RetrievedContextHandler(
    memory_provider=my_memory_provider,  # type: MemoryProvider
    compacting_llmfetcher_handler=fetcher,
    namespace="team:catalog",
)
```

The library provides the memory interface and retrieval-aware context handler;
it does not currently ship a concrete vector database implementation.

## Agent Lifecycle Controls and Events

`AgentRunControl` exposes safe boundaries between complete
model-and-tool steps. A control implementation may request a stop or enqueue
new user steering text. `Agent.request_completion()` is for terminal workflow
tools: it completes the Agent only after the active tool batch and context write
finish.

Hooks receive `ExecutionEvent` objects synchronously. Hook failures are
isolated from the running Agent.

```python
from llmfetcher.events import ExecutionEvent

def print_event(event: ExecutionEvent) -> None:
    print(event.event_type, event.agent_name, event.message)

agent.add_hook(print_event)
```

## Static Swarm Workflow

An `AgentSwarm` schedules Agents as soon as each node's dependencies are
satisfied. Independent nodes can run concurrently up to
`max_concurrency_agents`.

```python
from llmfetcher import Agent, AgentSwarm

researcher = Agent(llm_fetcher=fetcher, system_prompt="Find facts.")
writer = Agent(llm_fetcher=fetcher, system_prompt="Write a concise report.")

swarm = AgentSwarm(max_concurrency_agents=2)
swarm.add_agent("researcher", researcher)
swarm.add_agent("writer", writer)
swarm.add_connection("researcher", "writer")

outputs = swarm.run("Research the history of a football shirt.")
print(outputs["writer"].content)
```

`add_split`, `add_gather`, `set_mapper`, and `set_router` provide fan-out,
fan-in, input transformation, and post-completion routing. `print(swarm._graph)`
renders a diagnostic topology snapshot.

## Dynamic Subagents with TaskBus

For dynamic work, give `create_swarm_tools()` only to the coordinator Agent.
The coordinator can dispatch independent workers and wait for their structured
reports. A dispatched worker receives only its task objective, bounded handoff,
and expected artifacts; it does not receive a coordinator's raw model context.

```python
from llmfetcher import Agent, AgentSwarm
from llmfetcher.tools import create_swarm_tools

swarm = AgentSwarm(max_concurrency_agents=4)
coordinator = Agent(
    llm_fetcher=fetcher,
    system_prompt=(
        "Delegate independent research with dispatch_subagents. "
        "Wait for all reports before writing a conclusion."
    ),
    default_max_rounds=8,
    default_max_tokens=4_096,
)
swarm.add_agent("coordinator", coordinator)

coordinator.add_tools(create_swarm_tools(
    swarm=swarm,
    llm_fetcher=fetcher,
    worker_tool_pool=[],
    coordinator_name="coordinator",
    worker_max_rounds=6,
    worker_max_tokens=2_048,
))

outputs = swarm.run("Compare three public data sources.")
```

The task protocol is intentionally narrow:

1. `dispatch_subagent` or `dispatch_subagents` creates a `TaskAssignment`.
2. The scheduler runs the worker independently of DAG edges.
3. The worker persists detailed material as artifacts where appropriate.
4. The worker calls its local `report_task` tool.
5. `report_task` writes a bounded immutable `TaskReport`, then ends that
   worker after the current tool batch.
6. The coordinator calls `wait_for_reports` and synthesizes only report fields.

This prevents large tool output, reasoning traces, and raw `Agent.run()` text
from becoming implicit parent-Agent context.

## Package Layout

```text
llmfetcher/
├── agent.py                 # Tool-using synchronous Agent loop
├── llm_fetcher.py           # Backend selection, retry, fallback, streaming
├── llm_types.py             # Provider-neutral models, tool schemas, usage
├── context_handlers/        # Linear and retrieval-aware contexts
├── memory/                  # Long-term memory contracts
├── fetcher_handlers/        # Provider adapters
├── swarm_module/            # ExecutionGraph, AgentSwarm, TaskBus
├── tools/                   # Local tool factories and dynamic worker tools
└── tests/                   # Offline regression tests
```

## Testing

The repository tests are offline and do not require an API key.

```bash
python -m unittest discover -s tests -v
```

For a source checkout whose parent directory owns the package:

```bash
PYTHONPATH="$(pwd)/.." python -m unittest discover -s tests -v
```

## Current Limitations

- **No native MCP client or MCP server support.** MCP tools are not yet
  discovered, lifecycle-managed, or converted into `Tool` instances.
- **No provider-neutral multimodal content blocks.** Context messages are
  text-oriented; image URLs, Base64 images, file IDs, and multimodal tool
  results need a message-model and provider-adapter extension.
- **No task-aware provider routing.** A fetcher can have fallback backends, but
  dynamic workers created by `create_swarm_tools()` use the configured shared
  fetcher. There is no persisted `AgentProfile` that selects a visual, OCR, or
  text model by task capability.
- **No in-flight execution recovery.** `ExecutionGraph.save()` / `load()`
  persist a quiescent topology, Agent specifications, callback IDs, and
  TaskBus mailbox state. They deliberately do not checkpoint running threads;
  application-owned tools, custom contexts, mappers, and routers require safe
  serializer/resolver registries.
- **No generic middleware pipeline.** Policies such as model routing, tool
  approvals, retries, PII filtering, and budget enforcement currently belong
  in application code or individual tool handlers.
- **Synchronous public runtime.** Agent and swarm execution use threads for
  concurrent tool and Agent work; there is no async public `Agent.run()` API.

## Roadmap

The next foundational work should preserve the explicit TaskBus model while
adding:

1. Provider-neutral multimodal message content blocks.
2. Persisted `AgentProfile` and `FetcherRegistry` model routing.
3. A policy-controlled MCP client adapter for stdio and HTTP transports.
4. A durable execution/checkpoint store for graph and TaskBus state.
5. Middleware-style lifecycle interception for model, tool, budget, and
   approval policies.

## License

This repository is licensed under the GNU Affero General Public License,
version 3 or later (AGPL-3.0-or-later).  For code whose copyright is held by
LunaticLegacy, a separately executed commercial license is also available;
see [LICENSING.md](LICENSING.md).  The open-source license text remains in
[LICENSE](LICENSE).
