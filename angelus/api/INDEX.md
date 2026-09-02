# angelus/api/ — Phase 1 HTTP INDEX

Routes are transport adapters only. They resolve `AngelusCore` from app state,
validate HTTP input, call one service, and map known domain errors to HTTP.
They do not own Session, Agent, execution, persistence or credentials.

| File | Mounted routes | Responsibility |
|---|---|---|
| `__init__.py` | `/`, `/favicon.ico`, `/static/*` | Install mounted routers and SPA shell; call core shutdown hook. |
| `sessions.py` | `/api/sessions` | Create/list/delete Session identities and page legacy transcript projection. |
| `runs.py` | `/api/runs`, `/api/runs/{id}/…` | Start, inspect, stop/force-stop and event-index cursor-resumable replay/follow of one Session attempt. SSE uses default `message` frames so all trace types reach the browser handler. |
| `settings.py` | `/api/connectors`, `/api/settings/run-profile`, `/api/sessions/{id}/run-profile` | Connector CRUD and global/Session future-run settings. |
| `providers.py` | `/api/providers` | Read installed LLMFetcher provider capabilities. |
| `workspace_directory.py` | `/api/workspace-directory/pick` | Optional local native directory chooser. |
| `session_console.py` | `/api/sessions/{id}/agents`, graph, plan, events, usage and context routes | Typed Session-console projection, idle-only graph editing, and bounded portable context export/import. |
| `external_agent_hub.py` | `/api/external-agents` | External Agent definition CRUD, explicit local-process discovery, inspection, and capability-gated portable-context reads/writes. |
| `plugins.py` | `/api/plugins` | Controlled plugin discovery/lifecycle, persisted settings, static assets, and active declarative panel actions. |

## Not Mounted in Phase 1

`compact.py`, `external_agents.py` and `mcp.py` are retained historic source
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
| `runs.py` | `start_run`, `run_status`, stop endpoints | Execution lifecycle over `ExecutionService`. |
| `session_console.py` | graph/plan/events/context endpoints | Console projection over the Session's swarm, journal and persisted contexts; context export pages durable history and import appends only to idle Agents. |
| `settings.py` | connector/profile endpoints | Settings use cases over `SettingsService`. |
| `providers.py` | `list_providers` | Runtime capability read. |
| `workspace_directory.py` | directory picker endpoint | Desktop-only local directory selection. |
| `external_agent_hub.py` | External Agent CRUD/discovery/health/capabilities/sessions/contexts | Hub API; discovery is an explicit read-only scan and context exchange is capability-gated with no connector-secret serialization. |
| `plugins.py` | plugin lifecycle/settings/panel action endpoints | Register/load controlled packages; validate persistent settings and transient host-rendered panel input. |

## Class Map

