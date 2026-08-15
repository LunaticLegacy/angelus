# tests/ — Test Suite INDEX

`unittest`-based regression suite covering persistence, graph context, web API,
swarm, TLB-RAG, and utilities.

## Route Map — Leaf Files

| File | What It Tests |
|------|---------------|
| `test_agent_stop_persistence.py` | Agent stop boundary saves context before exit |
| `test_agent_turns_from_events.py` | `_agent_turns_from_events()` reconstructs conversation turns from event log |
| `test_archive_retrieval.py` | Bounded lexical retrieval over compacted raw archive records |
| `test_connector_store.py` | Connector CRUD, API-key encryption/redaction, and server-side resolution |
| `test_context_archive_api.py` | Archived raw-context API pagination and provenance fields |
| `test_execution_graph_persistence.py` | ExecutionGraph persistence and recovery |
| `test_graph_builder.py` | Entity/relation extraction and graph ingestion |
| `test_graph_handler.py` | Hybrid linear/graph handler, compaction, and archive evidence injection |
| `test_graph_retriever.py` | Graph retrieval scoring, expansion, and rendering |
| `test_graph_semantic.py` | Stateless semantic graph worker and reranking boundary |
| `test_graph_store.py` | Graph storage, relations, communities, and persistence |
| `test_retrieved_context.py` | RetrievedContextHandler: TLB-RAG memory injection |
| `test_run_profile_persistence.py` | Credential-free runtime profile and durable event persistence |
| `test_session_history.py` | Session history rebuild from events and legacy context files |
| `test_session_observability.py` | Session event logging, SSE streaming |
| `test_shell_tools.py` | Shell tool execution, sandboxing |
| `test_state_root.py` | `_default_state_root()`: workspace directory resolution |
| `test_swarm_failure_isolation.py` | Worker failure isolation and coordinator reporting |
| `test_task_planning.py` | TaskPlanStore: CRUD operations on JSON plans |
| `test_tlb_rag.py` | TLB-RAG handler: traversal, cache, retrieval |
| `test_tlb_reliability.py` | TLB-RAG reliability: edge cases, error handling |
| `test_web_markdown.py` | `render_markdown()`: CommonMark rendering |
| `test_webapp_context_threshold.py` | Webapp context threshold configuration |
| `test_workspace_deletion.py` | Workspace deletion: cleanup, active run handling |

## Intent Routing

- **Agent tests** → `test_agent_stop_persistence.py`, `test_agent_turns_from_events.py`
- **Web/API tests** → `test_connector_store.py`, `test_web_markdown.py`, `test_webapp_context_threshold.py`, `test_workspace_deletion.py`
- **Context tests** → `test_archive_retrieval.py`, `test_context_archive_api.py`, `test_graph_handler.py`, `test_retrieved_context.py`, `test_session_history.py`
- **Swarm tests** → `test_execution_graph_persistence.py`, `test_swarm_failure_isolation.py`
- **TLB-RAG tests** → `test_tlb_rag.py`, `test_tlb_reliability.py`
- **Other** → `test_session_observability.py`, `test_shell_tools.py`, `test_state_root.py`, `test_task_planning.py`
