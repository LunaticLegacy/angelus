# Code Semantic Map

This file is the repository's semantic contract for agentic code changes.
Read it before modifying code. Update it after changing behavior.

## Architecture

- **What the system does:** A multi‑agent LLM framework that orchestrates LLM‑backed agents with tool use, context management, swarm collaboration, and a RAG‑based knowledge base. Provides both a CLI and a web UI for interactive sessions.
- **Main execution path:** CLI (`cli.main`) or web server (`webapp.main`) → bootstrap an `Agent` (or `ExecutionGraph` swarm) → agents use `LLMFetcher` to call LLM backends → tools are executed via `ToolExecutor` → context is managed by `ContextHandler` → results streamed/returned.
- **Major components and dependencies:**
  - Core agent loop (`agent.py`)
  - LLM abstraction layer (`llm_fetcher.py`, `fetcher_handlers/*`)
  - Type system (`llm_types.py`)
  - Context handlers (linear with compaction, retrieved with memory)
  - Tool framework (`tool_handler.py`, `tool_executor.py`, `tools/*`)
  - Swarm orchestration (`swarm_module/*`, `task_bus.py`)
  - RAG knowledge base (`rag_module/*`)
  - Task planning (`task_planning.py`)
  - Web UI (`webapp.py`, `web/static/app.js`)
  - Configuration and CLI (`cli.py`, `pyproject.toml`)

## Modules

- **`llm_fetcher.py`** – Orchestrates calls to LLM backends with fallback/retry. Owns `LLMFetcher` class.
- **`agent.py`** – Core agent loop: handles message rounds, tool execution, hooks, and context.
- **`llm_types.py`** – Data types for LLM interactions (errors, configs, tool calls, usage, output).
- **`fetcher_handlers/`** – Pluggable backend providers: Anthropic, OpenAI, ONNX Runtime, OpenVINO, LiteLLM.
- **`context_handlers/`** – Conversation memory strategies: linear (with compaction) and retrieved (with memory provider).
- **`tool_handler.py` & `tool_executor.py`** – Tool registry and concurrent execution.
- **`tools/`** – Built‑in tool factories: shell, web search (obscura), knowledge base, swarm dynamic operations.
- **`swarm_module/`** – Execution graph (`ExecutionGraph`) and `TaskBus` for multi‑agent collaboration.
- **`memory/`** – Abstract memory provider interface for long‑term storage.
- **`rag_module/`** – RAG pipeline: document loading, chunking, embedding, vector store, keyword retrieval, hybrid retrieval.
- **`task_planning.py`** – File‑based task plan store for structured agent workflows.
- **`webapp.py`** – Flask web server exposing REST APIs and SSE event stream.
- **`cli.py`** – Command‑line interface for direct agent interaction.

---

## API Surface

### CLI Commands

| Command | Purpose | Flags/Args |
|---------|---------|-------------|
| `run` | Run a single prompt through the agent (one‑shot). | Prompt, backend/model options, tool selection. |
| `chat` | Interactive chat session with history. | Backend/model options, tool selection. |
| `web` | Start the web UI server. | Host/port (if configurable). |
| `workspace` | Manage persistent workspaces (list, create, delete). | Sub‑commands: create, list, delete. |
| `list-backends` | List available LLM backends. | – |
| `list-tools` | List available tool factories. | – |

*Note: The symbolic scan shows these commands are defined in `cli._build_parser`; actual flag details inferred from variable names and typical patterns.*

### HTTP/RPC API Endpoints (webapp.py)

| Method | Path | Request Shape | Response Shape |
|--------|------|---------------|-----------------|
| `GET` | `/` | – | `web/templates/index.html` (static) |
| `GET` | `/providers` | – | JSON list of backend providers |
| `GET` | `/connectors` | – | JSON list of saved connector configs |
| `POST` | `/connectors` | `ConnectorRequest {name}` | JSON created connector |
| `PUT` | `/connectors/<id>` | `ConnectorRequest {name}` | JSON updated connector |
| `DELETE` | `/connectors/<id>` | – | JSON remaining connectors |
| `GET` | `/workspaces` | – | JSON list of workspaces |
| `POST` | `/workspaces` | `WorkspaceRequest {name}` | JSON created workspace |
| `DELETE` | `/workspaces/<id>` | `WorkspaceDeleteRequest {confirmation}` | JSON remaining workspaces |
| `POST` | `/workspaces/<workspace_id>/sessions/<session_id>/run` | `RunRequest {session_id, workspace_id, message, config}` | JSON run started + SSE stream URL |
| `GET` | `/workspaces/<workspace_id>/sessions/<session_id>/events` | – | `text/event-stream` of `ExecutionEvent` |
| `POST` | `/workspaces/<workspace_id>/sessions/<session_id>/stop` | – | JSON stop confirmation |
| `POST` | `/workspaces/<workspace_id>/sessions/<session_id>/steer` | `SteerRequest {message}` | JSON steer confirmation |
| `GET` | `/workspaces/<workspace_id>/sessions/<session_id>/history` | – | JSON message history |
| `GET` | `/sessions/<session_id>/agents` | – | JSON selectable Agent identities from the persisted execution graph |
| `GET` | `/sessions/<session_id>/messages?agent=<agent_id>` | – | JSON message history for the aggregate session or one Agent context |
| `GET` | `/workspaces/<workspace_id>/sessions/<session_id>/graph` | – | Reconciled graph with typed edges, `run_status`, `node_states`, assignments and precise task terminals |
| `GET` | `/workspaces/<workspace_id>/sessions/<session_id>/plan` | – | JSON task plan |
| `POST` | `/workspaces/<workspace_id>/sessions/<session_id>/plan` | `TaskPlanRequest {goal, summary, tasks}` | JSON updated plan |
| `PATCH` | `/workspaces/<workspace_id>/sessions/<session_id>/tasks/<task_id>` | `TaskStatusRequest {status}` | JSON updated plan |

