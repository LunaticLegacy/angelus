# connector_module/ — Connector Capability INDEX

| File | Responsibility |
|---|---|
| `provider_catalog.py` | Runtime read-only LLMFetcher provider discovery. |
| `connector_store.py` | Global connector metadata and per-connector write-only secret document. |

Metadata lives in `settings/connectors.json`; keys live in
`secrets/connectors/<id>.json`. Public projections expose only `has_api_key`.

## Function Map

| Source | Function / method | Semantics |
|---|---|---|
| `ProviderCatalog.list` | Return registered provider names. |
| `ConnectorStore.create`, `replace`, `remove` | Manage metadata/secret records behind service-level reference checks. |
| `ConnectorStore.api_key` | Internal execution-time secret resolution; never HTTP output. |

## Class Map

| Source | Class | Semantics |
|---|---|---|
| `ProviderCatalog` | Read-only runtime capability catalog. |
| `ConnectorStore` | Thread-safe durable connector/secret owner. |
