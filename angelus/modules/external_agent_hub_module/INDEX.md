# external_agent_hub_module/ — External Agent Hub INDEX

This module owns credential-free configuration, bounded inspection, and typed
historical-context exchange boundaries for external Agent runtimes. It stores
no credentials: a definition can only name an optional `ConnectorStore`
reference. Protocol implementations remain isolated behind the adapter base
and are never allowed to dispatch remote work as part of context exchange.

| File | Responsibility |
|---|---|
| `models.py` | Dataclass contracts for definitions, health, capabilities, sessions, process candidates, and portable context envelopes. |
| `context_codec.py` | Strict bounded decoding of a JSON context package into dataclasses. |
| `context_exchange.py` | Session-owned paged export and idle-only historical append import; redacts credential-like text and never executes imported tool calls. |
| `discovery.py` | Bounded Linux procfs process scanner; discovery is read-only and never attaches to a process. |
| `store.py` | Atomic credential-free definition persistence. |
| `adapter.py` | Read-only protocol adapter contract and process-local registry. |
| `codex_app_server.py` | Constrained local-stdio Codex App Server handshake and thread inspection. |
| `adapters/claude_sdk.py` | Lazy, injectable Claude Agent SDK session-discovery adapter. |
| `adapters/read_only.py` | Shared typed HTTP/CLI/SDK facade boundary and session normalizer. |
| `adapters/coze.py` | Read-only Coze Bot and Workflow adapter. |
| `adapters/opencode.py` | Read-only OpenCode Server adapter. |
| `adapters/workbuddy.py` | Read-only WorkBuddy adapter. |
| `service.py` | Validation, CRUD, health, capability, session/context inspection, external context writes, and local process discovery use cases. |

## Phase-one Boundary

- The Hub can create, replace, list, delete, health-check, and inspect an
  external Agent definition.
- Missing protocol adapters produce `unsupported`; no fallback request is made.
- Context exchange uses `ContextPackage` schema 1 and is bounded to 200
  messages per package. Session export has an older-page cursor and therefore
  does not load a durable transcript in full.
- Session imports are allowed only while idle and append historical `system`,
  `user`, and `assistant` records. Historical tool calls are never executed;
  unsupported `tool`-role records are reported as rejected.
- External reads/writes exist only when an adapter exposes an audited protocol.
  Unsupported adapters raise a domain failure; they never return fake context
  data or successful writes.
- Codex App Server uses documented non-resuming `thread/list` and
  `thread/read(includeTurns=true)` calls for context listing and read-only
  package extraction. Context writes remain unsupported.
- Coze, OpenCode, and WorkBuddy adapters receive an injected HTTP, CLI, or SDK
  facade. They only health-check and list bounded session summaries; they do
  not start, resume, import, steer, or cancel a remote run.