### Exported Package API (`__init__.py`)

- `__version__`: package version string
- `__author__`: package author string
- Implicitly re‑exports public classes/functions from core modules (pattern unknown, but likely includes `Agent`, `LLMFetcher`, etc.)

---

## Classes

### `AgentRunControl` (`agent.py`)
- **Constructor:** no explicit parameters; initializes internal stop flag and steer queue.
- **Fields:**
  - `_stopped` (bool) – whether stop requested.
  - `_steers` (list) – collected steer messages.
- **Invariants:** Must be thread-safe (method calls likely protected).
- **Lifecycle:** Created per `Agent.run()` call, passed to tool handlers to check for stop/steer.

### `Agent` (`agent.py`)
- **Constructor:** `__init__(llm_fetcher, system_prompt, max_concurrency, max_context_threshold, context_path, context_handler, default_max_rounds, default_max_tokens)`
  - Sets up tool handler, tool executor, hooks list, usage tracking.
- **Stored fields/instance state:**
  - `llm_fetcher` (`LLMFetcher`)
  - `system_prompt` (str)
  - `max_concurrency` (int)
  - `max_context_threshold` (int)
  - `context_path` (str)
  - `default_max_rounds` (int)
  - `default_max_tokens` (int)
  - `tool_handler` (`ToolHandler`)
  - `tool_executor` (`ToolExecutor`)
  - `context_handler` (`ContextHandler`)
  - `_agent_name_in_graph` (str) – optional identity in graph.
  - `usage` (dict) – cumulative token usage.
  - `hooks` (list of callables)
  - `_completion_requested` (bool)
- **Invariants:** `context_handler` must implement `ContextHandler` interface.
- **Lifecycle:** Instantiated per session/graph node; `run()` callback until stop or max rounds; `close()` releases executor resources.

### `LLMFetcher` (`llm_fetcher.py`)
- **Constructor:** `__init__(backends, default_backend, backend)` – registers backend configs and creates handlers.
- **Fields:**
  - `backends` (dict of `LLMBackendConfig`)
  - `backend_order` (list) – fallback order.
  - `handlers` (dict of `LLMBackendHandler`)
  - `default_backend` (str)
- **Invariants:** At least one backend must be registered; handler list built lazily.
- **Lifecycle:** Long‑lived, shared across agents.

### `ContextHandlerLinear` (`context_handlers/linear.py`)
- **Constructor:** `__init__(compacting_llmfetcher_handler, max_context_threshold, compaction_input_char_limit, compaction_output_max_tokens)`
  - Stores compaction parameters.
- **Fields:** `llm_handler`, `compress_threshold`, `compaction_input_char_limit`, `compaction_output_max_tokens`, `abstract`, `messages`, `_round`.
- **Lifecycle:** Created per agent session; stores messages and periodically compacts conversation history into an abstract.

### `RetrievedContextHandler` (`context_handlers/retrieved.py`)
- **Constructor:** `__init__(memory_provider, compacting_llmfetcher_handler, memory_limit, namespace, persist_assistant, max_context_threshold)`
  - Delegates to linear handler and memory provider.
- **Fields:** `memory_provider`, `linear`, `memory_limit`, `namespace`, `persist_assistant`, `_retrieved`.
- **Lifecycle:** Similar to linear, but enriched with retrieved memory items.

### `ToolHandler` (`tool_handler.py`)
- **Constructor:** `__init__()` – initializes empty tool dict.
- **Fields:** `tool_dict` (dict of `Tool` by name)
- **Lifecycle:** Mutable registry; tools added/removed via `add_tool`/`remove_tool`.

