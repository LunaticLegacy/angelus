"""One canonical run-profile implementation for global and session settings."""

from __future__ import annotations

from collections.abc import Mapping
import math
from pathlib import Path
import threading
from typing import Any

from .json_store import read_json, write_json
from llmfetcher.context_handlers import DEFAULT_CONTEXT_HANDLER


DEFAULT_RUN_PROFILE: dict[str, Any] = {
    "system_prompt": "You are a helpful, precise assistant.\nAfter each checkpoint, DO NOT re-call the tool called `set_task_plan` for task updation.",
    "temperature": 0.4,
    "thinking_mode": "auto",
    "reasoning_effort": "auto",
    "max_tokens": 32768,
    "max_rounds": 0,
    "max_retries": 3,
    "request_timeout_seconds": 60.0,
    "max_context_threshold": 262144,
    "compaction_output_max_tokens": 16384,
    "context_keep_recent": 0,
    "tool_result_context_limit": 0,
    "context_handler": DEFAULT_CONTEXT_HANDLER,
    "context_handler_settings": {},
    "context_block_order": {},
    "max_swarm_agents": 4,
    "agent_overrides": {},
    "session_memory_search_sessions": [],
    "session_memory_read_sessions": [],
    "session_artifact_search_sessions": [],
    "session_artifact_open_sessions": [],
    "tool_permissions": {
        "categories": {
                "context_version": True, "session_memory": True, "notes": True, "vision": True, "file_discovery": True, "project_retrieval": True, "file_write": True,
            "shell": True, "planning": True,
        },
        "tools": {
            "file_list": True, "file_read": True, "file_search": True, "file_write": True,
            "inspect_agent_context": True, "search_agent_archive": True, "read_agent_archive": True,
            "edit_agent_context": True, "restore_agent_context": True,
            "search_session_memory": True, "read_session_memory": True,
            "search_session_artifacts": True, "open_session_artifact": True,
            "create_session_handoff": True, "read_session_handoff": True,
            "note_list": True, "note_search": True, "note_read": True, "note_create": True, "note_update": True, "note_delete": True,
            "view_image": True,
            "shell": True,
            "set_task_plan": True, "update_task_status": True, "read_task_plan": True,
        },
    },
}

