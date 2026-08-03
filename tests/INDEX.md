# tests/ — Test Suite INDEX

Pytest-based test suite covering agent lifecycle, context management, web API, swarm, TLB-RAG, and utilities.

## Route Map — Leaf Files

| File | What It Tests |
|------|---------------|
| `test_agent_stop_persistence.py` | Agent stop boundary saves context before exit |
| `test_agent_turns_from_events.py` | `_agent_turns_from_events()` reconstructs conversation turns from event log |
| `test_connector_store.py` | Connector CRUD: create, read, update, delete |
| `test_context_compaction.py` | ContextHandlerLinear compaction: threshold trigger, LLM summarization |
| `test_execution_graph_persistence.py` | ExecutionGraph persistence and recovery |
| `test_public_api.py` | Package public API surface: imports, exports |
| `test_retrieved_context.py` | RetrievedContextHandler: TLB-RAG memory injection |
| `test_session_history.py` | Session history rebuild from events and legacy context files |
| `test_session_observability.py` | Session event logging, SSE streaming |
| `test_shell_tools.py` | Shell tool execution, sandboxing |
| `test_state_root.py` | `_default_state_root()`: workspace directory resolution |
| `test_task_bus.py` | TaskBus: assignment, report, synchronization |
| `test_task_planning.py` | TaskPlanStore: CRUD operations on JSON plans |
| `test_tlb_rag.py` | TLB-RAG handler: traversal, cache, retrieval |
| `test_tlb_reliability.py` | TLB-RAG reliability: edge cases, error handling |
| `test_web_markdown.py` | `render_markdown()`: CommonMark rendering |
| `test_webapp_context_threshold.py` | Webapp context threshold configuration |
| `test_workspace_deletion.py` | Workspace deletion: cleanup, active run handling |

## Intent Routing

- **Agent tests** → `test_agent_stop_persistence.py`, `test_agent_turns_from_events.py`
- **Web/API tests** → `test_connector_store.py`, `test_web_markdown.py`, `test_webapp_context_threshold.py`, `test_workspace_deletion.py`
- **Context tests** → `test_context_compaction.py`, `test_retrieved_context.py`, `test_session_history.py`
- **Swarm tests** → `test_execution_graph_persistence.py`, `test_task_bus.py`
- **TLB-RAG tests** → `test_tlb_rag.py`, `test_tlb_reliability.py`
- **Other** → `test_public_api.py`, `test_session_observability.py`, `test_shell_tools.py`, `test_state_root.py`, `test_task_planning.py`
