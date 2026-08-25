"""Secure global MCP registry and session authorization coverage."""

from __future__ import annotations

from pathlib import Path

import pytest

from angelus import mcp_registry
from angelus.mcp_tools import MCPToolError


def test_registry_encrypts_credentials_and_public_view_is_masked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Never persist or return static headers, env values, or bearer tokens."""
    index = tmp_path / "mcp-servers.json"
    monkeypatch.setattr(mcp_registry, "MCP_SERVER_INDEX", index)
    monkeypatch.setattr(mcp_registry.storage, "CONNECTOR_INDEX", tmp_path / "connectors.json")
    record = mcp_registry._normalize_server({
        "name": "fixture", "transport": "stdio", "command": "python",
        "headers": {"X-Key": "header-secret"},
        "env": {"TOKEN": "env-secret"}, "bearer_token": "bearer-secret" * 100,
    })

    mcp_registry.write_servers([record])

    raw = index.read_text(encoding="utf-8")
    assert "header-secret" not in raw
    assert "env-secret" not in raw
    assert "bearer-secret" not in raw
    public = mcp_registry.public_server(mcp_registry.read_servers()[0])
    assert public["headers"] == ["X-Key"]
    assert public["env"] == ["TOKEN"]
    assert public["has_bearer_token"] is True
    assert "bearer_token" not in public
    assert mcp_registry.read_servers()[0]["bearer_token"] == "bearer-secret" * 100


def test_registry_rejects_legacy_sse_and_forbidden_templates() -> None:
    """Allow project expansion only in controlled stdio args and cwd."""
    with pytest.raises(MCPToolError, match="Legacy SSE"):
        mcp_registry._normalize_server({"name": "old", "transport": "sse", "url": "https://example.test/sse"})
    with pytest.raises(MCPToolError, match="allowed only"):
        mcp_registry._normalize_server({"name": "bad", "transport": "stdio", "command": "${project_root}/server"})


def test_run_config_rejects_removed_raw_mcp_fields() -> None:
    """Force browser clients to use server-side session bindings."""
    from pydantic import ValidationError
    from angelus.classes import RunConfig

    with pytest.raises(ValidationError):
        RunConfig(model="test", enable_mcp=True, mcp_servers=[])
