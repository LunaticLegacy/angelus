# tool_module/ — Unified Tool System INDEX

This module is the future sole source of truth for Tool identity, category,
authorization and runtime availability. Frontend panels and Agent construction
must consume its registry projection instead of maintaining separate lists.

| File | Responsibility |
|---|---|
| `tool_models.py` | Typed category, Tool-definition and availability records. |
| `tool_policy.py` | Session grant parsing plus legacy Tool-ID migration. |
| `tool_registry.py` | Process-wide provider registration, uniqueness validation and role-aware Tool materialization. |
| `tool_service.py` | Pending: API-facing projections and Session-policy use cases. |

## Invariants

- A Tool ID has exactly one registered owner and one category.
- A model receives a Tool only when both the category and Tool grants allow it.
- Historic permission IDs are translated at the policy boundary, never copied
  into new registrars or the frontend.

## Current Integration

`AngelusCore.tool_registry` is the only process-wide Registry. The Console
provider is registered at core startup; `SessionService` asks it to materialize
Coordinator and Worker tools from the effective Session `ToolPolicy`.

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [runtime_provider.py](runtime_provider.py#L30) | `RuntimeToolProvider.materialize` | `session: 'Session', policy: ToolPolicy, role: str` | `list[Tool]` | Build only explicitly authorized project-scoped runtime tools. |
| [runtime_provider.py](runtime_provider.py#L66) | `runtime_tool_registration` | `core: 'AngelusCore'` | `ToolProviderRegistration` | Return built-in runtime registration for the application's registry. |
| [tool_policy.py](tool_policy.py#L31) | `ToolPolicy.from_profile` | `value: object` | `'ToolPolicy'` | Decode profile grants and migrate recognized historic Tool names. |
| [tool_policy.py](tool_policy.py#L55) | `ToolPolicy.allows` | `category_id: str, tool_id: str` | `bool` | Return whether both grants needed to expose a Tool are present. |
| [tool_policy.py](tool_policy.py#L67) | `ToolPolicy.fingerprint` | `None` | `tuple[tuple[str, ...], tuple[str, ...]]` | Return a deterministic configuration identity for Agent rebuilding. |
| [tool_registry.py](tool_registry.py#L20) | `ToolProvider.materialize` | `session: 'Session', policy: ToolPolicy, role: str` | `list[Tool]` | Build only Tools this provider can safely expose. |
| [tool_registry.py](tool_registry.py#L60) | `ToolRegistry.register` | `registration: ToolProviderRegistration` | `None` | Register one complete provider atomically after uniqueness checks. |
| [tool_registry.py](tool_registry.py#L92) | `ToolRegistry.materialize` | `session: 'Session', policy: ToolPolicy, role: str` | `list[Tool]` | Build all authorized concrete Tools for one Agent role. |
| [tool_registry.py](tool_registry.py#L112) | `ToolRegistry.unregister` | `provider_id: str` | `None` | Remove one dynamically loaded provider and all of its metadata. |
| [tool_registry.py](tool_registry.py#L133) | `ToolRegistry.revision` | `None` | `int` | Return the monotonic materialization revision of this registry. |
| [tool_registry.py](tool_registry.py#L143) | `ToolRegistry.definitions` | `None` | `tuple[ToolDefinition, ...]` | Return all registered Tool definitions in stable registration order. |
| [tool_registry.py](tool_registry.py#L151) | `ToolRegistry.categories` | `None` | `tuple[ToolCategory, ...]` | Return registered user-visible categories in registration order. |
| [tool_registry.py](tool_registry.py#L159) | `ToolRegistry.catalog` | `None` | `ToolCatalog` | Build a typed public catalog from actual registrations only. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [runtime_provider.py](runtime_provider.py#L19) | `RuntimeToolProvider` | `core: 'AngelusCore'` | `object` | Materialize built-in tools that require Session profile state. |
| [tool_models.py](tool_models.py#L8) | `ToolCategory` | `id: str, title: str, description: str` | `object` | One user-visible group of registered Agent tools. |
| [tool_models.py](tool_models.py#L23) | `ToolDefinition` | `id: str, category_id: str, title: str, description: str, provider_id: str, roles: frozenset[str]` | `object` | One stable tool capability independent of a frontend implementation. |
| [tool_models.py](tool_models.py#L44) | `ToolAvailability` | `tool_id: str, available: bool, reason: str` | `object` | Current materialization state for one Tool. |
| [tool_models.py](tool_models.py#L59) | `ToolCatalogCategory` | `id: str, title: str, description: str, tools: tuple[ToolDefinition, ...]` | `object` | One registry category and its concrete model-visible tool records. |
| [tool_models.py](tool_models.py#L76) | `ToolCatalog` | `categories: tuple[ToolCatalogCategory, ...]` | `object` | HTTP-safe snapshot of every currently registered tool capability. |
| [tool_policy.py](tool_policy.py#L19) | `ToolPolicy` | `categories: frozenset[str], tools: frozenset[str]` | `object` | Effective category-and-tool grants for one future Agent construction. |
| [tool_registry.py](tool_registry.py#L17) | `ToolProvider` | `None` | `Protocol` | Materialize a registered family's concrete Tools for one Session. |
| [tool_registry.py](tool_registry.py#L34) | `ToolProviderRegistration` | `id: str, provider: ToolProvider, categories: tuple[ToolCategory, ...], definitions: tuple[ToolDefinition, ...]` | `object` | One provider plus its categories and Tool definitions. |
| [tool_registry.py](tool_registry.py#L50) | `ToolRegistry` | `None` | `object` | Validate unique registrations and materialize Tools from one policy. |

<!-- END GENERATED SYMBOL MAP -->
