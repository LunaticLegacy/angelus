"""Durable global connectors with credentials kept out of metadata records."""

from __future__ import annotations

from pathlib import Path
import threading
from typing import Any
from uuid import uuid4

from ..settings_module.json_store import read_json, write_json


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

    def list(self) -> tuple[dict[str, Any], ...]:
        """List public metadata without exposing or reading API-key values."""
        with self._lock:
            return tuple(self._public(item) for item in self._records().values())

    def create(self, values: dict[str, Any]) -> dict[str, Any]:
        """Create a connector and persist its optional API key separately.

        Returns:
            A public projection including ``has_api_key`` but never the key.
        """
        normalized, api_key = self._validate(values)
        with self._lock:
            records = self._records()
            connector_id = f"connector_{uuid4().hex[:16]}"
            record = {"id": connector_id, **normalized}
            records[connector_id] = record
            self._write_records(records)
            self._write_secret(connector_id, api_key)
            return self._public(record)

    def replace(self, connector_id: str, values: dict[str, Any]) -> dict[str, Any]:
        """Replace public fields, retaining secret when submitted key is blank.

        Raises:
            KeyError: If the stable connector ID is not registered.
            ValueError: If the ID or submitted field set is invalid.
        """
        self._validate_id(connector_id)
        normalized, api_key = self._validate(values)
        with self._lock:
            records = self._records()
            if connector_id not in records:
                raise KeyError(connector_id)
            record = {"id": connector_id, **normalized}
            records[connector_id] = record
            self._write_records(records)
            if api_key:
                self._write_secret(connector_id, api_key)
            return self._public(record)

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
            document = read_json(self._secret_path(connector_id), {})
            if not isinstance(document, dict) or document.get("schema_version") != 1:
                raise KeyError(connector_id)
            api_key = document.get("api_key")
            if not isinstance(api_key, str) or not api_key:
                raise KeyError(connector_id)
            return api_key

    def _records(self) -> dict[str, dict[str, Any]]:
        """Decode the metadata envelope into an ID-indexed copy."""
        document = read_json(self._metadata_path, {"schema_version": 1, "connectors": []})
        if not isinstance(document, dict) or document.get("schema_version") != 1:
            raise ValueError("unsupported connector catalog")
        entries = document.get("connectors")
        if not isinstance(entries, list):
            raise ValueError("invalid connector catalog")
        records: dict[str, dict[str, Any]] = {}
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
                raise ValueError("invalid connector record")
            records[entry["id"]] = dict(entry)
        return records

    def _write_records(self, records: dict[str, dict[str, Any]]) -> None:
        """Publish the supplied metadata map as the next catalog generation."""
        write_json(self._metadata_path, {"schema_version": 1, "connectors": list(records.values())})

    def _write_secret(self, connector_id: str, api_key: str) -> None:
        """Persist a non-empty API key in its private companion document."""
        if api_key:
            write_json(self._secret_path(connector_id), {"schema_version": 1, "api_key": api_key})

    def _secret_path(self, connector_id: str) -> Path:
        """Return the secret file path derived from an already validated ID."""
        return self._secret_root / f"{connector_id}.json"

    def _validate(self, values: dict[str, Any]) -> tuple[dict[str, str], str]:
        """Return normalized public fields plus write-only API key separately."""
        if not isinstance(values, dict):
            raise ValueError("connector fields must be an object")
        allowed = {"name", "provider", "model", "api_url", "api_key"}
        if set(values) - allowed:
            raise ValueError("unknown connector fields")
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
        api_key = normalized.pop("api_key")
        return normalized, api_key

    def _public(self, record: dict[str, Any]) -> dict[str, Any]:
        """Project catalog metadata for APIs without secret material."""
        return {**record, "has_api_key": self._secret_path(record["id"]).is_file()}

    def _validate_id(self, connector_id: str) -> None:
        """Reject IDs that could address another file or catalog namespace."""
        if not connector_id.startswith("connector_") or not connector_id.replace("_", "").isalnum():
            raise ValueError("invalid connector_id")
