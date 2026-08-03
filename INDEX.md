# Angelus — Root INDEX

Multi-agent LLM framework with observable agent control plane, built on LLMFetcher.
Provides CLI + Web UI for interactive sessions with tool use, swarm collaboration, and TLB-RAG knowledge retrieval.

## Route Map

| Entry | Type | Purpose |
|-------|------|---------|
| [`angelus/`](angelus/INDEX.md) | Package | Main Python package: agent loop, webapp, classes, tools, TLB-RAG, swarm |
| [`llmfetcher/`](llmfetcher/INDEX.md) | Submodule | LLM abstraction layer: backends, context handlers, tool framework |
| [`frontend/`](frontend/INDEX.md) | Dir | Web UI assets: HTML templates, JavaScript modules, CSS |
| [`tests/`](tests/INDEX.md) | Dir | Test suite (18 test files, pytest) |
| [`docs/`](docs/INDEX.md) | Dir | Design documents, semantic map, research drafts |
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

- **"How does the agent loop work?"** → `angelus/agent.py`
- **"How are API routes defined?"** → `angelus/webapp.py` → `angelus/api/`
- **"What classes/models exist?"** → `angelus/classes/INDEX.md`
- **"How does TLB RAG work?"** → `angelus/rag_module_tlb/INDEX.md`
- **"How does the swarm work?"** → `angelus/swarm_module/INDEX.md`
- **"What tools are available?"** → `angelus/tools/INDEX.md`
- **"What tests exist?"** → `tests/INDEX.md`
- **"Where is the frontend code?"** → `frontend/INDEX.md` → `frontend/static/INDEX.md`
- **"How does LLMFetcher work?"** → `llmfetcher/INDEX.md`
- **"What backends are supported?"** → `llmfetcher/fetcher_handlers/`
- **"How does context compaction work?"** → `llmfetcher/context_handlers/linear.py`
