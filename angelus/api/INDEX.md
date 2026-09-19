# angelus/api/ — Phase 1 HTTP INDEX

Routes are transport adapters only. They resolve `AngelusCore` from app state,
validate HTTP input, call one service, and map known domain errors to HTTP.
They do not own Session, Agent, execution, persistence or credentials.

| File | Mounted routes | Responsibility |
|---|---|---|
| `__init__.py` | `/`, `/favicon.ico`, `/static/*` | Install mounted routers and SPA shell; call core shutdown hook. |
| `sessions.py` | `/api/sessions` | Create/list/delete Session identities and page legacy transcript projection. |
| `runs.py` | `/api/runs`, `/api/runs/{id}/…` | Start (including optional targeted Agent), inspect, stop/force-stop and event-index cursor-resumable replay/follow of one Session attempt. |
| `attachments.py` | `/api/sessions/{id}/attachments/images` | Session-scoped image upload (bounded raw bytes plus `filename` query) and validated download. Owns no storage; the Session aggregate owns the bytes. |
| `settings.py` | `/api/connectors`, `/api/settings/run-profile`, `/api/sessions/{id}/run-profile` | Connector CRUD and global/Session future-run settings. |
| `providers.py` | `/api/providers` | Read installed LLMFetcher provider capabilities. |
| `workspace_directory.py` | `/api/workspace-directory/pick` | HTTP mapping over the backend system resource-manager adapter. |
| `session_console.py` | `/api/sessions/{id}/agents`, graph, workflow, plan, events, lifecycle SSE, usage and context routes | Session console with graph projection, durable lifecycle follow, editable workflow, and bounded context exchange. |
| `external_agent_hub.py` | `/api/external-agents` | External Agent definition CRUD, explicit local-process discovery, inspection, and capability-gated portable-context reads/writes. |
| `mcp.py` | `/api/mcp/servers`, `/api/sessions/{id}/mcp-bindings` | Managed server CRUD/probe/OAuth and Session role/tool grants through the core MCP service. |
| `plugins.py` | `/api/plugins` | Controlled plugin discovery/lifecycle, persisted settings, static assets, and active declarative panel actions. |

## Not Mounted in Phase 1

`compact.py` and `external_agents.py` are retained historic source
files but are not registered by `include_api_routes`. They must not be used as
backend capabilities or revived route-by-route; their replacement belongs to
the next Session-projection phase. Removed `connectors.py`/`profiles.py` are
replaced solely by `settings.py`.

## Function Map

| Source | Function / method | Semantics |
|---|---|---|
| `__init__.py` | `include_api_routes` | Register Phase-1 routers, static assets and host shutdown callback. |
| `sessions.py` | `list_sessions`, `create_session`, `delete_session` | Session identity lifecycle over `SessionService`. |
| `sessions.py` | `get_session_messages` | Bounded legacy conversation projection for selected Session. |
| `runs.py` | `start_run`, `run_status`, stop endpoints | Execution lifecycle over `ExecutionService`; validates image references and optional targeted Agent before dispatch. |
| `attachments.py` | `upload_image`, `download_image` | Session-scoped image transport over the Session-owned attachment store. |
| `session_console.py` | graph/workflow/plan/events/context endpoints | Console projection over Session execution evidence, the editable workflow and persisted contexts; context export pages durable history and import appends only to idle Agents. |
| `settings.py` | connector/profile endpoints | Settings use cases over `SettingsService`. |
| `providers.py` | `list_providers` | Runtime capability read. |
| `workspace_directory.py` | directory picker endpoint | Delegate desktop-only selection to `platform_module`; never invoke browser/Tauri pickers. |
| `external_agent_hub.py` | External Agent CRUD/discovery/health/capabilities/sessions/contexts | Hub API; discovery is an explicit read-only scan and context exchange is capability-gated with no connector-secret serialization. |
| `plugins.py` | plugin lifecycle/settings/panel action endpoints | Register/load controlled packages; validate persistent settings and transient host-rendered panel input. |

