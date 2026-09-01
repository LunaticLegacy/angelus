"""Atomic persistence for External Agent Hub definitions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
import threading

from ..settings_module.json_store import read_json, write_json
from .models import ExternalAgentAdapterKind, ExternalAgentDefinition


class ExternalAgentHubStore:
    """Own durable credential-free external Agent definitions."""

    def __init__(self, state_root: Path) -> None:
        """Create a store below the Angelus-owned state root.

        Args:
            state_root: Root directory for Angelus durable application state.

        Returns:
            None.
        """
        self._path = state_root / "external-agent-hub" / "agents.json"
        self._lock = threading.RLock()

    def list(self) -> tuple[ExternalAgentDefinition, ...]:
        """Return all definitions in durable document order.

        Returns:
            Immutable external Agent definition snapshot.
        """
        with self._lock:
            return self._read()

    def get(self, agent_id: str) -> ExternalAgentDefinition | None:
        """Find one definition by stable identifier.

        Args:
            agent_id: External Agent identifier.

        Returns:
            Matching definition, or ``None`` if absent.
        """
        return next((item for item in self.list() if item.id == agent_id), None)

    def put(self, definition: ExternalAgentDefinition) -> ExternalAgentDefinition:
        """Atomically create or replace one external Agent definition.

        Args:
            definition: Fully validated credential-free declaration.

        Returns:
            Persisted declaration.
        """
        with self._lock:
            records = [item for item in self._read() if item.id != definition.id]
            records.append(definition)
            write_json(self._path, {"schema_version": 1, "agents": [_json(item) for item in records]})
        return definition

    def remove(self, agent_id: str) -> bool:
        """Atomically remove one definition without touching connectors.

        Args:
            agent_id: External Agent identifier to remove.

        Returns:
            ``True`` when an existing declaration was removed.
        """
        with self._lock:
            records = self._read()
            remaining = tuple(item for item in records if item.id != agent_id)
            if len(remaining) == len(records):
                return False
            write_json(self._path, {"schema_version": 1, "agents": [_json(item) for item in remaining]})
            return True

    def _read(self) -> tuple[ExternalAgentDefinition, ...]:
        """Decode the complete persisted definition document.

        Returns:
            Valid immutable definition sequence.

        Raises:
            ValueError: If a durable document is malformed.
        """
        raw = read_json(self._path, {"schema_version": 1, "agents": []})
        if not isinstance(raw, Mapping) or raw.get("schema_version") != 1:
            raise ValueError("invalid external Agent Hub registry")
        agents = raw.get("agents")
        if not isinstance(agents, Sequence) or isinstance(agents, str):
            raise ValueError("invalid external Agent Hub definitions")
        return tuple(_definition(item) for item in agents)


def _definition(value: object) -> ExternalAgentDefinition:
    """Decode a JSON object into one typed definition.

    Args:
        value: Raw persisted definition item.

    Returns:
        Valid typed external Agent definition.

    Raises:
        ValueError: If the definition is malformed.
    """
    if not isinstance(value, Mapping):
        raise ValueError("invalid external Agent definition")
    fields = ("id", "title", "adapter_kind")
    if any(not isinstance(value.get(field), str) for field in fields):
        raise ValueError("invalid external Agent definition identity")
    enabled = value.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError("invalid external Agent enabled state")
    return ExternalAgentDefinition(
        id=str(value["id"]),
        title=str(value["title"]),
        adapter_kind=_adapter_kind(value["adapter_kind"]),
        endpoint=_text(value.get("endpoint", "")),
        connector_id=_text(value.get("connector_id", "")),
        enabled=enabled,
        description=_text(value.get("description", "")),
    )


def _adapter_kind(value: object) -> ExternalAgentAdapterKind:
    """Validate one persisted adapter kind.

    Args:
        value: Candidate adapter kind value.

    Returns:
        Supported external Agent adapter kind.

    Raises:
        ValueError: If the kind is unsupported.
    """
    if value not in {"codex_app_server", "claude_sdk", "coze", "opencode", "workbuddy", "custom"}:
        raise ValueError("invalid external Agent adapter kind")
    return value


def _text(value: object) -> str:
    """Validate an optional bounded non-secret text field.

    Args:
        value: Candidate persisted text value.

    Returns:
        Validated text.

    Raises:
        ValueError: If the value is not a bounded string.
    """
    if not isinstance(value, str) or len(value) > 2_000:
        raise ValueError("invalid external Agent text field")
    return value


def _json(definition: ExternalAgentDefinition) -> dict[str, object]:
    """Serialize one typed definition without connector secrets.

    Args:
        definition: Typed declaration to persist.

    Returns:
        JSON-safe primitive object.
    """
    return {
        "id": definition.id,
        "title": definition.title,
        "adapter_kind": definition.adapter_kind,
        "endpoint": definition.endpoint,
        "connector_id": definition.connector_id,
        "enabled": definition.enabled,
        "description": definition.description,
    }
