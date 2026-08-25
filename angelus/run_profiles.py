"""Persistent, credential-free defaults and per-Agent run-profile overrides.

Profiles are deliberately resolved at the run boundary.  This makes a saved
selection deterministic for a newly started run while leaving an already
constructed Agent and its audit snapshot untouched.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException

from . import storage
from .classes import RunConfig
from .storage import _safe_id


PROFILE_FIELDS = frozenset({
    "connector_id", "provider", "model", "api_url", "system_prompt", "temperature",
    "max_tokens", "max_rounds", "max_retries", "max_context_threshold", "enable_shell",
    "enable_swarm", "max_swarm_agents", "session_memory_search_sessions",
    "session_memory_read_sessions", "session_artifact_search_sessions",
    "session_artifact_open_sessions", "tool_permissions",
})


def default_profile() -> dict[str, Any]:
    """Return safe initial defaults for every new Agent profile.

    Returns:
        JSON-safe configuration fields.  API keys are intentionally absent;
        connector records are the sole credential store.
    """
    return RunConfig(model="").model_dump(exclude={"api_key"})


def _read() -> dict[str, Any]:
    """Read the small profile index, repairing absent or malformed state."""
    path = storage.RUN_PROFILE_INDEX
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        value = {}
    if not isinstance(value, dict):
        value = {}
    default = value.get("default")
    return {"default": default if isinstance(default, dict) else {},
            "agents": value.get("agents") if isinstance(value.get("agents"), dict) else {}}


def _write(value: dict[str, Any]) -> None:
    """Atomically persist credential-free profile state.

    Args:
        value: Complete profile index produced by this module.
    """
    path = storage.RUN_PROFILE_INDEX
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _clean_patch(values: dict[str, Any]) -> dict[str, Any]:
    """Reject credentials and unknown fields before saving a profile patch."""
    forbidden = {key for key in values if "key" in key.lower() or "secret" in key.lower()}
    if forbidden:
        raise HTTPException(status_code=422, detail="运行档案不得包含凭据")
    unknown = set(values) - PROFILE_FIELDS
    if unknown:
        raise HTTPException(status_code=422, detail=f"未知运行档案字段: {', '.join(sorted(unknown))}")
    return {key: value for key, value in values.items() if key in PROFILE_FIELDS}


def resolve_profile(workspace_id: str, agent_name: str = "coordinator") -> tuple[RunConfig, dict[str, str]]:
    """Resolve one Agent's default-plus-override configuration and sources.

    Args:
        workspace_id: Session/workspace owning the optional override.
        agent_name: ``coordinator`` or a durable named worker identity.

    Returns:
        A validated configuration without an API key and a field-to-source map.
    """
    workspace_id = _safe_id(workspace_id, "workspace")
    agent_name = _safe_id(agent_name, "agent")
    state = _read()
    base = default_profile() | _clean_patch(dict(state["default"]))
    override = state["agents"].get(workspace_id, {}).get(agent_name, {})
    override = _clean_patch(dict(override)) if isinstance(override, dict) else {}
    values = base | override
    sources = {key: ("agent_override" if key in override else "global_default") for key in PROFILE_FIELDS}
    try:
        return RunConfig(**values), sources
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"保存的运行档案无效: {exc}") from exc


def profile_view(workspace_id: str, agent_name: str = "coordinator") -> dict[str, Any]:
    """Return effective values, editable override, and provenance for settings UI."""
    config, sources = resolve_profile(workspace_id, agent_name)
    state = _read()
    override = state["agents"].get(workspace_id, {}).get(agent_name, {})
    return {"agent": agent_name, "inherits_default": not bool(override),
            "override": override if isinstance(override, dict) else {},
            "effective": config.model_dump(exclude={"api_key"}), "sources": sources}


def update_profile(workspace_id: str, values: dict[str, Any], agent_name: str = "coordinator", *, global_default: bool = False) -> dict[str, Any]:
    """Merge a validated patch into the global default or one Agent override.

    Args:
        workspace_id: Owning session; ignored only for global defaults.
        values: Credential-free fields supplied by settings.
        agent_name: Agent whose complete override is being edited.
        global_default: Select the shared default profile when true.
    """
    patch = _clean_patch(values)
    state = _read()
    if global_default:
        candidate = default_profile() | state["default"] | patch
        RunConfig(**candidate)
        state["default"] = {key: candidate[key] for key in PROFILE_FIELDS if key in candidate}
    else:
        workspace_id = _safe_id(workspace_id, "workspace")
        agent_name = _safe_id(agent_name, "agent")
        current = state["agents"].setdefault(workspace_id, {}).get(agent_name, {})
        candidate = dict(current) | patch
        # Validate merged values against the resolved default without persisting API keys.
        base = default_profile() | state["default"] | candidate
        RunConfig(**base)
        state["agents"][workspace_id][agent_name] = candidate
    _write(state)
    return profile_view(workspace_id, agent_name)


def restore_inheritance(workspace_id: str, agent_name: str = "coordinator") -> dict[str, Any]:
    """Remove one Agent override so every field again inherits the default."""
    workspace_id = _safe_id(workspace_id, "workspace")
    agent_name = _safe_id(agent_name, "agent")
    state = _read()
    bucket = state["agents"].get(workspace_id, {})
    if isinstance(bucket, dict):
        bucket.pop(agent_name, None)
        if not bucket:
            state["agents"].pop(workspace_id, None)
    _write(state)
    return profile_view(workspace_id, agent_name)