### `ToolExecutor` (`tool_executor.py`)
- **Constructor:** `__init__(max_concurrency)` – sets up thread pool.
- **Fields:** `_max_concurrency` (int) and internal executor.
- **Lifecycle:** Created per agent; executes tool calls in parallel; `close()` shuts down the pool.

### `ExecutionGraph` (`swarm_module/execution_graph.py`)
- **Constructor:** `__init__(max_concurrency_agents)` – creates graph structures and a `TaskBus`.
- **Fields:**
  - `agent_dict` (dict)
  - `_successors`, `_predecessors` (adjacency)
  - `_mappers`, `_routers`, `_routing_nodes`
  - `task_bus` (`TaskBus`)
  - `_node_states` (UI-safe latest state per graph node)
  - `hooks`, `_hooks_lock`, `_topology_lock`
  - `_shutdown_requested`
- **Invariants:** Topology changes must be guarded by `_topology_lock`.
- **Lifecycle:** Created per swarm; supports dynamic topology changes; `run()` executes until done and `finalize_tasks()` closes unfinished assignments before persistence.

### `TaskBus` (`swarm_module/task_bus.py`)
- **Constructor:** `__init__()` – creates lists and condition variable.
- **Fields:** `_condition`, `_assignments`, `_task_states`, `_reports`, `_inboxes`.
- **Lifecycle:** Owned by `ExecutionGraph`; manages task assignments, report collection, and immutable `completed`/`failed`/`interrupted`/`cancelled` terminals.

### `TaskPlanStore` (`task_planning.py`)
- **Constructor:** `__init__(path)` – sets file path.
- **Fields:** `path` (str) – path to JSON plan file.
- **Lifecycle:** Instantiated per session; reads/writes task plan JSON.

### `BrowserRunControl` (`webapp.py`)
- **Constructor:** `__init__()` – initializes stop flag and steer queue.
- **Fields:** `_stopped` (bool), `_steers` (list)
- **Lifecycle:** Created per browser run; allows UI to stop/steer.

### `ActiveRun` (`webapp.py`)
- **Constructor:** `__init__(control, events, done, swarm)` – initializes run metadata.
- **Fields:** `control` (`BrowserRunControl`), `events` (list), `done` (bool), `swarm` (optional `AgentSwarm`)
- **Lifecycle:** Created when a run starts; holds event log and completion flag.

### `BrowserSession` (`webapp.py`)
- **Constructor:** `__init__(lock, active)` – initializes session state.
- **Fields:** `lock` (threading.Lock), `active` (optional `ActiveRun`)
- **Lifecycle:** Created per workspace/session combo; serializes concurrent access.

### Knowledge‑base classes (RAG module)
- **`KnowledgeConfig`** (`rag_module/knowledge/config.py`): Global config loaded from environment; fields: `root`, `embedding_model_name`, `local_files_only`, `result_limit`, `context_limit`, `excerpt_chars`, `embedding_max_chars`, `chunk_max_chars`, `chunk_overlap_chars`, `semantic_candidates`, `strategy_prefix`, index/chroma paths, `manifest_version`, `semantic_backend`.
- **`MarkdownKnowledgeLoader`** (`rag_module/knowledge/markdown_loader.py`): Loads `.md` files from root, respecting ignore patterns.
- **`TextTools`** (`rag_module/knowledge/text_utils.py`): Text chunking, excerpt building, term extraction.
- **`EmbeddingModelProvider`** (`rag_module/knowledge/embedding_model.py`): Loads and caches sentence‑transformer model.
- **`ChromaVectorStore`** (`rag_module/knowledge/vector_store.py`): Wraps ChromaDB for document vector index.
- **`KeywordRetriever`** (`rag_module/knowledge/keyword_retriever.py`): TF‑IDF‑like keyword scoring.
- **`HybridRetriever`** (`rag_module/knowledge/hybrid_retriever.py`): Combines vector and keyword results with re‑ranking.
- **`KnowledgeManifestStore`** (`rag_module/knowledge/manifest_store.py`): Persists document fingerprints and chunk counts.
- **`VectorIndexManager`** (`rag_module/knowledge/index_manager.py`): Orchestrates building/updating the vector index.
- **`TaskRetrievalPolicy`** (`rag_module/knowledge/task_policy.py`): Query building and boost logic for task‑oriented retrieval.
- **`KnowledgeBase`** (`rag_module/knowledge/facade.py`): Public API aggregating all RAG components.

### Fetcher Handler Classes
- **`AnthropicHandler`**, **`OpenAIHandler`**, **`LiteLLMHandler`**, **`OnnxRuntimeGenAIHandler`**, **`OpenVINOHandler`**: Each implements `LLMBackendHandler` interface, providing provider‑specific message translation, streaming, and tool schema conversion.

