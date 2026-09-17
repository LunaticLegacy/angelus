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
| [bridge.py](bridge.py#L32) | `_safe_name_part` | `value: str` | `str` | Implement `_safe_name_part`. |
| [bridge.py](bridge.py#L37) | `_model_dump` | `value: Any` | `Any` | Return SDK Pydantic models as JSON-compatible values. |
| [bridge.py](bridge.py#L59) | `MCPServer.from_config` | `item: dict[str, Any]` | `'MCPServer'` | Validate one decrypted registry or compatibility server mapping. |
| [bridge.py](bridge.py#L162) | `MCPToolBridge._approval_agent` | `server: str` | `str` | Return the sole active caller for a server, or coordinator fallback. |
| [bridge.py](bridge.py#L168) | `MCPToolBridge._emit` | `kind: str, server: str, data: Any` | `None` | Forward credential-free MCP runtime metadata to the host Trace. |
| [bridge.py](bridge.py#L176) | `MCPToolBridge._run_loop` | `None` | `None` | Own the asyncio loop used by all run-scoped MCP transports. |
| [bridge.py](bridge.py#L181) | `MCPToolBridge.start` | `None` | `list[Tool]` | Discover remote MCP tools and return native synchronous wrappers. |
| [bridge.py](bridge.py#L194) | `MCPToolBridge.tools_for` | `agent: str, allowed: set[str] \| None` | `list[Tool]` | Create wrappers attributed to one Agent and optional allowlist. |
| [bridge.py](bridge.py#L213) | `MCPToolBridge.close` | `None` | `None` | Close every persistent transport and stop the owning event loop. |
| [bridge.py](bridge.py#L231) | `MCPToolBridge.cancel_agent` | `agent: str` | `int` | Cancel in-flight MCP calls attributed to one Agent. |
| [bridge.py](bridge.py#L246) | `MCPToolBridge._handler` | `server_name: str, tool_name: str, agent: str` | `Any` | Build a synchronous tool handler attributed to ``agent``. |
| [bridge.py](bridge.py#L264) | `MCPToolBridge._open_client` | `server: MCPServer` | `Any` | Open and retain one SDK client inside the run cleanup stack. |
| [bridge.py](bridge.py#L350) | `MCPToolBridge._ensure_client` | `server: MCPServer` | `Any` | Return a live client, asking the stack-owning task to reconnect. |
| [bridge.py](bridge.py#L363) | `MCPToolBridge._own_connections` | `None` | `None` | Open and close task-bound SDK transports in the same asyncio task. |
| [bridge.py](bridge.py#L405) | `MCPToolBridge._discover_all` | `None` | `None` | Open each configured server once and replace the tool cache. |
| [bridge.py](bridge.py#L412) | `MCPToolBridge._discover_tools` | `server: MCPServer, client: Any` | `None` | Page through one live client's tools into the public-name cache. |
| [bridge.py](bridge.py#L446) | `MCPToolBridge.capability_snapshot` | `None` | `dict[str, Any]` | Discover tools, resources, templates, and prompts on live clients. |
| [bridge.py](bridge.py#L454) | `MCPToolBridge.read_resource` | `server_name: str, uri: str` | `Any` | Read one MCP resource through the persistent server connection. |
| [bridge.py](bridge.py#L458) | `MCPToolBridge.subscribe_resource` | `server_name: str, uri: str` | `Any` | Subscribe to one resource; later notifications enter Trace. |
| [bridge.py](bridge.py#L462) | `MCPToolBridge.get_prompt` | `server_name: str, name: str, arguments: dict[str, str] \| None` | `Any` | Get one MCP prompt using the persistent server connection. |
| [bridge.py](bridge.py#L466) | `MCPToolBridge.complete` | `server_name: str, reference: Any, argument: dict[str, str], context_arguments: dict[str, str] \| None` | `Any` | Request MCP completion for a prompt or resource template reference. |
| [bridge.py](bridge.py#L473) | `MCPToolBridge._submit_client_method` | `server_name: str, method: str, *args: Any` | `Any` | Run one non-tool MCP capability call on the owning event loop. |
| [bridge.py](bridge.py#L480) | `MCPToolBridge._client_method` | `server_name: str, method: str, *args: Any` | `Any` | Invoke a named SDK client method without automatic replay. |
| [bridge.py](bridge.py#L489) | `MCPToolBridge._capability_snapshot_async` | `None` | `dict[str, Any]` | Collect JSON-safe full discovery data from every live server. |
| [bridge.py](bridge.py#L511) | `MCPToolBridge._call` | `server_name: str, tool_name: str, arguments: dict[str, Any], agent: str` | `dict[str, Any]` | Invoke one tool once, discarding a stale client after failure. |
| [bridge.py](bridge.py#L555) | `create_mcp_tools` | `servers: list[dict[str, Any]], approval_handler: Any \| None, sampling_handler: Any \| None, event_handler: Any \| None` | `tuple[MCPToolBridge, list[Tool]]` | Connect configured servers and expose remote tools natively. |
| [service.py](service.py#L23) | `MCPService.list_servers` | `None` | `Any` | Implement `MCPService.list_servers`. |
| [service.py](service.py#L24) | `MCPService.create_server` | `payload: Any` | `Any` | Implement `MCPService.create_server`. |
| [service.py](service.py#L25) | `MCPService.replace_server` | `server_id: Any, payload: Any` | `Any` | Implement `MCPService.replace_server`. |
| [service.py](service.py#L26) | `MCPService.remove_server` | `server_id: Any` | `Any` | Implement `MCPService.remove_server`. |
| [service.py](service.py#L27) | `MCPService.bindings` | `session_id: Any` | `Any` | Implement `MCPService.bindings`. |
| [service.py](service.py#L28) | `MCPService.fingerprint` | `session_id: str, role: str` | `str` | Return a secret-free identity that forces future Agent rebuilding. |
| [service.py](service.py#L34) | `MCPService.replace_bindings` | `session_id: Any, bindings: Any` | `Any` | Implement `MCPService.replace_bindings`. |
| [service.py](service.py#L35) | `MCPService.probe` | `server_id: str` | `dict[str, Any]` | Implement `MCPService.probe`. |
| [service.py](service.py#L43) | `MCPService.tools` | `session: Any, role: str, agent_name: str` | `list[Tool]` | Implement `MCPService.tools`. |
| [service.py](service.py#L69) | `MCPService.invalidate` | `session_id: str \| None` | `None` | Implement `MCPService.invalidate`. |
| [service.py](service.py#L73) | `MCPService.close` | `None` | `None` | Implement `MCPService.close`. |
| [service.py](service.py#L78) | `MCPToolProvider.materialize` | `session: Any, policy: ToolPolicy, role: str, agent_name: str \| None` | `list[Tool]` | Implement `MCPToolProvider.materialize`. |
| [service.py](service.py#L82) | `mcp_tool_registration` | `service: MCPService` | `ToolProviderRegistration` | Implement `mcp_tool_registration`. |
| [store.py](store.py#L23) | `MCPStore.list` | `None` | `tuple[dict[str, Any], ...]` | Implement `MCPStore.list`. |
| [store.py](store.py#L24) | `MCPStore.internal` | `None` | `list[dict[str, Any]]` | Implement `MCPStore.internal`. |
| [store.py](store.py#L26) | `MCPStore.create` | `payload: dict[str, Any]` | `dict[str, Any]` | Implement `MCPStore.create`. |
| [store.py](store.py#L33) | `MCPStore.replace` | `server_id: str, payload: dict[str, Any]` | `dict[str, Any]` | Implement `MCPStore.replace`. |
| [store.py](store.py#L45) | `MCPStore.remove` | `server_id: str` | `None` | Implement `MCPStore.remove`. |
| [store.py](store.py#L52) | `MCPStore.set_probe` | `server_id: str, probe: dict[str, Any], capabilities: dict[str, Any]` | `dict[str, Any]` | Implement `MCPStore.set_probe`. |
| [store.py](store.py#L56) | `MCPStore.get_internal` | `server_id: str` | `dict[str, Any]` | Implement `MCPStore.get_internal`. |
| [store.py](store.py#L59) | `MCPStore.update_credentials` | `server_id: str, **values: Any` | `dict[str, Any]` | Replace selected private OAuth fields without exposing them. |
| [store.py](store.py#L71) | `MCPStore.public` | `record: dict[str, Any]` | `dict[str, Any]` | Implement `MCPStore.public`. |
| [store.py](store.py#L77) | `MCPStore.read_bindings` | `session_id: str` | `list[dict[str, Any]]` | Implement `MCPStore.read_bindings`. |
| [store.py](store.py#L81) | `MCPStore.write_bindings` | `session_id: str, bindings: list[dict[str, Any]]` | `list[dict[str, Any]]` | Implement `MCPStore.write_bindings`. |
| [store.py](store.py#L89) | `MCPStore.resolve` | `session_id: str, project_root: Path, role: str` | `list[dict[str, Any]]` | Implement `MCPStore.resolve`. |
| [store.py](store.py#L98) | `MCPStore._records` | `None` | `list[dict[str, Any]]` | Implement `MCPStore._records`. |
| [store.py](store.py#L102) | `MCPStore._write` | `records: list[dict[str, Any]]` | `None` | Implement `MCPStore._write`. |
| [store.py](store.py#L103) | `MCPStore._write_secret` | `server_id: str, value: dict[str, Any]` | `None` | Implement `MCPStore._write_secret`. |
| [store.py](store.py#L107) | `MCPStore._with_secrets` | `record: dict[str, Any]` | `dict[str, Any]` | Implement `MCPStore._with_secrets`. |
| [store.py](store.py#L110) | `MCPStore._binding_path` | `session_id: str` | `Path` | Implement `MCPStore._binding_path`. |
| [store.py](store.py#L112) | `MCPStore._index` | `records: list[dict[str, Any]], server_id: str` | `int` | Implement `MCPStore._index`. |
| [store.py](store.py#L116) | `MCPStore._normalize` | `payload: dict[str, Any], server_id: str` | `tuple[dict[str, Any], dict[str, Any]]` | Implement `MCPStore._normalize`. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [bridge.py](bridge.py#L25) | `MCPToolError` | `None` | `RuntimeError` | Raised when MCP configuration, discovery, or invocation fails. |
| [bridge.py](bridge.py#L46) | `MCPServer` | `name: str, transport: str, command: str, args: tuple[str, ...], url: str, env: tuple[tuple[str, str], ...], cwd: str, headers: tuple[tuple[str, str], ...]` | `object` | One validated user-selected MCP server definition. |
| [bridge.py](bridge.py#L108) | `MCPToolBridge` | `servers: list[dict[str, Any]], approval_handler: Any \| None, sampling_handler: Any \| None, event_handler: Any \| None` | `object` | Keep one official SDK connection per server for the lifetime of a run. |
| [service.py](service.py#L20) | `MCPService` | `core: 'AngelusCore'` | `object` | Provide `MCPService` behavior. |
| [service.py](service.py#L76) | `MCPToolProvider` | `service: MCPService` | `object` | Provide `MCPToolProvider` behavior. |
| [store.py](store.py#L17) | `MCPStore` | `state_root: Path` | `object` | Provide `MCPStore` behavior. |

<!-- END GENERATED SYMBOL MAP -->