| Source | Class | Semantics |
|---|---|---|
| `runs.py` | `RunRequest`, `StopRequest` | Typed input for starting/cancelling a Session attempt. |
| `sessions.py` | `CreateSessionRequest`, `DeleteSessionRequest` | Typed Session registration/deletion input. |
| `settings.py` | `ConnectorPayload`, `ProfilePayload` | Typed connector and future-run profile input. |
| `external_agent_hub.py` | `ExternalAgentInput` | Typed non-secret HTTP definition body for one external Agent runtime. |

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [__init__.py](__init__.py#L20) | `include_api_routes` | `app: FastAPI, core: AngelusCore` | `None` | Install API routes and the local workbench assets on one host. |
| [compact.py](compact.py#L29) | `_stage` | `stage: str, detail: str, kind: str, error: str \| None, raw_content: str \| None` | `str` | Serialize one compaction progress record as an NDJSON line. |
| [compact.py](compact.py#L63) | `_build_compactor_fetcher` | `config: Any` | `LLMFetcher` | Create a throwaway LLM fetcher for the manual compaction call. |
| [compact.py](compact.py#L84) | `compact_session` | `session_id: str, request: CompactRequest` | `StreamingResponse` | Compress one Agent's linear context into a single summary abstract. |
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
| [plugins.py](plugins.py#L30) | `_core` | `request: Request` | `AngelusCore` | Resolve the host's only plugin manager ownership graph. |
| [plugins.py](plugins.py#L49) | `active_plugins` | `request: Request` | `dict[str, object]` | Return only currently active browser-loadable plugin packages. |
| [plugins.py](plugins.py#L62) | `plugin_status` | `request: Request` | `dict[str, object]` | Return discovered, registered, inactive, and active plugin status. |
| [plugins.py](plugins.py#L75) | `rescan_plugins` | `request: Request` | `dict[str, object]` | Refresh declarative package discovery without executing plugin code. |
| [plugins.py](plugins.py#L89) | `register_plugin` | `name: str, payload: PluginConfirmation, request: Request` | `dict[str, object]` | Register one validated discovered package without importing it. |
| [plugins.py](plugins.py#L109) | `load_plugin` | `plugin_id: str, payload: PluginConfirmation, request: Request` | `dict[str, object]` | Load one registered plugin after confirmation and permission approval. |
| [plugins.py](plugins.py#L133) | `unload_plugin` | `plugin_id: str, payload: PluginConfirmation, request: Request` | `dict[str, object]` | Unload one plugin while retaining its package, grants, and settings. |
| [plugins.py](plugins.py#L153) | `get_plugin_settings` | `plugin_id: str, request: Request` | `dict[str, object]` | Read typed non-secret settings and schema for one plugin. |
| [plugins.py](plugins.py#L170) | `put_plugin_settings` | `plugin_id: str, request: Request, values: object` | `dict[str, object]` | Validate and persist one plugin's non-secret scalar settings. |
| [plugins.py](plugins.py#L192) | `plugin_static` | `name: str, asset: str, request: Request` | `FileResponse` | Serve one active plugin's manifest-whitelisted static asset. |
| [providers.py](providers.py#L13) | `_core` | `request: Request` | `AngelusCore` | Resolve the application-owned core and its provider catalog. |
| [providers.py](providers.py#L22) | `list_providers` | `request: Request` | `dict[str, list[str]]` | Return providers available from the installed LLMFetcher handlers. |
| [runs.py](runs.py#L53) | `_core` | `request: Request` | `AngelusCore` | Resolve the app-owned core without constructing a fallback instance. |
| [runs.py](runs.py#L62) | `start_run` | `payload: RunRequest, request: Request` | `dict[str, Any]` | Start one attempt against the Session's configured coordinator. |
| [runs.py](runs.py#L82) | `run_status` | `session_id: str, request: Request` | `dict[str, Any]` | Return current process state; manifest is the restart source. |
| [runs.py](runs.py#L99) | `_stop` | `session_id: str, payload: StopRequest, request: Request, force: bool` | `dict[str, Any]` | Implement `_stop`. |
| [runs.py](runs.py#L113) | `stop_run` | `session_id: str, payload: StopRequest, request: Request` | `dict[str, Any]` | Request graceful stop through the attempt's only controller. |
| [runs.py](runs.py#L119) | `force_stop_run` | `session_id: str, payload: StopRequest, request: Request` | `dict[str, Any]` | Escalate the same request and close every registered live resource. |
| [runs.py](runs.py#L125) | `control_run` | `session_id: str, payload: AgentControlRequest, request: Request` | `dict[str, object]` | Apply one control command to every Agent or one selected Agent. |
| [runs.py](runs.py#L152) | `run_events` | `session_id: str, request: Request, cursor: int` | `StreamingResponse` | Replay and follow unified journal events for one Session attempt. |
| [session_console.py](session_console.py#L67) | `_service` | `request: Request` | `Any` | Resolve the installed console projection service. |
| [session_console.py](session_console.py#L82) | `_call` | `fn: Any` | `Any` | Map console-domain failures raised by one deferred route action. |
| [session_console.py](session_console.py#L97) | `agents` | `session_id: str, request: Request` | `Any` | Return safe metadata for all Session Agents. |
| [session_console.py](session_console.py#L109) | `graph` | `session_id: str, request: Request` | `Any` | Return the Session graph projection. |
| [session_console.py](session_console.py#L121) | `graph_info` | `session_id: str, request: Request` | `Any` | Return compact graph counts and editability. |
| [session_console.py](session_console.py#L133) | `add_agent` | `session_id: str, body: AgentEdit, request: Request` | `Any` | Persist one worker and rebuild the idle graph. |
| [session_console.py](session_console.py#L146) | `delete_agent` | `session_id: str, name: str, request: Request` | `Any` | Implement `delete_agent`. |
| [session_console.py](session_console.py#L148) | `delete_agent_body` | `session_id: str, body: AgentEdit, request: Request` | `Any` | Implement `delete_agent_body`. |
| [session_console.py](session_console.py#L150) | `add_connection` | `session_id: str, body: ConnectionEdit, request: Request` | `Any` | Implement `add_connection`. |
| [session_console.py](session_console.py#L152) | `delete_connection` | `session_id: str, body: ConnectionEdit, request: Request` | `Any` | Implement `delete_connection`. |
| [session_console.py](session_console.py#L154) | `mapper` | `session_id: str, body: MapperEdit, request: Request` | `Any` | Implement `mapper`. |
| [session_console.py](session_console.py#L156) | `router_edit` | `session_id: str, body: RouterEdit, request: Request` | `Any` | Implement `router_edit`. |
| [session_console.py](session_console.py#L158) | `plan` | `session_id: str, request: Request, agent: str \| None` | `Any` | Implement `plan`. |
| [session_console.py](session_console.py#L160) | `events` | `session_id: str, request: Request, cursor: int, limit: int` | `Any` | Implement `events`. |
| [session_console.py](session_console.py#L162) | `usage` | `session_id: str, request: Request` | `Any` | Implement `usage`. |
| [session_console.py](session_console.py#L164) | `context` | `session_id: str, agent: str, request: Request, before: int \| None, limit: int` | `Any` | Return the newest context page or one older cursor page. |
| [session_console.py](session_console.py#L179) | `context_graph` | `session_id: str, agent: str, request: Request` | `Any` | Implement `context_graph`. |
| [session_console.py](session_console.py#L181) | `request_preview` | `session_id: str, agent: str, body: RequestPreviewInput, request: Request` | `Any` | Compose the next dispatch-ready model request without sending it. |
| [session_console.py](session_console.py#L195) | `compaction_input` | `session_id: str, agent: str, request: Request` | `Any` | Implement `compaction_input`. |
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
| [workspace_directory.py](workspace_directory.py#L16) | `pick_workspace_directory` | `None` | `dict[str, bool \| str \| None]` | Open one native directory picker and return a selected absolute path. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [plugins.py](plugins.py#L17) | `PluginConfirmation` | `confirm: bool, grant_permissions: bool` | `BaseModel` | Explicit browser confirmation required for executable plugin actions. |
| [runs.py](runs.py#L23) | `RunRequest` | `session_id: str, message: str` | `BaseModel` | HTTP input for one configured Session execution. |
| [runs.py](runs.py#L30) | `StopRequest` | `reason: str` | `BaseModel` | HTTP input for either graceful or forced stop. |
| [runs.py](runs.py#L37) | `AgentControlRequest` | `agent_id: str, action: str, message: str, reason: str` | `object` | Typed input for an all-Agent or targeted runtime command. |
| [session_console.py](session_console.py#L12) | `AgentEdit` | `name: str, system_prompt: str` | `object` | Typed input for an idle graph worker edit. |
| [session_console.py](session_console.py#L23) | `ConnectionEdit` | `source: str, target: str` | `object` | Typed input for a directed dependency mutation. |
| [session_console.py](session_console.py#L34) | `MapperEdit` | `agent: str, mode: str` | `object` | Typed input for a declarative input mapper. |
| [session_console.py](session_console.py#L45) | `RouterEdit` | `agent: str, targets: list[str]` | `object` | Typed input for a declarative dynamic router. |
| [session_console.py](session_console.py#L57) | `RequestPreviewInput` | `message: str` | `object` | Typed input for one no-send next-request composition. |
| [sessions.py](sessions.py#L19) | `CreateSessionRequest` | `session_id: str \| None, name: str, project_path: str` | `BaseModel` | HTTP input for an empty logical Session and its workspace. |
| [sessions.py](sessions.py#L27) | `DeleteSessionRequest` | `confirmation: str` | `BaseModel` | Explicit confirmation for an irreversible session-data deletion. |
| [settings.py](settings.py#L19) | `ConnectorPayload` | `name: str, provider: str, model: str, api_url: str, api_key: str` | `BaseModel` | Public connector metadata plus an optional write-only API key. |
| [settings.py](settings.py#L37) | `ProfilePayload` | `settings: dict[str, Any]` | `BaseModel` | A complete profile document for global defaults or one Session override. |

<!-- END GENERATED SYMBOL MAP -->
