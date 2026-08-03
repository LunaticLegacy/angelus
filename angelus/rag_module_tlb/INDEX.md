# angelus/rag_module_tlb/ — TLB RAG Module INDEX

TLB-style hierarchical knowledge retrieval. Filesystem-based — no vector DB, no embeddings. LLM agent navigates `INDEX.md` trees like a multi-level page table walk.

## Route Map — Leaf Files

| File | Purpose |
|------|---------|
| `core.py` | `TLBRAGHandler`: main entry point. `retrieve()` walks the filesystem hierarchy using a worker Agent, reads INDEX.md files, and resolves intents to leaf paths. Manages TLB cache (`dict[str, Path]`) with `threading.Lock`. Cache injected into worker queries ("当前 TLB 路由缓存:..."). Worker is stateless: `clear_context()` after every `retrieve()`. |
| `type.py` | Type definitions: `TLBRetrieveResult` (traversal trail, resolved paths, rejected branches, miss flag) |
| `prompt.py` | Worker agent system prompt: the TLB-RAG traversal procedure (normalize intent → check cache → walk INDEX.md → load leaves → cache) |
| `_read_file_tool.py` | `read_file` tool for the worker agent: reads INDEX.md and leaf files during traversal |
| `tlb_rag_tool.py` | `tlb_rag_tool`: exposes TLB RAG as a tool usable by other agents |
| `test_helpers.py` | Shared test utilities for TLB RAG tests |
| `__init__.py` | Package init |

## Design Principles (from user)

- **No vector storage**: Pure hierarchical filesystem with `INDEX.md` at each level
- **LLM-as-navigator**: Agent reads INDEX.md, decides routing — no pre-computed similarity
- **TLB cache**: `dict[str, Path]` protected by `threading.Lock`; lock only during dict ops, never during `worker_agent.run()`
- **Stateless worker**: `clear_context()` after each `retrieve()`; cache lives in Python dict, not LLM context
- **Cache injection**: Cache contents prepended to query: `"当前 TLB 路由缓存:\n{entries}\n\n---\n\n查询: {query}"`
- **Auditable**: Results include full traversal trail (visited indexes, rejected branches)
