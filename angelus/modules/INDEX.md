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
| Files | [`file_module/INDEX.md`](file_module/INDEX.md) | Bounded listing, reading, searching and writing inside the bound Session workspace. |
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
| [context_module/registry.py](context_module/registry.py#L52) | `ContextProviderFactory.build` | `request: ContextProviderRequest` | `Sequence[ContextProvider]` | Return this module's sources for the requested Agent. |
| [context_module/registry.py](context_module/registry.py#L88) | `ContextProviderRegistry.register` | `registration: ContextProviderRegistration` | `None` | Register one complete module contribution atomically. |
| [context_module/registry.py](context_module/registry.py#L112) | `ContextProviderRegistry.materialize` | `request: ContextProviderRequest` | `tuple[ContextProvider, ...]` | Build every source authorized for the requested Agent. |
| [context_module/registry.py](context_module/registry.py#L133) | `ContextProviderRegistry.registrations` | `None` | `tuple[ContextProviderRegistration, ...]` | Return every registration in stable registration order. |
| [ctf_knowledge_module/catalog.py](ctf_knowledge_module/catalog.py#L31) | `KnowledgeEntry.to_json` | `None` | `dict[str, object]` | Encode the entry for the HTTP response and the build artifact. |
| [ctf_knowledge_module/catalog.py](ctf_knowledge_module/catalog.py#L51) | `KnowledgeCatalog.to_json` | `None` | `dict[str, object]` | Encode the catalog as the same payload the frontend always read. |
| [ctf_knowledge_module/catalog.py](ctf_knowledge_module/catalog.py#L60) | `summary_of` | `text: str` | `str` | Return the leaf's first 适用场景 paragraph, else its opening lines. |
| [ctf_knowledge_module/catalog.py](ctf_knowledge_module/catalog.py#L80) | `entry_for` | `root: Path, path: Path` | `KnowledgeEntry` | Build one catalog entry from a Markdown leaf below ``root``. |
| [ctf_knowledge_module/catalog.py](ctf_knowledge_module/catalog.py#L97) | `build_catalog` | `root: Path` | `KnowledgeCatalog` | Scan every non-index Markdown leaf below ``root`` in path order. |
| [ctf_knowledge_module/tree.py](ctf_knowledge_module/tree.py#L36) | `_lock_for` | `path: Path` | `threading.RLock` | Return the process-local lock guarding one knowledge leaf. |
| [ctf_knowledge_module/tree.py](ctf_knowledge_module/tree.py#L42) | `resolve_knowledge_root` | `None` | `Path \| None` | Resolve the one live knowledge root the Agent and the page share. |
| [ctf_knowledge_module/tree.py](ctf_knowledge_module/tree.py#L56) | `knowledge_tree_for` | `root: Path` | `'CtfKnowledgeTree'` | Return the process-wide tree instance for one resolved root. |
| [ctf_knowledge_module/tree.py](ctf_knowledge_module/tree.py#L72) | `CtfKnowledgeTree.catalog` | `None` | `KnowledgeCatalog` | Return every leaf, re-reading only files whose signature changed. |
| [ctf_knowledge_module/tree.py](ctf_knowledge_module/tree.py#L97) | `CtfKnowledgeTree.read` | `relative: object` | `KnowledgeEntry` | Return one parsed leaf without mutating the cache. |
| [ctf_knowledge_module/tree.py](ctf_knowledge_module/tree.py#L101) | `CtfKnowledgeTree.write` | `relative: object, content: object` | `KnowledgeEntry` | Replace one existing leaf atomically and return its new entry. |
| [ctf_knowledge_module/tree.py](ctf_knowledge_module/tree.py#L137) | `CtfKnowledgeTree._existing_leaf` | `value: object` | `Path` | Resolve one existing editable leaf, rejecting every escape. |
| [ctf_knowledge_module/tree.py](ctf_knowledge_module/tree.py#L160) | `_replace_with_retry` | `source: Path, target: Path` | `None` | Replace ``target`` with ``source`` despite a transient Windows refusal. |
| [note_module/context_provider.py](note_module/context_provider.py#L27) | `NoteContextProvider.source_id` | `None` | `str` | Implement `NoteContextProvider.source_id`. |
| [note_module/context_provider.py](note_module/context_provider.py#L30) | `NoteContextProvider.build_blocks` | `snapshot: ContextSnapshot` | `Sequence[ContextBlock]` | Implement `NoteContextProvider.build_blocks`. |
| [note_module/context_provider.py](note_module/context_provider.py#L65) | `NoteContextFactory.build` | `request: ContextProviderRequest` | `Sequence[ContextProvider]` | Return the note source bound to this Agent's Session and Project. |
| [note_module/context_provider.py](note_module/context_provider.py#L80) | `note_context_registration` | `state_root: Path` | `ContextProviderRegistration` | Return the note source registration for the process registry. |
| [note_module/store.py](note_module/store.py#L35) | `Note.as_dict` | `None` | `dict[str, Any]` | Implement `Note.as_dict`. |
| [note_module/store.py](note_module/store.py#L55) | `NoteStore.project_root` | `state_root: Path, project_path: Path \| None` | `Path \| None` | Implement `NoteStore.project_root`. |
| [note_module/store.py](note_module/store.py#L61) | `NoteStore._path` | `scope: str` | `Path` | Implement `NoteStore._path`. |
| [note_module/store.py](note_module/store.py#L69) | `NoteStore._initialize` | `path: Path` | `None` | Implement `NoteStore._initialize`. |
| [note_module/store.py](note_module/store.py#L80) | `NoteStore._connection` | `path: Path` | `Any` | Implement `NoteStore._connection`. |
| [note_module/store.py](note_module/store.py#L91) | `NoteStore._write_connection` | `path: Path` | `Any` | Hold one read-modify-write span behind SQLite's write lock. |
| [note_module/store.py](note_module/store.py#L119) | `NoteStore._validate_text` | `value: object, field: str` | `str` | Implement `NoteStore._validate_text`. |
| [note_module/store.py](note_module/store.py#L128) | `NoteStore._tags` | `tags: object` | `tuple[str, ...]` | Implement `NoteStore._tags`. |
| [note_module/store.py](note_module/store.py#L136) | `NoteStore._row` | `row: tuple[Any, ...]` | `Note` | Implement `NoteStore._row`. |
| [note_module/store.py](note_module/store.py#L139) | `NoteStore.create` | `scope: str, title: object, content: object, tags: object` | `Note` | Implement `NoteStore.create`. |
| [note_module/store.py](note_module/store.py#L149) | `NoteStore.read` | `scope: str, note_id: str` | `Note` | Implement `NoteStore.read`. |
| [note_module/store.py](note_module/store.py#L158) | `NoteStore.update` | `scope: str, note_id: str, title: object \| None, content: object \| None, tags: object \| None, status: str \| None, revision: int \| None` | `Note` | Replace selected fields of one note inside its write lock. |
| [note_module/store.py](note_module/store.py#L198) | `NoteStore.delete` | `scope: str, note_id: str, revision: int \| None` | `Note` | Implement `NoteStore.delete`. |
| [note_module/store.py](note_module/store.py#L201) | `NoteStore.list` | `scope: str, include_inactive: bool, limit: int` | `list[Note]` | Implement `NoteStore.list`. |
| [note_module/store.py](note_module/store.py#L212) | `NoteStore.search` | `scope: str, query: str, limit: int` | `list[Note]` | Implement `NoteStore.search`. |
| [note_module/tool_provider.py](note_module/tool_provider.py#L21) | `NoteToolProvider._store` | `session: object` | `NoteStore` | Implement `NoteToolProvider._store`. |
| [note_module/tool_provider.py](note_module/tool_provider.py#L26) | `NoteToolProvider.materialize` | `session: object, policy: ToolPolicy, role: str, agent_name: str \| None` | `list[Tool]` | Implement `NoteToolProvider.materialize`. |
| [note_module/tool_provider.py](note_module/tool_provider.py#L54) | `note_tool_registration` | `core: 'AngelusCore'` | `ToolProviderRegistration` | Implement `note_tool_registration`. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [context_module/registry.py](context_module/registry.py#L31) | `ContextProviderRequest` | `session: 'Session', workspace: Workspace, policy: ToolPolicy, role: str, agent_name: str` | `object` | Complete host state one module needs to build its sources. |
| [context_module/registry.py](context_module/registry.py#L49) | `ContextProviderFactory` | `None` | `Protocol` | Materialize one module's sources for one Agent. |
| [context_module/registry.py](context_module/registry.py#L65) | `ContextProviderRegistration` | `id: str, factory: ContextProviderFactory, roles: frozenset[str], gates: tuple[tuple[str, str], ...]` | `object` | One module contribution to every Agent's Composer. |
| [context_module/registry.py](context_module/registry.py#L81) | `ContextProviderRegistry` | `None` | `object` | Validate unique registrations and materialize sources per Agent. |
| [ctf_knowledge_module/catalog.py](ctf_knowledge_module/catalog.py#L20) | `KnowledgeEntry` | `path: str, direction: str, group: str, title: str, summary: str, headings: tuple[str, ...], content: str` | `object` | One Markdown leaf as the knowledge page consumes it. |
| [ctf_knowledge_module/catalog.py](ctf_knowledge_module/catalog.py#L45) | `KnowledgeCatalog` | `directions: dict[str, int], entries: tuple[KnowledgeEntry, ...]` | `object` | The complete knowledge tree projected into one document. |
| [ctf_knowledge_module/tree.py](ctf_knowledge_module/tree.py#L63) | `CtfKnowledgeTree` | `root: Path` | `object` | Read and edit the Markdown leaves below one runtime root. |
| [note_module/context_provider.py](note_module/context_provider.py#L18) | `NoteContextProvider` | `store: NoteStore, max_notes: int, max_characters: int` | `object` | Provide `NoteContextProvider` behavior. |
| [note_module/context_provider.py](note_module/context_provider.py#L54) | `NoteContextFactory` | `state_root: Path` | `object` | Materialize the active-note source for one Agent. |
| [note_module/store.py](note_module/store.py#L19) | `NoteError` | `None` | `ValueError` | Safe rejection of an invalid note operation. |
| [note_module/store.py](note_module/store.py#L24) | `Note` | `note_id: str, scope: str, title: str, content: str, tags: tuple[str, ...], status: str, created_at: float, updated_at: float, revision: int` | `object` | Provide `Note` behavior. |
| [note_module/store.py](note_module/store.py#L41) | `NoteStore` | `session_root: Path, project_root: Path \| None` | `object` | SQLite-backed notes with optimistic revision checks. |
| [note_module/tool_provider.py](note_module/tool_provider.py#L17) | `NoteToolProvider` | `core: 'AngelusCore'` | `object` | Provide `NoteToolProvider` behavior. |

<!-- END GENERATED SYMBOL MAP -->
