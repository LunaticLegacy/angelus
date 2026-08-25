# angelus/api/ — Browser API INDEX

FastAPI 路由层。路由只负责 HTTP/SSE 边界、请求验证与响应编排；持久化、运行构建和历史重建分别位于上一级包的 `storage.py`、`runtime.py` 和 `history/`。

## Route Map — Leaf Files

| File | Responsibility |
|---|---|
| `__init__.py` | `include_api_routes(app)`：注册所有路由并提供 SPA 根页面。 |
| `connectors.py` | 供应商列表与连接器 CRUD；桥接已启用插件的连接器类型。 |
| `runs.py` | 运行启动、状态、SSE、协作式停止、强制停止和运行中 steer 指令；启动前验证会话绑定的项目目录仍然可用。 |
| `sessions.py` | 工作区、会话历史、按 Agent 查询的计划、归档、图、用量、产物与跨会话记忆授权 API；创建会话时绑定既有项目目录，允许停止状态下重新绑定，并为本机回环客户端提供原生目录选择器；同时提供停止运行后的上下文检查、版本化编辑和恢复。 |
| `compact.py` | 手动上下文压缩，以及面向浏览器的阶段性进度流。 |
| `mcp.py` | 全局 MCP server CRUD/探测/OAuth，以及会话角色与工具白名单授权。 |
| `external_agents.py` | External Agent Hub：Provider 能力与安全本机自动检测、session archive 导入导出、handoff preview、link 与独占控制租约。 |

Kimi Code is exposed as a first-party provider preset and resolved to the existing OpenAI-compatible backend before a model request is made.

## Intent Routing