### Tool Classes (`tools/`)
- **`WebSearchStore`** (`tools/obscura_tools.py`): SQLite‑based store for search settings and usage.
- **`ObscuraCDPClient`** (`tools/obscura_tools.py`): WebSocket client for headless browser scraping.

---

## Interfaces / Types

| Name | Fields/Members | Implementers / Users | Semantic Meaning | Constraints |
|------|---------------|----------------------|------------------|-------------|
| `LLMError` | – (exception) | Raised by fetcher handlers | Base LLM error | – |
| `LLMTimeoutError` | – | Raised on timeout | Timeout during LLM call | – |
| `LLMBackendError` | – | Handler‑specific errors | Backend‑specific failure | – |
| `LLMBackendConfig` | `name`, `provider`, `model`, `api_key`, `api_url`, `timeout`, `max_retries`, `extra` | `LLMFetcher` registration | Describes an LLM endpoint | `provider` matches a handler’s `provider_names` |
| `LLMToolCall` | `name`, `arguments`, `call_id`, `source` | Tool execution pipeline | A call to a tool requested by the LLM | – |
| `ToolInfo` | `call` (LLMToolCall), `result` (any) | Agent tool result tracking | Outcome of a tool execution | – |
| `TokenUsage` | `input_tokens`, `output_tokens`, `total_tokens`, `cached_tokens`, `reasoning_tokens` | `LLMOutput` | Token consumption for a completion | Non‑negative integers; `cache_hit_rate()` computed if `input_tokens > 0` |
| `LLMOutput` | `content`, `provider`, `backend_name`, `model`, `role`, `reasoning_content`, `tool_calls`, `stop_reason`, `usage` | Returned by `LLMFetcher.fetch` | Normalized LLM response | `text()` returns `content` string |
| `LLMContext` | `role`, `timeline`, `content`, `content_reasoning`, `tool_calls`, `tags` | Context handlers | A turn in conversation history | – |
| `LLMContextCompacted` | `abstract_msg`, `source_timeline`, `source_uuid`, `tags` | Context compaction | Summarised version of older turns | – |
| `ToolParameter` | `name`, `type`, `description`, `required`, `enum`, `default` | `ToolSchema` | A tool input parameter | – |
| `ToolSchema` | `type` (str), `properties` (dict) → `to_dict()` | Tool registration | OpenAI‑compatible JSON schema for a tool | – |
| `Tool` | `name`, `description`, `schemas` (list of ToolSchema), `handler` | `ToolHandler` | A callable tool exposed to LLM | `handler` is a callable |
| `ToolBatch` | – | Placeholder for batch tool calls | Grouped tool execution | – |
| `ExecutionEvent` | `timestamp`, `source`, `agent_name`, `event_type`, `message`, `data` | Agent hooks, SSE streaming | Observable event during execution | – |
| `ExecutionHook` | Callable type | Agent/Graph hooks | Observer callback for events | Signature: `(ExecutionEvent) -> None` |
| `TaskAssignment` | `id`, `recipient`, `reply_to`, `objective`, `handoff`, `expected_artifacts`, `created_at` | `TaskBus` | A task delegated to an agent | – |
| `TaskReport` | `task_id`, `reporter`, `recipient`, `status`, `summary`, `findings`, `evidence`, `artifacts`, `open_questions`, `recommended_next_action`, `created_at` | `TaskBus` | Report of completed task | – |
| `MemoryItem` | `content`, `score`, `memory_id`, `metadata` | Memory providers | A recallable memory entry | – |
| `MemoryProvider` | `search(query, limit, namespace)`, `add(item, namespace)` | `RetrievedContextHandler` | Abstract interface for long‑term memory | Implementations must be thread‑safe? (inferred) |
| `ContextHandler` | `add_user_message`, `add_assistant_message`, `build_messages`, `save`, `load` | Agent context pipeline | Interface for conversation storage and retrieval | – |
| `LLMBackendHandler` | `create_completion`, `normalize_completion_response`, `iter_stream_text`, `prepare_tools`, etc. | All fetcher handler classes | Interface for LLM provider integration | Must map messages to provider format |
| Various knowledge types: `KnowledgeHit`, `KnowledgeIndexEntry`, `KnowledgeDocument`, `KnowledgeChunk`, `MarkdownBlock`, `VectorHit`, `RetrievalQuery`, `ManifestMeta` | As defined in `rag_module/knowledge/models.py` | RAG pipeline | Domain objects for document chunks and search results | – |

---

## Functions / Methods

*(For brevity, only high‑impact or publicly exposed functions are listed; implementation details inferred from signature and context.)*

