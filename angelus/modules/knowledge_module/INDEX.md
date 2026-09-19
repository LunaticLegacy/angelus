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
| [knowledge_store.py](knowledge_store.py#L34) | `KnowledgeStore._terms` | `value: str` | `list[str]` | Produce robust tokens for mixed Latin/CJK text without dependencies. |
| [knowledge_store.py](knowledge_store.py#L41) | `KnowledgeStore._document` | `None` | `dict[str, dict[str, Any]]` | Implement `KnowledgeStore._document`. |
| [knowledge_store.py](knowledge_store.py#L51) | `KnowledgeStore._save` | `documents: dict[str, dict[str, Any]]` | `None` | Implement `KnowledgeStore._save`. |
| [knowledge_store.py](knowledge_store.py#L55) | `KnowledgeStore._validate_id` | `value: object` | `str` | Implement `KnowledgeStore._validate_id`. |
| [knowledge_store.py](knowledge_store.py#L62) | `KnowledgeStore._excerpt` | `content: str, query: str, limit: int` | `str` | Implement `KnowledgeStore._excerpt`. |
| [knowledge_store.py](knowledge_store.py#L70) | `KnowledgeStore.upsert` | `identifier: object, content: object, title: object, tags: object` | `dict[str, object]` | Create or replace one explicitly supplied source document. |
| [knowledge_store.py](knowledge_store.py#L91) | `KnowledgeStore.search` | `query: object, limit: object` | `list[dict[str, object]]` | Return bounded ranked excerpts, never the entire corpus. |
| [knowledge_store.py](knowledge_store.py#L134) | `KnowledgeStore.read` | `identifier: object, max_chars: object` | `dict[str, object]` | Read one known document with an explicit output bound. |
| [knowledge_store.py](knowledge_store.py#L150) | `KnowledgeStore.delete` | `identifier: object` | `bool` | Delete one explicitly named document; missing IDs are harmless. |
| [tool_provider.py](tool_provider.py#L21) | `_schema` | `*parameters: ToolParameter` | `ToolSchema` | Implement `_schema`. |
| [tool_provider.py](tool_provider.py#L32) | `KnowledgeToolProvider._store` | `session: 'Session'` | `KnowledgeStore` | Implement `KnowledgeToolProvider._store`. |
| [tool_provider.py](tool_provider.py#L40) | `KnowledgeToolProvider._result` | `value: object` | `str` | Implement `KnowledgeToolProvider._result`. |
| [tool_provider.py](tool_provider.py#L43) | `KnowledgeToolProvider.materialize` | `session: 'Session', policy: ToolPolicy, role: str, agent_name: str \| None` | `list[Tool]` | Implement `KnowledgeToolProvider.materialize`. |
| [tool_provider.py](tool_provider.py#L86) | `knowledge_tool_registration` | `core: 'AngelusCore'` | `ToolProviderRegistration` | Return the built-in local knowledge-base provider registration. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [knowledge_store.py](knowledge_store.py#L21) | `KnowledgeStore` | `root: Path` | `object` | Own one session's explicit knowledge documents and lexical retrieval. |
| [tool_provider.py](tool_provider.py#L25) | `KnowledgeToolProvider` | `_core: 'AngelusCore'` | `object` | Materialize only authorized knowledge Tools for their owning Session. |

<!-- END GENERATED SYMBOL MAP -->