- **连接器 / Provider** → `connectors.py`
- **运行、停止、SSE 或 steering** → `runs.py`
- **会话、项目目录选择/绑定、计划、图、归档、用量或记忆授权** → `sessions.py`
- **手动压缩** → `compact.py`
- **MCP server、OAuth 或会话授权** → `mcp.py`
- **外部 Agent、archive、handoff 或控制租约** → `external_agents.py`
- **挂载路由或 SPA 根路径** → `__init__.py`

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [__init__.py](__init__.py#L19) | `include_api_routes` | `app: FastAPI` | `None` | Attach every browser API router plus the static console index. |
| [compact.py](compact.py#L29) | `_stage` | `stage: str, detail: str, kind: str, error: str \| None, raw_content: str \| None` | `str` | Serialize one compaction progress record as an NDJSON line. |
| [compact.py](compact.py#L63) | `_build_compactor_fetcher` | `config: Any` | `LLMFetcher` | Create a throwaway LLM fetcher for the manual compaction call. |
| [compact.py](compact.py#L84) | `compact_session` | `session_id: str, request: CompactRequest` | `StreamingResponse` | Compress one Agent's linear context into a single summary abstract. |
| [connectors.py](connectors.py#L22) | `providers` | `request: Request` | `dict[str, list[str]]` | Expose built-in providers plus plugin-registered connector kinds. |
| [connectors.py](connectors.py#L37) | `list_connectors` | `None` | `dict[str, list[dict[str, Any]]]` | List connector metadata without returning any saved API key. |
| [connectors.py](connectors.py#L42) | `create_connector` | `request: ConnectorRequest` | `dict[str, Any]` | Persist a named connection and return its complete local record. |
| [connectors.py](connectors.py#L59) | `update_connector` | `connector_id: str, request: ConnectorRequest` | `dict[str, Any]` | Replace one connector's persisted settings while retaining its ID. |
| [connectors.py](connectors.py#L88) | `delete_connector` | `connector_id: str` | `None` | Delete one persisted connector and its locally stored credential. |
| [external_agents.py](external_agents.py#L21) | `_require_mapping` | `payload: Any` | `dict[str, Any]` | Validate an untyped JSON body before passing it to the hub service. |
| [external_agents.py](external_agents.py#L29) | `external_agent_hub_page` | `None` | `FileResponse` | Serve the standalone External Agent Hub without altering the main shell. |
| [external_agents.py](external_agents.py#L40) | `list_external_providers` | `None` | `dict[str, Any]` | List built-in provider capabilities and connection status. |
| [external_agents.py](external_agents.py#L46) | `configure_external_provider` | `provider_id: str, payload: dict[str, Any]` | `dict[str, Any]` | Save public provider endpoint metadata without accepting credentials. |
| [external_agents.py](external_agents.py#L52) | `probe_external_provider` | `provider_id: str` | `dict[str, Any]` | Probe a Provider without creating a vendor session or turn. |
| [external_agents.py](external_agents.py#L78) | `auto_detect_external_providers` | `None` | `dict[str, Any]` | Probe all implemented local providers without persisting configuration. |
| [external_agents.py](external_agents.py#L99) | `discover_external_sessions` | `provider_id: str, project_path: str \| None` | `dict[str, Any]` | Discover readable vendor sessions through a registered fixed adapter. |
| [external_agents.py](external_agents.py#L119) | `get_external_session_meta` | `session_id: str` | `dict[str, Any]` | Return additive source metadata for an Angelus session. |
| [external_agents.py](external_agents.py#L126) | `export_session_archive` | `session_id: str` | `Response` | Download a credential-free Angelus Session Archive v1 ZIP. |
| [external_agents.py](external_agents.py#L136) | `import_preview` | `payload: dict[str, Any]` | `dict[str, Any]` | Validate an archive or transcript and report projected import fidelity. |
| [external_agents.py](external_agents.py#L156) | `commit_import` | `payload: dict[str, Any]` | `dict[str, Any]` | Create a new session from a validated archive or transcript source. |
| [external_agents.py](external_agents.py#L175) | `transfer_preview` | `session_id: str, payload: dict[str, Any]` | `dict[str, Any]` | Preview a native-history or handoff transfer without provider side effects. |
| [external_agents.py](external_agents.py#L197) | `create_external_link` | `payload: dict[str, Any]` | `dict[str, Any]` | Create a safe Angelus UUID link to an external provider session. |
| [external_agents.py](external_agents.py#L216) | `list_external_links` | `None` | `dict[str, Any]` | List external links excluding ephemeral control lease tokens. |
| [external_agents.py](external_agents.py#L222) | `heartbeat_external_lease` | `link_id: str, payload: dict[str, Any]` | `dict[str, Any]` | Acquire or renew a tab-scoped exclusive external control lease. |
| [external_agents.py](external_agents.py#L232) | `external_link_action` | `link_id: str, payload: dict[str, Any]` | `dict[str, Any]` | Validate a capability-gated action and require the controller lease. |
| [mcp.py](mcp.py#L24) | `_oauth_pending` | `None` | `dict[str, Any]` | Read short-lived OAuth state/PKCE transactions from private app state. |
| [mcp.py](mcp.py#L33) | `_write_oauth_pending` | `payload: dict[str, Any]` | `None` | Atomically persist private OAuth state and verifier values. |
| [mcp.py](mcp.py#L45) | `_record` | `server_id: str` | `tuple[list[dict[str, Any]], int, dict[str, Any]]` | Locate one MCP registry record under its stable identifier. |
| [mcp.py](mcp.py#L63) | `list_mcp_servers` | `None` | `dict[str, Any]` | List global MCP servers without returning credential values. |
| [mcp.py](mcp.py#L69) | `create_mcp_server` | `payload: dict[str, Any]` | `dict[str, Any]` | Validate, encrypt, and create one global MCP server. |
| [mcp.py](mcp.py#L89) | `update_mcp_server` | `server_id: str, payload: dict[str, Any]` | `dict[str, Any]` | Replace one global MCP server while preserving blank credentials. |
| [mcp.py](mcp.py#L121) | `delete_mcp_server` | `server_id: str` | `None` | Delete one global MCP server record. |
| [mcp.py](mcp.py#L145) | `probe_mcp_server` | `server_id: str` | `dict[str, Any]` | Temporarily connect and cache one server's discovered tools. |
| [mcp.py](mcp.py#L177) | `get_mcp_capabilities` | `server_id: str` | `dict[str, Any]` | Return the most recently probed capability cache. |
| [mcp.py](mcp.py#L184) | `connect_mcp_oauth` | `server_id: str, payload: dict[str, Any]` | `dict[str, str]` | Start standard OAuth authorization with state and PKCE protection. |
| [mcp.py](mcp.py#L218) | `callback_mcp_oauth` | `state: str, code: str` | `dict[str, Any]` | Validate OAuth state/PKCE and exchange the one-time code for tokens. |
| [mcp.py](mcp.py#L255) | `disconnect_mcp_oauth` | `server_id: str` | `dict[str, Any]` | Delete stored OAuth access and refresh tokens for one server. |
| [mcp.py](mcp.py#L268) | `refresh_mcp_oauth` | `server_id: str` | `dict[str, Any]` | Refresh one server's OAuth access token without exposing it. |
| [mcp.py](mcp.py#L298) | `get_mcp_bindings` | `session_id: str` | `dict[str, Any]` | Return server/role/tool grants for one browser session. |
| [mcp.py](mcp.py#L305) | `put_mcp_bindings` | `session_id: str, payload: dict[str, Any]` | `dict[str, Any]` | Replace MCP grants for one browser session. |
| [runs.py](runs.py#L47) | `_event_resume_offset` | `request: Request, workspace_id: str, session_id: str, after: int, cursor: int \| None` | `int` | Resolve an SSE durable cursor with compatibility precedence. |
| [runs.py](runs.py#L84) | `start_run` | `request: RunRequest` | `dict[str, str]` | Start one Agent or Swarm in a session-owned worker thread. |
| [runs.py](runs.py#L337) | `get_run_status` | `workspace_id: str, session_id: str` | `dict[str, Any]` | Return durable run state and diagnose a worker lost after a restart. |
| [runs.py](runs.py#L386) | `stream_events` | `workspace_id: str, session_id: str, request: Request, after: int, cursor: int \| None` | `StreamingResponse` | Stream durable session events after a chronological log offset. |
| [runs.py](runs.py#L441) | `_control_target` | `active: ActiveRun, requested: Any` | `tuple[str, dict[str, str]]` | Validate one control target and snapshot current Agent states. |
| [runs.py](runs.py#L473) | `stop_run` | `workspace_id: str, session_id: str, payload: dict[str, Any]` | `dict[str, Any]` | Request a cooperative stop for all work or one selected Agent. |
| [runs.py](runs.py#L495) | `force_stop_run` | `workspace_id: str, session_id: str, payload: dict[str, Any]` | `dict[str, Any]` | Force-stop model and tool I/O for all work or one Agent. |
| [runs.py](runs.py#L522) | `steer_run` | `workspace_id: str, session_id: str, request: SteerRequest` | `dict[str, bool]` | Queue a steering message that Agent.run applies at a safe boundary. |
| [runs.py](runs.py#L532) | `resolve_mcp_approval` | `workspace_id: str, session_id: str, approval_id: str, payload: dict[str, Any]` | `dict[str, Any]` | Resolve sampling or elicitation without logging submitted values. |
| [sessions.py](sessions.py#L67) | `list_workspaces` | `None` | `dict[str, list[dict[str, str]]]` | List local workspaces available to the browser console. |
| [sessions.py](sessions.py#L72) | `list_sessions` | `None` | `dict[str, list[dict[str, Any]]]` | List browser sessions with a compact durable run-status indicator. |
| [sessions.py](sessions.py#L97) | `workspace_root` | `None` | `dict[str, str]` | Return the on-disk state root that owns every browser session. |
| [sessions.py](sessions.py#L108) | `delete_workspace` | `workspace_id: str, request: WorkspaceDeleteRequest` | `dict[str, Any]` | Delete a workspace only after explicit confirmation and safe stopping. |
| [sessions.py](sessions.py#L155) | `get_task_plan` | `workspace_id: str, session_id: str, agent: str` | `dict[str, Any]` | Return one selected Agent's persisted task plan for a browser session. |
| [sessions.py](sessions.py#L162) | `get_session_plan` | `session_id: str, agent: str` | `dict[str, Any]` | Return one selected Agent's task plan for an independent session. |
| [sessions.py](sessions.py#L167) | `get_session_history` | `workspace_id: str, session_id: str, agent: str, cursor: str \| None, before: int \| None, limit: int` | `dict[str, Any]` | Return a bounded page of persisted display turns for a browser refresh. |
| [sessions.py](sessions.py#L197) | `get_session_archive` | `workspace_id: str, session_id: str, agent: str, before: int \| None, limit: int` | `dict[str, Any]` | Expose archived raw context evidence without changing model context. |
| [sessions.py](sessions.py#L210) | `get_session_archive_by_id` | `session_id: str, agent: str, before: int \| None, limit: int` | `dict[str, Any]` | Expose archived coordinator evidence for standalone browser sessions. |
| [sessions.py](sessions.py#L222) | `get_session_messages` | `session_id: str, agent: str, cursor: str \| None, before: int \| None, limit: int` | `dict[str, Any]` | Return a bounded page of the aggregate or selected Agent transcript. |
| [sessions.py](sessions.py#L250) | `get_session_agents` | `session_id: str` | `dict[str, list[dict[str, Any]]]` | Return selectable Agent identities from the persisted graph snapshot. |
| [sessions.py](sessions.py#L282) | `get_agent_context_graph` | `session_id: str, agent_name: str` | `dict[str, Any]` | Expose one Agent's persisted long-term memory graph for inspection. |
| [sessions.py](sessions.py#L312) | `get_agent_context_preview` | `session_id: str, agent_name: str` | `dict[str, Any]` | Expose the full model-ready preview of an Agent's active context. |
| [sessions.py](sessions.py#L335) | `get_agent_compaction_input_preview` | `session_id: str, agent_name: str` | `dict[str, Any]` | Expose the exact text the context compactor would send for one Agent. |
| [sessions.py](sessions.py#L358) | `_editable_context_store` | `session_id: str, agent_name: str` | `ContextEditStore` | Bind browser context-edit requests to one inactive Agent checkpoint. |
| [sessions.py](sessions.py#L388) | `inspect_editable_agent_context` | `session_id: str, agent_name: str` | `dict[str, Any]` | Return stable active-context records plus every recovery revision. |
| [sessions.py](sessions.py#L402) | `_parse_context_edit_operations` | `value: Any` | `list[ContextEditOperation]` | Convert one browser JSON operation array into the typed edit schema. |
| [sessions.py](sessions.py#L430) | `edit_agent_context` | `session_id: str, agent_name: str, payload: dict[str, Any]` | `dict[str, Any]` | Apply a version-checked browser edit to an inactive Agent context. |
| [sessions.py](sessions.py#L463) | `restore_agent_context` | `session_id: str, agent_name: str, payload: dict[str, Any]` | `dict[str, Any]` | Restore one saved revision as a new audit-preserving active revision. |
| [sessions.py](sessions.py#L492) | `get_session_graph` | `workspace_id: str, session_id: str` | `dict[str, Any]` | Return the reconciled execution-graph view for a browser session. |
| [sessions.py](sessions.py#L512) | `_reconcile_graph_view` | `workspace_id: str, session_id: str, graph: dict[str, Any]` | `dict[str, Any]` | Merge a persisted graph snapshot with durable run and event terminals. |
| [sessions.py](sessions.py#L701) | `get_session_graph_by_id` | `session_id: str` | `dict[str, Any]` | Return a session's safe persisted execution-graph view. |
| [sessions.py](sessions.py#L734) | `_require_live_swarm` | `session_id: str` | `tuple[Any, Any]` | Return ``(session, swarm)`` or reject edits against a live graph. |
| [sessions.py](sessions.py#L762) | `_persist_live_graph_view` | `session_id: str, swarm: Any` | `None` | Atomically persist the live topology for the browser graph inspector. |
| [sessions.py](sessions.py#L772) | `_publish_graph_mutation` | `session: Any, session_id: str, action: str, detail: str` | `None` | Append one durable graph-edit event and relay it to live SSE clients. |
| [sessions.py](sessions.py#L795) | `add_graph_agent` | `session_id: str, request: GraphAgentRequest` | `dict[str, Any]` | Create and register a new live Swarm worker from browser settings. |
| [sessions.py](sessions.py#L831) | `remove_graph_agent` | `session_id: str, name: str` | `dict[str, Any]` | Remove a single live Swarm node and every edge touching it. |
| [sessions.py](sessions.py#L860) | `add_graph_connection` | `session_id: str, request: GraphConnectionRequest` | `dict[str, Any]` | Add one dependency edge between two existing live graph nodes. |
| [sessions.py](sessions.py#L883) | `remove_graph_connection` | `session_id: str, source: str, target: str` | `dict[str, Any]` | Remove one dependency edge between two live graph nodes. |
| [sessions.py](sessions.py#L907) | `set_graph_mapper` | `session_id: str, request: GraphMapperRequest` | `dict[str, Any]` | Set a safe declarative input mapper on one live agent node. |
| [sessions.py](sessions.py#L929) | `set_graph_router` | `session_id: str, request: GraphRouterRequest` | `dict[str, Any]` | Set a declarative successor router on one live agent node. |
| [sessions.py](sessions.py#L952) | `get_graph_edit_info` | `session_id: str` | `dict[str, Any]` | Return a compact live topology view for the graph editing toolbar. |
| [sessions.py](sessions.py#L992) | `get_session_events` | `session_id: str, cursor: str \| None, before: int \| None, limit: int` | `dict[str, Any]` | Return a paginated, newest-first durable trace for one session. |
| [sessions.py](sessions.py#L1022) | `get_session_steers` | `session_id: str` | `dict[str, Any]` | Return every durable steering instruction applied to this session. |
| [sessions.py](sessions.py#L1051) | `get_session_usage` | `session_id: str` | `dict[str, Any]` | Return completed token usage for all Agents in one browser session. |
| [sessions.py](sessions.py#L1066) | `replace_task_plan` | `workspace_id: str, session_id: str, request: TaskPlanRequest, agent: str` | `dict[str, Any]` | Allow a user to replace one selected Agent's supervised task plan. |
| [sessions.py](sessions.py#L1077) | `update_task_plan_status` | `workspace_id: str, session_id: str, task_id: str, request: TaskStatusRequest, agent: str` | `dict[str, Any]` | Persist a status change in one selected Agent's task plan. |
| [sessions.py](sessions.py#L1088) | `update_session_plan_status` | `session_id: str, task_id: str, request: TaskStatusRequest, agent: str` | `dict[str, Any]` | Persist one task-status transition within one selected Agent plan. |
| [sessions.py](sessions.py#L1099) | `create_workspace` | `request: WorkspaceRequest` | `dict[str, str]` | Create a local session bound to an existing user project directory. |
| [sessions.py](sessions.py#L1130) | `create_session` | `request: WorkspaceRequest` | `dict[str, str]` | Create one browser-visible session and its private workspace path. |
| [sessions.py](sessions.py#L1136) | `update_session_project_path` | `session_id: str, request: ProjectPathRequest` | `dict[str, str]` | Rebind an inactive session to another existing project directory. |
| [sessions.py](sessions.py#L1170) | `_directory_picker_command` | `None` | `list[str] \| None` | Return the host-native folder picker command for the current platform. |
| [sessions.py](sessions.py#L1194) | `_request_is_loopback` | `request: Request` | `bool` | Return whether an HTTP request originated from this host. |
| [sessions.py](sessions.py#L1211) | `pick_workspace_directory` | `request: Request` | `dict[str, Any]` | Open the host folder picker for a loopback Workbench client. |
| [sessions.py](sessions.py#L1247) | `open_session_folder` | `session_id: str` | `dict[str, str]` | Open one session's bound user project in the host file manager. |
| [sessions.py](sessions.py#L1265) | `get_session_memory_capabilities` | `session_id: str` | `dict[str, Any]` | Describe the explicit run-scoped grants accepted by the browser API. |
| [sessions.py](sessions.py#L1272) | `register_session_artifact` | `session_id: str, payload: dict[str, Any]` | `dict[str, Any]` | Register browser-uploaded base64 attachment bytes without a source path. |
| [sessions.py](sessions.py#L1287) | `list_session_artifacts` | `session_id: str` | `dict[str, Any]` | Implement `list_session_artifacts`. |
| [sessions.py](sessions.py#L1293) | `list_session_handoffs` | `session_id: str` | `dict[str, Any]` | Implement `list_session_handoffs`. |
| [sessions.py](sessions.py#L1303) | `get_session_handoff` | `session_id: str, handoff_id: str` | `dict[str, Any]` | Implement `get_session_handoff`. |
| [sessions.py](sessions.py#L1310) | `create_browser_session_handoff` | `session_id: str, handoff: dict[str, Any]` | `dict[str, Any]` | Implement `create_browser_session_handoff`. |
| [sessions.py](sessions.py#L1317) | `delete_session` | `session_id: str, request: WorkspaceDeleteRequest` | `dict[str, Any]` | Delete one session after confirmation and cooperative run shutdown. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [sessions.py](sessions.py#L706) | `GraphAgentRequest` | `name: str, system_prompt: str` | `BaseModel` | Create one browser-added Swarm worker node. |
| [sessions.py](sessions.py#L713) | `GraphConnectionRequest` | `source: str, target: str` | `BaseModel` | Add one dependency edge between two existing graph nodes. |
| [sessions.py](sessions.py#L720) | `GraphMapperRequest` | `agent: str, mode: str` | `BaseModel` | Set a safe declarative input aggregator on one agent node. |
| [sessions.py](sessions.py#L727) | `GraphRouterRequest` | `agent: str, targets: list[str]` | `BaseModel` | Set a declarative router on one agent after its completion. |

<!-- END GENERATED SYMBOL MAP -->
