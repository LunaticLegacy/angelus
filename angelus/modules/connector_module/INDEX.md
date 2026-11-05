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

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| [connector_store.py](connector_store.py#L98) | `ConnectorStore.list` | `None` | `tuple[ConnectorView, ...]` | List public metadata without exposing or reading API-key values. |
| [connector_store.py](connector_store.py#L103) | `ConnectorStore.create` | `values: Mapping[str, object]` | `ConnectorView` | Create a connector and persist its optional API key separately. |
| [connector_store.py](connector_store.py#L125) | `ConnectorStore.replace` | `connector_id: str, values: Mapping[str, object]` | `ConnectorView` | Replace public fields, retaining secret when submitted key is blank. |
| [connector_store.py](connector_store.py#L151) | `ConnectorStore.remove` | `connector_id: str` | `None` | Delete metadata and companion secret after service-level reference checks. |
| [connector_store.py](connector_store.py#L165) | `ConnectorStore.exists` | `connector_id: str` | `bool` | Return whether a connector ID has durable metadata, not a valid secret. |
| [connector_store.py](connector_store.py#L170) | `ConnectorStore.config` | `connector_id: str` | `ConnectorConfig` | Return non-secret connection metadata for runtime materialization. |
| [connector_store.py](connector_store.py#L179) | `ConnectorStore.api_key` | `connector_id: str` | `str` | Return one connector secret for execution-time Agent construction. |
| [connector_store.py](connector_store.py#L209) | `ConnectorStore.api_url` | `connector_id: str` | `str` | Return the configured public endpoint for one connector. |
| [connector_store.py](connector_store.py#L223) | `ConnectorStore._records` | `None` | `dict[str, ConnectorRecord]` | Decode the metadata envelope into an ID-indexed map. |
| [connector_store.py](connector_store.py#L245) | `ConnectorStore._write_records` | `records: Mapping[str, ConnectorRecord]` | `None` | Publish the supplied metadata map as the next catalog generation. |
| [connector_store.py](connector_store.py#L252) | `ConnectorStore._write_secret` | `connector_id: str, api_key: str` | `None` | Persist a non-empty API key in its private companion document. |
| [connector_store.py](connector_store.py#L260) | `ConnectorStore._secret_path` | `connector_id: str` | `Path` | Return the secret file path derived from an already validated ID. |
| [connector_store.py](connector_store.py#L264) | `ConnectorStore._validate` | `values: Mapping[str, object]` | `ConnectorDraft` | Return normalized public fields plus the write-only API key. |
| [connector_store.py](connector_store.py#L288) | `ConnectorStore._view` | `record: ConnectorRecord` | `ConnectorView` | Project catalog metadata for APIs without secret material. |
| [connector_store.py](connector_store.py#L299) | `ConnectorStore._validate_id` | `connector_id: str` | `None` | Reject IDs that could address another file or catalog namespace. |
| [provider_catalog.py](provider_catalog.py#L16) | `ProviderCatalog.list` | `None` | `tuple[str, ...]` | Return stable, deduplicated provider identifiers from LLMFetcher. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [connector_store.py](connector_store.py#L18) | `ConnectorRecord` | `id: str, name: str, provider: str, model: str, api_url: str` | `object` | The metadata document persisted for one connector. |
| [connector_store.py](connector_store.py#L29) | `ConnectorCatalog` | `connectors: tuple[ConnectorRecord, ...], schema_version: int` | `object` | The complete ``connectors.json`` document. |
| [connector_store.py](connector_store.py#L37) | `ConnectorSecret` | `api_key: str, schema_version: int` | `object` | The private ``secrets/connectors/<id>.json`` document. |
| [connector_store.py](connector_store.py#L45) | `ConnectorDraft` | `name: str, provider: str, model: str, api_url: str, api_key: str` | `object` | Validated write-side fields, with the key kept separate. |
| [connector_store.py](connector_store.py#L56) | `ConnectorView` | `id: str, name: str, provider: str, model: str, api_url: str, has_api_key: bool` | `object` | Secret-free projection returned to settings surfaces. |
| [connector_store.py](connector_store.py#L68) | `ConnectorConfig` | `provider: str, model: str, api_url: str` | `object` | Non-secret fields needed to materialize one Agent connector. |
| [connector_store.py](connector_store.py#L76) | `ConnectorStore` | `state_root: Path` | `object` | Store connector metadata and each connector's secret in separate files. |
| [provider_catalog.py](provider_catalog.py#L8) | `ProviderCatalog` | `None` | `object` | Read-only catalog of providers available in this Angelus process. |

<!-- END GENERATED SYMBOL MAP -->
