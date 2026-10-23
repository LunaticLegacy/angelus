# knowledge_module/ — Session Knowledge Base INDEX

This module owns explicitly supplied, session-local knowledge documents under
`sessions/<id>/knowledge/`. It never reads a project tree, mutates Agent
context, task plans, checkpoints, or execution graphs. Document text reaches a
model only as the bounded result of an authorized Tool call.

| File | Responsibility |
|---|---|
| `knowledge_store.py` | Atomic JSON persistence, input validation and bounded lexical retrieval. |
| `tool_provider.py` | ToolRegistry registration and Coordinator/Worker Tool materialization. |

## Runtime Boundary

`AngelusCore` registers `knowledge_tool_registration` once. The provider
caches one `KnowledgeStore` per Session state root and exposes nothing unless
both the `knowledge` category and the individual Tool grant are enabled.

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [context_provider.py](context_provider.py#L44) | `KnowledgeContextProvider.source_id` | `None` | `str` | Return the stable Composer source identity. |
| [context_provider.py](context_provider.py#L48) | `KnowledgeContextProvider.build_blocks` | `snapshot: ContextSnapshot` | `Sequence[ContextBlock]` | Render one bounded block from the live corpus and the pin list. |
| [context_provider.py](context_provider.py#L115) | `KnowledgeContextFactory.build` | `request: ContextProviderRequest` | `Sequence[ContextProvider]` | Return the Agent's knowledge source. |
| [context_provider.py](context_provider.py#L124) | `knowledge_context_registration` | `injection: KnowledgeInjectionService` | `ContextProviderRegistration` | Return the knowledge source registration for the process registry. |
| [injection.py](injection.py#L39) | `KnowledgeInjectionService._document` | `session_id: str` | `Path` | Return the session's knowledge directory without creating it. |
| [injection.py](injection.py#L43) | `KnowledgeInjectionService._lock` | `path: Path` | `threading.RLock` | Return the process-wide lock guarding one Session's pin file. |
| [injection.py](injection.py#L49) | `KnowledgeInjectionService._agent` | `value: object` | `str` | Validate one Agent scope name. |
| [injection.py](injection.py#L57) | `KnowledgeInjectionService._targets` | `value: object` | `tuple[str, ...]` | Validate and normalize one complete pin list. |
| [injection.py](injection.py#L84) | `KnowledgeInjectionService.read` | `session_id: str, agent: str` | `tuple[str, ...]` | Return the pinned knowledge paths for one Agent. |
| [injection.py](injection.py#L96) | `KnowledgeInjectionService.set_pins` | `session_id: str, agent: str, pins: Sequence[object]` | `tuple[str, ...]` | Replace one Agent's pin list atomically. |
| [injection.py](injection.py#L128) | `KnowledgeInjectionService.add` | `session_id: str, agent: str, path: str` | `tuple[str, ...]` | Append one path to the Agent's pin list through ``set_pins``. |
| [injection.py](injection.py#L134) | `KnowledgeInjectionService.remove` | `session_id: str, agent: str, path: str` | `tuple[str, ...]` | Remove one path from the Agent's pin list through ``set_pins``. |
| [knowledge_store.py](knowledge_store.py#L54) | `KnowledgeStore._terms` | `value: str` | `list[str]` | Produce robust tokens for mixed Latin/CJK text without dependencies. |
| [knowledge_store.py](knowledge_store.py#L61) | `KnowledgeStore._document` | `None` | `dict[str, KnowledgeDocument]` | Decode the knowledge document or reject an unsupported shape. |
| [knowledge_store.py](knowledge_store.py#L70) | `KnowledgeStore._save` | `documents: dict[str, KnowledgeDocument]` | `None` | Atomically publish the complete knowledge document. |
| [knowledge_store.py](knowledge_store.py#L75) | `KnowledgeStore._validate_id` | `value: object` | `str` | Implement `KnowledgeStore._validate_id`. |
| [knowledge_store.py](knowledge_store.py#L82) | `KnowledgeStore._excerpt` | `content: str, query: str, limit: int` | `str` | Implement `KnowledgeStore._excerpt`. |
| [knowledge_store.py](knowledge_store.py#L90) | `KnowledgeStore.upsert` | `identifier: object, content: object, title: object, tags: object` | `dict[str, object]` | Create or replace one explicitly supplied source document. |
| [knowledge_store.py](knowledge_store.py#L114) | `KnowledgeStore._integer` | `value: object, field: str` | `int` | Coerce a tool-supplied scalar to int, preserving the old contract. |
| [knowledge_store.py](knowledge_store.py#L123) | `KnowledgeStore.search` | `query: object, limit: object` | `list[dict[str, object]]` | Return bounded ranked excerpts, never the entire corpus. |
| [knowledge_store.py](knowledge_store.py#L166) | `KnowledgeStore.read` | `identifier: object, max_chars: object` | `dict[str, object]` | Read one known document with an explicit output bound. |
| [knowledge_store.py](knowledge_store.py#L184) | `KnowledgeStore.delete` | `identifier: object` | `bool` | Delete one explicitly named document; missing IDs are harmless. |
| [tool_provider.py](tool_provider.py#L26) | `_schema` | `*parameters: ToolParameter` | `ToolSchema` | Implement `_schema`. |
| [tool_provider.py](tool_provider.py#L38) | `KnowledgeToolProvider._store` | `session: 'Session'` | `KnowledgeStore` | Implement `KnowledgeToolProvider._store`. |
| [tool_provider.py](tool_provider.py#L46) | `KnowledgeToolProvider._result` | `value: object` | `str` | Implement `KnowledgeToolProvider._result`. |
| [tool_provider.py](tool_provider.py#L49) | `KnowledgeToolProvider.materialize` | `session: 'Session', policy: ToolPolicy, role: str, agent_name: str \| None` | `list[Tool]` | Implement `KnowledgeToolProvider.materialize`. |
| [tool_provider.py](tool_provider.py#L178) | `knowledge_tool_registration` | `core: 'AngelusCore'` | `ToolProviderRegistration` | Return the knowledge provider registration: corpus, pins, session docs. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [context_provider.py](context_provider.py#L27) | `KnowledgeContextProvider` | `session_id: str, agent_name: str, injection: KnowledgeInjectionService` | `object` | Project the knowledge directions and the Agent's pinned leaves. |
| [context_provider.py](context_provider.py#L109) | `KnowledgeContextFactory` | `injection: KnowledgeInjectionService` | `object` | Materialize the knowledge source for one Agent. |
| [injection.py](injection.py#L23) | `KnowledgeInjectionError` | `None` | `ValueError` | Rejected pin set or invalid Agent scope. |
| [injection.py](injection.py#L27) | `KnowledgeInjectionService` | `state_root: Path` | `object` | Own the durable pin set of every (Session, Agent) pair. |
| [knowledge_store.py](knowledge_store.py#L24) | `KnowledgeDocument` | `title: str, content: str, tags: tuple[str, ...], updated_at: float` | `object` | One explicitly supplied source document. |
| [knowledge_store.py](knowledge_store.py#L34) | `KnowledgeBase` | `documents: dict[str, KnowledgeDocument], schema_version: int` | `object` | The complete ``knowledge/documents.json`` document. |
| [knowledge_store.py](knowledge_store.py#L41) | `KnowledgeStore` | `root: Path` | `object` | Own one session's explicit knowledge documents and lexical retrieval. |
| [tool_provider.py](tool_provider.py#L30) | `KnowledgeToolProvider` | `core: 'AngelusCore'` | `object` | Materialize only authorized knowledge Tools for their owning Session. |

<!-- END GENERATED SYMBOL MAP -->