| Full Name | Visibility | Parameters | Return | Side Effects | Errors | Calls Out To | Called By | Semantic Role |
|-----------|------------|-----------|--------|-------------|--------|--------------|-----------|---------------|
| `cli.main` | Public (CLI entry) | `argv=sys.argv` | None | Starts CLI or web server, possibly writes to stdout | Exits on parse errors | `_build_parser`, command handlers | OS | Dispatches sub‑command |
| `cli._bootstrap_agent` | Private | `args` (Namespace) | `Agent` | Reads config, creates LLMFetcher and Agent | Config errors | `_build_backend_config`, `LLMFetcher`, `Agent`, `_load_tools` | `_cmd_run`, `_cmd_chat` | Creates a fully configured agent |
| `LLMFetcher.fetch` | Public | `msg`, `system_prompt`, `temperature`, `max_tokens`, `context_handler`, `backend_name`, `tools` | `LLMOutput` | Makes HTTP (or local) LLM calls, may retry | `LLMError`, `LLMTimeoutError` | `_handler_for_backend`, handler’s `create_completion` | Agent, context handlers | Fetch an LLM completion with fallback |
| `LLMFetcher.fetch_stream` | Public | Similar + `output_reasoning` | Generator of `str`/`tool_calls` | As above, yields incremental text | As above | As above | Agent, SSE endpoint | Streaming LLM fetch |
| `Agent.run` | Public | `message`, `max_rounds`, `temperature`, `max_tokens`, `verbose`, `control` | `LLMOutput` (final) | Executes tool calls, emits events, updates context; saves every completed boundary before a cooperative stop | `LLMError`, tool errors, `AgentRunStopped` | `LLMFetcher.fetch`, `ToolExecutor.execute_batch`, `ContextHandler` methods, hooks | CLI, web, swarm | Main agent loop |
| `Agent._save_context` | Private | None (uses configured `context_path`) | `bool` | Writes the current context when persistence is configured | Handler write failures become `False` | `ContextHandler.save` | `Agent.run` | Share normal-completion and stop-boundary context persistence |
| `Agent.close` | Public | None | None | Shuts down `ToolExecutor` | – | `ToolExecutor.close` | Caller | Cleanup resources |
| `ContextHandlerLinear.add_assistant_message` | Public | `message`, `tool_results` | None | Parses tool calls, trims tool results, appends to message list; may trigger compaction | – | `ToolHandler.get_handlers_and_arguments`, `compact` | Agent | Store assistant response with tool results |
| `ContextHandlerLinear.compact` | Private | None (uses internal state) | None (updates `abstract`) | Calls a stateless LLM to summarise history, empties old messages | `LLMError` | `CompactionFetcher.fetch` | Called when context threshold exceeded | Reduce token usage by summarization |
| `ContextHandlerLinear.build_messages` | Public | None | `list[dict]` | Returns messages suitable for LLM API | – | – | Agent before fetch | Assemble conversation for the LLM |
| `ToolExecutor.execute_batch` | Public | `handlers`, `arguments_list` | `list[result]` | Runs tool functions in a thread pool; captures exceptions | Individual tool exceptions | Submits to executor | Agent | Parallel tool execution |
| `ExecutionGraph.run` | Public | `message`, `control` | `dict` of agent outputs | Dispatches tasks via `TaskBus`, schedules agents, collects reports | Task failures | `TaskBus`, `Agent.run`, routing functions | Swarm coordinator | Execute a DAG of agents |
| `ExecutionGraph.finalize_tasks` | Public | – | changed task-state mapping | Interrupts running tasks, cancels queued tasks, emits terminal events | – | `TaskBus.finalize_unfinished`, hooks | `AgentSwarm.finalize_tasks` | Make the persisted graph terminally consistent |
| `TaskBus.create_assignment` | Public | `recipient`, `reply_to`, `objective`, `handoff`, `expected_artifacts` | `TaskAssignment` | Adds assignment to internal state, notifies waiters | – | – | `ExecutionGraph` | Delegate work to an agent |
| `TaskBus.submit_report` | Public | `task_id`, `reporter`, `status`, `summary`, ... | `TaskReport` | Stores report, notifies waiters | – | – | Agent tool (report_task) | Report completion back |
| `TaskBus.finalize_unfinished` | Public | `running_state`, `queued_state` | changed task-state mapping | Closes unfinished tasks without inventing reports | Invalid terminal state | – | `ExecutionGraph.finalize_tasks` | Preserve precise task terminals |
| `TaskBus.wait_for_reports` | Public | `task_ids`, `timeout_seconds` | `dict[task_id, TaskReport]` | Blocks until all reports available | Timeout | – | Coordinator agent | Synchronization |
| `webapp._reconcile_graph_view` | Private | `workspace_id`, `session_id`, `graph` | reconciled graph payload | Reads durable run/events and upgrades legacy graph state in memory | Invalid session state falls back to durable defaults | `get_run_status`, event log reader | graph endpoint | Keep refresh rendering consistent without migrations |
| `webapp._context_path` | Private | `workspace_id`, `session_id`, `agent_name` | `Path` | Returns an Agent-specific context file and creates its parent `contexts/` directory | Invalid IDs | `_session_path`, `Path.mkdir` | `_build_agent`, history compatibility | Ensure conversation history can persist between browser runs |
| `webapp._session_event_page` | Private | `workspace_id`, `session_id`, `before`, `limit` | newest-first event page + cursor | Reads persisted NDJSON; malformed lines are skipped | – | `_read_session_event_log` | `get_session_events` | Page durable trace history safely |
| `webapp._session_usage_summary` | Private | `events` | total and per-Agent token usage | Aggregates completed `round_usage` deltas only | – | – | `get_session_usage` | Avoid cumulative-round double counting across session runs |
| `webapp.start_run` | HTTP POST handler | `RunRequest` | JSON + SSE generation | Creates `BrowserSession`, spawns execution thread, streams events, persists a completed stopped single-Agent turn, and records terminal errors in trace/state | Run errors | `_build_swarm` or `_build_agent`, `ExecutionGraph.run`/`Agent.run`, `_append_conversation_turn`, `_append_session_event` | Web client | Start an agent run |
| `webapp.get_run_status` | HTTP GET handler | `workspace_id`, `session_id` | durable status + error | Returns the live worker status or persisted terminal state; converts orphaned `running`/`force_stopping` records to `interrupted` | Invalid IDs | `_get_session`, `_run_state_path`, `_persist_json` | Refresh recovery | Explain service-restart or worker-loss failures |
| `webapp.get_session_events` | HTTP GET handler | `session_id`, `before`, `limit` | paginated durable events | Reads session event log | – | `_session_event_page` | Right-side Trace inspector | Inspect the entire session trace incrementally |
| `webapp.get_session_usage` | HTTP GET handler | `session_id` | session and per-Agent usage | Reads session event log | – | `_session_usage_summary` | Right-side Usage inspector | Inspect completed token consumption |
| `frontend/static/app.js.appendAgentBehavior` | Private UI helper | lifecycle event | None | Groups an Agent run's lifecycle records into one collapsed, expandable behavior block | – | `resetAgentBehaviorBlocks`, browser DOM | Historical aggregate loader and live SSE handler | Prevent event-card floods while retaining per-event inspection |
| `frontend/static/app.js.loadAllAgentBehavior` | Private UI helper | current session ID | None | Renders canonical session turns in saved order, then grouped lifecycle blocks and non-duplicate tool-free Agent results | Fetch failures surface in console trace | events/agents/messages session APIs, `appendAgentBehavior`, `appendMessage` | `loadHistory` when the all-Agent filter is selected | Preserve prompt/reply ordering while exposing results without tools or reasoning |
| `frontend/static/app.js.loadHistory` | Private UI helper | selected Agent/session ID | None | Loads aggregate behavior plus tool-free results for `all`, otherwise only the selected Agent's persisted transcript | Fetch failures surface in console trace | `loadAllAgentBehavior`, `/api/sessions/{id}/messages`, `appendMessage` | Agent selector and session initialization | Prevent Trace lifecycle cards from appearing inside an Agent conversation |
| `frontend/static/app.js.rehydrateSelectedView` | Private UI helper | `reloadAgents` flag | None | Rebuilds the selected filter from durable state and reconnects an active run | Fetch failures surface in console trace | `loadAgents`, `loadHistory`, `restoreRunState` | Initialization, session switch, and Agent selector | Keep refresh and in-session selection recovery identical |
| `frontend/static/app.js.agentStateView` / `acknowledgeAgent` | Private UI helpers | Agent ID and current selector records | canonical/UI state / None | Reconcile graph and Trace evidence, then persist completion acknowledgement in local storage | Malformed local storage is ignored | `currentGraph`, `traceEvents`, `renderAgentSelector` | Selector, Inspector, graph renderer and dot click handler | Keep every Agent status surface consistent |
| `frontend/static/app.js.loadWorkspaces` | Private UI helper | preferred session ID | None | Loads every session into the selector and bounded scrollable quick list, then reveals the active entry | Session API failures surface in Trace | sessions API, `switchSession`, browser DOM | Initialization, creation, deletion and session switching | Prevent large session registries from displacing sidebar controls |
| `frontend/static/app.js.start` / `handleEvent` | Private UI handlers | submitted message / SSE event | None | Optimistically shows every user turn; reloads aggregate history after a final result | Fetch failures surface in console trace | `appendMessage`, `loadHistory` | Composer and EventSource | Keep live aggregate rendering consistent with persisted refresh rendering |
| `frontend/static/app.js.appendMessage` | Private UI helper | role, content, reasoning, rendered HTML, tools, agentName | None | Appends a role-labelled transcript turn to the chat pane | – | `renderTools`, browser clipboard API | Agent-specific history and live result handler | Separate user input from named Agent replies without changing persisted message data |
| `frontend/static/app.js.appendRunErrorBlock` | Private UI helper | title, message | None | Appends an escaped, durable-looking failure card without clearing chat | – | `escapeHtml` | SSE error handler, start/stop failures, and refresh recovery | Make a failed or interrupted run actionable in the chat pane |
| `webapp.stream_events` | HTTP GET handler | `workspace_id`, `session_id`, `after` | `text/event-stream` | Tails durable `events.ndjson` after the supplied event offset until the run ends | – | `_read_session_event_log` | Web client EventSource reconnect | Prevent refresh/switch loss from the shared in-memory queue |
| `tools.knowledge_tools.create_knowledge_tools` | Public | `knowledge_base` | list of `Tool` | Creates `search_knowledge` and `read_knowledge_full` tools | – | `KnowledgeBase` methods | Agent bootstrap | Expose RAG to agents |
| `tools.shell_tools.create_shell_tools` | Public | `allowed_commands`, `max_timeout`, `sandbox_cwd` | list of `Tool` | Creates `shell` tool with safety filtering | – | `subprocess` | Agent bootstrap | Expose shell access to agents |
| `tools.obscura_tools.create_obscura_tools` | Public | – | list of `Tool` | Creates web search and scraping tools | – | DuckDuckGo, Brave, Bing APIs, `ObscuraCDPClient` | Agent bootstrap | Expose web retrieval |
| `tools.spawn_tools.create_swarm_tools` | Public | `swarm`, `llm_fetcher`, etc. | list of `Tool` | Creates dynamic swarm management tools (add agent, dispatch, report, etc.) | – | `ExecutionGraph` methods | Coordinator agent | Enable dynamic multi‑agent collaboration |
| `rag_module/knowledge/facade.KnowledgeBase.search` | Public | `query`, `limit` | list of `KnowledgeHit` | Uses hybrid retriever, may trigger index build | – | `HybridRetriever` | Knowledge tools | Full‑text + semantic search |
| `rag_module/knowledge/facade.KnowledgeBase.ensure_vector_index` | Public | `force=False` | None | Builds or updates ChromaDB index from markdown documents | Model load errors | `VectorIndexManager`, `EmbeddingModelProvider` | CLI, API | Keep vector index fresh |

