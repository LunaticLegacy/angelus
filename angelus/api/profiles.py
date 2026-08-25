"""HTTP routes for persistent global and session-Agent run profiles."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body

from .. import run_profiles

router = APIRouter()


@router.get("/api/run-profile")
def get_global_profile() -> dict[str, Any]:
    """Return the effective global default profile without credentials."""
    return run_profiles.profile_view("default")


@router.put("/api/run-profile")
def put_global_profile(values: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Persist shared default values used by Agents without an override."""
    return run_profiles.update_profile("default", values, global_default=True)


@router.get("/api/workspaces/{workspace_id}/agents/{agent_name}/run-profile")
def get_agent_profile(workspace_id: str, agent_name: str) -> dict[str, Any]:
    """Return one Agent's effective profile and inherited-field provenance."""
    return run_profiles.profile_view(workspace_id, agent_name)


@router.put("/api/workspaces/{workspace_id}/agents/{agent_name}/run-profile")
def put_agent_profile(workspace_id: str, agent_name: str, values: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Create or update one complete session-Agent override."""
    return run_profiles.update_profile(workspace_id, values, agent_name)


@router.delete("/api/workspaces/{workspace_id}/agents/{agent_name}/run-profile")
def delete_agent_profile(workspace_id: str, agent_name: str) -> dict[str, Any]:
    """Restore inherited defaults by deleting one Agent-specific override."""
    return run_profiles.restore_inheritance(workspace_id, agent_name)
