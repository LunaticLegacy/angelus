"""Durable global connectors with credentials kept out of metadata records."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import threading
from uuid import uuid4

from ..settings_module.json_schema import decode_record, encode_record
from ..settings_module.json_store import JsonSchemaError, read_json, write_json

_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ConnectorRecord:
    """The metadata document persisted for one connector."""

    id: str
    name: str
    provider: str
    model: str
    api_url: str


@dataclass(frozen=True)
class ConnectorCatalog:
    """The complete ``connectors.json`` document."""

    connectors: tuple[ConnectorRecord, ...]
    schema_version: int = _SCHEMA_VERSION


@dataclass(frozen=True)
class ConnectorSecret:
    """The private ``secrets/connectors/<id>.json`` document."""

    api_key: str
    schema_version: int = _SCHEMA_VERSION


@dataclass(frozen=True)
class ConnectorDraft:
    """Validated write-side fields, with the key kept separate."""

    name: str
    provider: str
    model: str
    api_url: str
    api_key: str


@dataclass(frozen=True)
class ConnectorView:
    """Secret-free projection returned to settings surfaces."""

    id: str
    name: str
    provider: str
    model: str
    api_url: str
    has_api_key: bool


@dataclass(frozen=True)
class ConnectorConfig:
    """Non-secret fields needed to materialize one Agent connector."""

    provider: str
    model: str
    api_url: str


class ConnectorStore:
    """Store connector metadata and each connector's secret in separate files.

    Public records are safe to return to a workbench.  A key is write-only:
    the store can report whether one exists but never reads it into a public
    projection.  Execution-time secret resolution is deliberately not added
    until Agent construction consumes an immutable run snapshot.
    """

    def __init__(self, state_root: Path) -> None:
        """Create a store rooted in the Angelus state directory.

        Args:
            state_root: Angelus-owned root containing metadata and secrets.
        """
        # Single catalog of non-secret connector fields and stable IDs.
        self._metadata_path = state_root / "settings" / "connectors.json"
        # One write-only secret document per connector, outside catalog JSON.
        self._secret_root = state_root / "secrets" / "connectors"
        # Serializes metadata/secret changes within this process.
        self._lock = threading.RLock()

    def list(self) -> tuple[ConnectorView, ...]:
        """List public metadata without exposing or reading API-key values."""
        with self._lock:
            return tuple(self._view(item) for item in self._records().values())

    def create(self, values: Mapping[str, object]) -> ConnectorView:
        """Create a connector and persist its optional API key separately.

        Returns:
            A public projection including ``has_api_key`` but never the key.
        """
        draft = self._validate(values)
        with self._lock:
            records = self._records()
            connector_id = f"connector_{uuid4().hex[:16]}"
            record = ConnectorRecord(
                id=connector_id,
                name=draft.name,
                provider=draft.provider,
                model=draft.model,
                api_url=draft.api_url,
            )
            records[connector_id] = record
            self._write_records(records)
            self._write_secret(connector_id, draft.api_key)
            return self._view(record)

    def replace(self, connector_id: str, values: Mapping[str, object]) -> ConnectorView:
        """Replace public fields, retaining secret when submitted key is blank.

        Raises:
            KeyError: If the stable connector ID is not registered.
            ValueError: If the ID or submitted field set is invalid.
        """
        self._validate_id(connector_id)
        draft = self._validate(values)
        with self._lock:
            records = self._records()
            if connector_id not in records:
                raise KeyError(connector_id)
            record = ConnectorRecord(
                id=connector_id,
                name=draft.name,
                provider=draft.provider,
                model=draft.model,
                api_url=draft.api_url,
            )
            records[connector_id] = record
            self._write_records(records)
            if draft.api_key:
                self._write_secret(connector_id, draft.api_key)
            return self._view(record)

    def remove(self, connector_id: str) -> None:
        """Delete metadata and companion secret after service-level reference checks."""
        self._validate_id(connector_id)
        with self._lock:
            records = self._records()
            if connector_id not in records:
                raise KeyError(connector_id)
            del records[connector_id]
            self._write_records(records)
            try:
                self._secret_path(connector_id).unlink()
            except FileNotFoundError:
                pass

    def exists(self, connector_id: str) -> bool:
        """Return whether a connector ID has durable metadata, not a valid secret."""
        with self._lock:
            return connector_id in self._records()

    def config(self, connector_id: str) -> ConnectorConfig:
        """Return non-secret connection metadata for runtime materialization."""
        self._validate_id(connector_id)
        with self._lock:
            record = self._records().get(connector_id)
            if record is None:
                raise KeyError(connector_id)
            return ConnectorConfig(record.provider, record.model, record.api_url)

    def api_key(self, connector_id: str) -> str:
        """Return one connector secret for execution-time Agent construction.

        This is intentionally an internal store method, not an API projection.
        Callers must already have validated that the Session profile is allowed
        to use this connector; the value must never be journaled or returned
        from a route.

        Raises:
            KeyError: If metadata or a non-empty secret is absent.
        """
        self._validate_id(connector_id)
        with self._lock:
            if connector_id not in self._records():
                raise KeyError(connector_id)
            document = read_json(self._secret_path(connector_id), None)
            if document is None:
                raise KeyError(connector_id)
            try:
                secret = decode_record(
                    ConnectorSecret,
                    document,
                    f"connector secret {connector_id}",
                )
            except JsonSchemaError as exc:
                raise KeyError(connector_id) from exc
            if not secret.api_key:
                raise KeyError(connector_id)
            return secret.api_key

    def api_url(self, connector_id: str) -> str:
        """Return the configured public endpoint for one connector.

        The endpoint is metadata, not a secret.  Keeping this lookup in the
        connector store lets older run profiles that only persisted
        ``connector_id`` continue to use custom providers correctly.
        """
        self._validate_id(connector_id)
        with self._lock:
            record = self._records().get(connector_id)
            if record is None:
                raise KeyError(connector_id)
            return record.api_url.strip()

    def _records(self) -> dict[str, ConnectorRecord]:
        """Decode the metadata envelope into an ID-indexed map.

        Raises:
            ValueError: If a record is duplicated or the document does not
                match the declared schema.
        """
        document = read_json(
            self._metadata_path,
            encode_record(ConnectorCatalog(connectors=())),
        )
        try:
            catalog = decode_record(ConnectorCatalog, document, "connector catalog")
        except JsonSchemaError as exc:
            raise ValueError("invalid connector catalog") from exc
        records: dict[str, ConnectorRecord] = {}
        for record in catalog.connectors:
            if record.id in records:
                raise ValueError("duplicate connector record")
            records[record.id] = record
        return records

    def _write_records(self, records: Mapping[str, ConnectorRecord]) -> None:
        """Publish the supplied metadata map as the next catalog generation."""
        write_json(
            self._metadata_path,
            encode_record(ConnectorCatalog(connectors=tuple(records.values()))),
        )

    def _write_secret(self, connector_id: str, api_key: str) -> None:
        """Persist a non-empty API key in its private companion document."""
        if api_key:
            write_json(
                self._secret_path(connector_id),
                encode_record(ConnectorSecret(api_key=api_key)),
            )

    def _secret_path(self, connector_id: str) -> Path:
        """Return the secret file path derived from an already validated ID."""
        return self._secret_root / f"{connector_id}.json"

    def _validate(self, values: Mapping[str, object]) -> ConnectorDraft:
        """Return normalized public fields plus the write-only API key."""
        allowed = {"name", "provider", "model", "api_url", "api_key"}
        unknown = sorted(set(values) - allowed)
        if unknown:
            raise ValueError(f"unknown connector fields: {', '.join(unknown)}")
        normalized: dict[str, str] = {}
        for key in allowed:
            value = values.get(key, "")
            if not isinstance(value, str):
                raise ValueError(f"connector field {key} must be a string")
            normalized[key] = value.strip()
        if not normalized["name"]:
            raise ValueError("connector name must not be blank")
        if not normalized["provider"]:
            raise ValueError("connector provider must not be blank")
        return ConnectorDraft(
            name=normalized["name"],
            provider=normalized["provider"],
            model=normalized["model"],
            api_url=normalized["api_url"],
            api_key=normalized["api_key"],
        )

    def _view(self, record: ConnectorRecord) -> ConnectorView:
        """Project catalog metadata for APIs without secret material."""
        return ConnectorView(
            id=record.id,
            name=record.name,
            provider=record.provider,
            model=record.model,
            api_url=record.api_url,
            has_api_key=self._secret_path(record.id).is_file(),
        )

    def _validate_id(self, connector_id: str) -> None:
        """Reject IDs that could address another file or catalog namespace."""
        if not connector_id.startswith("connector_") or not connector_id.replace("_", "").isalnum():
            raise ValueError("invalid connector_id")
