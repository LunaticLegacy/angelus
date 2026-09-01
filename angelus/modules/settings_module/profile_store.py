"""One canonical run-profile implementation for global and session settings."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import threading
from typing import Any

from .json_store import read_json, write_json


DEFAULT_RUN_PROFILE: dict[str, Any] = {
    # Empty means a future Agent may use directly-entered transient credentials.
    "connector_id": "",
    "provider": "openai",
    "model": "",
    "api_url": "",
    "system_prompt": "You are a helpful, precise assistant.",
    "temperature": 0.4,
    "max_tokens": 16384,
    "max_rounds": 0,
    "max_retries": 3,
    "max_context_threshold": 262144,
    "compaction_output_max_tokens": 8192,
    "max_swarm_agents": 4,
    "session_memory_search_sessions": [],
    "session_memory_read_sessions": [],
    "session_artifact_search_sessions": [],
    "session_artifact_open_sessions": [],
    "tool_permissions": {"categories": {}, "tools": {}},
}


class RunProfileStore:
    """Persist global defaults and sparse per-session overrides.

    A profile is configuration for a future attempt, never mutable execution
    state.  ``effective`` merges the global document and a session override;
    execution creation will later freeze that result into its attempt snapshot.
    """

    def __init__(self, state_root: Path) -> None:
        """Store defaults under ``settings`` and overrides under each Session.

        Args:
            state_root: Angelus-owned root; never an arbitrary project path.
        """
        # Base directory used to derive every Session-local override path.
        self._root = state_root
        # Sole durable global-default document.
        self._global_path = state_root / "settings" / "global-run-profile.json"
        # Serializes read/validate/write and effective-profile merge operations.
        self._lock = threading.RLock()

    def global_profile(self) -> dict[str, Any]:
        """Return the complete global default profile with omitted fields filled."""
        with self._lock:
            return self._validated(self._read(self._global_path), partial=False)

    def replace_global(self, values: Mapping[str, Any]) -> dict[str, Any]:
        """Validate and atomically replace global defaults.

        Args:
            values: Complete supported profile fields; unknown fields fail.
        """
        with self._lock:
            profile = self._validated(values, partial=False)
            write_json(self._global_path, {"schema_version": 1, "settings": profile})
            return profile

    def session_profile(self, session_id: str) -> dict[str, Any]:
        """Return effective settings and whether this Session has an override.

        Global values are copied first, then the Session's local values win.
        No disk state is changed by this read operation.
        """
        with self._lock:
            global_profile = self._validated(self._read(self._global_path), partial=False)
            override_path = self._session_path(session_id)
            override = self._validated(self._read(override_path), partial=True)
            return {
                "scope": "session",
                "inherits_default": not override_path.exists(),
                "effective": {**global_profile, **override},
            }

    def replace_session(self, session_id: str, values: Mapping[str, Any]) -> dict[str, Any]:
        """Replace a Session override with validated complete future-run values.

        This intentionally stores a full profile rather than a patch: a saved
        Session stays stable if a later version changes global defaults.
        """
        with self._lock:
            # A complete override makes its meaning independent of later UI
            # field additions; inherit is the explicit way back to global.
            override = self._validated(values, partial=False)
            write_json(self._session_path(session_id), {"schema_version": 1, "settings": override})
            return {"scope": "session", "inherits_default": False, "effective": override}

    def clear_session(self, session_id: str) -> dict[str, Any]:
        """Remove override file so the Session again resolves global defaults.

        Missing files are already equivalent to inheritance and are accepted.
        """
        with self._lock:
            path = self._session_path(session_id)
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        return self.session_profile(session_id)

    def effective(self, session_id: str) -> dict[str, Any]:
        """Return resolved values that execution creation will snapshot later."""
        return dict(self.session_profile(session_id)["effective"])

    def connector_references(self, connector_id: str, session_ids: tuple[str, ...]) -> tuple[str, ...]:
        """Return profile scopes whose effective setting references a connector.

        The result includes inherited global references, because those still
        become invalid when a connector disappears.
        """
        references: list[str] = []
        if self.global_profile().get("connector_id") == connector_id:
            references.append("global")
        for session_id in session_ids:
            if self.effective(session_id).get("connector_id") == connector_id:
                references.append(session_id)
        return tuple(references)

    def _read(self, path: Path) -> Mapping[str, Any]:
        """Decode one optional profile envelope, rejecting malformed documents."""
        document = read_json(path, {"schema_version": 1, "settings": {}})
        if not isinstance(document, dict) or document.get("schema_version") != 1:
            raise ValueError(f"unsupported run profile: {path}")
        settings = document.get("settings")
        if not isinstance(settings, dict):
            raise ValueError(f"invalid run profile: {path}")
        return settings

    def _session_path(self, session_id: str) -> Path:
        """Resolve a validated Session-local path without allowing traversal."""
        if not session_id or "/" in session_id or "\\" in session_id:
            raise ValueError("invalid session_id")
        return self._root / "sessions" / session_id / "run-profile.json"

    def _validated(self, values: Mapping[str, Any], *, partial: bool) -> dict[str, Any]:
        """Normalize supported fields and reject unknown or ill-typed settings.

        Args:
            values: Candidate profile object from a store/API caller.
            partial: When true, omit defaults for a sparse override read.

        Returns:
            A new JSON-safe profile mapping; input is never modified.

        Raises:
            ValueError: If a field is unknown, missing required shape, or out
                of supported numeric range.
        """
        if not isinstance(values, Mapping):
            raise ValueError("run profile must be an object")
        unknown = set(values) - set(DEFAULT_RUN_PROFILE)
        if unknown:
            raise ValueError(f"unknown run-profile fields: {', '.join(sorted(unknown))}")
        result: dict[str, Any] = {} if partial else dict(DEFAULT_RUN_PROFILE)
        for key, value in values.items():
            if key in {"connector_id", "provider", "model", "api_url", "system_prompt"}:
                if not isinstance(value, str):
                    raise ValueError(f"{key} must be a string")
                result[key] = value
            elif key == "temperature":
                if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 2:
                    raise ValueError("temperature must be between 0 and 2")
                result[key] = float(value)
            elif key in {"max_tokens", "max_retries", "max_context_threshold", "compaction_output_max_tokens", "max_swarm_agents", "max_rounds"}:
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    raise ValueError(f"{key} must be a non-negative integer")
                if key in {"max_tokens", "compaction_output_max_tokens"} and value < 1:
                    raise ValueError(f"{key} must be at least 1")
                result[key] = value
            elif key.endswith("_sessions"):
                if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
                    raise ValueError(f"{key} must be a list of session IDs")
                result[key] = list(dict.fromkeys(value))
            elif key == "tool_permissions":
                if not isinstance(value, dict):
                    raise ValueError("tool_permissions must be an object")
                result[key] = value
        return result