**(Additional functions like event hooks, serializer/deserializer, graph persistence follow analogous patterns.)**

---

## Execution Flows

### Startup Flow
1. **CLI entry:** `main()` parses arguments, calls `_bootstrap_agent` which:
   - Resolves backend config from CLI args or environment.
   - Creates `LLMFetcher` with registered backends.
   - Loads tools via `_load_tools` (dynamic import of tool factories).
   - Instantiates `Agent` with fetcher, tools, context handler.
2. **Web server entry:** `webapp.main()` starts Flask app on configured host/port. On first request:
   - Workspaces and connectors loaded from JSON files.
   - Each session initialises a `BrowserSession` with lock and `ActiveRun` slot.

### Agent Execution Flow (`Agent.run`)
1. Add user message to context.
2. Loop for up to `max_rounds`:
   - Build messages from context.
   - Call `LLMFetcher.fetch` (or `fetch_stream` if streaming) with tools.
   - If tool calls present:
     - Resolve handlers via `ToolHandler`.
     - Execute in parallel via `ToolExecutor.execute_batch` (respecting `max_concurrency`).
     - Collect results, wrap in `ToolInfo`, call context handler.
   - Emit events (round‑started, tool‑started, tool‑completed, completion).
   - If stop requested (`AgentRunControl.should_stop()`), save the completed context boundary and raise `AgentRunStopped` with its final output.
