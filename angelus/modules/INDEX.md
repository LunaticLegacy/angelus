# angelus/modules/ — Backend Domain INDEX

Each subdirectory has one ownership domain. Do not route around these modules
by storing mutable runtime state in an API adapter.

| Domain | Index | Responsibility |
|---|---|---|
| Session aggregate | [`session_module/INDEX.md`](session_module/INDEX.md) | Session registry, coordinator role, Agent/Swarm ownership. |
| Execution | [`execution_module/INDEX.md`](execution_module/INDEX.md) | Attempt lifecycle, journal, checkpoint, signal interruption evidence. |
| Application | [`application_module/INDEX.md`](application_module/INDEX.md) | Cross-domain Session, execution and settings use cases. |
| Settings | [`settings_module/INDEX.md`](settings_module/INDEX.md) | Atomic JSON and global/session future-run profiles. |
| Connector | [`connector_module/INDEX.md`](connector_module/INDEX.md) | Provider discovery and secret-separated connector persistence. |
| Workspace | [`workspace_module/INDEX.md`](workspace_module/INDEX.md) | Durable Session metadata catalog and legacy import marker. |
| Conversation | [`conversation_module/INDEX.md`](conversation_module/INDEX.md) | Legacy transcript read/delete bridge during migration. |
| Swarm adapter | [`swarm_module/INDEX.md`](swarm_module/INDEX.md) | Session-local execution boundary; no global swarm registry. |
| Plugins | [`plugin_module/INDEX.md`](plugin_module/INDEX.md) | Controlled global package discovery, typed settings, and ToolRegistry-backed loading. |
| Image attachments | [`attachment_module/INDEX.md`](attachment_module/INDEX.md) | Session-owned immutable image blobs, validated metadata, confined project import and provider-neutral byte resolution. |
| Session console | [`console_module/INDEX.md`](console_module/INDEX.md) | Persisted task-plan/topology blueprints and Session projections. |
| Run graph | [`run_graph_module/INDEX.md`](run_graph_module/INDEX.md) | Versioned read-only graph projection from attempt journals, checkpoints and live views. |
| Knowledge | [`knowledge_module/INDEX.md`](knowledge_module/INDEX.md) | Session-isolated durable knowledge documents and explicit Agent retrieval tools. |
| Unified tools | [`tool_module/INDEX.md`](tool_module/INDEX.md) | Canonical Tool identities, authorization policy and future runtime registry. |
| External Agent Hub | [`external_agent_hub_module/INDEX.md`](external_agent_hub_module/INDEX.md) | Credential-free external Agent definitions and protocol adapter boundary. |
| Platform integration | [`platform_module/INDEX.md`](platform_module/INDEX.md) | Operating-system desktop resource-manager dispatch; no browser or Tauri ownership. |
| Managed MCP | [`mcp_module/INDEX.md`](mcp_module/INDEX.md) | Secret-separated servers, Session bindings, SDK transports and dynamic tools. |
| Context versions | [`context_version_module/INDEX.md`](context_version_module/INDEX.md) | Caller-scoped immutable context revisions, edits and restores. |
| Cross-Session memory | [`session_memory_module/INDEX.md`](session_memory_module/INDEX.md) | Allowlist-checked snapshots, handoffs and read-only artifact copies. |

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [computer_use_module/backend.py](computer_use_module/backend.py#L22) | `ComputerBackend.screenshot` | `None` | `ScreenCapture` | Implement `ComputerBackend.screenshot`. |
| [computer_use_module/backend.py](computer_use_module/backend.py#L23) | `ComputerBackend.screen_size` | `None` | `tuple[int, int]` | Implement `ComputerBackend.screen_size`. |
| [computer_use_module/backend.py](computer_use_module/backend.py#L24) | `ComputerBackend.click` | `x: int, y: int, button: str` | `None` | Implement `ComputerBackend.click`. |
| [computer_use_module/backend.py](computer_use_module/backend.py#L25) | `ComputerBackend.double_click` | `x: int, y: int, button: str` | `None` | Implement `ComputerBackend.double_click`. |
| [computer_use_module/backend.py](computer_use_module/backend.py#L26) | `ComputerBackend.type_text` | `text: str` | `None` | Implement `ComputerBackend.type_text`. |
| [computer_use_module/backend.py](computer_use_module/backend.py#L27) | `ComputerBackend.press_key` | `key: str` | `None` | Implement `ComputerBackend.press_key`. |
| [computer_use_module/backend.py](computer_use_module/backend.py#L28) | `ComputerBackend.scroll` | `dx: int, dy: int` | `None` | Implement `ComputerBackend.scroll`. |
| [computer_use_module/backend.py](computer_use_module/backend.py#L31) | `backend_for_host` | `None` | `ComputerBackend` | Implement `backend_for_host`. |
| [computer_use_module/backend.py](computer_use_module/backend.py#L40) | `_UnavailableBackend._raise` | `None` | `None` | Implement `_UnavailableBackend._raise`. |
| [computer_use_module/provider.py](computer_use_module/provider.py#L23) | `ComputerUseProvider.materialize` | `session: 'Session', policy: ToolPolicy, role: str, agent_name: str \| None` | `list[Tool]` | Implement `ComputerUseProvider.materialize`. |
| [computer_use_module/provider.py](computer_use_module/provider.py#L79) | `ComputerUseProvider._validate_point` | `backend: ComputerBackend, x: int, y: int` | `None` | Implement `ComputerUseProvider._validate_point`. |
| [computer_use_module/windows_backend.py](computer_use_module/windows_backend.py#L30) | `WindowsComputerBackend.screenshot` | `None` | `ScreenCapture` | Implement `WindowsComputerBackend.screenshot`. |
| [computer_use_module/windows_backend.py](computer_use_module/windows_backend.py#L39) | `WindowsComputerBackend.screen_size` | `None` | `tuple[int, int]` | Implement `WindowsComputerBackend.screen_size`. |
| [computer_use_module/windows_backend.py](computer_use_module/windows_backend.py#L42) | `WindowsComputerBackend._move` | `x: int, y: int` | `None` | Implement `WindowsComputerBackend._move`. |
| [computer_use_module/windows_backend.py](computer_use_module/windows_backend.py#L46) | `WindowsComputerBackend.click` | `x: int, y: int, button: str` | `None` | Implement `WindowsComputerBackend.click`. |
| [computer_use_module/windows_backend.py](computer_use_module/windows_backend.py#L55) | `WindowsComputerBackend.double_click` | `x: int, y: int, button: str` | `None` | Implement `WindowsComputerBackend.double_click`. |
| [computer_use_module/windows_backend.py](computer_use_module/windows_backend.py#L59) | `WindowsComputerBackend.type_text` | `text: str` | `None` | Implement `WindowsComputerBackend.type_text`. |
| [computer_use_module/windows_backend.py](computer_use_module/windows_backend.py#L66) | `WindowsComputerBackend._unicode_key` | `char: str, key_up: bool` | `None` | Implement `WindowsComputerBackend._unicode_key`. |
| [computer_use_module/windows_backend.py](computer_use_module/windows_backend.py#L71) | `WindowsComputerBackend.press_key` | `key: str` | `None` | Implement `WindowsComputerBackend.press_key`. |
| [computer_use_module/windows_backend.py](computer_use_module/windows_backend.py#L84) | `WindowsComputerBackend.scroll` | `dx: int, dy: int` | `None` | Implement `WindowsComputerBackend.scroll`. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [computer_use_module/backend.py](computer_use_module/backend.py#L9) | `ComputerUseUnavailable` | `None` | `RuntimeError` | Raised when the host cannot provide desktop interaction. |
| [computer_use_module/backend.py](computer_use_module/backend.py#L14) | `ScreenCapture` | `png_bytes: bytes, width: int, height: int, scale: float` | `object` | Provide `ScreenCapture` behavior. |
| [computer_use_module/backend.py](computer_use_module/backend.py#L21) | `ComputerBackend` | `None` | `Protocol` | Provide `ComputerBackend` behavior. |
| [computer_use_module/backend.py](computer_use_module/backend.py#L39) | `_UnavailableBackend` | `None` | `object` | Provide `_UnavailableBackend` behavior. |
| [computer_use_module/provider.py](computer_use_module/provider.py#L18) | `ComputerUseProvider` | `core: 'AngelusCore', backend: ComputerBackend \| None` | `object` | Provide `ComputerUseProvider` behavior. |
| [computer_use_module/windows_backend.py](computer_use_module/windows_backend.py#L11) | `WindowsComputerBackend` | `None` | `object` | Provide `WindowsComputerBackend` behavior. |

<!-- END GENERATED SYMBOL MAP -->
