# Angelus — Root INDEX

Multi-agent LLM workbench with an observable browser control plane, built on
LLMFetcher. Provides interactive sessions, durable event/context state,
connector management, swarm collaboration, and graph-backed long-term memory.

## Route Map

| Entry | Type | Purpose |
|-------|------|---------|
| [`angelus/`](angelus/INDEX.md) | Package | Browser webapp, request models, run control, and task-planning helpers |
| [`llmfetcher/`](llmfetcher/INDEX.md) | Submodule | LLM abstraction layer: backends, context handlers, tool framework |
| [`frontend/`](frontend/INDEX.md) | Dir | Web UI assets: HTML templates, JavaScript modules, CSS |
| [`tests/`](tests/INDEX.md) | Dir | `unittest` regression suite for persistence, graph memory, web UI APIs, and swarm behavior |
| [`docs/`](docs/INDEX.md) | Dir | Design documents, semantic map, graph-memory design, and research drafts |
| `pyproject.toml` | File | Build config: setuptools, dependencies (fastapi, uvicorn, pydantic, markdown-it-py) |
| `README.md` | File | Project overview, quickstart, architecture summary |
| `CODEMAP.md` | File | Semantic contract for agentic code changes — authoritative architecture reference |
| `LICENSE` | File | License text |
| `LICENSING.md` | File | Licensing policy |
| `commercial-licensing.md` | File | Commercial licensing terms |
| `MANIFEST.in` | File | Source distribution manifest |
| `.gitignore` | File | Git ignore rules |
| `.gitmodules` | File | Submodule registration (llmfetcher) |

## Quick Intent Routing

- **"How does the agent loop work?"** → `llmfetcher/agent.py`
- **"How are API routes defined?"** → `angelus/webapp.py`
- **"What classes/models exist?"** → `angelus/classes/INDEX.md`
- **"How does graph context / archive retrieval work?"** → `llmfetcher/graph_memory/` and `llmfetcher/context_handlers/`
- **"How does the swarm work?"** → `llmfetcher/swarm_module/INDEX.md`
- **"What tools are available?"** → `llmfetcher/tools/INDEX.md`
- **"What tests exist?"** → `tests/INDEX.md`
- **"Where is the frontend code?"** → `frontend/INDEX.md` → `frontend/static/INDEX.md`
- **"How does LLMFetcher work?"** → `llmfetcher/INDEX.md`
- **"What backends are supported?"** → `llmfetcher/fetcher_handlers/`
- **"How does context compaction work?"** → `llmfetcher/context_handlers/linear.py`
