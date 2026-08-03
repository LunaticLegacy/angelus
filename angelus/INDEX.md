# angelus/ — Main Package INDEX

Core Python package: agent orchestration, web control plane, data classes, tools, TLB-RAG, and swarm collaboration.

## Route Map

| Entry | Type | Purpose |
|-------|------|---------|
| [`classes/`](classes/INDEX.md) | Package | Data models: Pydantic request models, dataclasses (ActiveRun, BrowserSession, BrowserRunControl) |
| [`rag_module_tlb/`](rag_module_tlb/INDEX.md) | Package | TLB-style hierarchical RAG: filesystem-based knowledge retrieval via INDEX.md traversal |
| [`swarm_module/`](swarm_module/INDEX.md) | Package | Multi-agent swarm: ExecutionGraph DAG, TaskBus coordination |
| [`tools/`](tools/INDEX.md) | Package | Built-in tool factories: shell execution, swarm spawn tools |
| `agent.py` | Module | Core Agent loop: message rounds, tool execution, hooks, context persistence |
| `webapp.py` | Module | FastAPI web server: REST API + SSE event stream, session/workspace/connector management |
| `cli.py` | Module | CLI entry point: `angelus web`, `run`, `chat`, `workspace` sub-commands |
| `task_planning.py` | Module | File-based JSON task plan store for structured agent workflows |
| `__init__.py` | Module | Package init |
| `__main__.py` | Module | `python -m angelus` entry |

## Direct Leaf Files

| File | Summary |
|------|---------|
| `agent.py` | `Agent` class: `run()` loop with tool execution, context management, hooks, stop/steer control. Uses `AgentRunControl` for cooperative interruption. |
| `webapp.py` | FastAPI app with 30+ REST endpoints. Manages workspaces, sessions, connectors, runs (SSE streaming), task plans, execution graphs. Session state in `workspace/` dir. |
| `cli.py` | argparse-based CLI. Sub-commands: `web` (start server), `run` (one-shot prompt), `chat` (interactive), `workspace` (CRUD), `list-backends`, `list-tools`. |
| `task_planning.py` | `TaskPlanStore`: JSON file-backed CRUD for task plans with goal, summary, and task list. |

## Intent Routing

- **Agent lifecycle** → `agent.py` (Agent.run, AgentRunControl)
- **Web API endpoint** → `webapp.py` (30 routes)
- **Request/response models** → `classes/INDEX.md`
- **Knowledge retrieval** → `rag_module_tlb/INDEX.md`
- **Multi-agent coordination** → `swarm_module/INDEX.md`
- **Tool implementation** → `tools/INDEX.md`
- **CLI commands** → `cli.py`
- **Task planning** → `task_planning.py`