- Local process discovery is an explicitly invoked, ephemeral procfs scan. A
  candidate is never persisted or attached automatically; the browser must
  create a separate durable definition after user confirmation.

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [adapter.py](adapter.py#L20) | `ExternalAgentAdapter.kind` | `None` | `ExternalAgentAdapterKind` | Return the adapter kind uniquely owned by this implementation. |
| [adapter.py](adapter.py#L27) | `ExternalAgentAdapter.health` | `definition: ExternalAgentDefinition` | `ExternalAgentHealth` | Probe a definition without starting a remote Agent run. |
| [adapter.py](adapter.py#L37) | `ExternalAgentAdapter.discover_capabilities` | `definition: ExternalAgentDefinition` | `tuple[ExternalAgentCapability, ...]` | Read declared remote capabilities without executing one. |
| [adapter.py](adapter.py#L50) | `ExternalAgentAdapter.discover_sessions` | `definition: ExternalAgentDefinition, limit: int` | `tuple[ExternalAgentSession, ...]` | Read remote session summaries without starting or importing one. |
| [adapter.py](adapter.py#L66) | `ExternalAgentAdapter.list_contexts` | `definition: ExternalAgentDefinition, cursor: str \| None, limit: int` | `ContextPage` | List bounded external context descriptors without importing one. |
| [adapter.py](adapter.py#L87) | `ExternalAgentAdapter.read_context` | `definition: ExternalAgentDefinition, context_id: str` | `ContextPackage` | Read one external context into Angelus's portable envelope. |
| [adapter.py](adapter.py#L106) | `ExternalAgentAdapter.write_context` | `definition: ExternalAgentDefinition, package: ContextPackage` | `ContextTransferResult` | Write one portable package only through an audited product protocol. |
| [adapter.py](adapter.py#L136) | `ExternalAgentAdapterRegistry.register` | `adapter: ExternalAgentAdapter` | `None` | Register one implementation for its declared adapter kind. |
| [adapter.py](adapter.py#L152) | `ExternalAgentAdapterRegistry.health` | `definition: ExternalAgentDefinition` | `ExternalAgentHealth` | Return adapter health or a safe unsupported state. |
| [adapter.py](adapter.py#L180) | `ExternalAgentAdapterRegistry.capabilities` | `definition: ExternalAgentDefinition` | `tuple[ExternalAgentCapability, ...]` | Return adapter capabilities or an empty result before implementation. |
| [adapter.py](adapter.py#L197) | `ExternalAgentAdapterRegistry.sessions` | `definition: ExternalAgentDefinition, limit: int` | `tuple[ExternalAgentSession, ...]` | Return remote sessions or an empty result before adapter installation. |
| [adapter.py](adapter.py#L215) | `ExternalAgentAdapterRegistry.contexts` | `definition: ExternalAgentDefinition, cursor: str \| None, limit: int` | `ContextPage` | List bounded external context descriptors through one adapter. |
| [adapter.py](adapter.py#L240) | `ExternalAgentAdapterRegistry.read_context` | `definition: ExternalAgentDefinition, context_id: str` | `ContextPackage` | Read one external context through its installed adapter. |
| [adapter.py](adapter.py#L264) | `ExternalAgentAdapterRegistry.write_context` | `definition: ExternalAgentDefinition, package: ContextPackage` | `ContextTransferResult` | Write one portable package through its installed audited adapter. |
| [adapters/claude_sdk.py](adapters/claude_sdk.py#L72) | `ClaudeSdkSessionDiscovery.availability` | `None` | `ClaudeSdkAvailability` | Report whether local SDK inspection can be attempted. |
| [adapters/claude_sdk.py](adapters/claude_sdk.py#L79) | `ClaudeSdkSessionDiscovery.list_sessions` | `limit: int` | `tuple[ClaudeSdkSessionRecord, ...]` | Read at most ``limit`` newest Claude session summaries. |
| [adapters/claude_sdk.py](adapters/claude_sdk.py#L93) | `LocalClaudeSdkSessionDiscovery.availability` | `None` | `ClaudeSdkAvailability` | Check package availability without importing the optional SDK. |
| [adapters/claude_sdk.py](adapters/claude_sdk.py#L107) | `LocalClaudeSdkSessionDiscovery.list_sessions` | `limit: int` | `tuple[ClaudeSdkSessionRecord, ...]` | Import the SDK only when a caller requests session summaries. |
| [adapters/claude_sdk.py](adapters/claude_sdk.py#L150) | `ClaudeSdkAdapter.kind` | `None` | `str` | Return the Hub adapter kind owned by this implementation. |
| [adapters/claude_sdk.py](adapters/claude_sdk.py#L158) | `ClaudeSdkAdapter.health` | `definition: ExternalAgentDefinition` | `ExternalAgentHealth` | Report local Claude SDK inspection availability without dispatching. |
| [adapters/claude_sdk.py](adapters/claude_sdk.py#L172) | `ClaudeSdkAdapter.discover_capabilities` | `definition: ExternalAgentDefinition` | `tuple[ExternalAgentCapability, ...]` | Describe the adapter's implemented read-only operation. |
| [adapters/claude_sdk.py](adapters/claude_sdk.py#L195) | `ClaudeSdkAdapter.discover_sessions` | `definition: ExternalAgentDefinition, limit: int` | `tuple[ExternalAgentSession, ...]` | Map locally discoverable Claude sessions into Hub summaries. |
| [adapters/claude_sdk.py](adapters/claude_sdk.py#L229) | `ClaudeSdkAdapter.list_contexts` | `definition: ExternalAgentDefinition, cursor: str \| None, limit: int` | `ContextPage` | Reject transcript listing until Claude publishes a supported SDK API. |
| [adapters/claude_sdk.py](adapters/claude_sdk.py#L262) | `ClaudeSdkAdapter.read_context` | `definition: ExternalAgentDefinition, context_id: str` | `ContextPackage` | Reject transcript reads until Claude publishes a supported SDK API. |
| [adapters/claude_sdk.py](adapters/claude_sdk.py#L292) | `ClaudeSdkAdapter.write_context` | `definition: ExternalAgentDefinition, package: ContextPackage` | `ContextTransferResult` | Reject imports because Claude SDK exposes no safe transcript writer. |
| [adapters/claude_sdk.py](adapters/claude_sdk.py#L324) | `_normalize_sessions` | `value: object, limit: int` | `tuple[ClaudeSdkSessionRecord, ...]` | Normalize SDK objects and mapping records without exposing SDK types. |
| [adapters/claude_sdk.py](adapters/claude_sdk.py#L346) | `_normalize_session` | `value: object` | `ClaudeSdkSessionRecord \| None` | Extract safe session summary fields from one vendor SDK result. |
| [adapters/claude_sdk.py](adapters/claude_sdk.py#L368) | `_text` | `value: object, field: str` | `str` | Read one string field from an SDK object or mapping. |
| [adapters/claude_sdk.py](adapters/claude_sdk.py#L382) | `_timestamp` | `value: object, field: str` | `int \| None` | Read one integer timestamp field from an SDK object or mapping. |
| [adapters/coze.py](adapters/coze.py#L18) | `CozeExternalAgentAdapter.kind` | `None` | `str` | Return the External Agent Hub kind reserved for Coze. |
| [adapters/coze.py](adapters/coze.py#L37) | `CozeExternalAgentAdapter.health` | `definition: ExternalAgentDefinition` | `ExternalAgentHealth` | Probe Coze without starting a Bot chat or Workflow execution. |
| [adapters/coze.py](adapters/coze.py#L48) | `CozeExternalAgentAdapter.discover_capabilities` | `definition: ExternalAgentDefinition` | `tuple[ExternalAgentCapability, ...]` | Return Coze Bot and Workflow capabilities without invoking either. |
| [adapters/coze.py](adapters/coze.py#L62) | `CozeExternalAgentAdapter.discover_sessions` | `definition: ExternalAgentDefinition, limit: int` | `tuple[ExternalAgentSession, ...]` | List Coze conversation or workflow session summaries without resume. |
| [adapters/coze.py](adapters/coze.py#L74) | `CozeExternalAgentAdapter.list_contexts` | `definition: ExternalAgentDefinition, cursor: str \| None, limit: int` | `'ContextPage'` | List Coze conversation contexts through an explicitly installed facade. |
| [adapters/coze.py](adapters/coze.py#L109) | `CozeExternalAgentAdapter.read_context` | `definition: ExternalAgentDefinition, context_id: str` | `'ContextPackage'` | Read one Coze context package through an explicitly installed facade. |
| [adapters/coze.py](adapters/coze.py#L140) | `CozeExternalAgentAdapter.write_context` | `definition: ExternalAgentDefinition, package: 'ContextPackage'` | `'ContextTransferResult'` | Reject writes because the installed Coze facade is read-only. |
| [adapters/opencode.py](adapters/opencode.py#L28) | `OpenCodeContextFacade.list_contexts` | `definition: ExternalAgentDefinition, cursor: str \| None, limit: int` | `ContextPage` | Read one bounded page of OpenCode session context summaries. |
| [adapters/opencode.py](adapters/opencode.py#L46) | `OpenCodeContextFacade.read_context` | `definition: ExternalAgentDefinition, context_id: str` | `ContextPackage` | Read one normalized OpenCode session context package. |
| [adapters/opencode.py](adapters/opencode.py#L66) | `OpenCodeExternalAgentAdapter.kind` | `None` | `str` | Return the External Agent Hub kind reserved for OpenCode. |
| [adapters/opencode.py](adapters/opencode.py#L85) | `OpenCodeExternalAgentAdapter.health` | `definition: ExternalAgentDefinition` | `ExternalAgentHealth` | Probe OpenCode Server without creating an OpenCode session. |
| [adapters/opencode.py](adapters/opencode.py#L96) | `OpenCodeExternalAgentAdapter.discover_capabilities` | `definition: ExternalAgentDefinition` | `tuple[ExternalAgentCapability, ...]` | Return known OpenCode session operations without dispatching a prompt. |
| [adapters/opencode.py](adapters/opencode.py#L110) | `OpenCodeExternalAgentAdapter.discover_sessions` | `definition: ExternalAgentDefinition, limit: int` | `tuple[ExternalAgentSession, ...]` | List OpenCode session summaries without importing or mutating them. |
| [adapters/opencode.py](adapters/opencode.py#L122) | `OpenCodeExternalAgentAdapter.list_contexts` | `definition: ExternalAgentDefinition, cursor: str \| None, limit: int` | `ContextPage` | Page OpenCode session context summaries through an installed facade. |
| [adapters/opencode.py](adapters/opencode.py#L147) | `OpenCodeExternalAgentAdapter.read_context` | `definition: ExternalAgentDefinition, context_id: str` | `ContextPackage` | Read an OpenCode session transcript without changing it. |
| [adapters/opencode.py](adapters/opencode.py#L169) | `OpenCodeExternalAgentAdapter.write_context` | `definition: ExternalAgentDefinition, package: ContextPackage` | `ContextTransferResult` | Reject external context writes until an audited OpenCode protocol exists. |
| [adapters/opencode.py](adapters/opencode.py#L198) | `OpenCodeExternalAgentAdapter._context_facade` | `None` | `OpenCodeContextFacade` | Return the optional facade capability needed for context reads. |
| [adapters/read_only.py](adapters/read_only.py#L54) | `ExternalAgentReadOnlyFacade.probe` | `definition: ExternalAgentDefinition` | `ExternalAgentProbe` | Inspect whether the remote runtime is reachable without dispatching. |
| [adapters/read_only.py](adapters/read_only.py#L67) | `ExternalAgentReadOnlyFacade.discover_sessions` | `definition: ExternalAgentDefinition, limit: int` | `tuple[RemoteSessionSummary, ...]` | List newest remote session summaries without creating or importing one. |
| [adapters/read_only.py](adapters/read_only.py#L96) | `UnavailableExternalAgentFacade.probe` | `definition: ExternalAgentDefinition` | `ExternalAgentProbe` | Report that no vendor transport facade has been installed. |
| [adapters/read_only.py](adapters/read_only.py#L108) | `UnavailableExternalAgentFacade.discover_sessions` | `definition: ExternalAgentDefinition, limit: int` | `tuple[RemoteSessionSummary, ...]` | Reject session discovery until a concrete vendor transport exists. |
| [adapters/read_only.py](adapters/read_only.py#L146) | `ReadOnlyExternalAgentAdapter._health` | `definition: ExternalAgentDefinition, adapter_kind: str` | `ExternalAgentHealth` | Normalize one facade probe into the Hub health shape. |
| [adapters/read_only.py](adapters/read_only.py#L167) | `ReadOnlyExternalAgentAdapter._sessions` | `definition: ExternalAgentDefinition, limit: int` | `tuple[ExternalAgentSession, ...]` | Read and normalize bounded vendor sessions into Hub session records. |
| [adapters/workbuddy.py](adapters/workbuddy.py#L21) | `WorkBuddyExternalAgentAdapter.kind` | `None` | `str` | Return the External Agent Hub kind reserved for WorkBuddy. |
| [adapters/workbuddy.py](adapters/workbuddy.py#L40) | `WorkBuddyExternalAgentAdapter.health` | `definition: ExternalAgentDefinition` | `ExternalAgentHealth` | Probe WorkBuddy without creating or steering a remote task. |
| [adapters/workbuddy.py](adapters/workbuddy.py#L51) | `WorkBuddyExternalAgentAdapter.discover_capabilities` | `definition: ExternalAgentDefinition` | `tuple[ExternalAgentCapability, ...]` | Return known WorkBuddy operations without starting a task. |
| [adapters/workbuddy.py](adapters/workbuddy.py#L65) | `WorkBuddyExternalAgentAdapter.discover_sessions` | `definition: ExternalAgentDefinition, limit: int` | `tuple[ExternalAgentSession, ...]` | List WorkBuddy conversation summaries without resuming one. |
| [adapters/workbuddy.py](adapters/workbuddy.py#L77) | `WorkBuddyExternalAgentAdapter.list_contexts` | `definition: ExternalAgentDefinition, cursor: str \| None, limit: int` | `ContextPage` | List WorkBuddy contexts through an explicitly installed read facade. |
| [adapters/workbuddy.py](adapters/workbuddy.py#L111) | `WorkBuddyExternalAgentAdapter.read_context` | `definition: ExternalAgentDefinition, context_id: str` | `ContextPackage` | Read one WorkBuddy context package through an installed read facade. |
| [adapters/workbuddy.py](adapters/workbuddy.py#L142) | `WorkBuddyExternalAgentAdapter.write_context` | `definition: ExternalAgentDefinition, package: ContextPackage` | `ContextTransferResult` | Reject writes because no audited WorkBuddy write protocol exists. |
| [codex_app_server.py](codex_app_server.py#L45) | `CodexAppServerTransport.request` | `method: str, params: Mapping[str, object]` | `Mapping[str, object]` | Send one request and return its result object. |
| [codex_app_server.py](codex_app_server.py#L61) | `CodexAppServerTransport.notify` | `method: str, params: Mapping[str, object]` | `None` | Send one JSON-RPC notification without waiting for a response. |
| [codex_app_server.py](codex_app_server.py#L73) | `CodexAppServerTransport.close` | `None` | `None` | Release the connection and any process owned by this transport. |
| [codex_app_server.py](codex_app_server.py#L96) | `CodexAppServerStdioTransport.request` | `method: str, params: Mapping[str, object]` | `Mapping[str, object]` | Send a JSON-RPC request over the owned JSONL process streams. |
| [codex_app_server.py](codex_app_server.py#L116) | `CodexAppServerStdioTransport.notify` | `method: str, params: Mapping[str, object]` | `None` | Send one JSON-RPC notification over the owned process streams. |
| [codex_app_server.py](codex_app_server.py#L131) | `CodexAppServerStdioTransport.close` | `None` | `None` | Terminate the child process if this transport started one. |
| [codex_app_server.py](codex_app_server.py#L148) | `CodexAppServerStdioTransport._ensure_process` | `None` | `subprocess.Popen[str]` | Start the fixed local App Server command only once. |
| [codex_app_server.py](codex_app_server.py#L172) | `CodexAppServerStdioTransport._write` | `process: subprocess.Popen[str], message: Mapping[str, object]` | `None` | Write one bounded JSONL message to the App Server stdin. |
| [codex_app_server.py](codex_app_server.py#L193) | `CodexAppServerStdioTransport._read_response` | `process: subprocess.Popen[str], request_id: int` | `Mapping[str, object]` | Read JSONL notifications until the matching response arrives. |
| [codex_app_server.py](codex_app_server.py#L245) | `CodexAppServerAdapter.kind` | `None` | `str` | Return the Hub kind owned by this adapter. |
| [codex_app_server.py](codex_app_server.py#L253) | `CodexAppServerAdapter.health` | `definition: ExternalAgentDefinition` | `ExternalAgentHealth` | Verify the required App Server handshake without starting a thread. |
| [codex_app_server.py](codex_app_server.py#L269) | `CodexAppServerAdapter.discover_capabilities` | `definition: ExternalAgentDefinition` | `tuple[ExternalAgentCapability, ...]` | Return supported read-only Codex inspection capabilities. |
| [codex_app_server.py](codex_app_server.py#L288) | `CodexAppServerAdapter.discover_sessions` | `definition: ExternalAgentDefinition, limit: int` | `tuple[ExternalAgentSession, ...]` | List bounded Codex threads without resuming or importing them. |
| [codex_app_server.py](codex_app_server.py#L312) | `CodexAppServerAdapter.list_contexts` | `definition: ExternalAgentDefinition, cursor: str \| None, limit: int` | `ContextPage` | List persisted Codex threads as readable context descriptors. |
| [codex_app_server.py](codex_app_server.py#L346) | `CodexAppServerAdapter.read_context` | `definition: ExternalAgentDefinition, context_id: str` | `ContextPackage` | Read one stored Codex thread without resuming it. |
| [codex_app_server.py](codex_app_server.py#L377) | `CodexAppServerAdapter.write_context` | `definition: ExternalAgentDefinition, package: ContextPackage` | `ContextTransferResult` | Reject context import because Codex has no audited restore protocol. |
| [codex_app_server.py](codex_app_server.py#L406) | `CodexAppServerAdapter._handshake` | `definition: ExternalAgentDefinition` | `None` | Open, initialize, and close one read-only protocol connection. |
| [codex_app_server.py](codex_app_server.py#L424) | `CodexAppServerAdapter._open` | `definition: ExternalAgentDefinition` | `CodexAppServerTransport` | Validate local stdio selection and create one inspection transport. |
| [codex_app_server.py](codex_app_server.py#L440) | `CodexAppServerAdapter._initialize` | `transport: CodexAppServerTransport` | `None` | Perform Codex App Server's required initialize notification pair. |
| [codex_app_server.py](codex_app_server.py#L462) | `_json_value` | `line: str` | `object` | Decode one JSONL value while keeping untyped JSON at the boundary. |
| [codex_app_server.py](codex_app_server.py#L480) | `_object_mapping` | `value: object` | `Mapping[str, object] \| None` | Return a JSON object as a read-only mapping when its keys are strings. |
| [codex_app_server.py](codex_app_server.py#L494) | `_sessions` | `agent_id: str, result: Mapping[str, object], limit: int` | `tuple[ExternalAgentSession, ...]` | Project a bounded App Server thread-list response into Hub sessions. |
| [codex_app_server.py](codex_app_server.py#L531) | `_contexts` | `agent_id: str, result: Mapping[str, object], limit: int` | `ContextPage` | Project one Codex thread-list response into context descriptors. |
| [codex_app_server.py](codex_app_server.py#L560) | `_context_package` | `agent_id: str, context_id: str, result: Mapping[str, object]` | `ContextPackage` | Extract ordered text messages from one ``thread/read`` response. |
| [codex_app_server.py](codex_app_server.py#L589) | `_codex_message` | `value: object, sequence: int` | `ContextMessage \| None` | Normalize a text-bearing Codex item without treating tools as messages. |
| [codex_app_server.py](codex_app_server.py#L612) | `_content_text` | `value: object` | `str` | Join supported textual content parts from a Codex item. |
| [codex_app_server.py](codex_app_server.py#L628) | `_text` | `value: object` | `str` | Return a string JSON field or an empty fallback. |
| [codex_app_server.py](codex_app_server.py#L640) | `_timestamp` | `value: object` | `int \| None` | Return a non-boolean integer JSON timestamp when present. |
| [context_codec.py](context_codec.py#L10) | `parse_context_package` | `payload: object` | `ContextPackage` | Decode one strict JSON-safe payload into a portable context package. |
| [context_codec.py](context_codec.py#L58) | `_message` | `payload: object` | `ContextMessage` | Decode one strict context record from an untrusted JSON value. |
| [context_codec.py](context_codec.py#L104) | `_tool` | `payload: object` | `ContextToolCall` | Decode one non-executable historical tool record. |
| [context_exchange.py](context_exchange.py#L50) | `SessionContextExchangeService.export_page` | `session_id: str, agent_name: str, before: int \| None, limit: int` | `tuple[ContextPackage, int \| None, bool]` | Export one durable context page without reading the full transcript. |
| [context_exchange.py](context_exchange.py#L95) | `SessionContextExchangeService.append_package` | `session_id: str, agent_name: str, package: ContextPackage` | `ContextTransferResult` | Append portable historical records to one idle Session Agent. |
| [context_exchange.py](context_exchange.py#L167) | `SessionContextExchangeService._message` | `raw: Mapping[object, object]` | `ContextMessage` | Convert one console message card into a portable record. |
| [context_exchange.py](context_exchange.py#L196) | `SessionContextExchangeService._context_path` | `session_id: str, agent_name: str` | `Path` | Return the durable pointer path for one valid Session Agent. |
| [context_exchange.py](context_exchange.py#L209) | `SessionContextExchangeService._redact` | `value: str` | `str` | Remove credential-like substrings from text copied across products. |
| [context_exchange.py](context_exchange.py#L221) | `SessionContextExchangeService._optional_int` | `value: object` | `int \| None` | Return a non-boolean integer cursor when the value is valid. |
| [discovery.py](discovery.py#L51) | `ExternalAgentProcessDiscovery.discover` | `None` | `tuple[ExternalAgentCandidate, ...]` | Return known local Agent processes in ascending process-id order. |
| [discovery.py](discovery.py#L69) | `ExternalAgentProcessDiscovery._read_candidate` | `process_path: Path` | `ExternalAgentCandidate \| None` | Project one readable procfs entry into a known-product candidate. |
| [discovery.py](discovery.py#L108) | `_process_sort_key` | `path: Path` | `int` | Return a deterministic numeric sort key for a procfs directory. |
| [discovery.py](discovery.py#L120) | `_safe_command` | `arguments: tuple[bytes, ...], limit: int` | `str` | Build a bounded command summary while avoiding environment inspection. |
| [discovery.py](discovery.py#L149) | `_working_directory` | `process_path: Path` | `str` | Read one process working directory without failing the whole scan. |
| [service.py](service.py#L41) | `ExternalAgentHubService.discover_local_processes` | `None` | `tuple[ExternalAgentCandidate, ...]` | Find currently running known Agent processes without attaching. |
| [service.py](service.py#L50) | `ExternalAgentHubService.list` | `None` | `tuple[ExternalAgentDefinition, ...]` | Return all configured external Agent definitions. |
| [service.py](service.py#L58) | `ExternalAgentHubService.get` | `agent_id: str` | `ExternalAgentDefinition` | Return one configured definition. |
| [service.py](service.py#L75) | `ExternalAgentHubService.create` | `definition: ExternalAgentDefinition` | `ExternalAgentDefinition` | Validate and persist a new external Agent definition. |
| [service.py](service.py#L92) | `ExternalAgentHubService.replace` | `agent_id: str, definition: ExternalAgentDefinition` | `ExternalAgentDefinition` | Replace one definition while preserving its stable identifier. |
| [service.py](service.py#L113) | `ExternalAgentHubService.remove` | `agent_id: str` | `None` | Delete one idle definition without deleting connector credentials. |
| [service.py](service.py#L128) | `ExternalAgentHubService.health` | `agent_id: str` | `ExternalAgentHealth` | Return a non-executing protocol health observation. |
| [service.py](service.py#L142) | `ExternalAgentHubService.capabilities` | `agent_id: str` | `tuple[ExternalAgentCapability, ...]` | Return declared capabilities without dispatching remote work. |
| [service.py](service.py#L156) | `ExternalAgentHubService.sessions` | `agent_id: str, limit: int` | `tuple[ExternalAgentSession, ...]` | Return bounded external session summaries without importing them. |
| [service.py](service.py#L174) | `ExternalAgentHubService.contexts` | `agent_id: str, cursor: str \| None, limit: int` | `ContextPage` | Return one bounded external context descriptor page. |
| [service.py](service.py#L194) | `ExternalAgentHubService.read_context` | `agent_id: str, context_id: str` | `ContextPackage` | Read one selected external context into a portable package. |
| [service.py](service.py#L213) | `ExternalAgentHubService.write_context` | `agent_id: str, package: ContextPackage` | `ContextTransferResult` | Write one portable package through an audited external adapter. |
| [service.py](service.py#L229) | `ExternalAgentHubService._validate` | `definition: ExternalAgentDefinition` | `None` | Validate bounded public configuration before persistence. |
| [store.py](store.py#L28) | `ExternalAgentHubStore.list` | `None` | `tuple[ExternalAgentDefinition, ...]` | Return all definitions in durable document order. |
| [store.py](store.py#L37) | `ExternalAgentHubStore.get` | `agent_id: str` | `ExternalAgentDefinition \| None` | Find one definition by stable identifier. |
| [store.py](store.py#L48) | `ExternalAgentHubStore.put` | `definition: ExternalAgentDefinition` | `ExternalAgentDefinition` | Atomically create or replace one external Agent definition. |
| [store.py](store.py#L63) | `ExternalAgentHubStore.remove` | `agent_id: str` | `bool` | Atomically remove one definition without touching connectors. |
| [store.py](store.py#L80) | `ExternalAgentHubStore._read` | `None` | `tuple[ExternalAgentDefinition, ...]` | Decode the complete persisted definition document. |
| [store.py](store.py#L98) | `_definition` | `value: object` | `ExternalAgentDefinition` | Decode a JSON object into one typed definition. |
| [store.py](store.py#L129) | `_adapter_kind` | `value: object` | `ExternalAgentAdapterKind` | Validate one persisted adapter kind. |
| [store.py](store.py#L146) | `_text` | `value: object` | `str` | Validate an optional bounded non-secret text field. |
| [store.py](store.py#L163) | `_json` | `definition: ExternalAgentDefinition` | `dict[str, object]` | Serialize one typed definition without connector secrets. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [adapter.py](adapter.py#L12) | `ExternalAgentAdapterFailure` | `None` | `RuntimeError` | Raised when a configured adapter cannot complete a supported operation. |
| [adapter.py](adapter.py#L16) | `ExternalAgentAdapter` | `None` | `Protocol` | Typed protocol contract for one external Agent product integration. |
| [adapter.py](adapter.py#L127) | `ExternalAgentAdapterRegistry` | `adapters: dict[ExternalAgentAdapterKind, ExternalAgentAdapter]` | `object` | Process-local registry of protocol adapters owned by Angelus. |
| [adapters/claude_sdk.py](adapters/claude_sdk.py#L28) | `ClaudeSdkContextUnsupportedError` | `None` | `ExternalAgentAdapterFailure` | Raised when callers request Claude context operations unsupported by its SDK. |
| [adapters/claude_sdk.py](adapters/claude_sdk.py#L38) | `ClaudeSdkAvailability` | `available: bool, message: str` | `object` | Non-secret local availability result for the optional Claude SDK. |
| [adapters/claude_sdk.py](adapters/claude_sdk.py#L51) | `ClaudeSdkSessionRecord` | `session_id: str, title: str, status: str, updated_at: int \| None, project_path: str` | `object` | Vendor-neutral values extracted from one Claude SDK session record. |
| [adapters/claude_sdk.py](adapters/claude_sdk.py#L69) | `ClaudeSdkSessionDiscovery` | `None` | `Protocol` | Minimal injectable boundary around Claude SDK session inspection. |
| [adapters/claude_sdk.py](adapters/claude_sdk.py#L90) | `LocalClaudeSdkSessionDiscovery` | `None` | `object` | Lazy facade over the optional local ``claude_agent_sdk`` package. |
| [adapters/claude_sdk.py](adapters/claude_sdk.py#L128) | `ClaudeSdkAdapter` | `discovery: ClaudeSdkSessionDiscovery \| None` | `object` | Expose Claude SDK's installed local session inspection through Hub. |
| [adapters/coze.py](adapters/coze.py#L14) | `CozeExternalAgentAdapter` | `facade: ExternalAgentReadOnlyFacade` | `ReadOnlyExternalAgentAdapter` | Normalize Coze discovery through an injected non-mutating facade. |
| [adapters/opencode.py](adapters/opencode.py#L19) | `OpenCodeContextFacade` | `None` | `Protocol` | Transport operations required for OpenCode context inspection. |
| [adapters/opencode.py](adapters/opencode.py#L62) | `OpenCodeExternalAgentAdapter` | `facade: ExternalAgentReadOnlyFacade` | `ReadOnlyExternalAgentAdapter` | Normalize OpenCode Server discovery through an injected HTTP facade. |
| [adapters/read_only.py](adapters/read_only.py#L11) | `ExternalAgentFacadeError` | `None` | `RuntimeError` | A user-safe failure returned by an injected read-only transport facade. |
| [adapters/read_only.py](adapters/read_only.py#L16) | `ExternalAgentProbe` | `available: bool, message: str` | `object` | One non-mutating transport availability observation. |
| [adapters/read_only.py](adapters/read_only.py#L29) | `RemoteSessionSummary` | `external_id: str, title: str, status: str, updated_at: int \| None, project_path: str` | `object` | Vendor-neutral data needed to project one external session summary. |
| [adapters/read_only.py](adapters/read_only.py#L47) | `ExternalAgentReadOnlyFacade` | `None` | `Protocol` | Injected HTTP, CLI, or SDK facade used by a read-only adapter. |
| [adapters/read_only.py](adapters/read_only.py#L87) | `UnavailableExternalAgentFacade` | `adapter_name: str` | `object` | Explicit inert facade used until a vendor transport is configured. |
| [adapters/read_only.py](adapters/read_only.py#L125) | `ReadOnlyExternalAgentAdapter` | `facade: ExternalAgentReadOnlyFacade` | `object` | Reusable normalization logic for vendor adapters using a typed facade. |
| [adapters/workbuddy.py](adapters/workbuddy.py#L17) | `WorkBuddyExternalAgentAdapter` | `facade: ExternalAgentReadOnlyFacade` | `ReadOnlyExternalAgentAdapter` | Normalize WorkBuddy discovery through an injected CLI or HTTP facade. |
| [codex_app_server.py](codex_app_server.py#L33) | `CodexAppServerError` | `None` | `RuntimeError` | Raised when the constrained Codex App Server protocol exchange fails. |
| [codex_app_server.py](codex_app_server.py#L37) | `CodexAppServerTransport` | `None` | `object` | One synchronous JSON-RPC connection to a Codex App Server process. |
| [codex_app_server.py](codex_app_server.py#L83) | `CodexAppServerStdioTransport` | `command: tuple[str, ...], timeout_seconds: float, _process: subprocess.Popen[str] \| None, _next_request_id: int` | `CodexAppServerTransport` | JSONL stdio transport which owns a locally spawned Codex App Server. |
| [codex_app_server.py](codex_app_server.py#L234) | `CodexAppServerAdapter` | `transport_factory: CodexAppServerTransportFactory` | `object` | Read-only External Agent Hub adapter for a local Codex App Server. |
| [context_exchange.py](context_exchange.py#L24) | `ContextExchangeError` | `None` | `RuntimeError` | Raised when a bounded context exchange cannot safely proceed. |
| [context_exchange.py](context_exchange.py#L28) | `SessionContextExchangeService` | `core: 'AngelusCore'` | `object` | Export and append portable packages through Session-owned contexts. |
| [discovery.py](discovery.py#L12) | `_ProcessPattern` | `executable_names: tuple[str, ...], adapter_kind: ExternalAgentAdapterKind, product_name: str, endpoint: str` | `object` | One safe executable-name mapping used by local process discovery. |
| [discovery.py](discovery.py#L35) | `ExternalAgentProcessDiscovery` | `proc_root: Path, command_limit: int` | `object` | Discover known local Agent processes without attaching or signaling them. |
| [models.py](models.py#L23) | `ContextToolCall` | `name: str, arguments_json: str, result: str` | `object` | One non-executable historical tool-call record in a context package. |
| [models.py](models.py#L38) | `ContextMessage` | `sequence: int, role: ContextRole, content: str, reasoning: str, tool_calls: tuple[ContextToolCall, ...], created_at: int \| None` | `object` | One ordered, credential-free conversation record. |
| [models.py](models.py#L59) | `ExternalAgentContext` | `agent_id: str, external_id: str, title: str, updated_at: int \| None, message_count: int \| None` | `object` | A remote context descriptor that may be read through an adapter. |
| [models.py](models.py#L78) | `ContextPage` | `items: tuple[ExternalAgentContext, ...], next_cursor: str \| None, has_more: bool` | `object` | One bounded page of external context descriptors. |
| [models.py](models.py#L93) | `ContextPackage` | `format_version: int, source: str, source_session_id: str, source_agent: str, messages: tuple[ContextMessage, ...], summary: str, redactions: tuple[str, ...]` | `object` | Portable, redacted context exchange envelope. |
| [models.py](models.py#L116) | `ContextTransferResult` | `direction: ContextTransferDirection, agent_id: str, context_id: str, accepted_messages: int, rejected_messages: int, detail: str` | `object` | Auditable result of a context read or write operation. |
| [models.py](models.py#L137) | `ExternalAgentDefinition` | `id: str, title: str, adapter_kind: ExternalAgentAdapterKind, endpoint: str, connector_id: str, enabled: bool, description: str` | `object` | One durable, credential-free declaration of an external Agent runtime. |
| [models.py](models.py#L160) | `ExternalAgentHealth` | `agent_id: str, adapter_kind: ExternalAgentAdapterKind, status: ExternalAgentHealthStatus, message: str` | `object` | One non-secret health projection returned by a Hub adapter. |
| [models.py](models.py#L177) | `ExternalAgentCapability` | `id: str, title: str, description: str, invocation_mode: Literal['tool', 'run']` | `object` | A future-discoverable operation advertised by an external Agent. |
| [models.py](models.py#L195) | `ExternalAgentSession` | `agent_id: str, external_id: str, title: str, status: str, updated_at: int \| None, project_path: str` | `object` | A read-only summary of a session held by an external Agent runtime. |
| [models.py](models.py#L218) | `ExternalAgentCandidate` | `candidate_id: str, adapter_kind: ExternalAgentAdapterKind, title: str, process_id: int, command: str, working_directory: str, endpoint: str, attachable: bool, detail: str` | `object` | One locally observed external Agent process that requires user approval. |
| [service.py](service.py#L17) | `ExternalAgentHubService` | `store: ExternalAgentHubStore, adapters: ExternalAgentAdapterRegistry, process_discovery: ExternalAgentProcessDiscovery \| None` | `object` | Validate and project phase-one external Agent configuration state. |
| [store.py](store.py#L13) | `ExternalAgentHubStore` | `state_root: Path` | `object` | Own durable credential-free external Agent definitions. |

<!-- END GENERATED SYMBOL MAP -->