# Accepted only so an explicit migration can read old documents. New profile
# writes never add these connector-owned fields unless a legacy caller submits
# them unchanged.
LEGACY_CONNECTOR_FIELDS = {"connector_id", "provider", "model", "api_url"}


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
            write_json(self._global_path, {"schema_version": 2, "settings": profile})
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
            write_json(self._session_path(session_id), {"schema_version": 2, "settings": override})
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
        if not isinstance(document, dict) or document.get("schema_version") not in {1, 2}:
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
        unknown = set(values) - (set(DEFAULT_RUN_PROFILE) | LEGACY_CONNECTOR_FIELDS)
        if unknown:
            raise ValueError(f"unknown run-profile fields: {', '.join(sorted(unknown))}")
        result: dict[str, Any] = {} if partial else dict(DEFAULT_RUN_PROFILE)
        for key, value in values.items():
            if key in LEGACY_CONNECTOR_FIELDS | {"system_prompt"}:
                if not isinstance(value, str):
                    raise ValueError(f"{key} must be a string")
                result[key] = value
            elif key == "temperature":
                if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 2:
                    raise ValueError("temperature must be between 0 and 2")
                result[key] = float(value)
            elif key == "thinking_mode":
                if value not in {"auto", "on", "off"}:
                    raise ValueError("thinking_mode must be auto, on, or off")
                result[key] = value
            elif key == "reasoning_effort":
                if value not in {"auto", "low", "medium", "high"}:
                    raise ValueError("reasoning_effort must be auto, low, medium, or high")
                result[key] = value
            elif key == "request_timeout_seconds":
                if (
                    not isinstance(value, (int, float))
                    or isinstance(value, bool)
                    or not math.isfinite(value)
                    or not 1 <= value <= 3600
                ):
                    raise ValueError("request_timeout_seconds must be between 1 and 3600")
                result[key] = float(value)
            elif key in {"max_tokens", "max_retries", "max_context_threshold", "compaction_output_max_tokens", "context_keep_recent", "tool_result_context_limit", "max_swarm_agents", "max_rounds"}:
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    raise ValueError(f"{key} must be a non-negative integer")
                if key in {"max_tokens", "compaction_output_max_tokens"} and value < 1:
                    raise ValueError(f"{key} must be at least 1")
                result[key] = value
            elif key == "agent_overrides":
                if not isinstance(value, dict):
                    raise ValueError("agent_overrides must be an object")
                overrides: dict[str, dict[str, int]] = {}
                allowed = {"max_rounds", "max_tokens", "max_context_threshold"}
                for name, override in value.items():
                    if not isinstance(name, str) or not name.strip():
                        raise ValueError("agent_overrides names must be non-empty strings")
                    if not isinstance(override, dict):
                        raise ValueError(f"agent_overrides[{name}] must be an object")
                    unknown_override = set(override) - allowed
                    if unknown_override:
                        raise ValueError(
                            f"unknown agent override fields for {name}: {', '.join(sorted(unknown_override))}"
                        )
                    normalized: dict[str, int] = {}
                    for override_key, override_value in override.items():
                        if (
                            not isinstance(override_value, int)
                            or isinstance(override_value, bool)
                            or override_value < 0
                        ):
                            raise ValueError(f"{override_key} override for {name} must be a non-negative integer")
                        if override_key == "max_tokens" and override_value < 1:
                            raise ValueError(f"max_tokens override for {name} must be at least 1")
                        if override_key == "max_context_threshold" and override_value < 1024:
                            raise ValueError(f"max_context_threshold override for {name} must be at least 1024")
                        normalized[override_key] = override_value
                    overrides[name.strip()] = normalized
                result[key] = overrides
            elif key == "context_handler":
                # Keep unknown IDs readable so a newer handler can be added
                # without making an existing profile impossible to edit.
                if not isinstance(value, str) or not value.strip():
                    raise ValueError("context_handler must be a non-empty string")
                result[key] = value.strip()
            elif key == "context_handler_settings":
                if not isinstance(value, dict):
                    raise ValueError("context_handler_settings must be an object")
                normalized: dict[str, dict[str, Any]] = {}
                for handler, settings in value.items():
                    if not isinstance(handler, str) or not handler.strip() or not isinstance(settings, dict):
                        raise ValueError("context_handler_settings must map handler names to objects")
                    normalized[handler.strip()] = dict(settings)
                result[key] = normalized
            elif key == "context_block_order":
                if not isinstance(value, dict):
                    raise ValueError("context_block_order must be an object")
                normalized_order: dict[str, int] = {}
                for source, priority in value.items():
                    if not isinstance(source, str) or not source.strip():
                        raise ValueError("context_block_order sources must be non-empty strings")
                    if isinstance(priority, bool) or not isinstance(priority, int):
                        raise ValueError("context_block_order priorities must be integers")
                    # Existence is deliberately not checked: a plugin provider
                    # may be absent on this machine while its saved position
                    # remains valid for a later run.
                    normalized_order[source.strip()] = priority
                result[key] = normalized_order
            elif key.endswith("_sessions"):
                if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
                    raise ValueError(f"{key} must be a list of session IDs")
                result[key] = list(dict.fromkeys(value))
            elif key == "tool_permissions":
                if not isinstance(value, dict):
                    raise ValueError("tool_permissions must be an object")
                default_permissions = DEFAULT_RUN_PROFILE["tool_permissions"]
                submitted_categories = value.get("categories", {})
                submitted_tools = value.get("tools", {})
                if not isinstance(submitted_categories, dict) or not isinstance(submitted_tools, dict):
                    raise ValueError("tool_permissions categories and tools must be objects")
                # New restored capabilities are on by default even for an old
                # saved `{categories:{}, tools:{}}`; an explicit false remains
                # authoritative and therefore still supports least privilege.
                result[key] = {
                    "categories": {**default_permissions["categories"], **submitted_categories},
                    "tools": {**default_permissions["tools"], **submitted_tools},
                }
        return result
