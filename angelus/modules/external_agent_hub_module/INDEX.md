# external_agent_hub_module/ — External Agent Hub INDEX

This module owns phase-one configuration and non-executing inspection of
external Agent runtimes. It stores no credentials: a definition can only name
an optional `ConnectorStore` reference. Protocol implementations are isolated
behind the adapter base and are not yet allowed to dispatch remote work.

| File | Responsibility |
|---|---|
| `models.py` | Dataclass contracts for definitions, health, and future capabilities. |
| `store.py` | Atomic credential-free definition persistence. |
| `adapter.py` | Read-only protocol adapter contract and process-local registry. |
| `service.py` | Validation, CRUD, health, and capability use cases. |

## Phase-one Boundary

- The Hub can create, replace, list, delete, health-check, and inspect an
  external Agent definition.
- Missing protocol adapters produce `unsupported`; no fallback request is made.
- No remote run, context handoff, ToolRegistry projection, or connector-secret
  read occurs in this module yet.
