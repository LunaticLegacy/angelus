"""Durable, optional Session preferences kept separate from run profiles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import threading

from .json_store import (
    JsonSchemaError,
    read_json,
    reject_unknown_keys,
    require_int,
    require_mapping,
    write_json,
)

_SCHEMA_VERSION = 1
_DOCUMENT_FIELDS = {"schema_version", "sessions"}
_PREFERENCE_FIELDS = {"default_connector_id"}


@dataclass(frozen=True)
class SessionPreference:
    """Optional UI conveniences owned by one Session."""

    default_connector_id: str | None = None

    def to_json(self) -> dict[str, object]:
        """Encode the value exactly as it is persisted."""
        return {"default_connector_id": self.default_connector_id}

    @classmethod
    def from_json(cls, value: object, where: str) -> "SessionPreference":
        """Decode one stored preference object.

        Raises:
            JsonSchemaError: If the object carries an unknown field or a
                non-string connector identity.
        """
        raw = require_mapping(value, where)
        reject_unknown_keys(raw, _PREFERENCE_FIELDS, where)
        connector = raw.get("default_connector_id")
        if connector is not None and not isinstance(connector, str):
            raise JsonSchemaError(
                f"{where}.default_connector_id must be a string or null"
            )
        return cls(default_connector_id=connector)


@dataclass(frozen=True)
class SessionPreferencesDocument:
    """The complete ``session-preferences.json`` document."""

    sessions: dict[str, SessionPreference]
    schema_version: int = _SCHEMA_VERSION

    def to_json(self) -> dict[str, object]:
        """Encode the document exactly as it is persisted."""
        return {
            "schema_version": self.schema_version,
            "sessions": {
                session_id: preference.to_json()
                for session_id, preference in self.sessions.items()
            },
        }

    @classmethod
    def from_json(cls, value: object) -> "SessionPreferencesDocument":
        """Decode one complete document.

        Raises:
            JsonSchemaError: If the envelope version or any entry is invalid.
        """
        document = require_mapping(value, "session preferences")
        reject_unknown_keys(document, _DOCUMENT_FIELDS, "session preferences")
        version = require_int(
            document.get("schema_version"), "session preferences.schema_version"
        )
        if version != _SCHEMA_VERSION:
            raise JsonSchemaError(
                f"session preferences.schema_version is not supported: {version}"
            )
        raw_sessions = require_mapping(
            document.get("sessions", {}), "session preferences.sessions"
        )
        return cls(
            sessions={
                session_id: SessionPreference.from_json(
                    preference, f"session preferences.sessions[{session_id}]"
                )
                for session_id, preference in raw_sessions.items()
            }
        )


class SessionPreferenceStore:
    """Persist UI conveniences without making them execution dependencies."""

    def __init__(self, state_root: Path) -> None:
        self._path = state_root / "settings" / "session-preferences.json"
        self._lock = threading.RLock()

    def get(self, session_id: str) -> SessionPreference:
        """Return one Session's preference, defaulting every field."""
        with self._lock:
            return self._read().get(session_id, SessionPreference())

    def set_default_connector(
        self, session_id: str, connector_id: str | None
    ) -> SessionPreference:
        """Store or clear the Session's default connector identity."""
        with self._lock:
            preferences = self._read()
            if connector_id:
                preferences[session_id] = SessionPreference(connector_id)
            else:
                preferences.pop(session_id, None)
            self._write(preferences)
            return preferences.get(session_id, SessionPreference())

    def clear_connector(self, connector_id: str) -> tuple[str, ...]:
        """Remove every Session default that references a deleted connector."""
        with self._lock:
            preferences = self._read()
            cleared = [
                session_id
                for session_id, preference in preferences.items()
                if preference.default_connector_id == connector_id
            ]
            for session_id in cleared:
                preferences.pop(session_id, None)
            if cleared:
                self._write(preferences)
            return tuple(cleared)

    def _read(self) -> dict[str, SessionPreference]:
        """Decode the document; a missing file means no preferences yet."""
        document = read_json(
            self._path, SessionPreferencesDocument(sessions={}).to_json()
        )
        return dict(SessionPreferencesDocument.from_json(document).sessions)

    def _write(self, sessions: dict[str, SessionPreference]) -> None:
        """Atomically replace the complete document."""
        write_json(
            self._path, SessionPreferencesDocument(sessions=sessions).to_json()
        )
