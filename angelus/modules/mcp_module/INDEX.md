# mcp_module/ — Managed MCP INDEX

| File | Responsibility |
|---|---|
| `store.py` | Secret-separated server catalog and Session role/tool bindings. |
| `bridge.py` | Official MCP SDK connections, discovery, invocation and cancellation. |
| `service.py` | Process lifecycle, cache invalidation and dynamic ToolRegistry provider. |
| `__init__.py` | Public exports. |

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [bridge.py](bridge.py#L35) | `_safe_name_part` | `value: str` | `str` | Implement `_safe_name_part`. |
| [bridge.py](bridge.py#L40) | `_model_dump` | `value: Any` | `Any` | Return SDK Pydantic models as JSON-compatible values. |
| [bridge.py](bridge.py#L61) | `MCPServer.from_record` | `record: MCPServerRecord, secrets: MCPSecrets` | `'MCPServer'` | Validate one decrypted server record into a connectable definition. |
| [bridge.py](bridge.py#L177) | `MCPToolBridge._approval_agent` | `server: str` | `str` | Return the sole active caller for a server, or coordinator fallback. |
| [bridge.py](bridge.py#L183) | `MCPToolBridge._emit` | `kind: str, server: str, data: Any` | `None` | Forward credential-free MCP runtime metadata to the host Trace. |
| [bridge.py](bridge.py#L191) | `MCPToolBridge._run_loop` | `None` | `None` | Own the asyncio loop used by all run-scoped MCP transports. |
| [bridge.py](bridge.py#L196) | `MCPToolBridge.start` | `None` | `list[Tool]` | Discover remote MCP tools and return native synchronous wrappers. |
| [bridge.py](bridge.py#L209) | `MCPToolBridge.tools_for` | `agent: str, allowed: set[str] \| None` | `list[Tool]` | Create wrappers attributed to one Agent and optional allowlist. |
| [bridge.py](bridge.py#L228) | `MCPToolBridge.close` | `None` | `None` | Close every persistent transport and stop the owning event loop. |
| [bridge.py](bridge.py#L246) | `MCPToolBridge.cancel_agent` | `agent: str` | `int` | Cancel in-flight MCP calls attributed to one Agent. |
| [bridge.py](bridge.py#L261) | `MCPToolBridge._handler` | `server_name: str, tool_name: str, agent: str` | `Any` | Build a synchronous tool handler attributed to ``agent``. |
| [bridge.py](bridge.py#L279) | `MCPToolBridge._open_client` | `server: MCPServer` | `Any` | Open and retain one SDK client inside the run cleanup stack. |
| [bridge.py](bridge.py#L365) | `MCPToolBridge._ensure_client` | `server: MCPServer` | `Any` | Return a live client, asking the stack-owning task to reconnect. |
| [bridge.py](bridge.py#L378) | `MCPToolBridge._own_connections` | `None` | `None` | Open and close task-bound SDK transports in the same asyncio task. |
| [bridge.py](bridge.py#L420) | `MCPToolBridge._discover_all` | `None` | `None` | Open each configured server once and replace the tool cache. |
| [bridge.py](bridge.py#L427) | `MCPToolBridge._discover_tools` | `server: MCPServer, client: Any` | `None` | Page through one live client's tools into the public-name cache. |
| [bridge.py](bridge.py#L461) | `MCPToolBridge.capability_snapshot` | `None` | `MCPCapabilities` | Discover tools, resources, templates, and prompts on live clients. |
| [bridge.py](bridge.py#L469) | `MCPToolBridge.read_resource` | `server_name: str, uri: str` | `Any` | Read one MCP resource through the persistent server connection. |
| [bridge.py](bridge.py#L473) | `MCPToolBridge.subscribe_resource` | `server_name: str, uri: str` | `Any` | Subscribe to one resource; later notifications enter Trace. |
| [bridge.py](bridge.py#L477) | `MCPToolBridge.get_prompt` | `server_name: str, name: str, arguments: dict[str, str] \| None` | `Any` | Get one MCP prompt using the persistent server connection. |
| [bridge.py](bridge.py#L481) | `MCPToolBridge.complete` | `server_name: str, reference: Any, argument: dict[str, str], context_arguments: dict[str, str] \| None` | `Any` | Request MCP completion for a prompt or resource template reference. |
| [bridge.py](bridge.py#L488) | `MCPToolBridge._submit_client_method` | `server_name: str, method: str, *args: Any` | `Any` | Run one non-tool MCP capability call on the owning event loop. |
| [bridge.py](bridge.py#L495) | `MCPToolBridge._client_method` | `server_name: str, method: str, *args: Any` | `Any` | Invoke a named SDK client method without automatic replay. |
| [bridge.py](bridge.py#L514) | `MCPToolBridge._capability_snapshot_async` | `None` | `MCPCapabilities` | Collect JSON-safe full discovery data from every live server. |
| [bridge.py](bridge.py#L556) | `MCPToolBridge._call` | `server_name: str, tool_name: str, arguments: dict[str, Any], agent: str` | `dict[str, Any]` | Invoke one tool once, discarding a stale client after failure. |
| [bridge.py](bridge.py#L600) | `create_mcp_tools` | `servers: list[dict[str, Any]], approval_handler: Any \| None, sampling_handler: Any \| None, event_handler: Any \| None` | `tuple[MCPToolBridge, list[Tool]]` | Connect configured servers and expose remote tools natively. |
| [records.py](records.py#L32) | `MCPProbe.from_snapshot` | `value: JsonObject` | `'MCPProbe'` | Decode a probe payload written by an older store version. |
| [records.py](records.py#L56) | `MCPCapabilities.from_snapshot` | `value: JsonObject` | `'MCPCapabilities'` | Decode the SDK discovery snapshot produced by the bridge. |
| [records.py](records.py#L71) | `_json_objects` | `value: object, field: str` | `tuple[JsonObject, ...]` | Return an array of JSON objects, rejecting non-object entries. |
| [records.py](records.py#L135) | `MCPBinding.from_mapping` | `value: object` | `'MCPBinding'` | Decode one HTTP-supplied binding, rejecting malformed members. |
| [service.py](service.py#L32) | `_resolved_fingerprint` | `servers: Sequence[MCPResolvedServer]` | `str` | Hash the non-secret identity of the resolved servers. |
| [service.py](service.py#L69) | `MCPService.list_servers` | `None` | `tuple[MCPPublicServer, ...]` | Return every configured server without credentials. |
| [service.py](service.py#L73) | `MCPService.create_server` | `payload: Mapping[str, JsonValue]` | `MCPPublicServer` | Create one server and invalidate cached bridges. |
| [service.py](service.py#L78) | `MCPService.replace_server` | `server_id: str, payload: Mapping[str, JsonValue]` | `MCPPublicServer` | Replace one server and invalidate cached bridges. |
| [service.py](service.py#L85) | `MCPService.remove_server` | `server_id: str` | `None` | Delete one server and invalidate cached bridges. |
| [service.py](service.py#L90) | `MCPService.bindings` | `session_id: str` | `tuple[MCPBinding, ...]` | Return one Session's server bindings. |
| [service.py](service.py#L94) | `MCPService.fingerprint` | `session_id: str, role: str` | `str` | Return a secret-free identity that forces future Agent rebuilding. |
| [service.py](service.py#L102) | `MCPService.replace_bindings` | `session_id: str, bindings: Sequence[MCPBinding]` | `tuple[MCPBinding, ...]` | Replace one Session's binding set and invalidate its bridge. |
| [service.py](service.py#L109) | `MCPService.probe` | `server_id: str` | `MCPPublicServer` | Connect once, persist the discovery snapshot, and disconnect. |
| [service.py](service.py#L135) | `MCPService.tools` | `session: 'Session', role: str, agent_name: str` | `list[Tool]` | Return the Session's MCP tools allowed for one Agent. |
| [service.py](service.py#L203) | `MCPService.invalidate` | `session_id: str \| None` | `None` | Close cached bridges for one Session, or for every Session. |
| [service.py](service.py#L214) | `MCPService.close` | `None` | `None` | Close every cached bridge. |
| [service.py](service.py#L225) | `MCPToolProvider.materialize` | `session: 'Session', policy: ToolPolicy, role: str, agent_name: str \| None` | `list[Tool]` | Return the MCP tools bound to this Session and Agent. |
| [service.py](service.py#L240) | `mcp_tool_registration` | `service: MCPService` | `ToolProviderRegistration` | Register the Session-scoped MCP tool provider. |
| [store.py](store.py#L62) | `MCPStore.list` | `None` | `tuple[MCPPublicServer, ...]` | Return every server without credentials or header/env values. |
| [store.py](store.py#L68) | `MCPStore.internal` | `None` | `tuple[MCPServerWithSecrets, ...]` | Return every server merged with its decrypted secrets. |
| [store.py](store.py#L72) | `MCPStore.create` | `payload: Mapping[str, JsonValue]` | `MCPPublicServer` | Create one server and persist its secrets separately. |
| [store.py](store.py#L87) | `MCPStore.replace` | `server_id: str, payload: Mapping[str, JsonValue]` | `MCPPublicServer` | Replace one server, retaining omitted credentials and header values. |
| [store.py](store.py#L126) | `MCPStore.remove` | `server_id: str` | `None` | Delete one server, its secrets, and every Session binding to it. |
| [store.py](store.py#L144) | `MCPStore.set_probe` | `server_id: str, probe: MCPProbe, capabilities: MCPCapabilities` | `MCPPublicServer` | Persist the latest connection probe and discovery snapshot. |
| [store.py](store.py#L163) | `MCPStore.get_internal` | `server_id: str` | `MCPServerWithSecrets` | Return one server with its decrypted secrets. |
| [store.py](store.py#L168) | `MCPStore.update_credentials` | `server_id: str, bearer_token: str \| None, oauth_client_secret: str \| None, oauth_token: str \| None, oauth_refresh_token: str \| None, oauth_expires_at: float \| None` | `MCPPublicServer` | Replace selected private credential fields without exposing them. |
| [store.py](store.py#L218) | `MCPStore.public` | `item: MCPServerWithSecrets` | `MCPPublicServer` | Project one stored server for API consumers without secret values. |
| [store.py](store.py#L254) | `MCPStore.read_bindings` | `session_id: str` | `tuple[MCPBinding, ...]` | Return one Session's authorized servers, or none yet. |
| [store.py](store.py#L268) | `MCPStore.write_bindings` | `session_id: str, bindings: Sequence[MCPBinding]` | `tuple[MCPBinding, ...]` | Validate and persist one Session's complete binding set. |
| [store.py](store.py#L293) | `MCPStore.resolve` | `session_id: str, project_root: Path, role: str` | `tuple[MCPResolvedServer, ...]` | Return the servers a Session may use for one Agent role. |
| [store.py](store.py#L317) | `MCPStore.read_pending` | `None` | `MCPOAuthPendingDocument` | Return in-flight OAuth transactions, or an empty document. |
| [store.py](store.py#L330) | `MCPStore.write_pending` | `document: MCPOAuthPendingDocument` | `None` | Persist the complete in-flight OAuth transaction map. |
| [store.py](store.py#L345) | `MCPStore._records` | `None` | `tuple[MCPServerRecord, ...]` | Decode the catalog, migrating legacy entries before validation. |
| [store.py](store.py#L372) | `MCPStore._write` | `records: Sequence[MCPServerRecord]` | `None` | Publish the complete catalog generation. |
| [store.py](store.py#L378) | `MCPStore._secret` | `server_id: str` | `MCPSecrets` | Decode one server's secrets, defaulting a never-written document. |
| [store.py](store.py#L392) | `MCPStore._write_secret` | `server_id: str, value: MCPSecrets` | `None` | Persist one server's private credential document. |
| [store.py](store.py#L403) | `MCPStore._with_secrets` | `record: MCPServerRecord` | `MCPServerWithSecrets` | Merge one catalog entry with its private document. |
| [store.py](store.py#L407) | `MCPStore._binding_path` | `session_id: str` | `Path` | Return the binding document path for an already validated Session. |
| [store.py](store.py#L412) | `MCPStore._index` | `records: Sequence[MCPServerRecord], server_id: str` | `int` | Return the position of one server, raising ``KeyError`` if absent. |
| [store.py](store.py#L419) | `MCPStore._normalize` | `payload: Mapping[str, JsonValue], server_id: str` | `tuple[MCPServerRecord, MCPSecrets]` | Validate one submitted server definition into record plus secrets. |
| [store.py](store.py#L490) | `_require_object` | `value: JsonValue, where: str` | `JsonObject` | Return one decoded JSON object or fail with the document name. |
| [store.py](store.py#L497) | `_probe` | `value: JsonValue` | `MCPProbe` | Decode an optional stored probe payload. |
| [store.py](store.py#L514) | `_capabilities` | `value: JsonValue` | `MCPCapabilities` | Decode an optional discovery snapshot. |
| [store.py](store.py#L524) | `_migrate_record` | `raw: JsonObject` | `JsonObject` | Fill fields added after the first catalog generation wrote its entries. |
| [store.py](store.py#L544) | `_migrate_env` | `value: JsonValue` | `dict[str, str]` | Accept the legacy ``env`` list of host variable names. |
| [store.py](store.py#L557) | `new_oauth_transaction` | `server_id: str, verifier: str, redirect_uri: str` | `MCPOAuthTransaction` | Build one pending OAuth transaction stamped with the current time. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [bridge.py](bridge.py#L28) | `MCPToolError` | `None` | `RuntimeError` | Raised when MCP configuration, discovery, or invocation fails. |
| [bridge.py](bridge.py#L48) | `MCPServer` | `name: str, transport: str, command: str, args: tuple[str, ...], url: str, env: tuple[tuple[str, str], ...], cwd: str, headers: tuple[tuple[str, str], ...]` | `object` | One validated user-selected MCP server definition. |
| [bridge.py](bridge.py#L121) | `MCPToolBridge` | `servers: Sequence[MCPResolvedServer], approval_handler: Any \| None, sampling_handler: Any \| None, event_handler: Any \| None` | `object` | Keep one official SDK connection per server for the lifetime of a run. |
| [records.py](records.py#L24) | `MCPProbe` | `ok: bool, checked_at: float, error: str` | `object` | Outcome of the last connection probe for one server. |
| [records.py](records.py#L47) | `MCPCapabilities` | `tools: tuple[str, ...], resources: tuple[JsonObject, ...], resource_templates: tuple[JsonObject, ...], prompts: tuple[JsonObject, ...]` | `object` | Last discovered capability snapshot for one server. |
| [records.py](records.py#L84) | `MCPServerRecord` | `id: str, name: str, transport: str, command: str, args: tuple[str, ...], cwd: str, url: str, auth_type: str, oauth_authorize_url: str, oauth_token_url: str, oauth_client_id: str, oauth_scopes: str, oauth_expires_at: float, capabilities: MCPCapabilities, probe: MCPProbe, updated_at: float` | `object` | One catalog entry in ``settings/mcp-servers.json``. |
| [records.py](records.py#L106) | `MCPCatalog` | `servers: tuple[MCPServerRecord, ...], schema_version: int` | `object` | The complete ``settings/mcp-servers.json`` document. |
| [records.py](records.py#L114) | `MCPSecrets` | `bearer_token: str, oauth_client_secret: str, oauth_token: str, oauth_refresh_token: str, headers: dict[str, str], env: dict[str, str], schema_version: int` | `object` | The private ``secrets/mcp/<id>.json`` document. |
| [records.py](records.py#L127) | `MCPBinding` | `server_id: str, roles: tuple[str, ...], tools: tuple[str, ...]` | `object` | One Session's authorization for a server and role set. |
| [records.py](records.py#L160) | `MCPBindingsDocument` | `bindings: tuple[MCPBinding, ...], schema_version: int` | `object` | The complete ``sessions/<id>/mcp-bindings.json`` document. |
| [records.py](records.py#L168) | `MCPOAuthTransaction` | `server_id: str, verifier: str, redirect_uri: str, created_at: float` | `object` | One in-flight OAuth authorization keyed by its state value. |
| [records.py](records.py#L178) | `MCPOAuthPendingDocument` | `pending: dict[str, MCPOAuthTransaction], schema_version: int` | `object` | The complete ``secrets/mcp-oauth-pending.json`` document. |
| [records.py](records.py#L186) | `MCPPublicServer` | `id: str, name: str, transport: str, command: str, args: tuple[str, ...], cwd: str, url: str, auth_type: str, oauth_authorize_url: str, oauth_token_url: str, oauth_client_id: str, oauth_scopes: str, oauth_expires_at: float, capabilities: MCPCapabilities, probe: MCPProbe, updated_at: float, headers: tuple[str, ...], env: tuple[str, ...], has_bearer_token: bool, oauth_connected: bool, credentials_configured: bool` | `object` | Secret-free projection returned to the settings surface. |
| [records.py](records.py#L213) | `MCPServerWithSecrets` | `record: MCPServerRecord, secrets: MCPSecrets` | `object` | One catalog entry merged with its private credential document. |
| [records.py](records.py#L221) | `MCPResolvedServer` | `record: MCPServerRecord, secrets: MCPSecrets, tool_allowlist: tuple[str, ...], project_root: str` | `object` | One server merged with its decrypted secrets for a live Agent. |
| [service.py](service.py#L59) | `MCPService` | `core: 'AngelusCore'` | `object` | Own MCP bridges per Session role and expose their tools to Agents. |
| [service.py](service.py#L219) | `MCPToolProvider` | `service: MCPService` | `object` | Materialize MCP tools for one Agent within an Agent role. |
| [store.py](store.py#L48) | `MCPStore` | `state_root: Path` | `object` | Own the MCP catalog, secrets, bindings and pending OAuth transactions. |

<!-- END GENERATED SYMBOL MAP -->