3. Return final `LLMOutput`.

### Compaction Flow
- When `ContextHandlerLinear.add_assistant_message` estimates context size exceeds threshold:
  - `compact()` builds a serialised transcript of all previous turns (omitting tool results beyond character limit).
  - Sends a stateless request to a compaction LLM with a system prompt.
  - Parses the compacted abstract and replaces `messages` list with the abstract + current request.
  - Old messages stored only for later reference but excluded from future builds.

### Swarm / Multi‑Agent Flow
1. Coordinator creates an `ExecutionGraph` with agents and routing nodes (can be dynamic).
2. Coordinator uses `dispatch_task` or dynamic tools to assign objectives.
3. Agents run concurrently (up to `max_concurrency_agents`), can spawn sub‑tasks via `dispatch_subagents`.
4. Agents report results via `report_task` tool.
5. Coordinator can wait for reports, aggregate, and decide next steps.
6. Graph topology can be mutated at runtime via swarm tools (`dynamic_add_agent`, `dynamic_add_connection`, etc.).

### Web Run Flow
1. POST `/run` → `start_run`:
   - Creates `BrowserRunControl` and `ActiveRun`.
   - If swarm config enabled, creates `AgentSwarm`; else single `Agent`.
   - Starts background thread to execute `ExecutionGraph.run` or `Agent.run`.
   - Background thread emits events into `ActiveRun.events`.
