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
| [connector_store.py](connector_store.py#L35) | `ConnectorStore.list` | `None` | `tuple[dict[str, Any], ...]` | List public metadata without exposing or reading API-key values. |
| [connector_store.py](connector_store.py#L40) | `ConnectorStore.create` | `values: dict[str, Any]` | `dict[str, Any]` | Create a connector and persist its optional API key separately. |
| [connector_store.py](connector_store.py#L56) | `ConnectorStore.replace` | `connector_id: str, values: dict[str, Any]` | `dict[str, Any]` | Replace public fields, retaining secret when submitted key is blank. |
| [connector_store.py](connector_store.py#L76) | `ConnectorStore.remove` | `connector_id: str` | `None` | Delete metadata and companion secret after service-level reference checks. |
| [connector_store.py](connector_store.py#L90) | `ConnectorStore.exists` | `connector_id: str` | `bool` | Return whether a connector ID has durable metadata, not a valid secret. |
| [connector_store.py](connector_store.py#L95) | `ConnectorStore.api_key` | `connector_id: str` | `str` | Return one connector secret for execution-time Agent construction. |
| [connector_store.py](connector_store.py#L118) | `ConnectorStore._records` | `None` | `dict[str, dict[str, Any]]` | Decode the metadata envelope into an ID-indexed copy. |
| [connector_store.py](connector_store.py#L133) | `ConnectorStore._write_records` | `records: dict[str, dict[str, Any]]` | `None` | Publish the supplied metadata map as the next catalog generation. |
| [connector_store.py](connector_store.py#L137) | `ConnectorStore._write_secret` | `connector_id: str, api_key: str` | `None` | Persist a non-empty API key in its private companion document. |
| [connector_store.py](connector_store.py#L142) | `ConnectorStore._secret_path` | `connector_id: str` | `Path` | Return the secret file path derived from an already validated ID. |
| [connector_store.py](connector_store.py#L146) | `ConnectorStore._validate` | `values: dict[str, Any]` | `tuple[dict[str, str], str]` | Return normalized public fields plus write-only API key separately. |
| [connector_store.py](connector_store.py#L166) | `ConnectorStore._public` | `record: dict[str, Any]` | `dict[str, Any]` | Project catalog metadata for APIs without secret material. |
| [connector_store.py](connector_store.py#L170) | `ConnectorStore._validate_id` | `connector_id: str` | `None` | Reject IDs that could address another file or catalog namespace. |
| [provider_catalog.py](provider_catalog.py#L16) | `ProviderCatalog.list` | `None` | `tuple[str, ...]` | Return stable, deduplicated provider identifiers from LLMFetcher. |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| [connector_store.py](connector_store.py#L13) | `ConnectorStore` | `state_root: Path` | `object` | Store connector metadata and each connector's secret in separate files. |
| [provider_catalog.py](provider_catalog.py#L8) | `ProviderCatalog` | `None` | `object` | Read-only catalog of providers available in this Angelus process. |

<!-- END GENERATED SYMBOL MAP -->
