"""Regression coverage for durable inherited Agent run profiles."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import HTTPException

from angelus import run_profiles, runtime, storage, webapp
from angelus.classes import RunConfig
from angelus.api import profiles


def test_agent_profile_merges_global_default_and_restores_inheritance(tmp_path: Path) -> None:
    """An override changes only supplied fields and deletion restores its sources."""
    original_index = storage.RUN_PROFILE_INDEX
    storage.RUN_PROFILE_INDEX = tmp_path / "run-profiles.json"
    try:
        run_profiles.update_profile("default", {
            "connector_id": "global-connector",
            "model": "global-model",
            "system_prompt": "Global instructions",
            "tool_permissions": {"shell": {"enabled": False, "tools": {}}},
        }, global_default=True)

        created = run_profiles.update_profile("workspace-a", {
            "model": "worker-model",
            "tool_permissions": {"shell": {"enabled": True, "tools": {"shell": True}}},
        }, "writer")

        assert created["inherits_default"] is False
        assert created["effective"]["connector_id"] == "global-connector"
        assert created["effective"]["model"] == "worker-model"
        assert created["effective"]["system_prompt"] == "Global instructions"
        assert created["sources"]["connector_id"] == "global_default"
        assert created["sources"]["model"] == "agent_override"
        assert created["sources"]["tool_permissions"] == "agent_override"

        restored = run_profiles.restore_inheritance("workspace-a", "writer")
        assert restored["inherits_default"] is True
        assert restored["override"] == {}
        assert restored["effective"]["model"] == "global-model"
        assert restored["effective"]["tool_permissions"] == {
            "shell": {"enabled": False, "tools": {}},
        }
        assert restored["sources"]["model"] == "global_default"
    finally:
        storage.RUN_PROFILE_INDEX = original_index


def test_profile_store_never_persists_api_keys_and_rejects_them(tmp_path: Path) -> None:
    """Profiles reference connectors but never duplicate connector credentials."""
    original_index = storage.RUN_PROFILE_INDEX
    storage.RUN_PROFILE_INDEX = tmp_path / "run-profiles.json"
    try:
        try:
            profiles.put_global_profile({"api_key": "must-not-save"})
        except HTTPException as exc:
            assert exc.status_code == 422
        else:
            raise AssertionError("credential-bearing profile patch was accepted")

        saved = profiles.put_global_profile({
            "connector_id": "saved-connector", "model": "safe-model",
        })
        encoded = storage.RUN_PROFILE_INDEX.read_text(encoding="utf-8")
        assert "api_key" not in encoded
        assert "must-not-save" not in encoded
        assert json.loads(encoded)["default"]["connector_id"] == "saved-connector"
        assert "api_key" not in saved["effective"]
    finally:
        storage.RUN_PROFILE_INDEX = original_index


def test_profile_routes_expose_effective_values_sources_and_restore(tmp_path: Path) -> None:
    """Settings routes expose an Agent override, field sources, and restore action."""
    original_index = storage.RUN_PROFILE_INDEX
    storage.RUN_PROFILE_INDEX = tmp_path / "run-profiles.json"
    try:
        profiles.put_global_profile({"model": "global-model"})
        initial = profiles.get_agent_profile("space", "coordinator")
        assert initial["inherits_default"] is True
        assert initial["sources"]["model"] == "global_default"

        updated = profiles.put_agent_profile("space", "coordinator", {"model": "agent-model"})
        assert updated["effective"]["model"] == "agent-model"
        assert updated["sources"]["model"] == "agent_override"

        restored = profiles.delete_agent_profile("space", "coordinator")
        assert restored["inherits_default"] is True
        assert restored["effective"]["model"] == "global-model"
    finally:
        storage.RUN_PROFILE_INDEX = original_index


def test_tool_permission_requires_both_category_and_named_tool() -> None:
    """No native or MCP tool is model-visible unless both gates are enabled."""
    disabled_category = RunConfig(model="test", tool_permissions={
        "categories": {"planning": False, "mcp": False},
        "tools": {"set_task_plan": True, "mcp.server.lookup": True},
    })
    assert not runtime._tool_permitted(disabled_category, "planning", "set_task_plan")
    assert not runtime._tool_permitted(disabled_category, "mcp", "mcp.server.lookup")

    disabled_tool = RunConfig(model="test", tool_permissions={
        "categories": {"planning": True, "mcp": True},
        "tools": {"set_task_plan": False, "mcp.server.lookup": False},
    })
    assert not runtime._tool_permitted(disabled_tool, "planning", "set_task_plan")
    assert not runtime._tool_permitted(disabled_tool, "mcp", "mcp.server.lookup")

    enabled = RunConfig(model="test", tool_permissions={
        "categories": {"planning": True, "mcp": True},
        "tools": {"set_task_plan": True, "mcp.server.lookup": True},
    })
    assert runtime._tool_permitted(enabled, "planning", "set_task_plan")
    assert runtime._tool_permitted(enabled, "mcp", "mcp.server.lookup")
    assert not runtime._tool_permitted(enabled, "planning", "update_task_status")