2. GET `/events` → `stream_events`:
   - Polls `ActiveRun.events` and yields SSE messages.
3. User can POST `/stop` or `/steer` to interact with the run.
4. After creating a browser session, `frontend/static/app.js.switchSession()`
   closes a prior event stream, selects the returned ID, and reloads the
   history, task plan, and graph in parallel so the chat pane immediately
   shows the new session's state and accepts input.

### Error Flow
- LLM calls: `LLMFetcher.fetch` retries across backends (configurable max attempts). Exceptions wrapped in `LLMError` subtypes and logged.
- Tool execution: `ToolExecutor.execute_batch` returns per‑call results with exceptions; agent can decide to continue or abort.
- Context compaction: if compaction LLM fails, context may remain large; no crash.
- Swarm tasks: unreported tasks can be failed via `fail_unreported_task`.

### Rollback Flow
- Not applicable; state is persisted in workspaces/sessions, but no formal rollback. Web app can delete workspaces.

---

## Data Flow

### Data Sources
- **LLM API keys / config:** Environment variables, ~/.codetalker/config.json (for web), CLI args.
- **Knowledge base:** Markdown files under `KnowledgeConfig.root`.
- **Web search:** DuckDuckGo HTML, Brave/Bing APIs.
- **Shell commands:** OS subprocess stdout/stderr.
- **User input:** CLI prompts, web chat messages.

### Data Transformations
- **User message → LLM input:** Context handler adds turn, builds message list with system prompt, history, tools.
- **LLM output → agent actions:** `LLMOutput` parsed for tool calls → `ToolHandler` resolves handlers → arguments mapped → `ToolExecutor` calls functions → results turned into `ToolInfo` and appended to context.
- **Tool results truncation:** Before storing in linear context, large results are trimmed to `_TOOL_RESULT_MAX_CHARS` (configurable).
- **Historical compaction:** Older conversation turns summarised into a single `LLMContextCompacted` message.
- **RAG pipeline:** Markdown → `MarkdownKnowledgeLoader` → chunked by `TextTools` → embedded via `EmbeddingModelProvider` → stored in `ChromaVectorStore`. Queries → keyword + vector retrieval → hybrid ranking → `KnowledgeHit` with excerpts.

### Data Sinks
- **Session history:** JSON files per session (`_session_path`).
- **Task plans:** JSON file per session (`TaskPlanStore`).
- **Workspace registry:** JSON file listing workspaces.
- **Connector registry:** JSON file listing saved backend configs.
- **Caching:**
  - Embedding model is cached in memory (`EmbeddingModelProvider._embedding_model`).
  - ChromaDB client and collection are cached in `ChromaVectorStore`.
  - `KnowledgeManifestStore` fingerprints documents to avoid re‑indexing unchanged files.
- **Output:** CLI prints final response to stdout; web streams events to browser.

---

## Side Effects

- **Files written:**
  - `_persist_json` writes session events, task plans, workspace/connector registries.
  - `ContextHandlerLinear.save` and `RetrievedContextHandler.save` write conversation history to disk.
  - `ExecutionGraph.save` writes graph snapshots.
  - `TaskPlanStore._write` replaces plan files.
  - RAG manifest store saves manifest JSON.
- **Network calls:**
  - `LLMFetcher.fetch` makes API calls to LLM providers.
  - Web search tools make HTTP requests to search engines.
  - `ObscuraCDPClient` connects via WebSocket to headless browser.
- **State changes:**
  - Agent usage counters, hooks, event logs.
  - `TaskBus` internal state (assignments, reports).
  - `ExecutionGraph` topology and agent states.
  - Workspace/session creation.
- **Caches / temporary artifacts:**
  - `LLMFetcher` holds handler instances.
  - `EmbeddingModelProvider` holds loaded model.
  - `ChromaVectorStore` holds client and collection.

---

## Agent Change Protocol

- **Before editing:** Read this semantic map and the source files relevant to the requested change.
- **During editing:** Treat this map as the current behavioral contract unless source inspection proves it stale.
- **After editing:** Update changed module, function, runtime‑flow, and side‑effect sections in the same change.
- **If code and map disagree:** Trust observed code, then repair the map before relying on it for further edits.

---

*This map was generated from a static symbol index and may contain inferences marked as such. Precise behavioral guarantees require code inspection.*