## Class Map

| Source | Class | Semantics |
|---|---|---|
| `runs.py` | `RunImageReference`, `RunRequest`, `StopRequest` | Typed input for starting/cancelling a Session attempt; image refs are validated Session attachment IDs only, never paths or remote URLs. |
| `sessions.py` | `CreateSessionRequest`, `DeleteSessionRequest` | Typed Session registration/deletion input. |
| `settings.py` | `ConnectorPayload`, `ProfilePayload` | Typed connector and future-run profile input. |
| `external_agent_hub.py` | `ExternalAgentInput` | Typed non-secret HTTP definition body for one external Agent runtime. |

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [__init__.py](__init__.py#L23) | `include_api_routes` | `app: FastAPI, core: AngelusCore` | `None` | Install API routes and the local workbench assets on one host. |
| [attachments.py](attachments.py#L13) | `_store` | `request: Request, session_id: str` | `Any` | Implement `_store`. |
| [attachments.py](attachments.py#L21) | `upload_image` | `session_id: str, request: Request, filename: str` | `dict` | Accept bounded raw image bytes without requiring a multipart parser. |
| [attachments.py](attachments.py#L37) | `download_image` | `session_id: str, attachment_id: str, request: Request` | `FileResponse` | Serve an existing validated image only within its owning Session. |
| [compact.py](compact.py#L29) | `_stage` | `stage: str, detail: str, kind: str, error: str \| None, raw_content: str \| None` | `str` | Serialize one compaction progress record as an NDJSON line. |
| [compact.py](compact.py#L63) | `_build_compactor_fetcher` | `config: Any` | `LLMFetcher` | Create a throwaway LLM fetcher for the manual compaction call. |
| [compact.py](compact.py#L84) | `compact_session` | `session_id: str, request: CompactRequest` | `StreamingResponse` | Compress one Agent's linear context into a single summary abstract. |
| [external_agent_hub.py](external_agent_hub.py#L41) | `_core` | `request: Request` | `AngelusCore` | Resolve the application composition root from FastAPI state. |
| [external_agent_hub.py](external_agent_hub.py#L60) | `list_external_agents` | `request: Request` | `dict[str, object]` | List all durable external Agent definitions. |
| [external_agent_hub.py](external_agent_hub.py#L73) | `discover_external_agent_processes` | `request: Request` | `dict[str, object]` | Read local known Agent processes without attaching or persisting one. |
| [external_agent_hub.py](external_agent_hub.py#L88) | `external_agent_contexts` | `agent_id: str, request: Request, cursor: str \| None, limit: int` | `dict[str, object]` | List one bounded page of readable external context descriptors. |
| [external_agent_hub.py](external_agent_hub.py#L121) | `read_external_agent_context` | `agent_id: str, context_id: str, request: Request` | `dict[str, object]` | Read one external context as a credential-redacted portable package. |
| [external_agent_hub.py](external_agent_hub.py#L147) | `write_external_agent_context` | `agent_id: str, request: Request, payload: object` | `dict[str, object]` | Write a user-selected portable package through an audited adapter. |
| [external_agent_hub.py](external_agent_hub.py#L175) | `get_external_agent` | `agent_id: str, request: Request` | `dict[str, object]` | Read one durable external Agent definition. |
| [external_agent_hub.py](external_agent_hub.py#L197) | `create_external_agent` | `request: Request, payload: object` | `dict[str, object]` | Create one external Agent definition without contacting it. |
| [external_agent_hub.py](external_agent_hub.py#L218) | `replace_external_agent` | `agent_id: str, request: Request, payload: object` | `dict[str, object]` | Replace one external Agent definition without contacting it. |
| [external_agent_hub.py](external_agent_hub.py#L242) | `delete_external_agent` | `agent_id: str, request: Request` | `None` | Remove one configuration definition without deleting its connector. |
| [external_agent_hub.py](external_agent_hub.py#L262) | `external_agent_health` | `agent_id: str, request: Request` | `dict[str, object]` | Perform a non-executing adapter health check. |
| [external_agent_hub.py](external_agent_hub.py#L282) | `external_agent_capabilities` | `agent_id: str, request: Request` | `dict[str, object]` | Read capabilities advertised by an installed adapter without running it. |
| [external_agent_hub.py](external_agent_hub.py#L305) | `external_agent_sessions` | `agent_id: str, request: Request, limit: int` | `dict[str, object]` | List bounded remote session summaries without importing or running them. |
| [external_agent_hub.py](external_agent_hub.py#L330) | `_parse_input` | `payload: object` | `ExternalAgentDefinition` | Decode a strict JSON request object into a typed definition. |
| [external_agent_hub.py](external_agent_hub.py#L377) | `_definition` | `value: ExternalAgentDefinition` | `dict[str, object]` | Serialize a definition without resolving connector credentials. |
| [external_agent_hub.py](external_agent_hub.py#L397) | `_candidate` | `value: ExternalAgentCandidate` | `dict[str, object]` | Serialize one ephemeral process observation without secrets. |
| [external_agent_hub.py](external_agent_hub.py#L419) | `_health` | `value: ExternalAgentHealth` | `dict[str, object]` | Serialize a typed health observation for the HTTP response. |
| [external_agent_hub.py](external_agent_hub.py#L436) | `_capability` | `value: ExternalAgentCapability` | `dict[str, object]` | Serialize one typed capability declaration for the HTTP response. |
| [external_agent_hub.py](external_agent_hub.py#L453) | `_session` | `value: ExternalAgentSession` | `dict[str, object]` | Serialize one remote session without treating references as local paths. |
| [external_agent_hub.py](external_agent_hub.py#L472) | `_context` | `value: ExternalAgentContext` | `dict[str, object]` | Serialize one external context descriptor for an HTTP response. |
| [external_agent_hub.py](external_agent_hub.py#L484) | `_package` | `value: ContextPackage` | `dict[str, object]` | Serialize a credential-redacted portable context package. |
| [external_agent_hub.py](external_agent_hub.py#L504) | `_message` | `value: ContextMessage` | `dict[str, object]` | Serialize one non-executable portable context record. |
| [external_agent_hub.py](external_agent_hub.py#L516) | `_tool` | `value: ContextToolCall` | `dict[str, object]` | Serialize one historical tool call without an executable handle. |
| [external_agent_hub.py](external_agent_hub.py#L528) | `_transfer_result` | `value: ContextTransferResult` | `dict[str, object]` | Serialize a typed context write acknowledgement. |
| [external_agents.py](external_agents.py#L21) | `_require_mapping` | `payload: Any` | `dict[str, Any]` | Validate an untyped JSON body before passing it to the hub service. |
| [external_agents.py](external_agents.py#L29) | `external_agent_hub_page` | `None` | `FileResponse` | Serve the standalone External Agent Hub without altering the main shell. |
| [external_agents.py](external_agents.py#L40) | `list_external_providers` | `None` | `dict[str, Any]` | List built-in provider capabilities and connection status. |
| [external_agents.py](external_agents.py#L46) | `configure_external_provider` | `provider_id: str, payload: dict[str, Any]` | `dict[str, Any]` | Save public provider endpoint metadata without accepting credentials. |
| [external_agents.py](external_agents.py#L52) | `probe_external_provider` | `provider_id: str` | `dict[str, Any]` | Probe a Provider without creating a vendor session or turn. |
| [external_agents.py](external_agents.py#L78) | `auto_detect_external_providers` | `None` | `dict[str, Any]` | Probe all implemented local providers without persisting configuration. |
| [external_agents.py](external_agents.py#L99) | `discover_external_sessions` | `provider_id: str, project_path: str \| None` | `dict[str, Any]` | Discover readable vendor sessions through a registered fixed adapter. |
| [external_agents.py](external_agents.py#L119) | `import_discovered_session` | `provider_id: str, external_session_id: str, payload: dict[str, Any]` | `dict[str, Any]` | Import one readable external session into a new Angelus workspace. |
| [external_agents.py](external_agents.py#L156) | `get_external_session_meta` | `session_id: str` | `dict[str, Any]` | Return additive source metadata for an Angelus session. |
| [external_agents.py](external_agents.py#L163) | `export_session_archive` | `session_id: str` | `Response` | Download a credential-free Angelus Session Archive v1 ZIP. |
| [external_agents.py](external_agents.py#L173) | `import_preview` | `payload: dict[str, Any]` | `dict[str, Any]` | Validate an archive or transcript and report projected import fidelity. |
| [external_agents.py](external_agents.py#L193) | `commit_import` | `payload: dict[str, Any]` | `dict[str, Any]` | Create a new session from a validated archive or transcript source. |
| [external_agents.py](external_agents.py#L212) | `transfer_preview` | `session_id: str, payload: dict[str, Any]` | `dict[str, Any]` | Preview a native-history or handoff transfer without provider side effects. |
| [external_agents.py](external_agents.py#L234) | `create_external_link` | `payload: dict[str, Any]` | `dict[str, Any]` | Create a safe Angelus UUID link to an external provider session. |
| [external_agents.py](external_agents.py#L253) | `list_external_links` | `None` | `dict[str, Any]` | List external links excluding ephemeral control lease tokens. |
| [external_agents.py](external_agents.py#L259) | `heartbeat_external_lease` | `link_id: str, payload: dict[str, Any]` | `dict[str, Any]` | Acquire or renew a tab-scoped exclusive external control lease. |
| [external_agents.py](external_agents.py#L269) | `external_link_action` | `link_id: str, payload: dict[str, Any]` | `dict[str, Any]` | Validate a capability-gated action and require the controller lease. |
| [mcp.py](mcp.py#L19) | `_service` | `request: Request` | `Any` | Implement `_service`. |
| [mcp.py](mcp.py#L20) | `_pending_path` | `request: Request` | `Any` | Implement `_pending_path`. |
| [mcp.py](mcp.py#L21) | `_pending` | `request: Request` | `dict[str, Any]` | Implement `_pending`. |
| [mcp.py](mcp.py#L25) | `_write_pending` | `request: Request, value: dict[str, Any]` | `None` | Implement `_write_pending`. |
| [mcp.py](mcp.py#L30) | `_call` | `operation: Any` | `Any` | Implement `_call`. |
| [mcp.py](mcp.py#L37) | `list_servers` | `request: Request` | `Any` | Implement `list_servers`. |
| [mcp.py](mcp.py#L40) | `create_server` | `request: Request, payload: dict[str, Any]` | `Any` | Implement `create_server`. |
| [mcp.py](mcp.py#L43) | `replace_server` | `server_id: str, request: Request, payload: dict[str, Any]` | `Any` | Implement `replace_server`. |
| [mcp.py](mcp.py#L46) | `remove_server` | `server_id: str, request: Request` | `Any` | Implement `remove_server`. |
| [mcp.py](mcp.py#L49) | `probe_server` | `server_id: str, request: Request` | `Any` | Implement `probe_server`. |
| [mcp.py](mcp.py#L52) | `capabilities` | `server_id: str, request: Request` | `Any` | Implement `capabilities`. |
| [mcp.py](mcp.py#L56) | `get_bindings` | `session_id: str, request: Request` | `Any` | Implement `get_bindings`. |
| [mcp.py](mcp.py#L59) | `put_bindings` | `session_id: str, request: Request, payload: dict[str, Any]` | `Any` | Implement `put_bindings`. |
| [mcp.py](mcp.py#L65) | `oauth_connect` | `server_id: str, request: Request, payload: dict[str, Any]` | `Any` | Implement `oauth_connect`. |
| [mcp.py](mcp.py#L75) | `oauth_callback` | `state: str, code: str, request: Request` | `Any` | Implement `oauth_callback`. |
| [mcp.py](mcp.py#L89) | `oauth_disconnect` | `server_id: str, request: Request` | `Any` | Implement `oauth_disconnect`. |
| [mcp.py](mcp.py#L93) | `oauth_refresh` | `server_id: str, request: Request` | `Any` | Implement `oauth_refresh`. |
| [plugins.py](plugins.py#L31) | `_core` | `request: Request` | `AngelusCore` | Resolve the host's only plugin manager ownership graph. |
| [plugins.py](plugins.py#L50) | `active_plugins` | `request: Request` | `dict[str, object]` | Return only currently active browser-loadable plugin packages. |
| [plugins.py](plugins.py#L63) | `plugin_status` | `request: Request` | `dict[str, object]` | Return discovered, registered, inactive, and active plugin status. |
| [plugins.py](plugins.py#L76) | `rescan_plugins` | `request: Request` | `dict[str, object]` | Refresh declarative package discovery without executing plugin code. |
| [plugins.py](plugins.py#L90) | `register_plugin` | `name: str, payload: PluginConfirmation, request: Request` | `dict[str, object]` | Register one validated discovered package without importing it. |
| [plugins.py](plugins.py#L110) | `load_plugin` | `plugin_id: str, payload: PluginConfirmation, request: Request` | `dict[str, object]` | Load one registered plugin after confirmation and permission approval. |
| [plugins.py](plugins.py#L134) | `unload_plugin` | `plugin_id: str, payload: PluginConfirmation, request: Request` | `dict[str, object]` | Unload one plugin while retaining its package, grants, and settings. |
| [plugins.py](plugins.py#L154) | `get_plugin_settings` | `plugin_id: str, request: Request` | `dict[str, object]` | Read typed non-secret settings and schema for one plugin. |
| [plugins.py](plugins.py#L171) | `put_plugin_settings` | `plugin_id: str, request: Request, values: object` | `dict[str, object]` | Validate and persist one plugin's non-secret scalar settings. |
| [plugins.py](plugins.py#L193) | `invoke_plugin_panel` | `plugin_id: str, panel_id: str, request: Request, values: object` | `dict[str, object]` | Submit transient user input to one active declarative plugin panel. |
| [plugins.py](plugins.py#L227) | `_action_result_json` | `result: PluginUiActionResult` | `dict[str, str]` | Serialize one typed plugin action result for the browser. |
| [plugins.py](plugins.py#L240) | `plugin_static` | `name: str, asset: str, request: Request` | `FileResponse` | Serve one active plugin's manifest-whitelisted static asset. |
| [providers.py](providers.py#L13) | `_core` | `request: Request` | `AngelusCore` | Resolve the application-owned core and its provider catalog. |
| [providers.py](providers.py#L22) | `list_providers` | `request: Request` | `dict[str, list[str]]` | Return providers available from the installed LLMFetcher handlers. |
| [runs.py](runs.py#L37) | `RunRequest.require_input` | `None` | `'RunRequest'` | Implement `RunRequest.require_input`. |
| [runs.py](runs.py#L70) | `_core` | `request: Request` | `AngelusCore` | Resolve the app-owned core without constructing a fallback instance. |
| [runs.py](runs.py#L79) | `start_run` | `payload: RunRequest, request: Request` | `dict[str, Any]` | Start one attempt against the Session's configured coordinator. |
| [runs.py](runs.py#L104) | `run_status` | `session_id: str, request: Request` | `dict[str, Any]` | Return current process state; manifest is the restart source. |
| [runs.py](runs.py#L121) | `_stop` | `session_id: str, payload: StopRequest, request: Request, force: bool` | `dict[str, Any]` | Implement `_stop`. |
| [runs.py](runs.py#L135) | `stop_run` | `session_id: str, payload: StopRequest, request: Request` | `dict[str, Any]` | Request graceful stop through the attempt's only controller. |
| [runs.py](runs.py#L141) | `force_stop_run` | `session_id: str, payload: StopRequest, request: Request` | `dict[str, Any]` | Escalate the same request and close every registered live resource. |
| [runs.py](runs.py#L147) | `control_run` | `session_id: str, payload: AgentControlRequest, request: Request` | `dict[str, object]` | Apply one control command to every Agent or one selected Agent. |
| [session_console.py](session_console.py#L80) | `_service` | `request: Request` | `Any` | Resolve the installed console projection service. |
| [session_console.py](session_console.py#L95) | `_call` | `fn: Any` | `Any` | Map console-domain failures raised by one deferred route action. |
| [session_console.py](session_console.py#L110) | `agents` | `session_id: str, request: Request` | `Any` | Return safe metadata for all Session Agents. |
| [session_console.py](session_console.py#L122) | `graph` | `session_id: str, request: Request, execution_id: str \| None` | `Any` | Return the selected/latest execution graph for this Session. |
| [session_console.py](session_console.py#L134) | `graph_events` | `session_id: str, request: Request, cursor: int, execution_id: str \| None, last_event_id: str \| None` | `StreamingResponse` | Replay and follow standardized RunGraph events for one execution. |
| [session_console.py](session_console.py#L165) | `workflow` | `session_id: str, request: Request` | `Any` | Return the persisted, editable Session workflow blueprint. |
| [session_console.py](session_console.py#L169) | `recover_graph` | `session_id: str, body: RecoveryRequest, request: Request` | `Any` | Create a new guided attempt from a verified RunGraph checkpoint. |
| [session_console.py](session_console.py#L179) | `graph_info` | `session_id: str, request: Request` | `Any` | Return compact graph counts and editability. |
| [session_console.py](session_console.py#L191) | `add_agent` | `session_id: str, body: AgentEdit, request: Request` | `Any` | Persist one worker and rebuild the idle graph. |
| [session_console.py](session_console.py#L204) | `delete_agent` | `session_id: str, name: str, request: Request` | `Any` | Implement `delete_agent`. |
| [session_console.py](session_console.py#L206) | `delete_agent_body` | `session_id: str, body: AgentEdit, request: Request` | `Any` | Implement `delete_agent_body`. |
| [session_console.py](session_console.py#L208) | `add_connection` | `session_id: str, body: ConnectionEdit, request: Request` | `Any` | Implement `add_connection`. |
| [session_console.py](session_console.py#L210) | `delete_connection` | `session_id: str, body: ConnectionEdit, request: Request` | `Any` | Implement `delete_connection`. |
| [session_console.py](session_console.py#L212) | `mapper` | `session_id: str, body: MapperEdit, request: Request` | `Any` | Implement `mapper`. |
| [session_console.py](session_console.py#L214) | `router_edit` | `session_id: str, body: RouterEdit, request: Request` | `Any` | Implement `router_edit`. |
| [session_console.py](session_console.py#L216) | `plan` | `session_id: str, request: Request, agent: str \| None` | `Any` | Implement `plan`. |
| [session_console.py](session_console.py#L218) | `events` | `session_id: str, request: Request, cursor: int, limit: int` | `Any` | Implement `events`. |
| [session_console.py](session_console.py#L222) | `events_stream` | `session_id: str, request: Request, cursor: int, last_event_id: str \| None` | `StreamingResponse` | Follow durable lifecycle facts so the browser renders live deltas. |
| [session_console.py](session_console.py#L252) | `usage` | `session_id: str, request: Request` | `Any` | Implement `usage`. |
| [session_console.py](session_console.py#L254) | `context` | `session_id: str, agent: str, request: Request, before: int \| None, limit: int` | `Any` | Return the newest context page or one older cursor page. |
| [session_console.py](session_console.py#L271) | `export_context` | `session_id: str, agent: str, request: Request, before: int \| None, limit: int` | `dict[str, object]` | Export one bounded durable context page without reading all history. |
| [session_console.py](session_console.py#L304) | `import_context` | `session_id: str, agent: str, request: Request, payload: object` | `Any` | Append a selected portable package to one idle Session Agent. |
| [session_console.py](session_console.py#L331) | `context_graph` | `session_id: str, agent: str, request: Request` | `Any` | Implement `context_graph`. |
| [session_console.py](session_console.py#L333) | `request_preview` | `session_id: str, agent: str, body: RequestPreviewInput, request: Request` | `Any` | Compose the next dispatch-ready model request without sending it. |
| [session_console.py](session_console.py#L347) | `compaction_input` | `session_id: str, agent: str, request: Request` | `Any` | Implement `compaction_input`. |
| [session_console.py](session_console.py#L350) | `_core_context_exchange` | `request: Request` | `Any` | Resolve the application-owned portable context exchange service. |
| [session_console.py](session_console.py#L368) | `_package` | `value: ContextPackage` | `dict[str, object]` | Serialize one portable package without exposing executable tool data. |
| [sessions.py](sessions.py#L33) | `_core` | `request: Request` | `AngelusCore` | Resolve the app-owned core without manufacturing application state. |
| [sessions.py](sessions.py#L42) | `list_sessions` | `request: Request` | `dict[str, list[dict[str, Any]]]` | List durable workspace identities, not process-local execution state. |
| [sessions.py](sessions.py#L59) | `create_session` | `payload: CreateSessionRequest, request: Request` | `dict[str, Any]` | Create an empty session; Agent and graph configuration come afterwards. |
| [sessions.py](sessions.py#L78) | `delete_session` | `session_id: str, payload: DeleteSessionRequest, request: Request` | `dict[str, str]` | Delete one confirmed Session after its active execution has stopped. |
| [sessions.py](sessions.py#L92) | `get_session_messages` | `session_id: str, request: Request, before: int \| None, limit: int, agent: str \| None` | `dict[str, Any]` | Return one Agent's durable context as a chronological chat page. |
| [settings.py](settings.py#L48) | `_core` | `request: Request` | `AngelusCore` | Resolve host-owned core without creating a second settings store. |
| [settings.py](settings.py#L61) | `tool_registry` | `request: Request` | `ToolCatalog` | Return categories and tools actually registered by backend providers. |
| [settings.py](settings.py#L74) | `version` | `None` | `RuntimeVersions` | Return independent Angelus and llmfetcher runtime versions. |
| [settings.py](settings.py#L84) | `list_connectors` | `request: Request` | `dict[str, list[dict[str, Any]]]` | List global connectors without serializing credentials in HTTP output. |
| [settings.py](settings.py#L90) | `create_connector` | `payload: ConnectorPayload, request: Request` | `dict[str, Any]` | Create one globally reusable connector and return its public projection. |
| [settings.py](settings.py#L99) | `replace_connector` | `connector_id: str, payload: ConnectorPayload, request: Request` | `dict[str, Any]` | Replace metadata, retaining a secret when the supplied API key is blank. |
| [settings.py](settings.py#L110) | `delete_connector` | `connector_id: str, request: Request` | `None` | Delete connector only when no effective run profile references it. |
| [settings.py](settings.py#L127) | `get_global_profile` | `request: Request` | `dict[str, Any]` | Return global defaults for future Session attempts, not a live config. |
| [settings.py](settings.py#L133) | `put_global_profile` | `payload: ProfilePayload, request: Request` | `dict[str, Any]` | Validate then atomically replace global defaults for later attempts. |
| [settings.py](settings.py#L142) | `get_session_profile` | `session_id: str, request: Request` | `dict[str, Any]` | Return one Session's effective future-attempt profile and inheritance. |
| [settings.py](settings.py#L151) | `put_session_profile` | `session_id: str, payload: ProfilePayload, request: Request` | `dict[str, Any]` | Validate then atomically replace one Session's future-run override. |
| [settings.py](settings.py#L162) | `delete_session_profile` | `session_id: str, request: Request` | `dict[str, Any]` | Discard a Session override and return its now-inherited effective profile. |
| [workspace_directory.py](workspace_directory.py#L19) | `pick_workspace_directory` | `None` | `dict[str, bool \| str \| None]` | Ask the system resource manager to select one absolute directory. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [external_agent_hub.py](external_agent_hub.py#L19) | `ExternalAgentInput` | `id: str, title: str, adapter_kind: str, endpoint: str, connector_id: str, enabled: bool, description: str` | `object` | Validated HTTP body fields for a complete external Agent definition. |
| [plugins.py](plugins.py#L18) | `PluginConfirmation` | `confirm: bool, grant_permissions: bool` | `BaseModel` | Explicit browser confirmation required for executable plugin actions. |
| [runs.py](runs.py#L19) | `RunImageReference` | `attachment_id: str, media_type: Literal['image/png', 'image/jpeg', 'image/webp', 'image/gif'], detail: Literal['auto', 'low', 'high']` | `BaseModel` | An existing Session image, never arbitrary paths or remote URLs. |
| [runs.py](runs.py#L28) | `RunRequest` | `session_id: str, message: str, images: list[RunImageReference], target_agent: str \| None` | `BaseModel` | HTTP input for one configured Session execution. |
| [runs.py](runs.py#L43) | `StopRequest` | `reason: str` | `BaseModel` | HTTP input for either graceful or forced stop. |
| [runs.py](runs.py#L50) | `AgentControlRequest` | `agent_id: str, action: str, message: str, reason: str, images: list[RunImageReference]` | `object` | Typed input for an all-Agent or targeted runtime command. |
| [session_console.py](session_console.py#L18) | `AgentEdit` | `name: str, system_prompt: str` | `object` | Typed input for an idle graph worker edit. |
| [session_console.py](session_console.py#L29) | `ConnectionEdit` | `source: str, target: str` | `object` | Typed input for a directed dependency mutation. |
| [session_console.py](session_console.py#L40) | `MapperEdit` | `agent: str, mode: str` | `object` | Typed input for a declarative input mapper. |
| [session_console.py](session_console.py#L51) | `RouterEdit` | `agent: str, targets: list[str]` | `object` | Typed input for a declarative dynamic router. |
| [session_console.py](session_console.py#L63) | `RequestPreviewInput` | `message: str` | `object` | Typed input for one no-send next-request composition. |
| [session_console.py](session_console.py#L75) | `RecoveryRequest` | `execution_id: str \| None` | `object` | Optional source execution selected for safe guided recovery. |
| [sessions.py](sessions.py#L19) | `CreateSessionRequest` | `session_id: str \| None, name: str, project_path: str \| None` | `BaseModel` | HTTP input for an empty logical Session and its workspace. |
| [sessions.py](sessions.py#L27) | `DeleteSessionRequest` | `confirmation: str` | `BaseModel` | Explicit confirmation for an irreversible session-data deletion. |
| [settings.py](settings.py#L19) | `ConnectorPayload` | `name: str, provider: str, model: str, api_url: str, api_key: str` | `BaseModel` | Public connector metadata plus an optional write-only API key. |
| [settings.py](settings.py#L37) | `ProfilePayload` | `settings: dict[str, Any]` | `BaseModel` | A complete profile document for global defaults or one Session override. |

<!-- END GENERATED SYMBOL MAP -->
