"""Use cases that coordinate global settings with Session ownership."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from .execution_service import UnknownSession

if TYPE_CHECKING:
    from ...core import AngelusCore
    from ..connector_module.connector_store import ConnectorView
    from ..settings_module.session_preferences import SessionPreference


class SettingsService:
    """Apply settings transactions without letting HTTP handlers own policy.

    This is the transaction boundary for settings validation across stores:
    Session behavior profiles and connector metadata are independent, while
    optional Session defaults are cleaned up when a connector is deleted.
    """

    def __init__(self, core: "AngelusCore") -> None:
        """Use the application's single stores and Session registry.

        Args:
            core: Composition root supplying the sole connector/profile stores
                and authoritative set of durable Sessions.
        """
        # Cross-store dependency retained only at the service boundary.
        self._core = core

    def global_profile(self) -> dict[str, Any]:
        """Read future-attempt defaults shared by all Sessions.

        Returns:
            A global-scope response shape matching session profile reads.
        """
        return {"scope": "global", "effective": self._core.run_profiles.global_profile()}

    def replace_global_profile(self, values: Mapping[str, Any]) -> dict[str, Any]:
        """Atomically replace global Session behavior defaults.

        The replacement is one profile-document transaction; it does not alter
        an already started ``ExecutionAttempt``.
        """
        return {"scope": "global", "effective": self._core.run_profiles.replace_global(values)}

    def session_profile(self, session_id: str) -> dict[str, Any]:
        """Read effective future-attempt settings for an existing Session."""
        self._require_session(session_id)
        return self._core.run_profiles.session_profile(session_id)

    def replace_session_profile(self, session_id: str, values: Mapping[str, Any]) -> dict[str, Any]:
        """Store a Session behavior override used only by future attempts.

        The caller submits a complete profile.  It is validated before its
        one durable JSON document is atomically replaced.
        """
        self._require_session(session_id)
        return self._core.run_profiles.replace_session(session_id, values)

    def clear_session_profile(self, session_id: str) -> dict[str, Any]:
        """Delete a Session override and restore global-default inheritance."""
        self._require_session(session_id)
        return self._core.run_profiles.clear_session(session_id)

    def list_connectors(self) -> "tuple[ConnectorView, ...]":
        """List safe connector projections; secrets never cross this boundary."""
        return self._core.connectors.list()

    def create_connector(self, values: Mapping[str, object]) -> "ConnectorView":
        """Create one global connector with its optional API key stored separately."""
        return self._core.connectors.create(values)

    def replace_connector(
        self, connector_id: str, values: Mapping[str, object]
    ) -> "ConnectorView":
        """Replace metadata without returning or erasing an omitted API key."""
        return self._core.connectors.replace(connector_id, values)

    def session_preferences(self, session_id: str) -> "SessionPreference":
        self._require_session(session_id)
        return self._core.session_preferences.get(session_id)

    def set_default_connector(
        self, session_id: str, connector_id: str | None
    ) -> "SessionPreference":
        self._require_session(session_id)
        if connector_id:
            if not self._core.connectors.exists(connector_id):
                raise ValueError("unknown connector_id")
        return self._core.session_preferences.set_default_connector(session_id, connector_id)

    def delete_connector(self, connector_id: str) -> None:
        """Delete metadata and clear optional Session convenience defaults."""
        self._core.connectors.remove(connector_id)
        self._core.session_preferences.clear_connector(connector_id)

    def _require_session(self, session_id: str) -> None:
        """Raise ``UnknownSession`` before a Session-scoped settings operation."""
        if not self._core.sessions.exists(session_id):
            raise UnknownSession(session_id)
